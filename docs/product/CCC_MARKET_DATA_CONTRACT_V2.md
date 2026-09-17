# CCC Market Data Contract V2

Status: **locked foundation contract**

Contract version: **2**

Canonical trading timezone: **Asia/Ho_Chi_Minh**

Scope: CCC V2 market/technical data; this document does not define proprietary signal thresholds.

## 1. Authority and precedence

This contract records the Product Owner decisions for DATA-V2-01. Where an older
product or UI document assigns technical market data to Supabase, this contract
takes precedence for CCC V2.

| Domain | Canonical owner |
|---|---|
| Vietnam realtime quotes, OHLCV, intraday/daily bars | VPS / CCC Market Engine using SSI |
| MA, price/volume features, market sessions, signal state/events | VPS / CCC Market Engine |
| Vietnam indices supported by SSI | VPS / CCC Market Engine using SSI |
| Feed health and technical data quality | VPS / CCC Market Engine |
| Auth, profiles, plans, subscriptions, temporary access, watchlist, payments | Supabase |
| Company/reference metadata | Supabase `stock_metadata` |
| Fundamentals | Supabase `financial_latest`, `financial_quarterly` |
| Slow global context such as S&P 500, DXY, Gold, WTI, BTC | Supabase may store it; approximately five-minute polling is acceptable |

Supabase is not the CCC V2 technical market database. Raw SSI messages are not
written there. Vietnam indices must not use the old vnstock/KBS/VCI Market Pulse
path after V2 cutover.

The VPS keeps a last-known-good `universe_cache` containing only `symbol`,
`exchange`, `active`, optional `source_updated_at`, and `synced_at`. Future runtime
will sync it from `public.stock_metadata` on startup and periodically, fall back to
the last valid cache during temporary Supabase failure, and retain the existing
minimum-universe safety gate. `stock_snapshot` is not a V2 universe authority.
The cache is operational only, not a second company metadata authority. No
component may assume that the universe is exactly 800 symbols.

### Confirmed SSI capability versus current persistence

Official SSI FastConnect contracts support stock Ceiling/Floor/RefPrice, OHLC,
TotalVol/TotalVal, bid/ask, change/ratio change, securities status/session,
realtime index MI, and the DailyStockPrice, DailyOhlc, IntradayOhlc, and DailyIndex
historical APIs.

The current collector persists only a subset. An unpersisted confirmed field is a
partial CCC implementation, not a missing provider capability. Parser expansion
and index ingestion are out of scope for DATA-V2-01. Vietnam indices use SSI/VPS;
vnstock/KBS/VCI must not become V2 Vietnam index authority.

## 2. Canonical units and missing data

| Field class | Canonical unit | Example |
|---|---|---|
| Price | VND/share | `28000` |
| Volume | shares | `1500000` |
| Value | VND | `42000000000` |
| Percentages and percentage distances | percentage points | `1.82` means `+1.82%`, not `0.0182` |
| RVOL | ratio/multiple | `2.4` means `2.4x`, equivalent to 240% |
| Boolean storage | SQLite `0`/`1`, nullable when unknown | `above_ma200 = NULL` if MA200 is unavailable |
| Trading date | local `YYYY-MM-DD` | `2026-09-18` |
| Serialized timestamp | ISO 8601 with timezone | `2026-09-18T10:30:00+07:00` |

Missing, unavailable, or not-yet-ready measurements are `NULL`. They are never
silently converted to numeric zero. A real observed zero remains zero. Physical
bar minute labels may be stored as local `HH:MM` beside `trading_date`; APIs must
serialize instants with an explicit timezone offset.

## 3. Market session semantics

All engines use the shared server-side Market Session Engine. Raw provider codes
such as `C` are diagnostic input and are not CCC semantic sessions.

Canonical session values are:

- `OPEN_AUCTION`
- `AM_CONTINUOUS`
- `LUNCH_BREAK`
- `PM_CONTINUOUS`
- `CLOSE_AUCTION`
- `POST_TRADING`
- `CLOSED`

The canonical session is derived from the provider event time, normalized to
Asia/Ho_Chi_Minh, plus exchange rules. The browser clock is never authoritative.
Day-cumulative metrics continue through lunch; continuous rolling windows reset
at lunch. ATO and ATC are not ordinary continuous windows.

`trading_calendar` supports expected-session/feed behavior on weekday holidays.
Historical actual completed sessions inferred and finalized from SSI market data
are authoritative. MA10/MA200 count valid completed `daily_bars`, never calendar
days. DATA-V2-01 does not add a holiday downloader.

## 4. Current stock state

`stock_state_current` is the server-side materialized current projection. There is
at most one row per symbol. Writers replace/update that row; historical transitions
belong in `signal_events`.

