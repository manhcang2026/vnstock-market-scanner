# Market Session Guard — Stage 1

Purpose: prevent a weekday holiday or catastrophic stale price-board response from
publishing a false new trading session.

## What this stage changes

1. `config/market_holidays.csv`
   - Official 2026 exchange holidays.
   - Includes the Jan-2 adjustment and Aug-31 → Sep-2 National Day closure.

2. `config/market_calendar_years.txt`
   - Explicit approved calendar coverage.
   - Any uncovered year FAILS CLOSED.

3. `src/market_session_guard.py`
   - trading-day decision;
   - session-slot decision;
   - `last_completed_trading_date`;
   - `history_exclusive_date`;
   - stale-source circuit breaker.

4. `src/intraday_scan_optimized.py`
   - installs the guard into the existing production scanner;
   - skips holidays before VNStock API access;
   - blocks catastrophic stale source data before any Supabase publish.

5. Daily Baseline wrappers
   - `src/daily_baseline_guarded.py`
   - `src/refresh_rvol_baseline_guarded.py`
   - both use the last completed VALID trading session rather than weekday logic.

6. `.github/workflows/daily-baseline.yml`
   - switches Daily Baseline and RVOL refresh to the guarded wrappers.

7. Read-only tools
   - `python tools/check_market_session_guard.py`
   - `python tools/audit_invalid_session.py --invalid-date 2026-08-31 --previous-date 2026-08-28`

## Important safety properties

- No SQL migration in Stage 1.
- No automatic deletion.
- No automatic repair of `stock_snapshot`.
- No frontend change.
- No Supabase write occurs from the audit tool.
- Existing GAS triggers may keep dispatching; Python exits safely on closed sessions.
- `FORCE_RUN=true` remains available for explicit connection tests. Existing scanner
  behavior still prevents forced out-of-session tests from writing intraday history.

## Stale source breaker

The breaker is intentionally conservative:
- only compares candidate data with an OLDER stock_snapshot date;
- requires at least 760 comparable symbols;
- blocks only if >=99.5% have BOTH identical price and accumulated volume.

Thus a normal quiet 5-minute interval on the same trading day is never rejected.

## Required local verification

Run:

    python tools/check_market_session_guard.py

Expected final line:

    PASS: Market Session Guard deterministic checks.

## After Stage 1 is deployed

Do NOT delete Aug-31 data manually.
Next stage is a separate recovery package:
- reconstruct 2026-08-28 stock_snapshot;
- assert KPI = 3 / 21 / 89 / 137;
- assert 4/4 = BVS, SSB, TLP;
- dry-run first;
- only then invalidate/delete the 2026-08-31 fake intraday rows.

## v1.1 calendar rollover hardening

Calendar coverage includes official HNX/VNX holiday schedules for both 2025 and 2026.
This is necessary so the first trading day of January 2026 can safely resolve the
last completed session as 2025-12-31. Year 2027 remains intentionally uncovered
and therefore fail-closed until its official exchange calendar is approved.
