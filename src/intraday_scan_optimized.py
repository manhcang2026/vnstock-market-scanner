from __future__ import annotations

import intraday_scan
from rvol30_fast import calculate_rvol_by_exchange_fast


def _fast_rvol(result, scan_at, live_snapshot_slot):
    return calculate_rvol_by_exchange_fast(
        result,
        scan_at,
        live_snapshot_slot,
        intraday_scan.supabase_request,
    )


def _skip_intraday_sheet_backup(*_args, **_kwargs):
    # Supabase is primary. With 800 symbols every 5 minutes,
    # sending 800 snapshots + 800 dashboard rows to Google Sheet
    # is unnecessary load and can become the slowest part of the run.
    return True, "Sheet backup disabled for 800-symbol intraday; Supabase is primary."


# Keep existing price-board, signal, retry and Supabase-write logic.
# Only replace the expensive RVOL history-read path.
intraday_scan.calculate_rvol_by_exchange = _fast_rvol
intraday_scan.backup_sheet_best_effort = _skip_intraday_sheet_backup


if __name__ == "__main__":
    intraday_scan.main()