| Group | Fields |
|---|---|
| Identity | `symbol`, `exchange`, `trading_date` |
| Quote | `last_price`, `ref_price`, `ceiling_price`, `floor_price`, `open_price`, `high_price`, `low_price`, `change_value`, `change_pct`, `total_volume`, `total_value`, `bid_price1`, `bid_volume1`, `ask_price1`, `ask_volume1` |
| Session | `session_type`, `session_id`, `session_started_at`, `session_ends_at`, `elapsed_valid_minutes` |
| Trend | `ma10`, `ma200`, `ma10_sessions`, `ma200_sessions`, `distance_ma10_pct`, `distance_ma200_pct`, `above_ma10`, `above_ma200` |
| Volume | `cumulative_volume`, `day_rvol`, `volume_15`, `avg_volume_15`, `rvol15`, `volume_30`, `avg_volume_30`, `rvol30`, `opening_volume`, `avg_opening_volume`, `opening_rvol`, `baseline_sessions_used`, `baseline_target_sessions`, `baseline_coverage_pct` |
| Price engine | `price5_pct`, `price15_pct`, `breakout_state`, `trigger_price`, `trigger_at` |
| Signal | `signal_state`, `signal_level`, `signal_summary_vi`, `signal_at`, `previous_signal_state`, `state_changed_at`, `engine_version`, `config_version` |
| Quality | `feed_status`, `quality_status`, `metrics_trusted`, `event_at`, `updated_at` |

Provider-dependent quote fields and computed metrics are nullable. Identity,
semantic state, versions, coverage counters, quality flags, and update timestamps
must be explicit. No unconfirmed SSI field is required merely to populate a row.

## 5. Daily trend contract

MA10 and MA200 use completed, valid daily sessions only. Today's unfinished
intraday value is excluded.

- `ma10` is the average close of exactly 10 completed sessions.
- `ma200` is the average close of exactly 200 completed sessions.
- `ma10 = NULL` when `ma10_sessions < 10`.
- `ma200 = NULL` when `ma200_sessions < 200`.
- An 83-session average must never be called MA200.
- `distance_ma10_pct` and `distance_ma200_pct` use percentage points.
- `above_ma10` and `above_ma200` are nullable when their MA is unavailable.

Canonical MA calculation will eventually read `daily_bars`. DATA-V2-01 does not
change the current runtime calculation.

## 6. Volume feature contract

The baseline target is 10 completed valid sessions. Partial build-up is allowed
and must expose `baseline_sessions_used`, `baseline_target_sessions = 10`, and
`baseline_coverage_pct`. Incomplete coverage must not claim full trust.

A 3/10 or 9/10 baseline may produce a useful metric, but its volume domain is not
fully trusted. `volume_trusted` may become true at 10/10 only when continuity and
all other volume-quality checks also pass. Missing symbol/minute data must not be
zero-filled unless continuity proves that the true traded-volume delta was zero.
Missing data and zero trading are different facts.

Definitions:

- `DayRVOL` = current day-cumulative volume divided by average cumulative volume
  at the same valid market time over baseline sessions.
- `RVOL15` = volume in the current 15 valid continuous trading minutes divided by
  the average comparable 15-minute window.
- `RVOL30` = volume in the current 30 valid continuous trading minutes divided by
  the average comparable 30-minute window.
- Opening RVOL, where enabled, uses exchange/session-specific opening semantics.

Rolling windows do not cross lunch or include ATO/ATC as ordinary continuous
minutes. Zero or unavailable denominators produce `NULL`, not zero or infinity.

## 7. Price feature contract

- `Price5` compares current price with the price five valid continuous trading
  minutes earlier in the same continuous session.
- `Price15` compares current price with the price 15 valid continuous trading
  minutes earlier in the same continuous session.

The stored fields are `price5_pct` and `price15_pct` in percentage points. At
13:05, neither window may reach back into the morning session. Trigger/breakout
storage is reserved, but DATA-V2-01 defines no proprietary threshold.

## 8. Signal contract

Canonical states and labels are:

| State | Vietnamese label |
|---|---|
| `NORMAL` | Bình thường |
| `FLOW_APPEARING` | Dòng tiền đang xuất hiện |
| `FLOW_PRICE_CONFIRMED` | Dòng tiền & giá đã xác nhận |
| `MOMENTUM_MAINTAINED` | Xu hướng đang được duy trì |
| `MOMENTUM_WEAKENING` | Động lượng đang suy yếu |
| `SELLING_PRESSURE` | Áp lực bán đang tăng |

`signal_level` is an ordinal value from 0 through 4. It is not the old V1
0/4-to-4/4 vote count. The browser must not reconstruct signal state, and public
payloads must not expose thresholds, weights, private reason trees, or scoring
recipes.

Every meaningful state transition creates an append-only `signal_events` row.
`event_id` is a canonical lowercase UUID4 text primary key. A unique semantic key
over `symbol`, `detected_at`, `signal_state`, `engine_version`, and
`config_version` protects retry idempotency.

`engine_version` is SemVer, for example `2.0.0`. `config_version` is an immutable
opaque identifier, for example `cfg-20260918-001`. `engine_meta` may store an
internal SHA-256 configuration fingerprint. Events and public APIs never store or
expose proprietary threshold values.

