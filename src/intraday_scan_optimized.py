from __future__ import annotations

import intraday_scan
import market_session_guard
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


_original_fetch_price_board = intraday_scan.fetch_price_board


def _guarded_fetch_price_board(symbols, deadline):
    price = _original_fetch_price_board(symbols, deadline)
    check = market_session_guard.assert_price_board_fresh(
        price,
        intraday_scan.supabase_request,
        intraday_scan.now_vn(),
    )
    if check.get("checked"):
        print(f"Freshness Guard: {check}")
    return price


# Market calendar replaces the old Mon-Fri-only decision.
intraday_scan.is_market_slot = market_session_guard.is_market_slot

# Catastrophic stale-source breaker.
intraday_scan.fetch_price_board = _guarded_fetch_price_board

# RVOL: use the precomputed Supabase baseline instead of reading 35 days
# every 5 minutes.
intraday_scan.calculate_rvol_by_exchange = _fast_rvol

# Google Sheet is fully disconnected from scanner storage.
intraday_scan.backup_sheet_best_effort = _skip_intraday_sheet_backup

# For the 800-symbol production universe, require at least 95% fresh prices.
intraday_scan.MIN_PRICE_BOARD_SUCCESS_RATIO = 0.95


if __name__ == "__main__":
    scan_at = intraday_scan.now_vn()
    force_run = intraday_scan.env_bool("FORCE_RUN", default=False)
    decision = market_session_guard.session_decision(scan_at)

    if not decision.trading_day and not force_run:
        print(
            "MARKET SESSION GUARD: skip before API access; "
            f"date={scan_at.date().isoformat()}; reason={decision.reason}"
        )
        raise SystemExit(0)

    # Forced out-of-session tests remain allowed; intraday_scan itself prevents
    # signals/snapshot history from being written in that mode.
    verify_vnstock_api_access()
    intraday_scan.main()
