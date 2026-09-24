# CCC SSI V3 — Realtime Ingestion, Recovery & Calculation Rules

**Project:** Chuyện Chợ Chứng (CCC)  
**Decision date:** 24/09/2026  
**Status:** APPROVED / LOCKED  
**Scope:** SSI FastConnect realtime ingestion, 1-minute canonical bars, ATO/ATC capture, REST recovery, calculation isolation, database cleanup, universe expansion.

This document is the operational data-flow rule for CCC V3. If older beta/proof documents conflict with it on ingestion/recovery behavior, this document wins.

---

## 1. Core rule

> **STORE FIRST — CALCULATE SECOND — QUALITY LAST.**  
> **LƯU TRƯỚC — TÍNH SAU — CHẤT LƯỢNG CHỈ GẮN NHÃN.**

SSI is the only canonical market-data provider for V3.

A calculation, baseline, trust rule, signal rule, Supabase mirror, or UI rule must never block or roll back market data that SSI has already delivered and CCC can identify.

Missing data remains missing. Missing is never silently converted to zero.

---

## 2. How SSI realtime works

SSI FastConnect is event-driven WebSocket streaming.

The VPS keeps the connection open. SSI pushes events whenever provider state changes. CCC does **not** depend on one exact provider message arriving exactly at each clock minute.

Example:

```text
09:11:02  event
09:11:17  event
09:11:42  event
09:11:58  event
```

Those events contribute to the canonical **09:11 minute**.

---

## 3. Continuous-session minute rule

For LO / continuous trading:

1. Every usable SSI event updates the working/current-minute canonical state immediately.
2. The minute remains open while its clock minute is active.
3. The default finalization grace is **3 seconds after the minute ends**.
4. Example: minute `09:11` covers `09:11:00..09:11:59` and is normally finalized at about `09:12:03`.
5. Calculation starts only after canonical persistence and must run independently of ingestion.

The 3-second grace is a default operational rule, not a reason to reject later data.

If a valid late/correction event for 09:11 arrives after 09:12:03:

- persist/merge it into the 09:11 historical minute;
- do not move `latest_quote` backwards;
- mark late/correction metadata when useful;
- recalculate affected derived state asynchronously when practical;
- never reject it merely because the minute was already finalized.

---

## 4. Canonical minute content

The 1-minute canonical layer should preserve what can be known without fabrication, including as available:

- symbol;
- exchange;
- trading date;
- minute;
- OHLC;
- minute volume;
- provider cumulative TotalVol / total volume evidence;
- provider session;
- first/last provider event time;
- source;
- missing/gap/partial/correction metadata.

A field may be NULL while other fields remain valid.

Examples:

```text
price available + volume missing  -> store price, volume=NULL
volume available + price missing  -> store volume, price=NULL
both available                     -> store both
known missing minute               -> GAP/MISSING metadata
```

Do not discard an entire event merely because one field is missing.

---

## 5. ATO / ATC are realtime-priority data

Explicit auction evidence is more time-sensitive than ordinary continuous-session minute OHLCV.

When SSI sends `TradingSession=ATO` or `TradingSession=ATC`, persist auction evidence immediately at event level.

Preserve as available:

- symbol;
- exchange;
- trading date;
- exact provider event time;
- provider session ATO/ATC;
- price, nullable;
- cumulative TotalVol, nullable;
- bid/ask fields if present;
- TradingStatus if present;
- source and quality metadata.

Do **not** require `LastPrice > 0` before recording an auction event.

Afterward, build the ATO/ATC summary/bucket from persisted evidence.

If evidence is incomplete, store an incomplete auction result. Do not make the auction disappear.

Why: SSI REST may recover minute OHLCV later, but it cannot be assumed to reproduce the exact realtime provider-session/event sequence for ATO/ATC.

---

## 6. Recoverable vs realtime-only priorities

### Usually recoverable later from SSI REST

- 1-minute OHLCV;
- daily OHLCV;
- MA10 / MA200;
- Day RVOL;
- RVOL15 / RVOL30;
- Price5 / Price15;
- baselines;
- current calculated state;
- signal results.

### Must be prioritized in realtime

- explicit `TradingSession=ATO` / `ATC`;
- auction event sequence;
- event-level cumulative TotalVol evidence;
- event timestamps/ordering;
- realtime bid/ask;
- TradingStatus;
- intra-minute event detail when the product explicitly needs it.

When forced to choose, preserve realtime-only evidence before derived metrics.

---

## 7. REST reconciliation

CCC accepts that realtime can have gaps.

### Lunch reconciliation

After the morning session:

1. identify missing/partial morning minutes;
2. query SSI `IntradayOhlc`;
3. fill or correct what SSI returns;
4. leave unresolved points marked GAP/MISSING.

### End-of-day reconciliation

After market close:

1. reconcile afternoon missing/partial minutes with `IntradayOhlc`;
2. fetch SSI `DailyOhlc`;
3. persist official daily data;
4. refresh/rebuild derived baselines and metrics;
5. record unresolved provider no-data and continue to the next session.

