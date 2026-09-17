# CCC Market Storage Schema V2

Status: **DATA-V2-01 storage foundation**

Market data contract: **2**

Storage schema: **1**

## 1. Scope

This is an additive local SQLite design. It creates no production database,
performs no data migration, changes no collector/runtime path, and implements no
retention deletion or signal thresholds.

The executable foundation is
`services/ssi_realtime_shadow/app/market_storage_schema.py`. It accepts an explicit
`sqlite3.Connection` and never opens a configured/production path. Nothing imports
it from the running collector in DATA-V2-01.

## 2. Existing-system audit

| Status | Capability/table | Evidence and V2 disposition |
|---|---|---|
| **EXISTING** | `minute_bars` | Canonical 1m OHLCV, cumulative volume, partial/gap flags, detailed quality/source, PK `(trading_date, minute, symbol)`; reuse unchanged. |
| **EXISTING** | `latest_quotes` | One raw/current SSI quote row per symbol, including provider session/status diagnostics; reuse unchanged as ingest state. |
| **EXISTING** | `collector_meta` | Collector operational key/value metadata; reuse, but do not confuse with schema metadata. |
| **EXISTING** | `historical_bootstrap_checkpoints` | Idempotent SSI REST bootstrap checkpoints; reuse. |
| **EXISTING** | `daily_finalize_runs` | Day-level QA/finalization metadata for promoting trusted 1m history; reuse as operational metadata. |
| **EXISTING** | `volume_baseline` | Same-valid-minute cumulative and 15/30/opening averages; reuse. |
| **EXISTING** | `volume_baseline_coverage` | Available/used and active-session coverage by symbol; reuse. |
| **EXISTING** | `volume_baseline_metadata` | Baseline schema version and lookback; reuse. It remains baseline-specific. |
| **EXISTING** | Market Session Engine | Canonical exchange/session classification, lunch reset support, valid rolling-window readiness, feed-expected/stale helpers; reuse. |
| **EXISTING** | Realtime volume engine | DayRVOL, RVOL15, RVOL30, opening RVOL, coverage, nullable unavailable metrics and trust reasons; preserve the working engine. |
| **EXISTING** | SSI stream/history normalization | Universe-filtered quote ingest, 1m aggregation, REST bootstrap, dedupe/checkpoints and quality flags; preserve. |
| **PARTIAL** | Daily history | Chart code can aggregate 1m data to daily at read time, and finalizer persists trusted 1m days; no canonical `daily_bars` exists. Add the table only. |
| **PARTIAL** | 5m candles | Chart/live paths aggregate intervals on demand; no approximately two-year canonical archive. Add `bars_5m_archive` only. |
| **PARTIAL** | Current stock state | `latest_quotes` covers raw quote state; volume snapshots are in memory/logs. No unified trend/price/signal/quality row. Add `stock_state_current`. |
| **PARTIAL** | Quality/feed health | Granular minute reasons and a stale detector exist. No persisted V2 feed enum separate from high-level metric quality. New current tables separate them. |
| **PARTIAL** | Baseline validity/trust | The current builder selects a global trading calendar and zero-fills absent symbol minutes/days; `metrics_trusted` does not become false solely for `INSUFFICIENT_HISTORY`. DATA-V2-02 must distinguish a valid no-trade minute from missing data and map incomplete coverage to degraded trust. |
| **PARTIAL** | Universe source | Runtime uses a file or legacy `stock_snapshot` symbol list and `stock_metadata` for exchange lookup. Schema V1 adds the approved minimal cache, but sync/fallback runtime remains for a later job. |
| **PARTIAL** | Confirmed SSI fields | SSI contracts support Ceiling/Floor/RefPrice, OHLC, TotalVol/TotalVal, bid/ask, change/ratio, security session/status, realtime index MI, DailyStockPrice, DailyOhlc, IntradayOhlc, and DailyIndex. The collector persists only a subset; this is an implementation gap, not missing provider capability. |
| **MISSING** | Canonical daily bars | Add `daily_bars`. |
| **MISSING** | Canonical 5m archive | Add `bars_5m_archive`. |
| **MISSING** | Persisted current technical state | Add `stock_state_current`. |
| **MISSING** | V2 event journal/private features | Add `signal_events` and `signal_event_features`. |
| **MISSING** | SSI Vietnam index current state | Add `market_index_current`. |
| **MISSING** | Cross-domain schema/contract version | Add `engine_meta`. |
| **MISSING** | Last-known-good operational universe | Add minimal `universe_cache`; runtime sync is later. |
| **MISSING** | Weekday-holiday/expected-session calendar | Add `trading_calendar`; downloader/population is later. |
| **MISSING** | Price5/Price15 and MA engines in this service | Reserve nullable fields; calculation/runtime wiring is a later job. |
| **LEGACY_ONLY** | Supabase `stock_snapshot`, `daily_baseline`, old four-vote signal fields | Continue serving V1; not V2 technical sources and untouched by this job. |
| **LEGACY_ONLY** | Existing daily MA calculation | `src/daily_baseline.py` labels an average over `min(available, 200)` rows as `ma200` and similarly allows partial MA10. It remains V1 only; V2 must emit `NULL` below exactly 200/10 valid completed sessions. |
| **LEGACY_ONLY** | Golden Board V1 | Remains untouched. V2 uses an event query over `signal_events`, not a new calculation table. |
| **LEGACY_ONLY** | Old vnstock/KBS/VCI Vietnam index path | Not connected to the V2 index table. |

