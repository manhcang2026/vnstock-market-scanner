# EOD Local Baseline Cutover — 2026-09-05

Production target after merge + GAS trigger reinstall:

1. Intraday Scan writes `intraday_snapshots` every 5 minutes.
2. GAS dispatches `eod-finalize.yml` around 15:30 VN on weekdays.
3. EOD Finalize:
   - writes valid positive-volume 15:00 snapshots to `daily_history`;
   - does **zero provider calls**;
   - fails closed if a final snapshot is actually missing;
   - computes all 800 Daily Baseline rows from `daily_history` using the legacy-compatible 500 calendar-day window;
   - verifies all 800 rows after write;
   - refreshes RVOL30.
4. Supabase cron at 16:10 independently refreshes Same-Time VOL10 from `intraday_snapshots`.
5. `daily-baseline.yml` remains manual provider fallback/repair only.

## One-time GAS action after merge

Update these GAS files from repo:

- `gas/00_Config.gs`
- `gas/02_GitHubTrigger.gs`
- `gas/03_TriggerManager.gs`

Then run `installBackendTriggers()` once.

Expected managed triggers afterward:

- `scheduledEodFinalize`
- `scheduledIntradayScan`
- `scheduledMarketPulseScan`

The old `scheduledDailyBaseline` 01:00 trigger must be gone.
