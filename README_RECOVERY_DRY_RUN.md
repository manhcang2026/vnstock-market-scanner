# Stage 2 — Fake Session Recovery DRY RUN

Target:
- valid last session: 2026-08-28
- invalid holiday session: 2026-08-31

This package is intentionally READ ONLY.

## What it reconstructs

The script reproduces the 2026-08-28 15:00 scanner state from stored inputs:

1. EOD price + accumulated volume
   - `intraday_snapshots`
   - 2026-08-28 / 15:00

2. Daily baseline exactly as scanner would have seen it that morning
   - latest `daily_baseline` row per symbol
   - strictly BEFORE 2026-08-28

3. RVOL30
   - rebuilt from raw intraday history
   - HOSE/HNX: 14:15 -> 14:45
   - UPCOM: 14:30 -> 15:00
   - previous max 10 available sessions
   - target session is NOT included in the historical average

4. Signals
   - price >= +3%
   - daily volume >= 200% AvgVol10
   - current price > MA200
   - RVOL30 >= 200%

5. Independent cross-check
   - `golden_board_daily`

6. Contamination proof
   - 2026-08-31 intraday row count
   - 2026-08-31 stock_snapshot row count
   - EOD 31/08 vs EOD 28/08 identical price + volume ratio

## Current expected reconstruction

After a second exact audit of the production inputs, the correct EOD reconstruction is:

- total: 800
- 4/4: 3
- >=3 signals: 21
- >=2 signals: 89
- RVOL30 >=200%: 137
- EOD 4/4 symbols: BVS, SSB, TLP

IMPORTANT CORRECTION (v1.1):
`>=2 = 89` is the correct point-in-time reconstruction.

Why the earlier `82` check was wrong:
- it used today's `latest_daily_baseline` view after the 28/08 EOD baseline had already been written;
- that view currently contains many rows dated 28/08;
- those rows did not exist yet when the 28/08 15:00 scanner ran.

A historical replay must use the newest baseline row strictly BEFORE 28/08.
The dry-run script does exactly that, and returns `>=2 = 89`.

## Safety

This package contains:
- GET requests only
- no POST
- no PATCH
- no DELETE
- no SQL migration
- no repair function
- no frontend change

Even if the workflow fails, the database is unchanged.

## Run

GitHub Actions:
`Recover Fake Session - Dry Run`

Expected final line:
`DRY RUN PASS — NOTHING WAS WRITTEN`

Only after that should a separate Stage 2B write package be created.
