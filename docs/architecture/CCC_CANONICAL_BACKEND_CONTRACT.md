# CCC Canonical Backend Contract

> **Status:** Production checkpoint as of 2026-09-27  
> **Repository:** `manhcang2026/vnstock-market-scanner`  
> **Backend branch:** `fix/ssi-ato-realtime-boundary`  
> **Production source commit:** `b513b891720003d0ed2162794d0b926c86cc0b71`  
> **Purpose:** This is the single handoff document for frontend/backend integration. Frontend work should use this contract instead of inferring behavior from legacy databases or old V2 code.

---

## 1. Reading rule / source of truth

This document describes the **current canonical architecture and frontend-facing data contract**.

Source-of-truth order:

1. Canonical storage schemas and runtime code.
2. `services/ssi_realtime_shadow/config/ccc_signal_v2_beta_config.yaml` for signal thresholds/state definitions.
3. This document for architecture, frontend field mapping, rollout state, and deprecated components.

If code/schema changes, this document must be updated in the same backend change before frontend integration is considered complete.

**Frontend MUST NOT reconstruct signal rules or thresholds.** The backend owns signal classification. Frontend displays canonical metrics, state, reasons, quality, and versions.

---

## 2. Current production checkpoint

Production collector is on the validated backend line through:

- `74f65b3` — harden HOSE ATO realtime lifecycle.
- `9bf697b` — port signals to canonical engine.
- `ecba55e` — stabilize canonical signal transitions.
- `b513b89` — add SELLING_PRESSURE alert episode policy.

Current runtime flags:

```text
CANONICAL_ENGINE_ENABLED=true
CANONICAL_SIGNAL_ENABLED=true
VOLUME_ENGINE_ENABLED=false
LIVE_STATE_ENABLED=false
```

Current operational state:

- canonical engine initialized successfully;
- canonical signal projector initialized successfully;
- `canonical_signal_errors=0` at enable time;
- `current_state` rebuilt for 2026-09-28 with 800 symbols and 0 rebuild failures;
- signal tables are expected to be empty before the first live projected market minute of 2026-09-28;
- legacy `ccc-ssi-daily-finalize.timer` is installed but **disabled/inactive**;
- `ccc-chart-api` and `ccc-live-ws` are currently exited and were already exited before the signal production enablement.

**Important:** 2026-09-28 is the first intended full live-session validation day for the canonical signal runtime.

---

## 3. Canonical architecture

The intended production data flow is:

```text
SSI FastConnect / SSI REST
          |
          v
  raw/hot collector evidence
      ssi_shadow.db
          |
          v
Canonical yearly market store
  ccc_market_2025.db
  ccc_market_2026.db
          |
          v
Canonical calculation engine
      ccc_engine.db
          |
          +--> current_state
          +--> signal_state_current
          +--> signal_events
          |
          v
Canonical API layer
          |
          v
Frontend / scanner / stock detail / future notifications
```

Core principle:

```text
STORE FIRST -> CALCULATE SECOND -> QUALITY LAST
```

Rules:

- SSI is the canonical market-data provider.
- Missing data is `NULL`, never fabricated and never silently converted to zero.
- A missing minute and a zero-trade minute are not the same fact.
- REST reconciliation may repair missing historical evidence.
- Daily OHLC authority is SSI DailyOhlc.
- Canonical market state remains shared for all users.
- VIP/user personalization is an overlay only and must not modify canonical market state.

---

## 4. Database contract

### 4.1 KEEP — active/canonical

#### `ssi_shadow.db`

Role: hot/raw SSI collector evidence.

Current uses:

- collector write path;
- hot latest quotes/minute evidence;
- live WebSocket source if/when `live-ws` is enabled;
- may remain useful as transport/hot evidence even after legacy cleanup.

Do **not** treat it as the long-term canonical historical database.

#### `ccc_market_2025.db`

Role: canonical market shard for 2025.

Current important content:

- `daily_bars`: 166,736 rows, 2025-01-02 through 2025-12-31.

Current minute history for 2025 is not the frontend intraday source in this checkpoint.

Used by canonical engine for long technical history such as MA10/MA200.