A failed recovery attempt must not invalidate otherwise usable data.

Daily provider volume and the sum of minute volumes may differ. Do not fabricate or scale minute data to force them to match.

---

## 8. Calculation isolation

RVOL, MA, Price5/15, auction metrics and signals read canonical market data and write derived state.

They must not execute inside a transaction whose failure can roll back canonical SSI persistence.

Required direction:

```text
SSI WebSocket
    |
    v
canonical persistence
    |
    +--> commit succeeds
            |
            +--> async calculation/projection
            +--> async Supabase audit mirror
```

If one metric cannot be calculated:

```text
metric = NULL
reason = explicit reason
```

Other independent metrics continue.

---

## 9. Quality / trust semantics

Quality is **description, not permission**.

Examples:

- OK / TRUSTED;
- PARTIAL;
- GAP;
- MISSING_PRICE;
- MISSING_VOLUME;
- VOLUME_REGRESSION;
- REST_FILLED;
- LATE_CORRECTION;
- INSUFFICIENT_HISTORY.

A quality label must not itself prevent canonical storage.

Each metric decides only whether its own required inputs exist.

---

## 10. Baseline philosophy

Target up to 10 usable historical sessions.

Do not let one bad historical session poison future ingestion.

General behavior:

- use good historical sessions;
- skip unusable historical evidence for the metric that needs it;
- record `sessions_used`;
- if product policy requires a minimum coverage, below that minimum set only that metric to NULL with `INSUFFICIENT_HISTORY`;
- continue accumulating new sessions normally.

No baseline rule may stop raw SSI collection.

---

## 11. Stream outage behavior

Provider/network silence is an operational condition, not a reason to destroy the collector.

Required behavior:

- reconnect/recover;
- keep retrying with sensible backoff;
- alert/record downtime;
- resume persistence when SSI returns;
- reconcile missing continuous minutes later by REST.

Do not permanently FATAL the canonical collector solely because SSI was silent for a bounded period.

The external watchdog exists to recover a CCC process that is truly hung/not progressing, not to enforce data completeness.

---

## 12. Universe direction

The product direction is **the full Vietnamese equity market**, not a permanent 800-symbol ceiling.

Target equity venues:

- HOSE;
- HNX;
- UPCOM.

A smaller rollout universe may be used temporarily for operational validation, but code/data contracts must not hard-code 800 as the permanent architecture limit.

Derivatives/non-equity products remain a separate scope unless explicitly approved.

---

## 13. Clean database direction

After cleanup, keep canonical market data logically separate from derived/calculated data.

Transition target:

```text
ccc_market_2026.db
  canonical SSI market history/current market state

ccc_engine.db
  baselines / RVOL / MA / signals / calculated state
```

The exact physical schema may evolve, but the ownership boundary is locked:

- market DB must survive engine bugs;
- engine DB can be rebuilt from canonical market data;
- Supabase remains audit mirror only;
- long-term VPS PostgreSQL should preserve the same logical separation.

Before deleting old/reset/replay/proof databases, first salvage any realtime-only ATO/ATC evidence that cannot be fetched back from REST.

---

## 14. Legacy Supabase scanner compatibility rule

The currently deployed legacy websites remain online and continue to read the OLD Supabase market/scanner tables.

Their repository source folders do **not** need to be restored to `main` merely to keep the deployed sites online.

What must remain operational on `main` is the legacy VNStock scanner path that updates OLD Supabase:

```text
root src/ legacy scanner
        |
        v
GitHub Actions / legacy scanner runtime
        |
        v
OLD Supabase market/scanner tables
        |
        v
currently deployed legacy websites
```

Therefore:

- preserve the root legacy scanner code required for this path;
- preserve its required GitHub workflows and config;
- do not delete/disable it during V3 repo cleanup;
- do not use OLD Supabase market data as a V3 fallback;
- the legacy path remains only for the currently deployed sites until the Product Owner explicitly retires/cuts them over.

`website/` and `website-next/` may remain absent from `main` if their deployed copies are already running and the Product Owner does not require those source folders in the active repository.

---

## 15. Minimum production tests for the new collector

Before the next production session, focus on these core behaviors:

1. price + volume event -> canonical row persists;
2. missing price -> useful remaining fields still persist;
3. missing volume -> useful remaining fields still persist;
4. late/out-of-order historical event -> history updates but latest state does not move backwards;
5. calculation intentionally fails -> canonical market write remains committed;
6. `ATO`/`ATC` event with missing price -> auction evidence still persists;
7. SSI silence/reconnect -> collector survives and resumes.

Broader metric tests are secondary to proving loss-tolerant canonical ingestion.

---

## 16. One-line operating principle

> **SSI gives what it gives. CCC stores what it can identify, recovers what it can later, marks what remains missing, calculates only what available inputs support, and keeps moving.**

**END OF DECISION**