The Signal Engine writes the immutable event and its private 1:1
`signal_event_features` snapshot at transition time. A future separate,
idempotent `signal_outcome_worker` enriches only the reserved close/max/min and
30m/EOD/T+1/T+3 outcome fields; it never creates a second signal event or rewrites
the detection facts. The private feature table is not part of the normal public
frontend API.

Golden Board V2 is a query/view/API over `signal_events` plus outcome fields. It is
not a separate calculation table. Existing V1 Golden Board data remains untouched.

## 9. Feed health and metric quality

Market session, feed health, and metric quality are separate dimensions.

`feed_status`:

- `LIVE`: expected feed is connected and timely.
- `STALE`: feed is expected but freshness exceeded the configured tolerance.
- `DISCONNECTED`: the provider connection is unavailable.
- `EXPECTED_IDLE`: no live events are expected for the current session state.

Proposed configurable V2 defaults use collector/global accepted market-event age,
not the last trade of one symbol:

- `LIVE`: feed expected and global accepted-event age is at most 15 seconds.
- `STALE`: feed expected and age is greater than 15 seconds.
- `DISCONNECTED`: known WebSocket disconnect, or age greater than 60 seconds while
  feed is expected.
- `EXPECTED_IDLE`: feed is not expected because of lunch, closed/weekend, or a
  known holiday.

One illiquid symbol not trading is never sufficient evidence of global feed
failure. The current legacy 180-second setting remains untouched in DATA-V2-01.

`quality_status`:

- `TRUSTED`
- `DEGRADED`
- `UNAVAILABLE`

Quality is evaluated by domain: quote, volume, price-window, trend, session, and
feed. A missing MA200 remains `NULL`; it does not become zero. Partial-baseline
volume is calculable but not volume-trusted. `metrics_trusted` means that every
mandatory input required for the particular evaluated CCC signal is trusted; it
does not mean every optional display metric exists. Minute-level internals may
retain detailed reasons such as `PARTIAL`, `GAP`, `VOLUME_REGRESSION`,
`MISSING_TOTAL_VOLUME`, `INVALID_OHLC`, and `UNKNOWN_MARKET`; these do not replace
the high-level quality enum.

## 10. Bars and index contract

`daily_bars` is canonical long-term SSI/VPS daily history: date, symbol, exchange,
OHLC, volume, optional value, source, quality, and finalized timestamp. Only
completed valid sessions feed MA calculations.

`bars_5m_archive` is derived from trusted canonical 1-minute data. It stores symbol,
exchange, date, local bar time, OHLC, volume, optional value, quality, source, and
creation timestamp. It is not derived from browser data.

`market_index_current` is generic by `index_code`, initially targeting `VNINDEX`,
`VN30`, `HNXINDEX`, and `UPCOMINDEX` where SSI supports them. Missing values are
nullable and accompanied by feed/quality status. No old market-data fallback is
connected by this contract.

## 11. Retention contract

| Data | Policy | Owner of future cleanup |
|---|---|---|
| Raw SSI messages | transient; no long-term archive | ingest/recovery process |
| Current quote/state/index | overwrite/current-state semantics | writer |
| Canonical 1-minute bars | 15 recent trading sessions | future retention job |
| Canonical 5-minute archive | approximately two years | future retention job |
| Daily OHLCV | long-term | archival policy |
| Volume baseline | rolling target of 10 completed sessions | baseline rebuild |
| Signal events and private feature snapshots | long-term | archival policy |
| Operational logs | configurable 30–90 days | operations/log rotation |

DATA-V2-01 performs no deletion and installs no retention scheduler.

## 12. Serving projections

The future Scanner reads `stock_state_current`; it does not calculate technical
metrics in the browser. Its default projection supports:

`symbol`, `exchange`, `last_price`, `change_pct`, `total_volume`, `ma10`, `ma200`,
`distance_ma10_pct`, `distance_ma200_pct`, `day_rvol`, `rvol30`,
`baseline_sessions_used`, `baseline_target_sessions`, `signal_state`,
`signal_level`, `signal_at`, `metrics_trusted`, and `updated_at`.

Future filters: exchange, state, level, change range, DayRVOL/RVOL30 range, volume
range, MA-distance range, above-MA flags, and signal time. Future sorts: signal
time/level, change, DayRVOL, RVOL30, volume, MA distances, and symbol.

`Price5`, `Price15`, `RVOL15`, breakout context, and internal reasons are not
default Scanner UI fields.

Stock Detail may read a richer entitled projection. Golden Board reads event
history. Business entitlement remains a Supabase responsibility, while protected
technical values are served by the VPS only after the server verifies entitlement.

## 13. Compatibility and staged adoption

The current V1 website, Supabase market tables, GitHub Actions, and Golden Board V1
remain in production during shadow build-out. This contract authorizes neither a
cutover nor a migration. SSI history may progressively replace temporary legacy
seed data, but providers must never be mixed silently in an active volume baseline.
