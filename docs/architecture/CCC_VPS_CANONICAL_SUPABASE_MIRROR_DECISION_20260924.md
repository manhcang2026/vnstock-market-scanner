# CCC Architecture Decision — VPS Canonical + Supabase Audit Mirror

**Project:** Chuyện Chợ Chứng (CCC)  
**Decision date:** 24/09/2026  
**Status:** APPROVED / LOCKED  
**Scope:** Market-data runtime, storage ownership, remote audit mirror, operational monitoring  
**Supersedes:** Any assumption that NEW Supabase `ccc-ssi-v2` will become the primary/canonical CCC market database.

---

## 1. Final decision

CCC will continue to use the **VPS as the primary market-data runtime and long-term infrastructure destination**.

```text
SSI FastConnect + SSI REST
          |
          v
CCC Engine on VPS
  - collector
  - session engine
  - volume/RVOL engine
  - Price5/Price15
  - auction engine
  - MA engine
  - signal engine
  - EOD/baseline workers
          |
          v
VPS canonical storage
  - transition: SQLite
  - long-term: PostgreSQL on VPS
          |
          +--------------------+
          | async / fail-open  |
          v
NEW Supabase ccc-ssi-v2
= remote audit mirror only
```

The NEW Supabase project is **not** the production source of truth for market data.

---

## 2. Storage ownership

### 2.1 VPS

VPS is the canonical owner of market-data processing and storage.

Current transition:

```text
VPS Engine -> SQLite
```

Long-term:

```text
VPS Engine -> PostgreSQL on VPS
```

The move from SQLite to PostgreSQL is storage modernization. It does **not** replace the CCC calculation engines and does not move market processing to Supabase.

### 2.2 OLD Supabase

OLD Supabase continues to own:

- Auth / profiles;
- watchlists;
- plans / subscriptions / VIP / entitlement;
- company / symbol / exchange / industry metadata;
- fundamental / BCTC data.

OLD Supabase market tables are not a fallback source for SSI V3.

### 2.3 NEW Supabase — `ccc-ssi-v2`

The NEW Supabase project is a **remote audit mirror**.

Its purpose is to make CCC data remotely inspectable without requiring the Product Owner to understand SSH, Docker, SQLite/PostgreSQL administration, or VPS internals.

It may be used for:

- remote inspection by ChatGPT/DB tooling;
- troubleshooting a symbol/minute/day;
- comparing raw data and calculated outputs;
- checking signal/state history;
- checking ingest/EOD/data-gap/health records;
- regression and incident audit.

It must never become a runtime dependency of the canonical VPS collector.

---

## 3. Mirror write rule

Mirror writes are **asynchronous, fail-open and best-effort**.

```text
SSI event
   |
   v
VPS canonical processing/storage succeeds
   |
   +--> CCC runtime continues immediately
   |
   +--> enqueue Supabase mirror write
              |
              +--> success -> mirrored
              +--> temporary failure -> retry/backoff
              +--> prolonged failure -> alert
```

Forbidden:

```text
VPS transaction waits for Supabase
Supabase failure rolls back VPS canonical data
Supabase outage stops SSI collection
```

Canonical success is determined by the VPS path, not the mirror.

---

## 4. Mirror coverage and retention

Intended mirror start:

```text
01/09/2026 onward
```

Mirror as much as available capacity allows.

### Raw / canonical market data
- live quotes;
- 1-minute bars;
- daily bars;
- reference prices;
- ATO/ATC sessions/evidence.

### Calculated data
- volume baselines;
- Day RVOL;
- RVOL15;
- RVOL30;
- Price5;
- Price15;
- MA-related state;
- stock_state_current;
- quality/trust/reason context.

### Signals
- signal events;
- state transitions;
- Market Movers/performance records when implemented.

### Operations
- ingest runs;
- data gaps;
- finalize runs;
- reconciliation;
- heartbeat/health snapshots.

Historical/event tables are append-oriented. Current-state tables are upsert-oriented.

```text
minute_bars_1m      -> append by symbol + trading_date + minute
daily_bars          -> append by symbol + trading_date
signal_events       -> append immutable events
live_quotes         -> upsert latest state
stock_state_current -> upsert latest state
```

---

## 5. Supabase capacity rule

The mirror has finite capacity.

If the Supabase database is forced into read-only mode, reads may continue but new `INSERT/UPDATE/DELETE` operations cannot continue. Therefore CCC must never depend on the mirror for production continuity.

