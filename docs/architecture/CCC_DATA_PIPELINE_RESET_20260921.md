# CCC Data Pipeline Reset — Canonical Plan

**Date:** 2026-09-21  
**Status:** ACTIVE / SOURCE OF TRUTH  
**Applies from:** trading session 2026-09-22

> This document is the canonical operating plan for CCC market data after the 2026-09-21 audit.
> If an older document, prompt, branch note, or implementation assumption conflicts with this document, this document wins unless explicitly superseded later.

---

## 1. Non-negotiable rules

- Do not create another product/version name.
- Freeze the current frontend/API contract. Do not rename `/api/v2/*` routes or existing state fields.
- SSI is the only canonical market-data provider.
- Missing data remains missing/NULL; missing is never silently converted to zero.
- Supabase remains authoritative for Auth, users/profiles, Watchlist, packages/subscriptions, VIP Day, billing state, stock metadata, and financial/BCTC data.
- Supabase legacy market tables may be used for comparison only, never as canonical VPS market input.
- Keep the current signal classifier/config/state contract except for the baseline-tolerance policy explicitly defined in this document.

---

## 2. Canonical ownership

### During the trading session

```text
SSI FastConnect
    ↓
Realtime quote / cumulative volume / provider session
    ↓
Hot realtime state
    ↓
stock_state_current
    ↓
/api/v2/*
    ↓
Current frontend
```

FastConnect owns live behavior:
- current quote
- current volume
- chart/live state
- Price5 / Price15
- intraday signal state
- ATO/ATC provider-session evidence

### After the trading session

```text
SSI REST IntradayOhlc + DailyOhlc
    ↓
Canonical historical databases
    ↓
MA / Day RVOL / RVOL15 / RVOL30
    ↓
Historical baseline
    ↓
Baseline for next trading session
```

REST is the canonical historical source for ordinary minute and daily history.

### Auctions

```text
SSI FastConnect provider sessions ATO / ATC
    ↓
Auction-session history
    ↓
ATO / ATC metrics
```

ATO/ATC must not be reconstructed from generic minute OHLC where provider-session proof does not exist.

---

## 3. Baseline selection policy — target 10, tolerate up to 2 breaks

### 3.1 Terminology

The baseline uses the **nearest valid historical trading sessions**, not “sessions that produced a trading signal”.

A valid session means the required SSI historical data for that metric can be proven safe enough for baseline use.

Do **not** select sessions based on whether CCC produced a bullish/bearish signal. That would introduce selection bias.

### 3.2 Preferred baseline

Target:

```text
10 valid historical trading sessions
```

The system scans backward from the session immediately before the target session and collects valid sessions.

It may skip unavailable/unproven sessions, but may cross at most:

```text
2 separate missing-data break blocks
```

A break block is one contiguous run of unavailable/unproven trading sessions.

Example:

```text
Target session: 2026-09-22

21/09  VALID
18/09  VALID
17/09  VALID
16/09  MISSING      <- break block #1
15/09  VALID
14/09  VALID
11/09  VALID
10/09  VALID
09/09  MISSING      <- break block #2
08/09  VALID
07/09  VALID
04/09  VALID
```

The engine may skip 16/09 and 09/09 and continue backward to collect 10 valid sessions.

If another separate missing-data block is encountered before enough valid sessions are collected:

```text
break block #3
```

the baseline search fails the gap-tolerance rule.

### 3.3 Why allow two breaks

This is intentional operational tolerance for cases such as:
- temporary SSI outage
- rate-limit/retrieval failure
- one isolated historical session that cannot be proven
- local collection interruption

The goal is to avoid making the entire signal system unusable because of one or two isolated data failures.

### 3.4 Safety bound

The baseline builder must not search arbitrarily far back.

Implementation should use a bounded historical search window and report:
- valid sessions collected
- skipped sessions
- number of break blocks
- first/last session actually used

No silent unlimited backfill is allowed.

---

## 4. Baseline coverage policy — 10/10 preferred, 8/10 minimum accepted

The target remains:

```text
10/10 = preferred / full baseline
```

But the signal system may operate with:

```text
9/10 = accepted
8/10 = accepted minimum
<8/10 = insufficient
```

This applies to ordinary historical volume baselines:
- Day RVOL
- RVOL15
- RVOL30

Conditions for 8/10 or 9/10 acceptance:

- current-session data is otherwise clean enough for signal use;
- no more than 2 missing-data break blocks were crossed;
- no fabricated zero volume is used;
- no unsupported provider mixing is used;
- baseline provenance remains SSI-only.