#### `ccc_market_2026.db`

Role: canonical market shard for 2026.

Audited checkpoint before the 2026-09-28 session:

- `minute_bars`: 7,610,490 rows, 2026-01-05 through 2026-09-25;
- `daily_bars`: 118,267 rows, 2026-01-05 through 2026-09-25;
- `auction_sessions`: 2,264 rows, 2026-09-22 through 2026-09-25;
- `data_gaps`: explicit missing-data evidence.

Primary canonical tables:

- `minute_bars`
- `daily_bars`
- `latest_quotes`
- `auction_sessions`
- `data_gaps`
- `rest_fetch_status`
- `rest_session_status`
- `schema_meta`

#### `ccc_engine.db`

Role: canonical calculated state.

Primary tables:

- `technical_baseline`
- `volume_baseline_curve`
- `current_state`
- `signal_state_current`
- `signal_events`
- `schema_meta`

Schema version at production signal enablement: **3**.

2026-09-28 pre-session checkpoint:

- technical baseline: 800 symbols;
- volume baseline curve: 197,531 rows / 800 symbols;
- current state: 800 symbols;
- rebuild failures: 0.

### 4.2 LEGACY — archive/delete-later candidates

These databases are **not canonical** and frontend must not build new dependencies on them.

#### `ssi_history_2026.db`

Status: **ARCHIVE CANDIDATE -> DELETE-LATER**

Reasons:

- legacy historical minute store;
- stopped being current around 2026-09-21;
- canonical `ccc_market_2026.db` contains the replacement history and is newer/more complete in the late-September transition period;
- still referenced by legacy chart/EOD code, so it cannot be removed until those dependencies are ported.

#### `ccc_v2_baseline.db`

Status: **ARCHIVE CANDIDATE -> DELETE-LATER**

Reasons:

- V2 baseline store;
- `VOLUME_ENGINE_ENABLED=false`;
- last audited metadata: `as_of_date=2026-09-23`;
- canonical baseline now lives in `ccc_engine.db.volume_baseline_curve`;
- still referenced by the legacy EOD wrapper/settings.

#### `ccc_market_v2.db`

Status: **ARCHIVE CANDIDATE -> DELETE-LATER**

Reasons:

- old V2 current state and signal architecture;
- `stock_state_current` is stale relative to canonical runtime;
- old `signal_events` is empty;
- all legacy `daily_bars` keys are covered by canonical 2025/2026 daily bars;
- canonical has additional daily rows not present in V2.

One migration decision remains before deletion:

- `auction_session_history` contains 90 older rows (2026-08-25 through 2026-09-17) that predate the current canonical auction history start.
- Those rows must either be intentionally imported or explicitly retired before the DB is deleted.

---

## 5. Canonical market fields

### 5.1 `ccc_market_2026.minute_bars`

Canonical key:

```text
(symbol, trading_date, minute)
```

Important fields:

```text
symbol
trading_date
minute
exchange
open
high
low
close
volume
value
provider_total_volume
provider_session
provider_time
first_event_at
last_event_at
source
quality_status
is_finalized
event_count
first_price_at
last_price_at
updated_at
```

Frontend must not assume every minute exists.

### 5.2 `daily_bars`

Important fields:

```text
symbol
trading_date
exchange
open
high
low
close
volume
value
source
quality_status
updated_at
```

Daily OHLC is the authority for daily technical history.

---

## 6. Canonical calculated-state contract

### 6.1 `ccc_engine.current_state`

One current row per symbol.

Frontend-relevant fields:

```text
symbol
exchange
trading_date
minute
last_price
cumulative_volume

day_rvol
rvol15
rvol30

price5_pct
price15_pct

ma10
ma200
distance_ma10_pct
distance_ma200_pct

baseline_sessions_used
day_rvol_sessions_used
rvol15_sessions_used
rvol30_sessions_used

quality_status
reason_codes_json
updated_at
```

Frontend rules:

- display `NULL` metrics as unavailable (`—`), never as zero;
- do not locally recompute RVOL or MA;
- do not infer trust from MA availability;
- MA10/MA200 are context metrics, not the strong-signal trust gate;
- baseline coverage may legitimately differ by metric/symbol.

