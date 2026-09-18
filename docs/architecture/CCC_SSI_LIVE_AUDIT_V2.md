# CCC SSI Live Audit V2

Status: **DATA-V2-03 review candidate; no production execution**

The locked principles in `../product/CCC_V2_OPERATING_PRINCIPLES.md` dated
2026-09-18 are authoritative. CCC is a current-centric scanner/signal engine,
not a general-purpose historical warehouse.

## 1. Purpose and boundary

The audit harness measures provider behavior before CCC is allowed to bootstrap
production daily history. It answers questions about SSI contract conformance,
CCC/SSI universe overlap, MA200 history coverage, bulk DailyOhlc feasibility,
pagination capacity, and observable rate limits. It never writes `daily_bars` or
any production database.

The DailyOhlc planning horizon is bounded to approximately two calendar years/
enough completed sessions for MA200 plus reasonable buffer. The audit does not
plan a long-term 5m archive or pre-2026 1m warehouse.

`services/ssi_realtime_shadow/app/ssi_daily_audit.py` is deliberately read-only.
Its live modes issue authenticated SSI `GET` requests only. The planner and
coverage modes are pure/offline. The implementation does not access a VPS,
Supabase, Docker, runtime services, or the website, and does not add a production
scheduler.

CCC `stock_metadata` remains the authoritative reference universe. The audit
core accepts in-memory records, CSV, or JSON so tests and controlled runs do not
depend on Supabase. This job does not add another Supabase client: a future
controlled run may provide a read-only `stock_metadata` snapshot or reuse an
approved GET-only adapter. It must never mutate the reference universe.

## 2. Audit modes

### Probe

`probe` accepts one to five explicit `SYMBOL:EXCHANGE` pairs and a requested date
range. It reuses DATA-V2-02 DailyOhlc chunking, pagination, deduplication and
normalization. Per-symbol evidence includes requested/returned exchange, row
count, date bounds, validation outcome, observed response keys, request/retry/429
counts, rate-limit headers, and `PASS`, `WARN`, or `FAIL`.

No sample symbol is hardcoded. A controlled run can prefer HPG, SHS and VGI only
after confirming they exist in the supplied CCC universe.

### SSI universe

`universe` fetches `GET /api/v2/Market/Securities` separately for `HOSE`, `HNX`
and `UPCOM`. Each market is fully paged with stable `totalrecord` validation,
page size at most 1,000 and page index at most 10. Capacity overflow, early
termination and changing totals fail the audit instead of returning partial
evidence. Rows normalize symbol and exchange aliases; malformed rows and exact
duplicates are counted, while conflicting duplicates fail.

Comparison with the supplied CCC reference emits:

- `MATCHED`;
- `MISSING_IN_SSI`;
- `EXCHANGE_MISMATCH`;
- `SSI_ONLY`.

The comparison never adds, removes or updates a CCC symbol.

### Bulk DailyOhlc hypothesis

`bulk` makes one deliberately small, single-completed-date DailyOhlc request
without a `symbol` parameter. It validates pagination and captures total rows,
pages, distinct symbols, markets, duplicates, malformed/out-of-date rows and
response shape.

The result is one of:

- `SUPPORTED_AND_COMPLETE` only when a stable `totalrecord` is present and all
  returned rows are structurally usable;
- `SUPPORTED_BUT_AMBIGUOUS` for malformed data, missing completeness evidence,
  or non-definitive provider failure;
- `NOT_SUPPORTED` for an explicit unsupported-request HTTP response;
- `NOT_TESTED` without live evidence.

Documentation saying that Symbol is optional is a hypothesis, not proof that
bulk mode is complete or deterministic for production bootstrap.

### MA200 coverage

`coverage` consumes offline JSON history grouped by symbol. It never persists
the rows. It reuses DATA-V2-02 normalization and the exact moving-average
calculator rather than implementing another formula.

