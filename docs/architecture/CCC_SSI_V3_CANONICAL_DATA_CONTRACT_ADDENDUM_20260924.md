# CCC SSI V3 Canonical Contract — Infrastructure Addendum 24/09/2026

**Status:** APPROVED / LOCKED  
**Applies to:** `CCC_SSI_V3_CANONICAL_DATA_CONTRACT.md`  
**Purpose:** Record the final infrastructure decision after the 23/09/2026 incident review.

This addendum **supersedes any conflicting infrastructure wording** in the canonical contract, especially wording that describes NEW Supabase as the temporary primary market database before a later cutover.

Business/data definitions in the original contract remain unchanged unless explicitly overridden below.

---

## A. Final canonical ownership

```text
SSI = only canonical market-data provider

VPS CCC Engine = canonical processing runtime

VPS storage = canonical market storage
  current transition: SQLite
  long-term target: PostgreSQL on VPS

NEW Supabase ccc-ssi-v2 = remote audit mirror only
```

NEW Supabase is not a planned primary production market database.

---

## B. Supabase mirror behavior

The mirror:

- receives copies of VPS data asynchronously;
- may be delayed;
- may retry/backoff;
- may temporarily stop when quota/network is unavailable;
- must never block, roll back, or stop VPS canonical processing.

The mirror should cover data from **01/09/2026 onward** as capacity allows.

Preferred mirror scope:
- raw/canonical market data;
- calculation outputs;
- signal/state history;
- baseline/audit fields;
- operational health, gaps, finalize/reconciliation logs.

---

## C. Historical vs current-state write semantics

Historical data is append-oriented:

```text
minute bars
daily bars
signal events
ingest/finalize history
data gaps
```

Current state is upsert-oriented:

```text
live_quotes
stock_state_current
current health/status
```

A new trading day does not overwrite prior historical minute/daily rows.

---

## D. Runtime philosophy

Keep strict data truth:
- SSI-only;
- missing is not zero;
- no fabricated bars;
- no silent provider fallback.

Relax unnecessary runtime brittleness:
- transient feed silence should trigger reconnect/recovery and alerting;
- raw ingest must not depend on calculation success;
- Supabase mirror must be fail-open;
- health must detect “process alive but not progressing”;
- Telegram should notify Product Owner of important operational state.

---

## E. 23/09 incident implication

The 23/09 incident does not justify moving the canonical database to Supabase.

The observed failure chain indicates:
1. stale SSI feed before 09:03;
2. intentional watchdog restart;
3. successful reconnect;
4. brief writes through about 09:03:11;
5. subsequent hang while VPS resources remained healthy.

The leading root-cause hypothesis is application/runtime lock-order deadlock/race, not database capacity failure.

Therefore:
- fix/harden runtime orchestration;
- keep VPS as canonical;
- use Supabase to improve visibility/auditability.

---

## F. Replacement text for old infrastructure roadmap

Where the original contract says or implies:

```text
NEW Supabase -> primary temporary PostgreSQL -> later VPS PostgreSQL
```

interpret it from 24/09/2026 onward as:

```text
VPS canonical (SQLite transition)
        |
        +--> NEW Supabase remote audit mirror

then

VPS canonical (PostgreSQL target)
        |
        +--> NEW Supabase optional remote audit mirror
```

The “5 stable sessions then migrate from Supabase to VPS” assumption is retired.

Future stability observation may still be used as a validation gate for **SQLite -> PostgreSQL on VPS**, but not as a Supabase-primary cutover plan.

**END OF ADDENDUM**
