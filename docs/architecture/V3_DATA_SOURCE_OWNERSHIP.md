# CCC V4 Data Source Ownership

**Status:** Current architecture reference for Beta 10/10  
**Supersedes:** older V3 persistence wording where it conflicts with `AGENTS.md`.

## 1. Canonical market-data authority

SSI FastConnect is the canonical external market-data provider for V4.

The VPS CCC Engine is the canonical V4 runtime/storage owner.

Current production direction:

```text
SSI
  -> VPS CCC Engine
  -> canonical VPS storage (currently SQLite)
  -> /api/v2/* and /api/v2/live
  -> React frontend
```

Long-term storage may migrate to PostgreSQL on the VPS without requiring a frontend API-contract rewrite.

## 2. Frontend boundary

Browser market traffic must use:

- HTTP `/api/v2/*`;
- WebSocket `/api/v2/live`.

The browser must not select or depend on physical market database tables.

The frontend must not know whether the backend currently uses SQLite or later PostgreSQL.

## 3. OLD Supabase ownership

The existing OLD Supabase remains owner for:

- authentication/session;
- profiles;
- Watchlists;
- plans/packages;
- subscriptions;
- VIP/full-market entitlement;
- company/symbol metadata;
- exchange/industry metadata;
- Fundamental Research;
- BCTC/quarterly financial data;
- legacy market/scanner tables still required by legacy deployed websites until retirement.

OLD Supabase market tables are not a V4 market-data fallback.

Missing canonical SSI/CCC market data remains missing/NULL.

## 4. NEW Supabase `ccc-ssi-v2`

`ccc-ssi-v2` is a remote audit/mirror system only when used.

Mirror writes must be:

- asynchronous;
- fail-open;
- best effort;
- retryable;
- unable to roll back or block canonical VPS writes.

It must not be a production browser dependency.

Do not expose privileged NEW Supabase credentials to frontend code.

## 5. Runtime preservation

Do not remove current working canonical dependencies until the replacement is proven.

Data cleanup must preserve canonical/recoverable data and realtime-only ATO/ATC evidence where required.

The legacy Supabase scanner path described by `AGENTS.md` must remain intact until the Product Owner explicitly retires it.

## 6. Product data ownership matrix

| Data | Owner/source |
|---|---|
| Realtime quote / OHLCV / bid-ask | SSI -> VPS CCC backend |
| Intraday minute bars / chart market history | VPS canonical market runtime |
| Daily bars / current market state | VPS CCC Engine |
| RVOL / Price5 / Price15 / MA technical metrics | CCC Engine |
| ATO/ATC Intelligence | CCC Engine |
| Signals / reasons | CCC Engine |
| Auth / user profile | OLD Supabase |
| Watchlist | OLD Supabase |
| Package / subscription / VIP entitlement | OLD Supabase |
| Symbol/company/exchange/industry metadata | OLD Supabase |
| Fundamental / BCTC | OLD Supabase |
| `ccc-ssi-v2` | audit mirror only |

## 7. Data quality

Missing data is not zero.

Frontend/API states must distinguish at least:

- live/current;
- outside market hours;
- stale;
- degraded;
- missing/unavailable;
- locked by entitlement;
- error.

The UI must not present stale trading-date data as healthy live data.

## 8. P0 Beta cutover check

Before 10/10, verify that current-session endpoints use the current CCC Engine state rather than a legacy stale market-state layer.

At minimum verify:

- `/api/v2/quote/{symbol}`;
- `/api/v2/stock-detail/{symbol}`;
- `/api/v2/ccc/{symbol}`;
- `/api/v2/scanner`;
- `/api/v2/live`.

The frontend must consume the API contract only; fixing a stale backend source must not require browser-side table knowledge.
