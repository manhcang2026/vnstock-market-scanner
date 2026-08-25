from __future__ import annotations

import argparse
import os
from datetime import date, time
from typing import Any

import backfill_daily_history as backfill
from common import load_watchlist, now_vn


MARKET_CLOSE_SAFE_AFTER = time(15, 10)


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
            "Bo sung daily_history tu intraday snapshot cuoi phien. "
            "Mac dinh dry-run; chi INSERT khi row chua ton tai."
        )
    )
    parser.add_argument(
        "--trading-date",
        default=os.getenv("EOD_TRADING_DATE", ""),
        help="Ngay giao dich YYYY-MM-DD.",
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
        help="Cho phep insert missing-only.",
    )
    return parser.parse_args()


def daily_row_exists(symbol: str, trading_date: date) -> bool:
    response = backfill.supabase_request(
        "GET",
        "daily_history",
        params={
            "select": "symbol",
            "symbol": f"eq.{symbol}",
            "trading_date": f"eq.{trading_date.isoformat()}",
            "limit": "1",
        },
    )
    return bool(response.json())


def load_final_snapshot(
    symbol: str,
    trading_date: date,
) -> dict[str, Any] | None:
    response = backfill.supabase_request(
        "GET",
        "intraday_snapshots",
        params={
            "select": (
                "symbol,exchange,trading_date,time_slot,current_price,"
                "volume_accumulated,data_status,updated_at"
            ),
            "symbol": f"eq.{symbol}",
            "trading_date": f"eq.{trading_date.isoformat()}",
            "current_price": "gt.0",
            "volume_accumulated": "gte.0",
            "data_status": "eq.OK",
            "order": "time_slot.desc",
            "limit": "1",
        },
    )
    rows = response.json()
    return rows[0] if rows else None


def insert_ignore_duplicate(row: dict[str, Any]) -> None:
    backfill.supabase_request(
        "POST",
        "daily_history",
        params={"on_conflict": "symbol,trading_date"},
        payload=[row],
        prefer="resolution=ignore-duplicates,return=minimal",
    )


def session_is_completed(trading_date: date) -> bool:
    current = now_vn()
    if trading_date < current.date():
        return True
    if trading_date > current.date():
        return False
    if current.weekday() >= 5:
        return False
    return current.time().replace(tzinfo=None) >= MARKET_CLOSE_SAFE_AFTER


def main() -> None:
    args = parse_args()
    if not args.trading_date:
        raise RuntimeError("EOD_TRADING_DATE/--trading-date bat buoc.")

    try:
        trading_date = date.fromisoformat(args.trading_date)
    except ValueError as exc:
        raise RuntimeError(
            f"Ngay giao dich khong hop le: {args.trading_date!r}"
        ) from exc

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

    run_at = now_vn()
    exists = 0
    candidates = 0
    written = 0
    no_snapshot = 0
    errors: list[tuple[str, str]] = []

    print(
        f"EOD Daily History Fallback: trading_date={trading_date}, "
        f"symbols={len(symbols)}, write={args.write}."
    )

    for index, symbol in enumerate(symbols, start=1):
        exchange = exchanges.get(symbol)
        if not exchange:
            errors.append((symbol, "Khong co exchange trong watchlist"))
            print(f"[{index}] {symbol} -> ERROR: no exchange")
            continue

        try:
            if daily_row_exists(symbol, trading_date):
                exists += 1
                print(f"[{index}] {symbol} -> EXISTS; no overwrite.")
                continue

            snapshot = load_final_snapshot(symbol, trading_date)
            if snapshot is None:
                no_snapshot += 1
                print(f"[{index}] {symbol} -> NO VALID SNAPSHOT; skip.")
                continue

            price = round(float(snapshot["current_price"]), 4)
            volume = round(float(snapshot["volume_accumulated"]), 4)
            if price <= 0 or volume < 0:
                raise RuntimeError("Snapshot price/volume invalid")

            row = {
                "symbol": symbol,
                "exchange": exchange,
                "trading_date": trading_date.isoformat(),
                "close": price,
                "volume": volume,
                "source": "INTRADAY_EOD",
                "updated_at": run_at.isoformat(),
            }
            candidates += 1
            print(
                f"[{index}] {symbol} -> CANDIDATE "
                f"slot={snapshot.get('time_slot')}, "
                f"close={price}, volume={volume}"
            )

            if not args.write:
                continue

            insert_ignore_duplicate(row)
            if not daily_row_exists(symbol, trading_date):
                raise RuntimeError("Insert xong nhung verify khong thay row")

            written += 1
            print("  -> WRITTEN + VERIFIED")
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            errors.append((symbol, message))
            print(f"  -> ERROR {symbol}: {message}")

    print(
        f"EOD summary: symbols={len(symbols)}, exists={exists}, "
        f"candidates={candidates}, written={written}, "
        f"no_snapshot={no_snapshot}, errors={len(errors)}, write={args.write}."
    )
    for symbol, reason in errors:
        print(f"  - {symbol}: {reason[:500]}")

    # No snapshot is expected for suspended/illiquid/unavailable symbols and
    # is not a workflow failure. Real read/write/verify errors are.
    if args.write and errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
