# CCC V2 Operating Principles

Status: **LOCKED PRODUCT OWNER PRINCIPLES**

Date: **2026-09-18**

These principles override conflicting retention, history, archive, signal-state,
and cleanup assumptions in older CCC V2 documents. They do not authorize a
deployment, production write, migration, or deletion.

## 1. Current-centric product boundary

CCC is a realtime/near-realtime stock scanner and signal engine. It is not a
general-purpose historical market-data warehouse.

Historical data is retained only when it directly supports:

- current technical calculations;
- quality verification;
- CCC signal evaluation;
- Golden Board and signal-outcome analysis.

Data must not be stored merely because it may be useful someday.

## 2. SSI 1-minute history

The SSI 1-minute 2026 corpus already present on the VPS is an asset. Its
completeness is unknown until measured, so it must neither be declared complete
nor deleted or downloaded again blindly.

The required operating sequence is:

1. inventory the existing 2026 corpus;
2. measure symbol/date/session coverage;
3. identify missing sessions and incomplete symbols;
4. fetch only the missing SSI portions;
5. preserve already-valid rows;
6. after sufficient completion, append each newly completed trading day.

The previous generic “retain only 15 sessions of `minute_bars`” rule is
superseded for this corpus. No automatic deletion of valid 2026 1-minute data is
allowed. Pre-2026 1-minute backfill requires a separately approved Product Owner
use case. Future retention beyond the preserved 2026 corpus is capacity-driven
and also requires separate approval.

## 3. Daily OHLC and moving averages

Daily OHLC exists primarily for current MA10/MA200 and related trend context.

- MA10 requires exactly 10 valid completed sessions.
- MA200 requires exactly 200 valid completed sessions.
- The current intraday session is excluded.
- A partial MA200 remains `NULL`.
- No synthetic/fallback row or provider mixing may manufacture coverage.
- A symbol with fewer than 200 valid sessions naturally accumulates sessions
  over time.

Target `daily_bars` retention is bounded to approximately two calendar years,
or enough completed sessions to support MA200 with a reasonable buffer. Daily
history is not an unlimited archive.

## 4. Five-minute archive

The former approximately two-year `bars_5m_archive` requirement is superseded.

- Do not build a long-term 5-minute archive writer.
- Do not bootstrap 5-minute history.
- Do not allocate storage for a two-year 5-minute archive.
- Do not make that archive a prerequisite for maintaining other data.
- The existing schema/table may remain inert for compatibility.
- No production writer or retention job targets it.

A future approved product need for long intraday history must redesign this
decision rather than silently reviving the old archive plan.

## 5. Supabase and cutover boundary

Supabase remains canonical for authentication/users, profiles, plans,
subscriptions, watchlists, payments, `stock_metadata`, `financial_latest`,
`financial_quarterly`, and other business/product data. Financial and reference
databases stay in Supabase; they are not migrated to the VPS.

The VPS is the V2 Vietnam technical market-history engine and keeps only a
minimal last-known-good universe cache derived from `stock_metadata`. Current V1
technical scanner/data stays operational until V2 cutover.

The Product Owner target for the end of September 2026 is:

1. stop legacy Supabase technical intraday and daily scanner writers;
2. verify V2/SSI operation;
3. preserve the required backup;
4. identify V1 technical tables with no remaining readers;
5. only then consider cleanup of obsolete technical data.

This target is not authorization to stop a writer or delete Supabase data.

## 6. RVOL semantics and required cleanup

The baseline target is 10 completed valid prior sessions. V2 operates from
1-minute data.

- `DayRVOL` is current-day cumulative volume at a valid market minute divided by
  average cumulative volume at that same valid minute across baseline sessions.
- `RVOL15` is volume over the latest 15 valid continuous minutes divided by the
  average volume for the identical comparable 15-minute window across baseline
  sessions.
- `RVOL30` is the corresponding latest/comparable 30-minute ratio.