---

## 7. RVOL / technical rules

Canonical baseline target:

```text
target sessions  = 10
minimum accepted = 8
```

Strong continuous signal behavior:

- 10/9/8 usable sessions may emit a strong signal;
- 7 or fewer may not emit strong signal;
- degraded data may still produce `NORMAL` or `WATCHING`;
- missing is `NULL`, not zero.

Continuous windows:

- RVOL15 does not cross lunch;
- RVOL30 does not cross lunch;
- Price5 does not cross lunch;
- Price15 does not cross lunch.

Price state may carry forward through sparse no-trade minutes only within the same valid continuous session and only when missing-data evidence does not invalidate the carry.

---

## 8. Canonical signal contract

Signal config source:

```text
services/ssi_realtime_shadow/config/ccc_signal_v2_beta_config.yaml
```

Current versions:

```text
signal contract = ccc-state-v1
engine_version  = 2.0.2-beta
config_version  = cfg-20260922-beta-003
timezone        = Asia/Ho_Chi_Minh
```

### 8.1 States exposed to frontend

| State | Level | Direction | Meaning |
|---|---:|---|---|
| `NORMAL` | 0 | NEUTRAL | Chưa ghi nhận tín hiệu nổi bật |
| `WATCHING` | 1 | NEUTRAL | Khối lượng tăng nhưng giá chưa xác nhận |
| `FLOW_APPEARING` | 2 | BULLISH | Dòng tiền bắt đầu xuất hiện |
| `FLOW_PRICE_CONFIRMED` | 3 | BULLISH | Dòng tiền và giá cùng xác nhận |
| `MOMENTUM_MAINTAINED` | 4 | BULLISH | Động lượng đang được duy trì |
| `MOMENTUM_WEAKENING` | 2 | NEUTRAL | Động lượng đang suy yếu |
| `SELLING_PRESSURE` | 3 | BEARISH | Khối lượng mạnh đi cùng áp lực giảm giá |

Evaluation priority:

```text
SELLING_PRESSURE
MOMENTUM_WEAKENING
MOMENTUM_MAINTAINED
FLOW_PRICE_CONFIRMED
FLOW_APPEARING
WATCHING
NORMAL
```

### 8.2 Current transition hardening

The positive path is intentionally constrained:

```text
FLOW_APPEARING
    -> FLOW_PRICE_CONFIRMED
    -> MOMENTUM_MAINTAINED
```

`FLOW_APPEARING -> MOMENTUM_MAINTAINED` is not allowed.

`MOMENTUM_WEAKENING` may persist while weakening conditions remain true; it is no longer forced to disappear after one minute.

Direct `NORMAL/WATCHING -> FLOW_PRICE_CONFIRMED` remains valid if the stronger confirmed thresholds are already satisfied.

---

## 9. `signal_state_current`

One canonical signal-state row per symbol for the current trading date.

Frontend-relevant fields:

```text
symbol
exchange
trading_date
minute
session_type

signal_state
signal_level
signal_direction
reason_codes_json
signal_summary_vi

previous_signal_state
state_changed_at
signal_at

metrics_trusted
baseline_sessions_used

engine_version
config_version
updated_at
```

Frontend should use these values directly.

**Do not duplicate the signal threshold logic in JavaScript.**

---

## 10. `signal_events`

Append-only audit trail of canonical signal transitions.

Important fields:

```text
id
symbol
exchange
trading_date
minute
session_type
previous_signal_state
signal_state
signal_level
signal_direction
reason_codes_json
engine_version
config_version
detected_at
```

Behavior:

- first non-`NORMAL` state may create an event;
- unchanged state does not create duplicate transition events;
- canonical signal events are audit evidence, not automatically a user notification;
- notification policy is a separate layer.

---

## 11. Alert/notification policy

Telegram/email delivery is **not yet wired to production**.

Current implemented policy module:

```text
app/signal_alert_policy.py
```

Current implemented beta policy covers `SELLING_PRESSURE` notification episode grouping only.

Rule:

- first daily SELLING_PRESSURE is alert-eligible;
- SELLING -> WATCHING for 1-2 projected continuous minutes -> SELLING is treated as the same notification episode;
- 3+ projected WATCHING minutes re-arm;
- NORMAL or FLOW/MOMENTUM states immediately re-arm;
- lunch, auction, CLOSED and POST_TRADING wall-clock time do not manufacture recovery minutes;
- canonical `signal_state_current` and `signal_events` remain unchanged.

This does **not** mean SELLING_PRESSURE is the only future notification type.

Future alert policy must cover all meaningful states separately. `NORMAL` is generally not a notification. `WATCHING` may be optional/user-configurable. Strong positive, weakening, and selling states can each have independent notification policy.

---

## 12. Auction scope

ATO ingestion was hardened in commit `74f65b3`.

Current ATO storage contract:

- HOSE only for canonical ATO bucket;
- provider session must be `ATO`;
- official market classification must be `OPEN_AUCTION`;
- volume is monotonic high-water evidence;
- auction price remains nullable;
- unknown start/end volume remains `NULL`;
- finalized ATO bucket is immutable;
- transition event after the official auction may finalize the bucket without contaminating ATO values.

**Current canonical signal projector skips both `OPEN_AUCTION` and `CLOSE_AUCTION`.**

Therefore frontend must **not** assume canonical auction signal states are currently emitted, even though the beta config still contains auction threshold definitions for future work.

ATC signal work is not part of the current production signal port.

---

## 13. Data quality contract

Frontend must preserve backend uncertainty.

Never convert:

```text
NULL -> 0
missing -> zero volume
missing price -> previous price across invalid boundaries
FAILED/PARTIAL -> trusted
```

Relevant quality concepts:

- `quality_status`
- `reason_codes_json`
- `metrics_trusted`
- per-metric baseline session counts
- `data_gaps`

Strong signals require trusted usable continuous metrics.

Missing MA10/MA200 alone does not make the signal metrics untrusted.

---

## 14. Frontend integration rules

### Mandatory

1. Frontend consumes backend APIs, never SQLite files directly.
2. Frontend uses canonical metric/state names from this document.
3. Frontend displays unavailable values as `—`.
4. Frontend does not recreate signal thresholds.
5. Frontend does not silently fall back to Supabase for chart/live market data.
6. Supabase remains appropriate for Auth, Watchlist, Package/VIP, metadata, Fundamental/BCTC unless separately migrated.
7. Guest/basic chart access remains a product requirement; advanced/watchlist/VIP gating belongs above the canonical market state.
8. Personalization must be an overlay; it must not overwrite shared canonical state.

### Existing HTTP route surface

The current chart API code exposes route families:

```text
/health
/v1/quote/{symbol}
/v1/access/{symbol}
/v1/stock-detail/{symbol}
/v1/ccc/{symbol}
/v1/radar
/v1/scanner
/v1/chart/{symbol}
```

Frontend dev proxy currently maps `/api/v2/*` to backend `/v1/*`, while `/api/v2/live` is the WebSocket proxy.

### Critical migration warning

The current chart API implementation still contains legacy storage defaults:

```text
history  -> ssi_history_2026.db
realtime -> ssi_shadow.db
state    -> ccc_market_v2.db
```

Therefore **new frontend work must not deepen dependency on the legacy response semantics**.

Planned task `CHART-API-CANONICAL-01` must port the API implementation to canonical sources:

```text
ccc_market_2025.db
ccc_market_2026.db
ccc_engine.db
+ ssi_shadow.db only where hot transport evidence is intentionally required
```

Frontend may build UI against the canonical field contract now, but final backend binding must be validated after that port.

---

## 15. Legacy retirement plan

The backend is not considered fully cleaned until the following sequence completes:

```text
SIGNAL-LIVE-AUDIT-01
        |
        v
CANONICAL-EOD-01
        |
        v
LEGACY-RETIRE-01
        |
        v
CHART-API-CANONICAL-01
        |
        v
DB-ARCHIVE-01
        |
        v
DB-CLEANUP-01 / DELETE-LATER
```

Legacy runtime/config targeted for retirement includes:

- `VOLUME_ENGINE_ENABLED`
- `LIVE_STATE_ENABLED`
- `VOLUME_BASELINE_PATH`
- `MARKET_V2_DATABASE_PATH`
- `SSI_HISTORY_PATH`
- old V2 volume engine/baseline runtime;
- old V2 stock-state build runtime;
- legacy EOD wrapper/timer once canonical EOD replaces it;
- tests that exist only for removed production architecture, after replacement coverage exists.

Do not delete legacy code/data before its canonical replacement is proven.

---

## 16. EOD status

The installed legacy timer:

```text
ccc-ssi-daily-finalize.timer
```

is currently:

```text
disabled
inactive
```

Its old wrapper still references legacy V2/history/baseline databases, so it must not be re-enabled as-is.

A canonical EOD task is still required to provide a single post-close path for:

1. REST IntradayOhlc reconciliation;
2. SSI DailyOhlc canonical daily finalization;
3. explicit missing/gap evidence;
4. next-session baseline rebuild in `ccc_engine.db`;
5. preparation of next-session `current_state`.

Until `CANONICAL-EOD-01` is complete, do not assume EOD automation is finished.

---

## 17. Production validation gates still pending

As of this document version:

- [x] DATA-CLOSE-01
- [x] ENGINE-BASELINE-01
- [x] RUNTIME-ENABLE-01
- [x] ACC-PORT-01
- [x] SIGNAL-PORT-01
- [x] SIGNAL-STABILITY-01A
- [x] SIGNAL-STABILITY-01B
- [x] SIGNAL-VALIDATION-02 replay
- [x] SIGNAL-PROD-PREP-01
- [x] SIGNAL-PROD-ENABLE-01
- [ ] SIGNAL-LIVE-AUDIT-01 — first full live session, 2026-09-28
- [ ] CANONICAL-EOD-01
- [ ] LEGACY-RETIRE-01
- [ ] CHART-API-CANONICAL-01
- [ ] DB-ARCHIVE-01 / DB-CLEANUP-01

---

## 18. Backend-ready gate for V3 frontend production binding

Backend is considered fully locked for V3 production integration when all are true:

```text
one full live trading day clean
        +
canonical signal audit clean
        +
canonical EOD clean
        +
chart API reads canonical stores
        +
legacy runtime removed
        +
legacy DBs archived/removed
        +
this contract updated
        =
BACKEND READY FOR V3 FRONTEND
```

Frontend design/development can continue before the gate, but production data binding must follow the canonical contract above and must not create new legacy dependencies.

---

## 19. Quick reference for frontend developers / Codex

When starting frontend work, read this section first.

**Use:**

```text
Market history/current evidence:
  ccc_market_2025.db
  ccc_market_2026.db

Calculated current metrics:
  ccc_engine.current_state

Canonical signal state:
  ccc_engine.signal_state_current

Canonical transition history:
  ccc_engine.signal_events
```

**Never build new frontend logic around:**

```text
ccc_market_v2.db
ccc_v2_baseline.db
ssi_history_2026.db
legacy stock_state_current
legacy signal_events
```

**Canonical UI metrics:**

```text
last_price
cumulative_volume
day_rvol
rvol15
rvol30
price5_pct
price15_pct
ma10
ma200
distance_ma10_pct
distance_ma200_pct
quality_status
reason_codes_json
```

**Canonical UI signal fields:**

```text
signal_state
signal_level
signal_direction
signal_summary_vi
previous_signal_state
state_changed_at
signal_at
metrics_trusted
baseline_sessions_used
engine_version
config_version
```

**Golden rule:**

> The browser displays canonical facts. It does not recreate market calculations or signal classification.

---

## 20. Maintenance rule

Any backend change that alters one of the following must update this file:

- canonical DB names or tables;
- frontend-exposed field names;
- signal states or versions;
- quality/trust semantics;
- API route/response contract;
- EOD ownership;
- legacy retirement state.

This file is intentionally stable-path documentation so frontend/Codex can always start from:

```text
docs/architecture/CCC_CANONICAL_BACKEND_CONTRACT.md
```