## 3. Physical storage boundaries

The intended production layout is locked as follows. DATA-V2-01 does not create,
open, migrate, or change the configured runtime paths.

| Physical file | Tables/role |
|---|---|
| `/app/data/ssi_shadow.db` | Existing realtime ingest: `minute_bars`, `latest_quotes`, collector/checkpoint metadata. |
| `/app/data/ccc_v2_baseline.db` | Existing `volume_baseline`, `volume_baseline_coverage`, `volume_baseline_metadata`. |
| `/app/data/ccc_market_v2.db` | `daily_bars`, `stock_state_current`, `signal_events`, `signal_event_features`, `market_index_current`, `universe_cache`, `trading_calendar`, `engine_meta`. |
| `/app/data/ccc_5m_archive.db` | `bars_5m_archive` only. |

The dedicated 5m database is required because roughly 800 symbols × 54 bars per
session × 500 sessions already yields about 21.6 million rows, before V3 universe
expansion. `signal_events` and `signal_event_features` remain together in
`ccc_market_v2.db` for enforced foreign-key ownership.

The schema code remains path-agnostic: `ensure_market_storage_schema` initializes
the `ccc_market_v2.db` table set on an explicit connection, while
`ensure_5m_archive_schema` initializes only the archive table. A later rollout job
must pass the locked paths explicitly after a SQLite-consistent backup.

## 4. Table catalog

| Table | Status | Key | Role |
|---|---|---|---|
| `minute_bars` | existing/reused | `(trading_date, minute, symbol)` | Canonical 1m bars and detailed ingest quality. |
| `latest_quotes` | existing/reused | `symbol` | Latest raw/current SSI quote and provider diagnostics. |
| `collector_meta` | existing/reused | `key` | Collector operations. |
| `historical_bootstrap_checkpoints` | existing/reused | `(symbol, from_date, to_date, resolution)` | REST bootstrap idempotency. |
| `daily_finalize_runs` | existing/reused | `trading_date` | Finalization QA. |
| `volume_baseline` | existing/reused | `(symbol, minute)` | Same-time volume baseline points. |
| `volume_baseline_coverage` | existing/reused | `symbol` | Baseline coverage. |
| `volume_baseline_metadata` | existing/reused | `key` | Baseline build schema/lookback. |
| `daily_bars` | new | `(symbol, trading_date)` | Canonical completed daily OHLCV. |
| `bars_5m_archive` | new | `(symbol, trading_date, bar_time)` | Longer-retention 5m archive. |
| `stock_state_current` | new | `symbol` | One canonical current V2 state row per symbol. |
| `signal_events` | new | `event_id` UUID4 text | Append-only transition journal and future outcomes. |
| `signal_event_features` | new/private | `signal_event_id` | Private 1:1 feature snapshot. |
| `market_index_current` | new | `index_code` | Generic Vietnam index current state. |
| `universe_cache` | new | `symbol` | Minimal last-known-good operational cache sourced from `stock_metadata`. |
| `trading_calendar` | new | `(trading_date, exchange)` | Expected-session/holiday operations; SSI actual sessions remain authoritative. |
| `engine_meta` | new | `key` | Market contract and storage schema versions. |

