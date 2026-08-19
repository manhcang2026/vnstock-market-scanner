from __future__ import annotations

import intraday_scan
from daily_baseline import verify_vnstock_api_access
from rvol30_fast import calculate_rvol_by_exchange_fast


def _fast_rvol(result, scan_at, live_snapshot_slot):
    return calculate_rvol_by_exchange_fast(
        result,
        scan_at,
        live_snapshot_slot,
        intraday_scan.supabase_request,
    )


def _skip_intraday_sheet_backup(*_args, **_kwargs):
    return True, "Google Sheet disabled; Supabase is the only scanner data store."


# RVOL: use the precomputed Supabase baseline instead of reading 35 days
# every 5 minutes.
intraday_scan.calculate_rvol_by_exchange = _fast_rvol

# Google Sheet is fully disconnected from scanner storage.
intraday_scan.backup_sheet_best_effort = _skip_intraday_sheet_backup

# 80% allowed the 648/800 force test to finish green.
# For the 800-symbol production universe, require at least 95% fresh prices.
intraday_scan.MIN_PRICE_BOARD_SUCCESS_RATIO = 0.95


if __name__ == "__main__":
    # Intraday MUST use the same Community API key as Daily Baseline.
    # This fails early if GitHub Actions did not inject VNSTOCK_API_KEY
    # or vnstock still sees Guest 20 requests/minute.
    verify_vnstock_api_access()
    intraday_scan.main()