Suggested initial warning levels:

```text
~350 MB -> INFO
~400 MB -> WARNING
~450 MB -> CRITICAL
~475 MB -> Product Owner action required
```

These are operational defaults, not permanent business rules.

When capacity becomes tight:

1. prune old mirror-only data; or
2. reduce mirror retention/coverage; or
3. upgrade Supabase capacity.

None of these changes VPS canonical ownership.

---

## 6. Data collection philosophy

CCC should be strict about **truth**, but not unnecessarily fragile about **collection**.

Keep:
- SSI as the only market-data provider;
- missing data remains missing;
- missing is not zero;
- no fabricated/interpolated market data;
- no silent provider mixing.

But runtime should tolerate transient operational issues:
- short feed silence should prefer reconnect/recovery over killing the entire application;
- collection should be isolated from heavy calculation/storage work;
- one calculation failure must not stop raw SSI ingest;
- one mirror failure must not stop VPS;
- quality may degrade explicitly instead of turning every disturbance into a fatal process error.

---

## 7. 23/09/2026 incident conclusion

The 23/09 morning incident is not evidence that VPS storage is fundamentally unsuitable.

Observed:
- before 09:03, the process was alive but had no accepted current-day market events;
- at approximately 09:03, the 180-second stale-feed watchdog intentionally raised an error;
- Docker restarted the collector correctly;
- the collector reconnected to SSI and wrote fresh data briefly;
- data/state then stopped around 09:03:11 while the process remained alive;
- no OOM, disk exhaustion or kernel/storage failure was found.

The leading technical cause of the post-restart hang is a **high-confidence lock-order/race/deadlock risk** between the SSI callback/hot-store transaction and the LiveStateRuntime calculation path. This is not claimed as 100% proven without a thread dump at the moment of the hang.

The incident must be fixed at the runtime/orchestration layer. Moving the canonical database to Supabase would not address this class of failure.

---

## 8. Runtime hardening direction

Before relying on the collector again for production sessions:

- remove lock inversion/deadlock risk;
- keep SSI callback lightweight;
- decouple ingest from calculation with queue/worker boundaries where appropriate;
- reconnect SSI proactively when feed liveness is lost;
- use a watchdog/heartbeat able to detect a process that is alive but no longer progressing;
- preserve fail-open behavior for non-canonical mirror writes;
- avoid duplicate collector instances;
- maintain explicit data-gap/quality reporting.

Prefer graceful degradation and observable recovery over unnecessary fatal exits.

---

## 9. Telegram operational monitoring

The Product Owner is not expected to understand VPS internals.

Telegram notifications should cover important runtime states.

```text
CCC MARKET READY
SSI connected
Universe ready
Baseline ready
Database healthy

SSI FEED DELAYED
No accepted current-day event for N seconds
Reconnect in progress

SSI RECOVERED
Downtime duration
Current provider/event time

COLLECTOR DOWN / HUNG
Last successful heartbeat
Last accepted SSI event
Recovery/restart status

SUPABASE MIRROR DELAYED
VPS canonical healthy
Pending mirror records
Website unaffected

SUPABASE MIRROR CAPACITY WARNING
Current database size / threshold
```

Alerts must be rate-limited/deduplicated.

---

## 10. Migration path

```text
PHASE A
VPS engines + SQLite canonical
             |
             +--> Supabase audit mirror

PHASE B
Harden runtime, ingest, monitoring, EOD and calculation boundaries

PHASE C
Migrate canonical storage SQLite -> PostgreSQL on VPS

PHASE D
VPS PostgreSQL remains canonical
Supabase remains optional remote audit mirror
```

There is no planned production cutover in which NEW Supabase becomes the canonical market database.

---

## 11. Non-negotiable invariants

1. SSI is the only canonical market-data provider.
2. VPS is the canonical CCC market runtime.
3. Long-term market database target is PostgreSQL on VPS.
4. NEW Supabase `ccc-ssi-v2` is audit mirror only.
5. Mirror writes are async/fail-open and never block VPS canonical writes.
6. Missing data is never fabricated.
7. History is appended; current-state tables are upserted.
8. Product Owner receives clear operational alerts rather than being required to inspect VPS internals.
9. Do not delete existing useful engine logic simply because storage is being modernized.
10. Do not remove SQLite data/runtime until the PostgreSQL VPS replacement is proven.

**END OF DECISION**
