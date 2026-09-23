# CCC V3 Data Source Ownership

## 1. Market-data authority

SSI FastConnect is the sole canonical source for V3 market data.

This includes:

- realtime quote
- OHLCV
- intraday minute bars
- daily bars
- bid/ask where available
- chart market history
- volume calculations
- RVOL metrics
- price momentum
- MA and technical metrics
- ATO/ATC intelligence
- stock state
- signals/reasons
- Radar / market scanner market state

No other provider may silently fill missing SSI market data.

Missing SSI data must remain missing / NULL.

## 2. Runtime boundary

Frontend market traffic follows:

Frontend
→ VPS `/api/v2/*` REST
→ VPS `/api/v2/live` WebSocket
→ SSI runtime / CCC engine

The browser does not choose or know the backend market database.

## 3. Temporary V3 market persistence

During V3 stabilization, market persistence uses the NEW Supabase PostgreSQL project:

`ccc-ssi-v2`

Its purpose is:

- inspectability;
- SQL auditing;
- schema stabilization;
- baseline verification;
- RVOL verification;
- EOD verification;
- signal/state verification;
- easier diagnosis during development.

It is not intended to be the permanent market database.

The implementation must prefer portable PostgreSQL constructs and avoid unnecessary Supabase-specific coupling.

When V3 is stable:

`ccc-ssi-v2 PostgreSQL`
→ PostgreSQL migration
→ VPS PostgreSQL

Frontend/API/WS contracts remain unchanged.

## 4. OLD Supabase ownership

The existing OLD Supabase project continues to own:

- authentication and sessions
- profiles
- Watchlist
- plans/packages
- subscriptions
- VIP access
- entitlement
- company/symbol metadata
- exchange/industry metadata
- financial/fundamental research
- `financial_latest`
- `financial_quarterly`
- BCTC-related public research data

Frontend may use OLD Supabase for these approved responsibilities.

OLD Supabase must never become a fallback market-data provider for V3.

## 5. Browser security boundary

The browser must not receive NEW Supabase privileged credentials.

NEW market persistence is accessed by backend/server-side services only.

Frontend market data continues to use VPS REST/WebSocket endpoints.

## 6. Current runtime migration rule

Current VPS chart/API/WebSocket runtime remains operational while NEW persistence is developed.

Do not remove current storage/runtime dependencies before the replacement has been proven.

Migration order:

1. preserve current working runtime;
2. build NEW PostgreSQL schema;
3. validate incoming SSI data;
4. validate baseline and calculated metrics;
5. validate API/chart/WS output;
6. switch persistence;
7. observe in production;
8. retire obsolete storage.

## 7. Repository ownership

`infra/supabase-user-system/`
= OLD Supabase user/account entitlement material.

`supabase/`
= NEW `ccc-ssi-v2` market database migrations only.

`services/ssi_realtime_shadow/`
= current SSI/backend runtime.

`website-v2-react/`
= current V3 frontend.