### Coverage tiers

```text
10 sessions → FULL
9 sessions  → ACCEPTABLE
8 sessions  → ACCEPTABLE_MINIMUM
0–7         → INSUFFICIENT
```

The existing frontend contract remains unchanged.

Existing fields continue to expose:
- `baseline_sessions_used`
- `baseline_target_sessions`
- `baseline_coverage_pct`
- quality/trust/reason information

No new frontend field is required solely for this policy.

---

## 5. Signal gating under the new tolerance policy

The previous rule requiring exactly 10/10 for all strong states is superseded.

For ordinary continuous-session signals, strong states may be evaluated when:

```text
baseline_sessions_used >= 8
AND
break_blocks <= 2
AND
current metric integrity is acceptable
```

This allows these states to remain eligible at 8/10 or 9/10:

```text
FLOW_APPEARING
FLOW_PRICE_CONFIRMED
MOMENTUM_MAINTAINED
SELLING_PRESSURE
```

10/10 remains preferred and should carry the strongest baseline confidence.

8/10 and 9/10 are accepted operationally because isolated SSI/data outages should not disable the scanner.

However:

```text
baseline_sessions_used < 8
```

must block strong positive/negative flow conclusions that depend on historical RVOL comparison.

`WATCHING` and `NORMAL` remain available under weaker coverage.

The current state machine structure remains:

```text
NORMAL
→ WATCHING
→ FLOW_APPEARING
→ FLOW_PRICE_CONFIRMED
→ MOMENTUM_MAINTAINED

and:
MOMENTUM_WEAKENING
SELLING_PRESSURE
```

Only the baseline eligibility threshold changes; the state definitions, evaluation priority, and configured signal thresholds remain unchanged unless separately approved.

---

## 6. Preserve vs reset

### Preserve

- current frontend
- current `/api/v2/*` contracts
- current field names such as `day_rvol`, `rvol15`, `rvol30`, `ma10`, `ma200`, ATO/ATC fields, coverage, signal, quality and trust fields
- Supabase Auth/Watchlist/Package/VIP
- Supabase metadata and financial data
- trustworthy SSI DailyOhlc history
- trustworthy SSI REST minute history
- MA10/MA200 logic
- current signal config / classifier / state contract, except the approved baseline-tolerance policy

### Reset / rebuild

- hot realtime database for the new epoch
- broken/ambiguous stream-derived canonical minute history
- generated RVOL baseline state
- current stock state
- old signal state/events/features when dependent on unreliable history
- old auction baseline/history that lacks strong provider-session proof
- failed/faulty finalize journal entries

**Clean operational epoch:** `2026-09-22`.

---

## 7. Historical backfill priorities

### P0 — required before 2026-09-22 open

Backfill/reconcile enough recent SSI REST IntradayOhlc history to build the target 10-session baseline.

The builder may skip up to 2 missing-data break blocks according to Section 3.

Purpose:
- Day RVOL
- RVOL15
- RVOL30
- recent historical volume baseline

This baseline should be precomputed on 2026-09-21, before the next session starts.

Target:
- 10 valid sessions where possible
- accept 9
- accept minimum 8
- below 8 remains insufficient

### P1 — Daily history

Download/reconcile SSI DailyOhlc from `2025-01-01` through `2026-09-21`.

Purpose:
- MA10
- MA200
- daily OHLCV history

MA10 and MA200 should be computable before the 2026-09-22 session once the required trusted DailyOhlc history exists.

### P2 — Full 2025 minute history

Create:

```text
ssi_history_2025.db
```

Download full-year SSI IntradayOhlc resolution=1.

Requirements:
- checkpoint/resume
- bounded batching
- adaptive throttling/cooldown
- safe HTTP 429 handling
- pause/reduce during market hours if needed
- never restart the full job after interruption

Full 2025 minute backfill is not required before 2026-09-22 opens.

### P3 — 2026 repair

Repair missing SSI REST minute history through 2026-09-21 using targeted repair only, not full-universe retry storms.

---

## 8. Baseline policy by metric

### Precompute before 2026-09-22

From trusted SSI history:

- MA10
- MA200
- Day RVOL baseline
- RVOL15 baseline
- RVOL30 baseline
- cumulative intraday baseline
- baseline coverage metadata

If P0/P1 succeed, ordinary RVOL and MA metrics can be ready before market open on 2026-09-22.

### Reset and accumulate from 2026-09-22

