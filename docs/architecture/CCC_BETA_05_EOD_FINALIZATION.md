# CCC BETA-05 — EOD canonical finalization contract

## Storage topology

- `ssi_shadow.db` remains the read-only hot source during finalization.
- `ssi_history_YYYY.db` is the canonical yearly one-minute archive.
- The V2 market database owns `daily_bars` and `auction_session_history`.
- The finalizer does not delete hot rows and does not create another permanent database.
- `yearly_history_path()` deterministically maps a trading date to
  `ssi_history_<year>.db`.

All local/test database paths are explicit. The CLI defaults to dry-run and requires
`--write` before any mutation.

## Canonical settlement authority

Official SSI DailyOhlc is the settlement authority. Its canonical identity is:

- `source = SSI_DAILY_OHLC`
- `quality_status = TRUSTED`

For each symbol, the sum of the reconstructed canonical minute volumes must equal
the DailyOhlc volume exactly. Missing DailyOhlc, a volume mismatch, invalid OHLCV,
an unresolved gap, a non-SSI stream source, an invalid market minute, or an
unresolved event quality blocks that symbol.

## Event quality and settled quality

Hot rows preserve event-level evidence. `PARTIAL`, `VOLUME_REGRESSION`, and
`is_partial = 1` are recorded in the finalize journal. They do not permanently
poison a completed session when deterministic reconstruction is valid, there is no
gap, and the reconstructed volume reconciles exactly with DailyOhlc.

Accepted yearly minute rows are the settled representation:

- `data_source = SSI_STREAM`
- `quality_status = TRUSTED`
- `is_partial = 0`
- `has_gap = 0`

Finalization is represented by `daily_finalize_runs`; provider identity is never
changed to a synthetic `SSI_STREAM_FINAL` source.

## Idempotency and conflicts

Minute identity is `(trading_date, minute, symbol)`.

- Missing canonical minute rows are inserted.
- Existing canonical `SSI_REST` or `SSI_STREAM` rows with identical exchange and
  OHLCV are safe no-ops and retain their source.
- Any conflicting existing row blocks that symbol and is never overwritten.
- DailyOhlc rows are inserted once; identical reruns are no-ops; conflicts block.
- No canonical row is deleted.

The transaction scope is one symbol/session across the attached yearly history and
V2 market databases. Every symbol is fully preflighted before its transaction.
This isolates a bad symbol while keeping retries deterministic: a later retry sees
already-identical canonical evidence and completes as a no-op.

## Auction finalization

Only finalized `auction_session_buckets` with `data_source = SSI_STREAM`, trusted
quality, positive event evidence, and an explicit matching provider session may
become `PROVEN`:

- `OPEN_AUCTION` requires provider session `ATO`.
- `CLOSE_AUCTION` requires provider session `ATC`.

A PROVEN ATC row may supersede the same date's BETA-04C
`INFERRED_BOUNDARY` row. The prior source, quality, and proof code remain in the
canonical provenance columns. Historical ATO is never inferred from a clock time
or a 09:15 minute bar; ATO coverage grows only from live PROVEN rows.

## Journal and status

`daily_finalize_runs` records timing/mode, source coverage, per-symbol outcomes,
minute/daily/auction write counts, raw anomaly counts, reconciliation counts,
volume mismatches, missing DailyOhlc, unresolved gaps, and detailed symbol reasons.

- `DRY_RUN_PASS`: every symbol preflights successfully and nothing is mutated.
- `PASS`: every attempted symbol settles successfully.
- `PARTIAL`: at least one symbol settles and remaining failures are non-conflict
  availability or quality failures.
- `BLOCKED`: no symbol settles, or any unresolved canonical conflict exists.

The EOD journal is written only in explicit write mode; dry-run performs zero
mutation.