Only sessions strictly before `as_of_date` are eligible. Calendar days and the
same-day unfinished candle are not counted. A recent degraded/unavailable row
blocks the required window; older data is not pulled in to hide it. Per-symbol
output includes completed and trusted-valid counts, earliest/latest session,
MA10/MA200 readiness, reason, and exactly one status:

- `MA200_READY`;
- `INSUFFICIENT_HISTORY`;
- `NO_SSI_HISTORY`;
- `EXCHANGE_MISMATCH`;
- `INVALID_PROVIDER_DATA`;
- `PROVIDER_ERROR`;
- `NOT_AUDITED`.

## 3. Safe rate-limit telemetry

The existing `SSIHistoricalClient` now accepts an optional observer. One event is
emitted per HTTP attempt with only:

- endpoint path and HTTP status;
- request duration;
- attempt number, whether it is a retry, and whether another retry will occur;
- `X-RATELIMIT-LIMIT`, `X-RATELIMIT-REMAINING`, `X-RATELIMIT-RESET`, and
  `Retry-After` when actually present;
- top-level response key names, never response values.

Absent headers remain `NULL`; the harness does not infer a rate. Existing bounded
retry/backoff and HTTP 429 handling remain authoritative. Events contain no
request headers/body, Consumer ID, Consumer Secret, access token, Authorization
value, or Supabase key. Output serialization additionally redacts caller-supplied
secret sentinels, and the SSI URL is reduced to scheme plus host without user
information or paths.

## 4. Bootstrap planner

`plan` is pure and makes no network request. It accepts universe size, calendar
range, page size/capacity, expected daily rows per symbol, bulk audit status and
an observed safe request rate if one has actually been established.

It reports 30-day chunks, per-symbol and conditionally bulk request estimates,
elapsed seconds only when an observed safe rate is supplied, and pagination
capacity risk. Bulk estimates and recommendation are unavailable until bulk is
classified `SUPPORTED_AND_COMPLETE`. Without observed safe-rate evidence,
`recommended_strategy` stays `UNKNOWN`; no guessed requests-per-second value is
embedded in code.

Planner output is a request estimate, not authority to bootstrap unlimited
history. A controlled operator must request only the locked bounded DailyOhlc
horizon.

## 5. Output schema

All modes print a JSON summary. Optional paths produce the same JSON plus CSV
detail. The summary sections are:

- `metadata`: audit version/time/environment, sanitized SSI host, range,
  universe count and exchanges;
- `provider`: endpoint, response shapes, safe rate-limit observations, request,
  retry and 429 counts;
- `universe`: CCC totals and four comparison categories;
- `history`: audited/readiness/error counts;
- `bulk_probe`: capability status and completeness evidence;
- `planner`: request estimates, observed rate evidence, elapsed estimates and
  recommendation.

Outputs are diagnostic artifacts. They are not bootstrap checkpoints and never
authorize a production write.

## 6. Future controlled execution

After Product Owner approval, an operator may run a temporary controlled audit
on `ccc-realtime-01` using credentials already provisioned in that environment.
The safe sequence is:

1. separately inventory the existing 2026 1m corpus before any gap-fill plan;
2. provide a current read-only CCC `stock_metadata` reference snapshot;
3. run the three-symbol/small-range probe;
4. inspect provider shape and rate headers;
5. run the three-market Securities comparison;
6. run the single-completed-date bulk probe;
7. choose a conservative observed request rate from evidence;
8. generate a bounded DailyOhlc planner result;
9. only after separate approval, perform a coverage audit at controlled scale.

Any 429, incomplete pagination, changing total, ambiguous bulk result, exchange
mismatch or unexpected provider shape stops escalation to bootstrap. DATA-V2-03
itself performed none of these production/VPS steps and created no production
data.

Supabase remains authoritative for `stock_metadata`, financial, auth, and
business data. The end-of-September 2026 V1 technical-writer cutover is only a
Product Owner target: backup, V2 verification, and reader audit must precede any
writer stop or later cleanup. This audit authorizes no Supabase mutation or
deletion.