- ATO baseline
- ATO RVOL10
- ATC baseline
- ATC RVOL10
- auction-specific historical metrics requiring explicit provider-session proof

Thus `2026-09-22` is auction session `1/10`.

The 8/10 tolerance in Sections 4–5 applies to ordinary historical RVOL baselines first.

Auction baseline tolerance must be reviewed separately after enough clean provider-session data is accumulated. Do not silently apply the same relaxation to ATO/ATC without explicit approval.

---

## 9. Supabase legacy RVOL policy

Supabase legacy tables such as:

- `daily_history`
- `intraday_snapshots`
- `intraday_volume_baseline_10`
- legacy scanner RVOL fields

are comparison/audit references only.

They may include KBS/VCI and older 5-minute assumptions.

Rules:
- compare if useful
- do not import as canonical SSI baseline
- do not use as fallback when SSI canonical data is missing

---

## 10. Collector requirements for 2026-09-22

- Start before market open, preferably around 08:30–08:45 VN time.
- Preserve sufficient provider-time/order evidence.
- Lower cumulative-volume events must not lower retained high watermark.
- Stale/regressive events must not silently corrupt minute OHLC.
- Startup partial remains explicit.
- Morning partial must not automatically poison a valid ATC bucket.
- Auction quality must be based on auction-local evidence plus only continuity failures that materially affect the auction anchor.
- Post-trading volume must never be included in ATC-specific metrics.

---

## 11. EOD target model

The old target:

```text
raw FastConnect hot minute rows
→ directly settled/copied as canonical history
```

is superseded.

The target model is:

```text
FastConnect = live/hot
SSI REST IntradayOhlc + DailyOhlc = canonical historical
FastConnect provider session = ATO/ATC evidence
```

EOD must:
- finalize SSI REST historical data safely
- update next-session baselines
- preserve provenance and quality
- fail closed on unresolved data
- never launch an uncontrolled 800-symbol REST storm
- keep automatic targeted repair bounded

---

## 12. Required behavior on 2026-09-22

Expected if P0/P1 complete successfully:

- realtime price
- percent change
- realtime volume
- live chart
- MA10
- MA200
- distance to MA10 / MA200
- Price5
- Price15
- Day RVOL using 8–10 accepted historical sessions
- RVOL15 using 8–10 accepted historical sessions
- RVOL30 using 8–10 accepted historical sessions
- current-day ATO absolute metrics
- current-day ATC absolute metrics

Auction baseline after finalization:
- ATO: `1/10`
- ATC: `1/10`

Ordinary signal strength may operate with 8/10 or 9/10 under the approved tolerance policy.

---

## 13. VPS cleanup policy

Do not keep accumulating ad-hoc backups.

Before cleanup:
- measure filesystem usage
- measure DB sizes
- measure Docker image/build-cache usage

Then remove proven unnecessary items:
- temporary audit TXT/JSON
- temporary Git bundles
- obsolete intermediate DB backups
- obsolete Docker images/build cache
- abandoned broken-history DBs after clean replacement is verified

Do not delete active `.env`, SSI vendor SDK/archive needed for builds, active canonical DBs, or the last rollback image until the new collector passes a live session.

---

## 14. Codex operating rule

Codex does not choose architecture.

For each task:

1. ChatGPT defines architecture and exact scope.
2. Codex implements only that scope.
3. Codex must not switch branch, deploy, broaden scope, or run UI/server unless explicitly asked.
4. ChatGPT reviews the result/diff.
5. User commits/pushes/deploys only after review.

Preferred task sequence:

1. historical loader throttle/resume
2. recent-session baseline proof with 2-break tolerance
3. collector/auction evidence hardening
4. clean DB initialization
5. baseline rebuild
6. production cutover
7. VPS cleanup

---

## 15. Definition of success

The reset is complete when:

- frontend/API contract is unchanged
- FastConnect runs reliably during market hours
- SSI REST owns canonical daily/minute history
- baseline builder targets 10 valid sessions, tolerates at most 2 break blocks, and accepts minimum 8 valid sessions
- MA10/MA200 are reproducible from SSI DailyOhlc
- ordinary Day RVOL/RVOL15/RVOL30 can run from 8–10 accepted historical sessions
- ATO/ATC accumulate cleanly from 2026-09-22
- missing data remains explicit
- no legacy Supabase/KBS/VCI market data is mixed into canonical VPS metrics
- historical backfills are resumable and rate-limit safe
- VPS storage remains within safe headroom
