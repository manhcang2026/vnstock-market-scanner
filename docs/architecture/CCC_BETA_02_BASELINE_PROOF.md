# CCC BETA-02 — Volume baseline coverage proof

## Purpose

The legacy baseline treated every absent one-minute row, including a wholly
absent session, as observed zero volume. That made incomplete SSI history look
complete and could incorrectly mark RVOL metrics as trusted. BETA-02 enforces
the rule **missing is not zero**.

## Session proof

`daily_bars` from `SSI_DAILY_OHLC` with `quality_status=TRUSTED` is the daily
authority. A symbol/session is proven only when all stored intraday rows are
canonical `SSI_REST` rows, trusted, non-partial, gap-free, use the same
canonical exchange, fall on the exchange volume grid, and their represented
volume sum exactly equals the official daily volume.

A trusted daily volume of zero with no intraday rows is a proven real-zero
session. A mismatch or unsafe row excludes the entire session; the builder
does not repair or invent volume. Only after a session is proven may absent
canonical grid minutes be zero-filled for cumulative and rolling windows.

## Exact previous-session window

The required `--as-of-date` is excluded. Candidate dates are the latest
`--lookback` trusted SSI DailyOhlc session dates strictly before it. If one of
those exact dates cannot be proven for a symbol, the builder records fewer
used sessions and never reaches back to an older replacement date.

## Durable proof and trust propagation

The derived baseline retains schema version 2 and records:

- `coverage_proof=SSI_DAILY_VOLUME_RECONCILED_V1`
- `as_of_date=YYYY-MM-DD`

Legacy databases without those keys remain unproven. `stock_state_current`
can trust volume metrics only when the proof mechanism is supported, the
baseline date exactly matches the selected replay date, both used/proven
coverage counts are 10, the volume engine has no quality failure, and the
current replay session is independently complete.

The offline state builder reports current-day evidence: selected date, minute
and quote symbol counts, per-exchange stored minute range, trusted/partial/gap
and non-trusted row counts, unsafe-symbol count, DailyOhlc reconciliation
coverage, failure samples, and the final replay completeness decision. It
does not advance a truncated day into trusted output merely because a 10-day
historical baseline exists.

## Local commands

```powershell
cd services/ssi_realtime_shadow
python -m app.volume_baseline_build `
  --history-db data/ssi_shadow.db `
  --daily-db data/ccc_market_v2.db `
  --output-db data/ccc_v2_baseline.db `
  --lookback 10 `
  --as-of-date 2026-09-18

python -m app.stock_state_build `
  --realtime-db data/ssi_shadow.db `
  --baseline-db data/ccc_v2_baseline.db `
  --market-db data/ccc_market_v2.db
```

Both source databases are opened read-only by the baseline builder. The
baseline output must be a separate, derived local database. This job does not
access Supabase, production, or a VPS and performs no deployment.