`latest_quotes` is not renamed or duplicated: it remains provider-facing ingest
state. `stock_state_current` is a different, engine-facing materialized projection.

## 5. Keys and relationships

### Daily and 5m bars

The symbol-first primary keys optimize per-symbol chronological reads and enforce
one canonical bar at a given grain. Secondary date/time indexes support finalization,
retention selection, and all-market session scans.

Both tables enforce nonnegative volume/value and valid OHLC envelopes. `value` is
nullable while the current collector persists only a subset of confirmed SSI
fields. `source` and high-level quality are mandatory for provider traceability.
The 5m table and its date/time index live only in `ccc_5m_archive.db`.

### Current state

`stock_state_current.symbol` is the primary key, so a writer must upsert rather
than append. Scanner-oriented indexes cover:

- `(signal_state, signal_level DESC, signal_at DESC)`;
- `(exchange, updated_at DESC)`;
- `(updated_at DESC)`.

Schema V1 does not create an index for every possible numeric filter. DATA-V2-02
should profile real query plans before adding write-amplifying indexes.

MA coverage checks enforce the contract: MA10 exists only at 10 sessions and MA200
only at 200. Distances/above flags cannot exist without their MA. Nullable metric
columns have no numeric defaults. Coverage counters may correctly be zero, but
their values must be provided explicitly.

### Signal journal

`signal_events.event_id` is a canonical lowercase UUID4 text identifier. Multiple
rows per symbol are expected. Retry idempotency is additionally enforced by a
unique constraint on `(symbol, detected_at, signal_state, engine_version,
config_version)`. Indexes support:

- symbol timeline: `(symbol, detected_at DESC)`;
- recent global events: `(detected_at DESC)`;
- Golden Board/state journal: `(trading_date, signal_state, detected_at DESC)`.

Append-only means a new state transition gets a new event ID. The Signal Engine
writes the immutable event and feature snapshot together. A future separate,
idempotent `signal_outcome_worker` may update only the reserved close/max/min and
30m/EOD/T+1/T+3 outcome columns. It must not create a second event or rewrite the
detection facts. No cleanup trigger is installed.

`signal_event_features.signal_event_id` is both its primary key and a foreign key
to `signal_events.event_id`, with `ON DELETE RESTRICT`. This enforces 1:1 ownership and
prevents orphan features. Every connection that writes must enable
`PRAGMA foreign_keys = ON`.

`engine_version` uses SemVer such as `2.0.0`. `config_version` is a non-empty,
immutable opaque ID such as `cfg-20260918-001`. An internal SHA-256 configuration
fingerprint may be stored under a private `engine_meta` key. Threshold values are
never stored in the public event row or exposed through public APIs.

### Universe and trading calendar

`universe_cache` contains exactly the minimal operational fields: symbol,
exchange, active flag, nullable source timestamp, and sync timestamp. Future
runtime syncs from authoritative Supabase `public.stock_metadata`, falls back to
the last valid cache on temporary failure, and still enforces the minimum-universe
safety gate. `stock_snapshot` is not a V2 authority.

`trading_calendar` stores one exchange/date row with trading-day boolean, source,
status, and update timestamp. It supports expected-session/feed behavior,
including weekday holidays. Historical actual completed sessions are derived from
SSI data and valid finalized `daily_bars`; MA windows never count calendar days.
Schema V1 includes no holiday downloader.

### Market indices

`market_index_current.index_code` provides one overwrite/current row per generic
index. Numeric values are nullable so feed loss cannot be encoded as zero. Session,
feed, and quality fields remain mandatory.

## 6. Enum and nullability rules

Schema checks enforce:

- sessions: `OPEN_AUCTION`, `AM_CONTINUOUS`, `LUNCH_BREAK`, `PM_CONTINUOUS`,
  `CLOSE_AUCTION`, `POST_TRADING`, `CLOSED`;
- states: `NORMAL`, `FLOW_APPEARING`, `FLOW_PRICE_CONFIRMED`,
  `MOMENTUM_MAINTAINED`, `MOMENTUM_WEAKENING`, `SELLING_PRESSURE`;
- signal level: integer 0 through 4;
- feed: `LIVE`, `STALE`, `DISCONNECTED`, `EXPECTED_IDLE`;
- high-level quality: `TRUSTED`, `DEGRADED`, `UNAVAILABLE`;
- booleans: SQLite integer 0 or 1.

Detailed `minute_bars.quality_status` values are intentionally not rewritten;
existing reasons such as `PARTIAL` and `GAP` remain valid at that internal layer.

Quality is evaluated per domain. A partial 3/10 or 9/10 baseline may produce an
RVOL value, but volume trust remains false. At 10/10 it may become true only when
continuity and every other volume-quality check pass. Missing symbol/minute data is
never zero-filled unless continuity proves a zero traded-volume delta. Missing
MA/RVOL/Price values remain `NULL`. Overall `metrics_trusted` means all mandatory
inputs for the evaluated signal are trusted, not that every optional field exists.

Feed state is global/collector-aware and separate from session state. Proposed
configurable defaults are: `LIVE` at no more than 15 seconds accepted market-event
age while feed is expected; `STALE` above 15 seconds; `DISCONNECTED` on a known
WebSocket disconnect or above 60 seconds; and `EXPECTED_IDLE` during lunch,
closed/weekend, or a known holiday. One illiquid symbol cannot establish global
feed failure. The legacy 180-second runtime setting is unchanged here.

SQLite cannot reliably enforce every ISO-8601 timezone semantic with a simple
CHECK. Writers must use aware timestamps. The schema module exposes
`canonical_timestamp`, rejects naive timestamps, normalizes to
Asia/Ho_Chi_Minh, and uses that convention for migration metadata.

## 7. Versioning and migration strategy

`engine_meta` contains at least:

| Key | Value |
|---|---|
| `market_data_contract` | `2` |
| `storage_schema` | `1` |

Initialization runs in an explicit SQLite transaction and enables foreign keys.
It is idempotent, preserves unrelated metadata, and refuses a database whose
contract/schema version is newer than the code. Version timestamps change only
when a version advances, so a no-op ensure is deterministic.

The isolated `ccc_5m_archive.db` has no application metadata table and uses SQLite
`PRAGMA user_version = 1`; its only application table is `bars_5m_archive`.
`engine_meta` may later hold a private `config_sha256` fingerprint alongside the
contract/schema versions, but DATA-V2-01 has no config payload to fingerprint.

Future changes follow this sequence:

1. add numbered migration statements for `N -> N+1`;
2. test each supported starting version on temporary databases;
3. apply DDL/data backfill in one explicit transaction where SQLite allows it;
4. validate required objects and invariants;
5. advance `storage_schema` only after success;
6. deploy runtime readers before or together with compatible writers;
7. retain a verified rollback/restore path.

`CREATE TABLE IF NOT EXISTS` is a safety property, not the sole migration system.
Existing tables are not renamed, dropped, or rewritten by schema V1.

## 8. Retention ownership

| Object | Retention | Future mechanism (not implemented here) |
|---|---|---|
| raw SSI payload | transient only | bounded recovery buffer |
| `latest_quotes`, `stock_state_current`, `market_index_current` | current row | upsert writer |
| `minute_bars` | 15 completed trading sessions | session-aware retention job after archive/finalization verification |
| `bars_5m_archive` | approximately two years | date/session-aware retention job |
| `daily_bars` | long-term | backup/archive policy |
| baseline tables | rolling 10 completed sessions | deterministic rebuild/swap |
| signal tables | long-term | backup/archive policy |
| operational logs | configurable 30–90 days | log rotation |

Calendar days must not be substituted for trading-session counts. No deletion is
performed by DATA-V2-01.

