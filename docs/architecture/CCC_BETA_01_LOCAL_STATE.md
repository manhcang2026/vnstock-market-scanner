# CCC BETA-01 Local Current-State Materialization

Status: **LOCAL/OFFLINE BETA FOUNDATION**

Date: **2026-09-18**

## 1. Scope and safety boundary

BETA-01 provides the minimum local path from already-collected SSI data to the
existing `stock_state_current` schema. It does not modify the live collector,
`app/main.py`, Docker/systemd behavior, Supabase, production databases, or the
signal event journal. No deployment or production mutation occurred.

SSI remains the sole Vietnam technical-data source. Source databases are opened
read-only. The destination is an explicitly supplied local SQLite path. Existing
minute bars and volume baselines are neither rewritten nor deleted.

## 2. Inputs and output

Inputs:

- realtime DB (`DATABASE_PATH` or `--realtime-db`): existing `ssi_shadow.db`
  containing `minute_bars` and `latest_quotes`;
- baseline DB (`VOLUME_BASELINE_PATH` or `--baseline-db`): existing
  `ccc_v2_baseline.db` with schema version 2 and lookback exactly 10;
- market DB (`MARKET_V2_DATABASE_PATH` or `--market-db`): local
  `ccc_market_v2.db`, including canonical `daily_bars` where available.

Output is one atomic batch of UPSERTs into the existing
`stock_state_current` table. The table primary key keeps one row per symbol.
The builder does not insert, update, or delete `signal_events`.

The latest usable trading date is selected from stored SSI `minute_bars`; the
machine's wall-clock date is not used as replay authority. This permits a
Saturday/Sunday run to materialize the latest collected Friday session.

## 3. Reused engines and calculations

- `RealtimeVolumeEngine` replays the selected day's canonical 1-minute bars and
  supplies DayRVOL, RVOL15/RVOL30, opening RVOL, and baseline coverage.
- `calculate_moving_averages_from_db` supplies exact MA10/MA200 over canonical
  completed `daily_bars`, strictly before the selected trading date.
- `price_momentum.calculate_price_momentum` supplies Price5/Price15 from the
  exact same-session anchor minute. It never crosses lunch, treats ATO/ATC as
  non-continuous, and returns `NULL` for a missing or untrusted anchor.
- `stock_state_current.project_stock_state` maps the existing quote, market
  session, volume, MA, and price results into the existing schema.

Provider fields not persisted in `latest_quotes`, including ceiling, floor and
total value, remain `NULL`. Missing MA, RVOL, or price-window values remain
`NULL`; they are never converted to zero.

## 4. Trust and bootstrap signal state

The unified row cannot be trusted when the baseline uses fewer than 10 sessions,
when active sessions used are fewer than baseline sessions used, when the volume
snapshot is untrusted, or when current volume has a GAP/PARTIAL/non-trusted
condition. Zero baseline produces `UNAVAILABLE`; incomplete or otherwise
untrusted coverage produces `DEGRADED`.

The current baseline schema does not prove per-symbol/per-minute historical
continuity because the legacy builder can zero-fill absent minutes. Therefore the
BETA-01 CLI reports `baseline_coverage_proven = false` and does not emit a trusted
unified row even for a nominal 10/10 baseline. A later cleanup must add evidence
of complete coverage before a reusable projector caller may explicitly mark that
coverage proven.

BETA-01 is not a Signal Engine. Every local bootstrap row uses:

- `signal_state = NORMAL`;
- `signal_level = 0`;
- `signal_at`, `previous_signal_state`, and `state_changed_at = NULL`;
- a Vietnamese summary explicitly stating that the beta Signal Engine has not
  evaluated the row;
- fixed beta `engine_version` and neutral `config_version` identifiers, without
  numerical signal thresholds.

## 5. CLI

From `services/ssi_realtime_shadow`:

```text
python -m app.stock_state_build \
  --realtime-db data/ssi_shadow.db \
  --baseline-db data/ccc_v2_baseline.db \
  --market-db data/ccc_market_v2.db
```

All three paths can instead be supplied through `DATABASE_PATH`,
`VOLUME_BASELINE_PATH`, and `MARKET_V2_DATABASE_PATH`. The market DB must not be
the same file as either read-only source DB.

## 6. Audit JSON

The command prints deterministic JSON containing:

- `latest_trading_date`, `universe_symbols`, and `latest_quote_symbols`;
- `state_rows_written`, `skipped_symbols`, details, and valid-exchange count;
- full/partial/no-baseline counts;
- MA10/MA200 readiness counts;
- Price5/Price15 availability counts;
- trusted and degraded/unavailable state counts;
- `baseline_coverage_proven`, which remains `false` in BETA-01;
- a stable HPG/SHS/VGI sample containing only symbols present in the build.

Rerunning against unchanged inputs upserts the same rows and creates no history
duplicates.

## 7. Known blockers before production trust

- The legacy baseline builder can still zero-fill a missing symbol minute with
  `day.get(point.minute, 0)`. BETA-01 does not claim this is fixed. Coverage that
  is incomplete or unproven must remain degraded/untrusted, and the baseline
  cleanup remains the next production-trust blocker.
- Local `daily_bars` depth determines MA readiness; fewer than exactly 10/200
  valid completed sessions returns `NULL`.
- The offline builder does not establish live feed health, add Price/Signal
  thresholds, wire a scheduler, or enable a production writer.
- Production paths, ownership, backup, and controlled V2 shadow verification
  still require a separately approved job.
