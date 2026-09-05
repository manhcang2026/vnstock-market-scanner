from __future__ import annotations

import argparse
import json
import os
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any

import backfill_daily_history as backfill
from common import load_watchlist, now_vn


MARKET_CLOSE_SAFE_AFTER = time(15, 10)
MIN_EOD_TIME_SLOT = "15:00:00"
WRITE_BATCH_SIZE = 50
REPORT_JSON = Path("daily_history_eod_report.json")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_symbols(raw: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in raw.replace(";", ",").split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in seen:
            result.append(symbol)
            seen.add(symbol)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bo sung daily_history sau dong cua. Uu tien final intraday EOD; "
            "neu snapshot khong dung duoc thi provider xac nhan bar/NO_BAR. "
            "Mac dinh dry-run; write chi INSERT missing rows, khong overwrite."
        )
    )
    parser.add_argument(
        "--trading-date",
        default=os.getenv("EOD_TRADING_DATE", ""),
        help="Ngay giao dich YYYY-MM-DD; de trong = ngay VN hien tai.",
    )
    parser.add_argument(
        "--symbols",
        default=os.getenv("EOD_SYMBOLS", ""),
        help="Danh sach ma; de trong = toan watchlist.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        default=env_bool("EOD_WRITE", False),
        help="Cho phep INSERT missing rows + verify; khong overwrite row da co.",
    )
    return parser.parse_args()


def resolve_trading_date(raw: str) -> date:
    value = raw.strip()
    if not value:
        return now_vn().date()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError(f"Ngay giao dich khong hop le: {value!r}") from exc


def session_is_completed(trading_date: date) -> bool:
    current = now_vn()
    if trading_date < current.date():
        return True
    if trading_date > current.date():
        return False
    if current.weekday() >= 5:
        return False
    return current.time().replace(tzinfo=None) >= MARKET_CLOSE_SAFE_AFTER


def load_existing_symbols(trading_date: date) -> set[str]:
    response = backfill.supabase_request(
        "GET",
        "daily_history",
        params={
            "select": "symbol",
            "trading_date": f"eq.{trading_date.isoformat()}",
            "order": "symbol.asc",
            "limit": "1000",
        },
    )
    result: set[str] = set()
    for row in response.json():
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol:
            result.add(symbol)
    return result


def load_final_snapshots(trading_date: date) -> dict[str, dict[str, Any]]:
    """Load one latest >=15:00 OK snapshot for each symbol in one request."""
    response = backfill.supabase_request(
        "GET",
        "intraday_snapshots",
        params={
            "select": (
                "symbol,exchange,trading_date,time_slot,current_price,"
                "volume_accumulated,data_status,updated_at"
            ),
            "trading_date": f"eq.{trading_date.isoformat()}",
            "time_slot": f"gte.{MIN_EOD_TIME_SLOT}",
            "data_status": "eq.OK",
            "order": "symbol.asc,time_slot.desc",
            "limit": "1000",
        },
    )
    result: dict[str, dict[str, Any]] = {}
    for row in response.json():
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol and symbol not in result:
            result[symbol] = row
    return result


def intraday_eod_row(
    *,
    symbol: str,
    exchange: str,
    snapshot: dict[str, Any] | None,
    trading_date: date,
    updated_at,
) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    try:
        price = round(float(snapshot.get("current_price")), 4)
        volume = round(float(snapshot.get("volume_accumulated")), 4)
    except (TypeError, ValueError):
        return None

    # Zero-volume snapshot is not trusted as an official daily bar.
    # Provider fallback will decide whether the date truly has a bar.
    if price <= 0 or volume <= 0:
        return None

    return {
        "symbol": symbol,
        "exchange": exchange,
        "trading_date": trading_date.isoformat(),
        "close": price,
        "volume": volume,
        "source": "INTRADAY_EOD",
        "updated_at": updated_at.isoformat(),
    }


def fetch_provider_eod_row(
    *,
    symbol: str,
    exchange: str,
    preferred_source: str,
    trading_date: date,
    updated_at,
) -> tuple[dict[str, Any] | None, str]:
    """
    Provider is used only when final intraday snapshot is unusable.

    NO_BAR is accepted only after at least one provider answered successfully.
    A technical/provider failure must never be silently converted to NO_BAR.
    """
    run_date = trading_date + timedelta(days=1)
    start = (trading_date - timedelta(days=10)).isoformat()
    end = run_date.isoformat()
    preferred = preferred_source.upper().strip()
    if preferred not in {backfill.PRIMARY_SOURCE, backfill.FALLBACK_SOURCE}:
        preferred = backfill.PRIMARY_SOURCE
    alternate = (
        backfill.FALLBACK_SOURCE
        if preferred == backfill.PRIMARY_SOURCE
        else backfill.PRIMARY_SOURCE
    )

    successful_provider_response = False
    notes: list[str] = []

    for source in (preferred, alternate):
        try:
            history = backfill.fetch_source_history(
                symbol=symbol,
                source=source,
                start=start,
                end=end,
                run_date=run_date,
            )
            successful_provider_response = True
            match = history[history["time"].dt.date == trading_date]
            if match.empty:
                notes.append(f"{source}: no {trading_date} bar")
                continue

            bar = match.iloc[-1]
            price = round(float(bar["close"]), 4)
            volume = round(float(bar["volume"]), 4)
            if price <= 0 or volume < 0:
                notes.append(f"{source}: invalid bar")
                continue

            return (
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "trading_date": trading_date.isoformat(),
                    "close": price,
                    "volume": volume,
                    "source": source,
                    "updated_at": updated_at.isoformat(),
                },
                f"{source}_EOD",
            )
        except Exception as exc:
            notes.append(f"{source}: {type(exc).__name__}: {exc}")

    if successful_provider_response:
        return None, "NO_BAR | " + " | ".join(notes)

    raise RuntimeError(
        "EOD provider unavailable; khong duoc tu suy dien NO_BAR. "
        + " | ".join(notes)
    )


