# CCC Incident Review — 23/09/2026 Morning Feed Freeze

**Project:** Chuyện Chợ Chứng (CCC)  
**Incident date:** 23/09/2026  
**Review date:** 24/09/2026  
**Status:** INVESTIGATED — runtime hardening required  
**Evidence source:** `ccc_incident_20260923.txt`

---

## 1. Executive conclusion

The morning freeze was **not caused by VPS resource exhaustion** and is **not evidence that SQLite/VPS storage must be abandoned**.

The observed sequence was:

```text
pre-open / opening
SSI connection alive but no accepted current-day events
        |
        v
09:03 stale watchdog fires after 180s
        |
        v
collector exits
        |
        v
Docker restarts correctly
        |
        v
SSI reconnect succeeds
        |
        v
fresh data writes briefly through about 09:03:11
        |
        v
process remains alive but stops progressing
```

The leading technical cause of the second freeze is a **high-confidence lock-order/race/deadlock risk** in the runtime. This remains a hypothesis until reproduced with thread-dump evidence.

---

## 2. Evidence

### Before 09:03

Collector stats repeatedly showed:

```text
received_messages = 1979
accepted_events = 0
ignored_non_current_trading_date = 799
```

The counters stayed unchanged for many minutes.

Interpretation:
- process was alive;
- no acceptable current-day event was advancing the collector;
- liveness watchdog was therefore necessary.

### 09:03 watchdog

Configured:

```text
STALE_STREAM_SECONDS=180
```

At approximately 09:03:

```text
RuntimeError: SSI stream stale for more than 180s during market session
```

This was an intentional fail/restart path, not a storage crash.

### Docker restart

Docker reported exit code 1 and automatic restart with `unless-stopped`.

The restarted process:
- reinitialized volume engine;
- reinitialized live state;
- loaded 800 symbols;
- started collector;
- reconnected WebSocket.

### Brief recovery

SQLite showed:
- 48 symbols with rows for 23/09;
- minute buckets through 09:03;
- latest quotes updated through about 09:03:11;
- `stock_state_current` latest update around 09:03:11.

This proves the restarted process did receive and persist fresh market data briefly.

### Host health

At audit time:
- disk had roughly 37 GB available;
- memory had roughly 4.9 GiB available;
- no OOM kill;
- no kernel/storage error evidence;
- host load was near idle.

Therefore no evidence supports CPU/RAM/disk exhaustion as the primary cause.

---

## 3. Leading root-cause hypothesis

There is a potential lock-order inversion between:

```text
SSI callback path
hot-store transaction lock
    -> volume/live-state projection
    -> LiveStateRuntime lock
```

and:

```text
main/advance path
LiveStateRuntime lock
    -> hot-store read
    -> hot-store lock
```

Possible deadlock:

```text
Thread A holds HOT_STORE lock, waits for LIVE_STATE lock
Thread B holds LIVE_STATE lock, waits for HOT_STORE lock
```

Expected symptom:
- no traceback;
- process still alive;
- no new data;
- internal watchdog may also stop progressing;
- Docker sees process as running.

This matches the observed post-restart behavior closely.

---

## 4. Required hardening

Do not rely on a single in-process loop to detect all failures.

Required direction:

1. keep SSI callback lightweight;
2. remove lock inversion;
3. decouple raw ingest from calculation via queue/worker boundary where appropriate;
4. raw ingest must continue if calculation fails;
5. Supabase mirror must be async/fail-open;
6. add external heartbeat/watchdog able to detect alive-but-stalled collector;
7. reconnect SSI proactively on stale feed;
8. prevent duplicate collectors;
9. preserve explicit `data_gap` / degraded quality instead of fabricating data;
10. add Telegram operational alerts.

---

## 5. Alerting target

Product Owner should receive simple operational messages.

```text
🟢 CCC MARKET READY
SSI connected
Universe 800
Baseline ready

🟡 SSI FEED DELAYED
No current-day accepted event
Reconnect in progress

🟢 SSI RECOVERED
Downtime: N seconds

🔴 CCC COLLECTOR STALLED
Process alive but heartbeat not advancing
Last accepted event: HH:MM:SS
Recovery action: ...

🟡 SUPABASE MIRROR DELAYED
VPS canonical healthy
Website unaffected
```

---

## 6. Architectural implication

Do **not** move the canonical market database to Supabase as a reaction to this incident.

Approved response:

```text
fix runtime/orchestration
keep VPS canonical
mirror asynchronously to Supabase for remote audit
later move canonical SQLite -> PostgreSQL on VPS
```

**END OF INCIDENT REVIEW**
