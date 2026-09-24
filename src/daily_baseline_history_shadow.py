from __future__ import annotations

import os
from datetime import date

import backfill_daily_history as backfill
import compare_local_baseline as compare
import daily_baseline_after_close as after_close
from common import load_watchlist, now_vn


def parse_run_date(raw: str) -> date:
    value = raw.strip()
    if value:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise RuntimeError(
                f"SHADOW_RUN_DATE khong hop le: {value!r}"
            ) from exc
    return after_close.history_exclusive_date(now_vn())


def ensure_matching_production_success(
    run_date: date,
    symbols_requested: int,
) -> dict:
    """Do not compare against a half-finished/mixed production baseline."""
    cutoff = run_date.isoformat()
    response = backfill.supabase_request(
        "GET",
        "scan_runs",
        params={
            "select": (
                "run_id,started_at,finished_at,status,symbols_requested,"
                "symbols_success,symbols_failed,message"
            ),
            "job_type": "eq.DAILY_BASELINE",
            "status": "eq.SUCCESS",
            "symbols_requested": f"eq.{symbols_requested}",
            "message": f"like.*history_exclusive_date={cutoff}*",
            "order": "finished_at.desc",
            "limit": "1",
        },
    )
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(
            "SHADOW SAFETY STOP: chua thay DAILY_BASELINE SUCCESS "
            f"cho history_exclusive_date={cutoff} va "
            f"symbols_requested={symbols_requested}."
        )
    return rows[0]


def main() -> None:
    backfill.verify_supabase_config()
    run_date = parse_run_date(os.getenv("SHADOW_RUN_DATE", ""))

    watchlist = load_watchlist()
    symbol_count = len(watchlist)
    production_run = ensure_matching_production_success(run_date, symbol_count)

    print(
        "Daily Baseline History Shadow - READ ONLY\n"
        f"compare_run_date={run_date.isoformat()} | symbols={symbol_count}\n"
        f"production_run_id={production_run.get('run_id')} | "
        f"finished_at={production_run.get('finished_at')}\n"
        "RULE: legacy-compatible 500 calendar-day window; "
        "khong ghi daily_baseline, khong goi provider."
    )

    # Reuse the already-audited local-vs-production comparator.
    os.environ["COMPARE_RUN_DATE"] = run_date.isoformat()
    compare.main()


if __name__ == "__main__":
    main()