def insert_ignore_duplicates(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    backfill.supabase_request(
        "POST",
        "daily_history",
        params={"on_conflict": "symbol,trading_date"},
        payload=rows,
        prefer="resolution=ignore-duplicates,return=minimal",
    )


def write_report(report: dict[str, Any]) -> None:
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    trading_date = resolve_trading_date(args.trading_date)
    if not session_is_completed(trading_date):
        raise RuntimeError(
            f"SAFETY STOP: phien {trading_date} chua duoc xem la da ket thuc."
        )

    backfill.verify_supabase_config()

    watchlist = load_watchlist()
    exchanges = {
        str(row.symbol).strip().upper(): str(row.exchange).strip().upper()
        for row in watchlist.itertuples(index=False)
    }
    requested = parse_symbols(args.symbols)
    symbols = requested or sorted(exchanges)

    unknown = [symbol for symbol in symbols if symbol not in exchanges]
    if unknown:
        raise RuntimeError(
            "Co symbol khong nam trong watchlist: " + ", ".join(unknown[:20])
        )

    run_at = now_vn()
    existing_symbols = load_existing_symbols(trading_date)
    snapshots = load_final_snapshots(trading_date)
    profiles = backfill.load_baseline_profiles()

    report: dict[str, Any] = {
        "run_at": run_at.isoformat(),
        "trading_date": trading_date.isoformat(),
        "write": args.write,
        "selected": len(symbols),
        "counts": {
            "exists": 0,
            "intraday_eod": 0,
            "provider_eod": 0,
            "no_bar": 0,
            "candidates": 0,
            "written": 0,
            "errors": 0,
        },
        "results": [],
    }

    print(
        f"Daily History EOD: trading_date={trading_date}, "
        f"symbols={len(symbols)}, write={args.write}."
    )

    pending_write: list[dict[str, Any]] = []
    provider_access_verified = False

    for index, symbol in enumerate(symbols, start=1):
        exchange = exchanges[symbol]
        result: dict[str, Any] = {
            "symbol": symbol,
            "status": "",
            "source": "",
            "detail": "",
        }
        try:
            if symbol in existing_symbols:
                report["counts"]["exists"] += 1
                result["status"] = "EXISTS"
                print(f"[{index}/{len(symbols)}] {symbol} -> EXISTS; no overwrite.")
                report["results"].append(result)
                continue

            row = intraday_eod_row(
                symbol=symbol,
                exchange=exchange,
                snapshot=snapshots.get(symbol),
                trading_date=trading_date,
                updated_at=run_at,
            )
            if row is not None:
                report["counts"]["intraday_eod"] += 1
                result["status"] = "CANDIDATE"
                result["source"] = "INTRADAY_EOD"
                result["detail"] = (
                    f"slot={snapshots[symbol].get('time_slot')}, "
                    f"close={row['close']}, volume={row['volume']}"
                )
            else:
                if not provider_access_verified:
                    backfill.verify_vnstock_api_access()
                    provider_access_verified = True

                profile = profiles.get(symbol) or {}
                preferred_source = str(
                    profile.get("source") or backfill.PRIMARY_SOURCE
                )
                row, detail = fetch_provider_eod_row(
                    symbol=symbol,
                    exchange=exchange,
                    preferred_source=preferred_source,
                    trading_date=trading_date,
                    updated_at=run_at,
                )
                result["detail"] = detail
                if row is None:
                    report["counts"]["no_bar"] += 1
                    result["status"] = "NO_BAR"
                    print(f"[{index}/{len(symbols)}] {symbol} -> {detail}")
                    report["results"].append(result)
                    continue

                report["counts"]["provider_eod"] += 1
                result["status"] = "CANDIDATE"
                result["source"] = str(row["source"])

            report["counts"]["candidates"] += 1
            pending_write.append(row)
            print(
                f"[{index}/{len(symbols)}] {symbol} -> CANDIDATE "
                f"source={result['source']}"
            )

            if args.write and len(pending_write) >= WRITE_BATCH_SIZE:
                insert_ignore_duplicates(pending_write)
                report["counts"]["written"] += len(pending_write)
                existing_symbols.update(str(item["symbol"]) for item in pending_write)
                pending_write.clear()

        except Exception as exc:
            report["counts"]["errors"] += 1
            result["status"] = "ERROR"
            result["detail"] = f"{type(exc).__name__}: {exc}"
            print(
                f"[{index}/{len(symbols)}] {symbol} -> ERROR: "
                f"{result['detail']}"
            )

        report["results"].append(result)
        write_report(report)

    if args.write and pending_write:
        insert_ignore_duplicates(pending_write)
        report["counts"]["written"] += len(pending_write)
        existing_symbols.update(str(item["symbol"]) for item in pending_write)
        pending_write.clear()

    if args.write:
        stored = load_existing_symbols(trading_date)
        candidate_symbols = {
            str(row["symbol"])
            for row in report["results"]
            if row.get("status") == "CANDIDATE"
        }
        missing_after_write = sorted(candidate_symbols - stored)
        if missing_after_write:
            report["counts"]["errors"] += len(missing_after_write)
            report["write_verify_missing"] = missing_after_write
            print(
                "WRITE VERIFY ERROR: missing after insert: "
                + ", ".join(missing_after_write[:30])
            )

    write_report(report)
    counts = report["counts"]
    print(
        "EOD SUMMARY: "
        + ", ".join(f"{key}={value}" for key, value in counts.items())
    )

    if counts["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
