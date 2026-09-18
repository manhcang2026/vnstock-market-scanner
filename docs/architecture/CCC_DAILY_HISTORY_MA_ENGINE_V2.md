# CCC Daily History and MA Engine V2

Status: **DATA-V2-02 implementation candidate — Product Owner review required**

This is an isolated, local foundation. It does not wire a scheduler, modify the
running collector, write `stock_state_current`, change Supabase, or create a
production database.

## 1. SSI endpoint decision

`GET /api/v2/Market/DailyOhlc` owns canonical `daily_bars`.

Evidence was checked against the official SSI FastConnect [API guide](https://guide.ssi.com.vn/ssi-products/fastconnect-data/api-specs)
and [API specification PDF](https://ftp2.ssi.com.vn/Customers/GDDT/Document/SSI_FastConnectData_Specs.pdf):

- the request supports `symbol`, `fromDate`, `toDate`, `pageIndex`, `pageSize`,
  and ascending order;
- the official row supplies lowercase `symbol`, `market`, `tradingdate`, `time`,
  `open`, `high`, `low`, `close`, `volume`, and `value`;
- the official envelope uses `dataList`, lowercase `totalrecord`, and
  `status: "SUCCESS"`; official daily-row examples use lowercase field names
  such as `symbol`, `market`, and `tradingdate`. These exact names are supported
  while the previously observed casing/envelope variants remain explicit aliases;
- an empty daily `time` is accepted because daily canonical identity is the
  trading date, not an intraday timestamp;
- `Volume` is the total normal matched volume and `Value` is the total normal
  matched value;
- the official numeric example (for example price `28600`, volume `23382100`,
  and value about `663258204999.985`) agrees with the V2 contract units:
  VND/share, shares, and VND. No price, volume, or value scaling is applied;
- the official PDF limits a DailyOhlc request range to 30 days. The client
  therefore chunks larger requested ranges into at most 30 calendar days,
  while MA depth remains session-based rather than calendar-based.

`DailyStockPrice` remains useful for later validation/enrichment but is not the
canonical OHLC source: DailyOhlc is the purpose-built OHLC history response and
includes `Market`, which permits direct exchange validation.

The official `DailyStockPrice` example for `SSI` on `04/05/2020` independently
reports `openprice=12900`, `highestprice=13000`, `lowestprice=12700`,
`closeprice=12700`, `totalmatchvol=2180310`, and
`totalmatchval=27943000000`. Those values numerically match the official
`DailyOhlc` example and support the no-scaling decision. `DailyStockPrice` is not
used as a canonical source or runtime dependency.

## 2. Fetch, normalization, and completion boundary

The new daily method extends the existing `SSIHistoricalClient`; it reuses its
authentication, bounded retry/backoff, one-time refresh after HTTP 401, provider
status validation, and maximum page-index handling.

For each 30-day-or-shorter range it:

1. requests pages in ascending order;
2. validates a stable `totalRecord` and refuses early termination, overrun, or
   ambiguous capacity exhaustion;
3. recursively splits again if a response exceeds safe pagination capacity;
4. deterministically deduplicates `(symbol, raw trading date)` rows.

Canonical normalization then:

- uppercases and verifies the requested symbol;
- parses the trading date without a current-date fallback;
- requires the row date and the requested `to_date` to be strictly before the
  evaluation `as_of_date`;
- normalizes `HSX` to `HOSE` and `UPCO` to `UPCOM`, and rejects disagreement
  with trusted exchange metadata;
- requires finite, positive OHLC and `low <= open/close <= high`;
- requires nonnegative integer-share volume;
- preserves missing/blank value as `NULL` and otherwise requires a finite,
  nonnegative value;
- assigns source `SSI_DAILY_OHLC` and quality `TRUSTED` only after validation.

No zero fill, forward fill, weekend/holiday row, synthetic close, or unit
conversion occurs. Current-session EOD finalization remains out of scope.

## 3. Bootstrap and idempotency

`bootstrap_daily_history` accepts an explicit SQLite connection and a requested
date range. Provider fetch and complete-response validation finish before a
write transaction starts. Valid rows are inserted atomically into the existing
DATA-V2-01 `daily_bars` schema.

- A first row is inserted.
- An identical `(symbol, trading_date)` rerun is a no-op counted as existing.
- A conflicting existing canonical row raises and rolls back the entire batch.
- Malformed rows are rejected and make the result `PARTIAL_REJECTED`, never
  `COMPLETE`.
- Network/pagination/provider exceptions propagate and write no rows.

There is no production checkpoint or scheduler wiring in this job. This keeps
daily bootstrap independent of the existing resolution-specific 1-minute
checkpoint table. A later rollout can add orchestration only after review.

## 4. Exact completed-session MA semantics

`calculate_moving_averages` is pure; a small adapter selects canonical
`daily_bars` with `trading_date < as_of_date`.

- MA10 is the arithmetic mean of exactly the latest 10 trusted completed rows.
- MA200 is the arithmetic mean of exactly the latest 200 trusted completed rows.
- With fewer than N rows, MA-N is `NULL`; the session count reports trustworthy
  rows available in that recent candidate window.
- A nonpositive/non-finite close or non-`TRUSTED` row inside the latest required
  N-row window makes MA-N `NULL`. The engine does not reach farther back to hide
  a known bad recent row.
- MA10 and MA200 are evaluated independently. `math.fsum` is used before
  division, and tests use tolerant floating-point comparison.
- `latest_completed_session` is the most recent trusted valid canonical close
  strictly before the evaluation date. The current intraday price is never an
  MA input.

Calendar gaps have no arithmetic effect. The engine does not infer a missing
session from weekdays alone: `trading_calendar` is operational context and must
not manufacture a price. Detecting an absent expected session requires a future
orchestrator to reconcile trusted calendar/provider completeness and record a
degraded/unavailable canonical fact.

## 5. Local SQLite storage benchmark

Command:

```text
python -m app.storage_benchmark --rows 100000
```

Method: three temporary local databases, 100,000 synthetic rows per table, the
real `daily_bars`, current `minute_bars`, and `bars_5m_archive` schemas plus their
indexes, SQLite 4,096-byte pages, `journal_mode=DELETE`, commit then `VACUUM`.
WAL was zero. “Incremental bytes/row” is `(populated DB - empty real schema) /
rows`, so it includes table and index growth while excluding unrelated empty
schema overhead.

| Schema | Page count | Total DB bytes | Empty schema bytes | Incremental bytes/row |
|---|---:|---:|---:|---:|
| `daily_bars` | 3,874 | 15,867,904 | 126,976 | 157.40928 |
| `minute_bars` | 4,372 | 17,907,712 | 40,960 | 178.66752 |
| `bars_5m_archive` | 4,153 | 17,010,688 | 16,384 | 169.94304 |

Measured projections (binary GiB, `1 GiB = 1,073,741,824 bytes`):

| Projection | Rows | Estimated GiB |
|---|---:|---:|
| 1m, 800 × 270 × 15 sessions | 3,240,000 | 0.539 |
| 5m, 800 × 54 × 250 sessions | 10,800,000 | 1.709 |
| 5m, two years | 21,600,000 | 3.419 |
| Daily, five years | 1,000,000 | 0.147 |
| Daily, ten years | 2,000,000 | 0.293 |

At the observed 5.2 GiB used, the upper-order 15-session 1m + two-year 5m +
ten-year daily projection adds about 4.251 GiB, for about 9.451 GiB used or 21%
of a 45 GiB filesystem. It remains below the stated 60%, 70%, and 80% levels.
Those levels correspond to 27.0, 31.5, and 36.0 GiB used, leaving 21.8, 26.3,
and 30.8 GiB of growth from the observed baseline. With the intended bounded
15-session/2-year retention, the estimate does not cross any threshold; no date
can be honestly assigned without actual growth, fragmentation, WAL, indexes from
future schemas, and non-market filesystem usage.

For a deliberately unbounded comparison only, adding one measured 5m year plus
one daily year per year after the 1m footprint would reach roughly 60% in 12.2
years, 70% in 14.8 years, and 80% in 17.4 years. This is not the retention model
and is not a deletion recommendation.

The synthetic values have relatively uniform text lengths and insertion order;
real symbol mix, page fill, churn, WAL/checkpoint behavior, fragmentation,
SQLite version, filesystem allocation, and future indexes will change results.
GB and GiB must not be interchanged: decimal `1 GB = 1,000,000,000 bytes`.

## 6. Verification status and rollout remainder

The unit suite covers normalization failures, pagination completeness and retry,
range splitting, deduplication/conflict rollback, idempotent reruns, exact 0/9/10/
11/199/200/201-session MA boundaries, look-ahead exclusion, gaps, and degraded
recent history.

No local SSI credentials were available, so no live request was made. No local
legacy MA database/value was present, so no numeric V1/V2 comparison was
possible. Code inspection still confirms the known semantic difference: V1 may
label an average of fewer than N observations as MA-N, while V2 returns `NULL`.

Production rollout still needs Product Owner approval, credentials-backed small
HOSE/HNX/UPCOM verification, coverage/depth reporting across the approved
universe, production path/orchestration design, expected-session reconciliation,
backup/rollback, and a separate current-day EOD finalizer. None is implemented
or implied by DATA-V2-02.
