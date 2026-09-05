from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import compare_local_baseline as compare
import daily_baseline as base
import market_session_guard
from common import load_watchlist, now_vn

SOURCE_NAME = "DAILY_HISTORY"
COMPARE_FIELDS = (
    "trading_date",
    "previous_close",
    "ma10",
    "ma10_sessions",
    "ma200",
    "ma200_sessions",
    "avg_volume_10",
    "avg_volume_sessions",
)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def resolve_run_date(run_at) -> date:
    # Explicit exclusive cutoff remains available for repair/debug jobs.
    raw = os.getenv("LOCAL_BASELINE_RUN_DATE", "").strip()
    if raw:
        return date.fromisoformat(raw)

    # EOD workflow accepts a trading_date. Baseline must include that completed
    # session, therefore the history upper bound is trading_date + 1 day.
    eod_trading_date = os.getenv("EOD_TRADING_DATE", "").strip()
    if eod_trading_date:
        return date.fromisoformat(eod_trading_date) + timedelta(days=1)

    # Normal production path: derive the last completed approved session from
    # the Vietnam market calendar.
    return market_session_guard.history_exclusive_date(run_at)


def rows_equal(local: dict[str, Any], stored: dict[str, Any]) -> tuple[bool, list[str]]:
    diffs: list[str] = []
    for field in COMPARE_FIELDS:
        left = local.get(field)
        right = stored.get(field)
        if field == "trading_date":
            equal = str(left) == str(right)
        elif field.endswith("_sessions"):
            try:
                equal = int(left) == int(right)
            except (TypeError, ValueError):
                equal = False
        else:
            equal = compare.value_equal(left, right)
        if not equal:
            diffs.append(field)
    return not diffs, diffs


def build_row(
    symbol: str,
    exchange: str,
    local: dict[str, Any],
    updated_at: str,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "exchange": exchange,
        "trading_date": local["trading_date"],
        "previous_close": local["previous_close"],
        "ma200": local["ma200"],
        "ma200_sessions": local["ma200_sessions"],
        "avg_volume_10": local["avg_volume_10"],
        "avg_volume_sessions": local["avg_volume_sessions"],
        "source": SOURCE_NAME,
        "updated_at": updated_at,
        "data_status": "OK",
        "ma10": local["ma10"],
        "ma10_sessions": local["ma10_sessions"],
    }


def verify_after_write(expected: dict[str, dict[str, Any]]) -> None:
    # EOD runtime runs outside the market window. At that time the
    # latest_daily_baseline view exposes the full-day VOL10 fields, not the
    # same-time intraday overlay.
    stored = compare.load_production()
    errors: list[str] = []

    for symbol, local in expected.items():
        row = stored.get(symbol)
        if row is None:
            errors.append(f"{symbol}: missing after write")
            continue
        if str(row.get("data_status") or "").upper() != "OK":
            errors.append(f"{symbol}: data_status={row.get('data_status')}")
            continue

        equal, diffs = rows_equal(local, row)
        if not equal:
            errors.append(f"{symbol}: {','.join(diffs)}")

    if errors:
        raise RuntimeError(
            "POST-WRITE VERIFY FAILED: "
            f"{len(errors)} symbols. " + "; ".join(errors[:20])
        )

    print(f"POST-WRITE VERIFY PASS: {len(expected)}/{len(expected)} EXACT.")


def main() -> None:
    base.verify_supabase_config()

    run_at = now_vn()
    if market_session_guard.is_market_slot(run_at):
        raise RuntimeError(
            "SAFETY STOP: local Daily Baseline runtime must not write during market hours."
        )

    run_date = resolve_run_date(run_at)
    write = env_bool("LOCAL_BASELINE_WRITE", default=False)

    watchlist = load_watchlist()
    watchlist["symbol"] = (
        watchlist["symbol"].fillna("").astype(str).str.strip().str.upper()
    )
    watchlist["exchange"] = (
        watchlist["exchange"].fillna("").astype(str).str.strip().str.upper()
    )
    watchlist = watchlist[watchlist["symbol"] != ""].drop_duplicates(
        "symbol", keep="first"
    )

    print(
        "Daily Baseline Local Runtime\n"
        f"run_date={run_date.isoformat()} | symbols={len(watchlist)} | write={write}\n"
        "RULE: 500 calendar-day legacy window; no provider calls."
    )

    local_rows: dict[str, dict[str, Any]] = {}
    write_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    # Build the whole generation before the first write. One bad local history
    # row blocks the generation instead of publishing a partial baseline.
    for index, row in enumerate(watchlist.itertuples(index=False), start=1):
        symbol = str(row.symbol).strip().upper()
        exchange = str(row.exchange).strip().upper()
        try:
            local = compare.calculate_local(
                symbol,
                compare.load_history(symbol),
                run_date,
            )
            if date.fromisoformat(str(local["trading_date"])) >= run_date:
                raise RuntimeError(
                    f"trading_date={local['trading_date']} is not before run_date={run_date}"
                )

            local_rows[symbol] = local
            write_rows.append(
                build_row(symbol, exchange, local, run_at.isoformat())
            )
            print(f"[{index}/{len(watchlist)}] {symbol} -> READY")
        except Exception as exc:
            message = f"{symbol}: {type(exc).__name__}: {exc}"
            errors.append(message)
            print(f"[{index}/{len(watchlist)}] {symbol} -> ERROR: {message}")

    if errors or len(write_rows) != len(watchlist):
        raise RuntimeError(
            "SAFETY STOP: local history cannot build a complete baseline. "
            f"ready={len(write_rows)}/{len(watchlist)}, errors={len(errors)}. "
            + "; ".join(errors[:20])
        )

    if not write:
        print(
            f"DRY RUN PASS: {len(write_rows)}/{len(watchlist)} rows ready; "
            "no database writes performed."
        )
        return

    batch: list[dict[str, Any]] = []
    for row in write_rows:
        batch.append(row)
        if len(batch) >= base.SUPABASE_BATCH_SIZE:
            base.upsert_daily_rows(batch)
            batch.clear()
    if batch:
        base.upsert_daily_rows(batch)

    verify_after_write(local_rows)

    finished_at = now_vn()
    run_log = {
        "run_id": run_at.strftime("daily-local-%Y%m%d-%H%M%S"),
        "job_type": "DAILY_BASELINE",
        "started_at": run_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "status": "SUCCESS",
        "symbols_requested": len(watchlist),
        "symbols_success": len(watchlist),
        "symbols_failed": 0,
        "message": (
            f"Daily baseline from daily_history: {len(watchlist)}/{len(watchlist)} "
            f"symbols; history_exclusive_date={run_date.isoformat()}; "
            f"source={SOURCE_NAME}; provider_calls=0"
        )[:1000],
    }
    base.upsert_scan_run(run_log)

    print(
        f"DONE: {len(watchlist)}/{len(watchlist)} local baseline rows written + verified; "
        f"history_exclusive_date={run_date.isoformat()}."
    )


if __name__ == "__main__":
    main()
