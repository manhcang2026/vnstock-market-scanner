# EOD Local Baseline Cutover — 2026-09-05

## Production architecture

1. Intraday Scan remains the primary market-data collector.
2. After market close, `EOD Finalize · Local History`:
   - reads the final intraday snapshot for all symbols;
   - writes valid positive-volume bars directly to `daily_history`;
   - uses KBS/VCI only as a targeted fallback when a final snapshot is missing,
     invalid, or cannot establish an official bar (including ambiguous zero-volume
     cases);
   - calculates MA10 / MA200 / full-day VOL10 from `daily_history`;
   - writes `daily_baseline`;
   - refreshes RVOL30.
3. Same-Time VOL10 is refreshed separately by Supabase cron.

## What is removed

The old nightly 800-symbol Daily Baseline provider scan is no longer part of
the normal schedule. `daily-baseline.yml` remains available as a manual
provider fallback / audit workflow.

## Holiday safety

`market_session_guard` checks the approved Vietnam exchange calendar before
EOD provider access. Weekends and configured holidays skip immediately.

## Why targeted provider fallback remains

An intraday `price=0, volume=0` snapshot is not sufficient to prove that the
official daily history has no bar. Real validation found symbols such as NQN
and THN where VCI carried a valid zero-volume daily bar. Therefore the EOD job
queries providers only for this ambiguous minority, preserving canonical
history without returning to an 800-symbol nightly scan.

## Trigger target

After deployment, GAS should have only:
- `scheduledEodFinalize` around 15:30 VN;
- `scheduledIntradayScan` every 5 minutes;
- `scheduledMarketPulseScan` every 5 minutes.

The old `scheduledDailyBaseline` 01:00 trigger is removed.