### Backup policy

Backups must be SQLite-consistent (SQLite backup API or an equivalent WAL-aware
method); never raw-copy an actively WAL-written database.

| Database | Planned backup cadence |
|---|---|
| `/app/data/ccc_market_v2.db` | Nightly after market close/finalization |
| `/app/data/ccc_v2_baseline.db` | Nightly |
| `/app/data/ssi_shadow.db` | Short-retention operational backup |
| `/app/data/ccc_5m_archive.db` | Weekly |

Oracle volume backup is an additional infrastructure layer, not the sole database
backup. DATA-V2-01 installs no backup job.

## 9. Legacy compatibility

- V1 Supabase market tables and data remain unchanged.
- Existing GitHub Actions, website routes, Golden Board V1, Docker/systemd/nginx,
  and VPS databases remain unchanged.
- Existing SSI collector, historical bootstrap, chart API, live gateway, daily
  finalizer, and volume shadow engine are not wired to the new tables.
- `volume_baseline_metadata.schema_version` remains a separate subsystem version;
  it does not replace `engine_meta.storage_schema`.
- Old MA/daily-baseline jobs are bootstrap/validation candidates only, not V2
  canonical writers.

## 10. Rollout stages

1. **DATA-V2-01 (this stage):** docs, path-agnostic schema module, temporary-DB
   tests. No runtime effect.
2. **Schema rollout:** back up consistently, then apply/verify schema to the locked
   `/app/data/ccc_market_v2.db` and `/app/data/ccc_5m_archive.db` paths without
   starting writers.
3. **Canonical daily/5m writers:** finalize trusted 1m data into daily/5m tables;
   verify session boundaries and provider consistency.
4. **Feature/state shadow writer:** implement MA and Price engines, project existing
   volume snapshots, persist `stock_state_current`; compare without serving it.
5. **Signal/event shadow writer:** implement approved private config/state machine
   and append events/features; no public threshold disclosure.
6. **Index ingest:** connect supported SSI Vietnam indices and validate feed health.
7. **Read APIs:** add entitlement-aware Scanner/Stock Detail/Golden Board projections.
8. **Retention:** enable only after archives, backups, observability, and restore
   tests are accepted.
9. **Cutover:** separate Product Owner approval; V1 remains rollback-capable.

## 11. Inputs for DATA-V2-02 implementation planning

The Product Owner amendment resolves placement, cache/calendar ownership, event ID,
version format, outcome-writer ownership, feed defaults, and backup cadence. The
next job still needs engineering validation rather than new architecture invention:

- exact field mapping from the confirmed SSI contracts into normalized writers;
- the source/status vocabulary and population process for expected calendar rows;
- mapping detailed ingest reasons into domain and overall trust;
- SQLite-consistent backup/restore commands validated on the deployment host;
- Price5/Price15 implementation details within the locked session semantics;
- query-plan measurements before adding more Scanner indexes.

## 12. Known contract gaps; no runtime change in DATA-V2-01

The audit found four runtime differences that the foundation intentionally does not
repair:

1. The legacy daily baseline calculates and labels partial-window MA10/MA200 values;
   V2 requires `NULL` until exactly 10/200 completed valid sessions are available.
2. The current volume baseline zero-fills a missing symbol minute/day selected from
   the global trading calendar. Without a separate continuity decision, this can
   conflate “no trade” with “missing data.”
3. `INSUFFICIENT_HISTORY` is recorded as a volume reason, but by itself does not
   currently make `metrics_trusted` false. V2 requires incomplete coverage not to
   claim full trust.
4. The current universe fallback reads symbols from Supabase `stock_snapshot`,
   whereas V2 keeps company/reference authority in `stock_metadata` and permits
   only a minimal operational cache.

The older product engine specification also described Supabase as a possible home
for selected technical snapshots, events, or daily history and used a different
feed-health vocabulary (`DELAYED`/`OFFLINE`). The newer locked DATA-V2-01 contract
resolves both points: VPS/SSI is authoritative for V2 technical data, and the
canonical feed enum is `LIVE`/`STALE`/`DISCONNECTED`/`EXPECTED_IDLE`.
