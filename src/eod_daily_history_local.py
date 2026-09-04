from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import backfill_daily_history as backfill
import eod_daily_history_from_intraday as legacy_eod
import market_session_guard
from common import load_watchlist, now_vn

REPORT_JSON = Path("daily_history_eod_local_report.json")


def resolve_trading_date() -> date:
    raw = os.getenv("EOD_TRADING_DATE", "").strip()
    if raw:
        return date.fromisoformat(raw)
    return now_vn().date()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def write_report(report: dict[str, Any]) -> None:
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> None:
    trading_date = resolve_trading_date()
    write = env_bool("EOD_WRITE", default=False)
    run_at = now_vn()

    decision = market_session_guard.session_decision(trading_date)
    report: dict[str, Any] = {
        "run_at": run_at.isoformat(),
        "trading_date": trading_date.isoformat(),
        "write": write,
        "provider_calls": 0,
        "session_decision": decision.reason,
        "counts": {
            "exists": 0,
            "intraday_eod": 0,
            "zero_volume_no_bar": 0,
            "written": 0,
            "errors": 0,
        },
        "results": [],
    }

    if not decision.trading_day:
        report["skipped"] = decision.reason
        write_report(report)
        print(
            f"EOD LOCAL SKIP: {trading_date} is not an approved trading day; "
            f"reason={decision.reason}."
        )
        return

    if not legacy_eod.session_is_completed(trading_date):
        raise RuntimeError(
            f"SAFETY STOP: session {trading_date} is not completed (safe after 15:10 VN)."
        )

    backfill.verify_supabase_config()

    watchlist = load_watchlist()
    exchanges = {
        str(row.symbol).strip().upper(): str(row.exchange).strip().upper()
        for row in watchlist.itertuples(index=False)
    }
    symbols = sorted(exchanges)

    existing = legacy_eod.load_existing_symbols(trading_date)
    snapshots = legacy_eod.load_final_snapshots(trading_date)

    # Missing final snapshots are not the same as legitimate zero-volume bars.
    # Fail before any write so a broken 15:00 scan can never create silent gaps.
    missing_snapshots = [
        symbol
        for symbol in symbols
        if symbol not in existing and symbol not in snapshots
    ]
    if missing_snapshots:
        report["counts"]["errors"] = len(missing_snapshots)
        report["missing_snapshots"] = missing_snapshots
        write_report(report)
        raise RuntimeError(
            "SAFETY STOP: missing final >=15:00 OK snapshots for "
            f"{len(missing_snapshots)} symbols: "
            + ", ".join(missing_snapshots[:30])
        )

    candidates: list[dict[str, Any]] = []

    for index, symbol in enumerate(symbols, start=1):
        result: dict[str, Any] = {
            "symbol": symbol,
            "status": "",
            "detail": "",
        }

        if symbol in existing:
            report["counts"]["exists"] += 1
            result["status"] = "EXISTS"
            report["results"].append(result)
            print(f"[{index}/{len(symbols)}] {symbol} -> EXISTS")
            continue

        snapshot = snapshots[symbol]

        try:
            volume = float(snapshot.get("volume_accumulated"))
        except (TypeError, ValueError) as exc:
            report["counts"]["errors"] += 1
            result["status"] = "ERROR"
            result["detail"] = (
                f"invalid volume: {snapshot.get('volume_accumulated')!r}"
            )
            report["results"].append(result)
            write_report(report)
            raise RuntimeError(f"{symbol}: {result['detail']}") from exc

        if volume < 0:
            report["counts"]["errors"] += 1
            result["status"] = "ERROR"
            result["detail"] = f"negative volume={volume}"
            report["results"].append(result)
            write_report(report)
            raise RuntimeError(f"{symbol}: {result['detail']}")

        if volume == 0:
            # Production EOD makes no provider call. A zero-volume final
            # snapshot contributes no new bar to the sparse canonical history.
            report["counts"]["zero_volume_no_bar"] += 1
            result["status"] = "ZERO_VOLUME_NO_BAR"
            result["detail"] = f"slot={snapshot.get('time_slot')}"
            report["results"].append(result)
            print(f"[{index}/{len(symbols)}] {symbol} -> ZERO_VOLUME_NO_BAR")
            continue

        row = legacy_eod.intraday_eod_row(
            symbol=symbol,
            exchange=exchanges[symbol],
            snapshot=snapshot,
            trading_date=trading_date,
            updated_at=run_at,
        )
        if row is None:
            report["counts"]["errors"] += 1
            result["status"] = "ERROR"
            result["detail"] = (
                "positive volume but invalid EOD price/row; "
                f"price={snapshot.get('current_price')}, volume={volume}"
            )
            report["results"].append(result)
            write_report(report)
            raise RuntimeError(f"{symbol}: {result['detail']}")

        candidates.append(row)
        report["counts"]["intraday_eod"] += 1
        result["status"] = "CANDIDATE"
        result["detail"] = (
            f"slot={snapshot.get('time_slot')}, "
            f"close={row['close']}, volume={row['volume']}"
        )
        report["results"].append(result)
        print(f"[{index}/{len(symbols)}] {symbol} -> CANDIDATE")

    if not write:
        write_report(report)
        print(
            "EOD LOCAL DRY RUN PASS: "
            f"candidates={len(candidates)}, "
            f"zero_volume_no_bar={report['counts']['zero_volume_no_bar']}, "
            "provider_calls=0."
        )
        return

    for offset in range(0, len(candidates), legacy_eod.WRITE_BATCH_SIZE):
        batch = candidates[offset:offset + legacy_eod.WRITE_BATCH_SIZE]
        legacy_eod.insert_ignore_duplicates(batch)
        report["counts"]["written"] += len(batch)

    stored = legacy_eod.load_existing_symbols(trading_date)
    candidate_symbols = {str(row["symbol"]) for row in candidates}
    missing_after_write = sorted(candidate_symbols - stored)
    if missing_after_write:
        report["counts"]["errors"] += len(missing_after_write)
        report["write_verify_missing"] = missing_after_write
        write_report(report)
        raise RuntimeError(
            "WRITE VERIFY ERROR: missing after insert: "
            + ", ".join(missing_after_write[:30])
        )

    write_report(report)
    print(
        "EOD LOCAL SUMMARY: "
        f"written={report['counts']['written']}, "
        f"zero_volume_no_bar={report['counts']['zero_volume_no_bar']}, "
        "provider_calls=0, errors=0."
    )


if __name__ == "__main__":
    main()
