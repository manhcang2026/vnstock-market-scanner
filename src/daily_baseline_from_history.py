from __future__ import annotations

import os
from datetime import date
from typing import Any

import daily_baseline as base
import compare_local_baseline as compare
from common import load_watchlist, now_vn
from daily_baseline_after_close import history_exclusive_date

CONFIRM_TEXT = "CUTOVER"
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
    raw = os.getenv("LOCAL_BASELINE_RUN_DATE", "").strip()
    if raw:
        return date.fromisoformat(raw)
    return history_exclusive_date(run_at)


def rows_equal(local: dict[str, Any], prod: dict[str, Any]) -> tuple[bool, list[str]]:
    diffs: list[str] = []
    for field in COMPARE_FIELDS:
        left = local.get(field)
        right = prod.get(field)

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


def verify_after_write(
    expected: dict[str, dict[str, Any]],
) -> None:
    production = compare.load_production()
    errors: list[str] = []

    for symbol, local in expected.items():
        prod = production.get(symbol)
        if prod is None:
            errors.append(f"{symbol}: missing after write")
            continue

        equal, diffs = rows_equal(local, prod)
        if not equal:
            errors.append(f"{symbol}: {','.join(diffs)}")

    if errors:
        preview = "; ".join(errors[:20])
        raise RuntimeError(
            f"POST-WRITE VERIFY FAILED: {len(errors)} symbols. {preview}"
        )

    print(f"POST-WRITE VERIFY PASS: {len(expected)}/{len(expected)} EXACT.")


def main() -> None:
    base.verify_supabase_config()

    run_at = now_vn()
    run_date = resolve_run_date(run_at)
    write = env_bool("LOCAL_BASELINE_WRITE", default=False)
    confirm = os.getenv("LOCAL_BASELINE_CONFIRM", "").strip().upper()

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

    production = compare.load_production()

    print("Daily Baseline Local History Cutover")
    print(f"run_date={run_date.isoformat()} | symbols={len(watchlist)} | write={write}")
    print("RULE: 500 calendar-day legacy window; no provider calls.")

    exact = 0
    mismatches: list[str] = []
    local_rows: dict[str, dict[str, Any]] = {}
    write_rows: list[dict[str, Any]] = []

    for index, row in enumerate(watchlist.itertuples(index=False), start=1):
        symbol = str(row.symbol).strip().upper()
        exchange = str(row.exchange).strip().upper()

        try:
            local = compare.calculate_local(
                symbol,
                compare.load_history(symbol),
                run_date,
            )
        except Exception as exc:
            mismatches.append(f"{symbol}: LOCAL_ERROR {type(exc).__name__}: {exc}")
            print(f"[{index}/{len(watchlist)}] {symbol} -> LOCAL_ERROR")
            continue

        prod = production.get(symbol)
        if prod is None:
            mismatches.append(f"{symbol}: MISSING_PRODUCTION")
            print(f"[{index}/{len(watchlist)}] {symbol} -> MISSING_PRODUCTION")
            continue

        equal, diffs = rows_equal(local, prod)
        if not equal:
            mismatches.append(f"{symbol}: {','.join(diffs)}")
            print(
                f"[{index}/{len(watchlist)}] {symbol} -> MISMATCH "
                + ",".join(diffs)
            )
            continue

        exact += 1
        local_rows[symbol] = local
        write_rows.append(
            build_row(
                symbol,
                exchange,
                local,
                run_at.isoformat(),
            )
        )
        print(f"[{index}/{len(watchlist)}] {symbol} -> EXACT")

    print(
        f"\nLOCAL CUTOVER SUMMARY: exact={exact}, "
        f"mismatch_or_error={len(mismatches)}, total={len(watchlist)}"
    )

    if mismatches:
        preview = "; ".join(mismatches[:20])
        raise RuntimeError(
            f"SAFETY STOP: local history is not 100% EXACT. "
            f"{len(mismatches)} problem symbols. {preview}"
        )

    if exact != len(watchlist):
        raise RuntimeError(
            f"SAFETY STOP: expected {len(watchlist)} EXACT, got {exact}."
        )

    if not write:
        print("DRY RUN PASS: no database writes performed.")
        return

    if confirm != CONFIRM_TEXT:
        raise RuntimeError(
            f"SAFETY STOP: write=true requires confirm={CONFIRM_TEXT}."
        )

    print(
        f"WRITE ENABLED: upserting {len(write_rows)} rows into daily_baseline "
        f"with source={SOURCE_NAME}."
    )

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
        "run_id": run_at.strftime("daily-%Y%m%d-%H%M%S"),
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
            f"source={SOURCE_NAME}"
        )[:1000],
    }
    base.upsert_scan_run(run_log)

    print(
        f"DONE: {len(watchlist)}/{len(watchlist)} written + verified; "
        f"history_exclusive_date={run_date.isoformat()}."
    )


if __name__ == "__main__":
    main()