RVOL15/RVOL30 may update every valid minute. Continuous rolling windows reset
between AM and PM, do not cross lunch, and do not treat ATO/ATC as ordinary
continuous minutes. DayRVOL continues cumulatively through the day. Every
comparison uses comparable timing/windows from prior sessions.

Missing data is not zero. Zero is valid only when actual continuity proves zero
traded volume. The known legacy baseline-builder behavior that can zero-fill a
missing symbol minute/day is a **REQUIRED CLEANUP / FIX** before production V2
volume metrics can be trusted.

## 7. Signal states and configuration

The canonical state model is:

| State | Vietnamese | Meaning |
|---|---|---|
| `NORMAL` | Bình thường | No meaningful abnormal activity. |
| `WATCHING` | Đang theo dõi | Early abnormal volume/price behavior merits monitoring, but official signal conditions are not yet satisfied. |
| `FLOW_APPEARING` | Dòng tiền đang xuất hiện | Abnormal flow is sufficiently established. |
| `FLOW_PRICE_CONFIRMED` | Dòng tiền & giá đã xác nhận | Flow has meaningful price confirmation. |
| `MOMENTUM_MAINTAINED` | Xu hướng đang được duy trì | The confirmed condition continues. |
| `MOMENTUM_WEAKENING` | Động lượng đang suy yếu | Momentum is fading. |
| `SELLING_PRESSURE` | Áp lực bán đang tăng | Active configuration indicates elevated selling pressure. |

No numerical threshold is decided here. Thresholds remain server-side and must
not be hardcoded into browser code or fixed permanently in source. Future
authorized Product Owner configuration may cover WATCHING volume, DayRVOL,
RVOL15, RVOL30, Price5/Price15 confirmation, weakening, selling pressure, and
future approved parameter categories.

Configuration has a draft/editable state and an explicit Apply/Activate action.
Each activation creates a new immutable `config_version`. Historical events keep
the version active at detection time; configuration changes never rewrite old
facts. Public/browser APIs never expose proprietary threshold values. A future
admin preview may simulate counts before activation, but no UI is authorized by
this principle.

## 8. Current state, event journal, and Golden Board

CCC continuously evaluates every eligible symbol but upserts only one current
state per symbol. It must not append one historical row per symbol per minute.

An append-only `signal_events` row is created only for a meaningful transition,
including `NORMAL -> WATCHING`, `WATCHING -> FLOW_APPEARING`, confirmation,
maintenance, weakening, or selling pressure. Events/features are retained
long-term because they support auditability, configuration evaluation, Golden
Board, and 30m/EOD/T+1/T+3 outcomes. They are not raw market-history storage.

Golden Board uses this canonical journal to preserve the detection journey: first
WATCHING time, flow appearance, confirmation, subsequent state changes, features
and outcomes. No redundant Golden Board calculation table is created.

## 9. Cleanup and pre-cutover manifest

### KEEP

- valid existing SSI 1-minute 2026 data;
- required bounded daily data for MA;
- volume baseline;
- signal events/features and current state;
- `stock_metadata`, financial tables, and auth/business data.

### FILL_GAPS

- incomplete or missing 2026 SSI 1-minute sessions;
- required DailyOhlc history up to the bounded MA horizon.

### STOP_WRITER_AT_V2_CUTOVER

- legacy Supabase technical intraday scanner;
- legacy Supabase daily technical scanner;
- obsolete V1 technical writers confirmed unused.

### DO_NOT_BUILD

- long-term 5-minute archive writer;
- pre-2026 1-minute history warehouse;
- duplicate fundamentals/reference storage on the VPS.

### DELETE_ONLY_AFTER_BACKUP_AND_READER_AUDIT

- obsolete Supabase V1 technical tables/data;
- redundant benchmark/audit copies on the VPS;
- superseded temporary bootstrap artifacts.

### UNKNOWN / AUDIT FIRST

- coverage/completeness of `ssi_history_2026.db`;
- actual readers of legacy Supabase technical tables;
- redundant local SQLite copies;
- production database ownership/path status.

No physical deletion, writer shutdown, migration, or production access is
authorized or performed by this document.
