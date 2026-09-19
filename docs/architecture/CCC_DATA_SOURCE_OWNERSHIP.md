# CCC Data Source Ownership — Stock Detail V3 / F3

## Authority by data class

| Source | Owns | F3 rule |
| --- | --- | --- |
| VPS / SSI market stack | Current quote, OHLC, volume, bid/ask, chart/history, MA and standard technical indicators, RVOL, Price5/Price15, ATO/ATC, Current State, signals/reasons, Radar, proprietary CCC metrics | Authoritative. Read through same-origin `/api/v2/*` HTTP and `/api/v2/live` WebSocket. Never substitute Supabase values when an endpoint is unavailable. |
| Supabase | Auth, profiles/users, Watchlist, plans/packages, subscriptions, VIP Day, future payments/billing, the approximately 800-symbol directory, company name, exchange, industry/metadata, `financial_latest`, `financial_quarterly`, BCTC/public fundamental research | Keep the signed-in client for identity/account features and a separate anonymous public-read client for public metadata and financial research. No market/CCC feed comes from this client. |
| Static host | CCC logo, favicon, stock logos, static application assets | Asset delivery only; not market data or authorization. |

The legacy production `website/` may still read `stock_snapshot`; it is **not** a fallback for F3 Stock Detail market data. A missing VPS market/technical endpoint must produce an honest unavailable or `—` state, not a reconstructed quote, MA, RVOL, signal, or Radar identity from Supabase.

## Permission boundary

Public product information (no login): symbol/company/exchange/industry, quote, basic chart, volume, MA and standard indicators, financial metrics and quarterly BCTC research. Protected CCC information: DayRVOL, RVOL15/RVOL30, Price5/Price15, ATO/ATC, Current State, signal/reason, Radar identities, and CCC alerts.

An active VIP Package or VIP Day grants full-market CCC scope. An ordinary signed-in user can receive protected CCC data only for symbols in the active Watchlist. Anonymous visitors receive public data only. A signed-in user outside the Watchlist still sees public data while protected CCC remains locked. The backend entitlement decision is authoritative; the frontend displays its result and never grants access locally. Supabase Auth, user sessions, Watchlist, package/subscription and VIP Day flows remain in place.

## CCCChartAPI/1.2 compatibility

The frozen CCCChartAPI/1.2 VPS deployment requires authentication and entitlement for chart/history and authentication for WebSocket, even though a basic public chart is the product target. F3 sends `Authorization: Bearer <accessToken>` for chart HTTP when a session exists, and includes `token: accessToken` in a chart WebSocket subscription when present. Anonymous clients may make one public attempt per browser runtime; an anonymous chart `401` becomes a neutral legacy-protected state and suppresses further guest chart HTTP probes across symbols until reload. Authenticated chart requests remain independent of that guest latch. Authenticated `401` indicates a session issue; `403` indicates an entitlement denial. Neither case authorizes a Supabase fallback. WebSocket `4401`/`4403` stops reconnect for that connection lifecycle; normal network failures retain exponential backoff.

`/stock-detail`, `/ccc`, and `/radar` may be absent on API 1.2. An HTTP `404` latches that endpoint capability as unavailable for the current browser runtime, across Stock Detail route instances and auth transitions, and stops its polling/probes. A reload starts a new check. CCC metric slots remain visible with `—`; Radar uses a neutral empty state without invented counts. An HTTP `5xx` is transient and must not be latched as permanent capability absence. No API version string is used as the feature gate. When the VPS adds an endpoint, a new browser runtime can use its real response without changing the data owner.

Chart responses and in-flight requests are keyed by an opaque in-memory auth scope, never by a raw JWT. A session change invalidates reuse of protected chart bars and live candles across logout or account switches while retaining lazy history and in-flight deduplication within the current scope.

Development uses ENV-only Vite proxy targets; the browser continues to call relative `/api/v2/*`. The production static host requires equivalent reverse-proxy routing as documented in `website-v2-react/DEPLOY_VPS.md`. This document changes no VPS, database, migration, or production Nginx configuration.
