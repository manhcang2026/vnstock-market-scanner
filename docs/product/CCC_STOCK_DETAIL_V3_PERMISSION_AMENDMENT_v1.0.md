# CCC Stock Detail V3 Permission Amendment v1.0

**Status:** PRODUCT OWNER APPROVED  
**Date:** 2026-09-19  
**Scope:** Stock Detail V3 and the minimum API boundary required by it

This versioned amendment supersedes older Stock Detail permission text where it
conflicts with the boundary below. It does not change plan inheritance,
Watchlist quota/capacity, upgrade or downgrade rules.

## Public / free

- Market Quote and company identity.
- Chart history and live candle updates.
- 5m, 15m, 30m, 1H and 1D chart resolutions.
- Zoom, pan, fullscreen and candle inspection.
- MA10, MA25, MA99, MA200, Bollinger Bands, RSI and MACD.
- MA10/MA200 values and distance.
- Fundamental Research from `financial_latest` and `stock_metadata`.
- Quarterly financial history from `financial_quarterly` and the real external
  BCTC link.

Public API serializers are allowlists. They must not reuse the full current CCC
state serializer.

## CCC entitlement protected

- DayRVOL, RVOL15 and RVOL30.
- CCC Price5 / Price15 engine values.
- ATO/ATC intelligence and ATC price impact.
- `signal_state`, `signal_level`, `signal_direction`, summaries and reason-code
  explanations.
- Historical signal journey when canonical `signal_events` exists.
- Market-wide Radar identities outside the authenticated user's entitled scope.
- CCC alerts and automation.

Raw engine/config thresholds are never public. Signal logic is never rebuilt in
browser JavaScript.

## Entitlement semantics

Server authorization uses `technical_allowed`,
`effective_full_market_access`, active VIP Day and the authenticated active
Watchlist scope. No new `VIP_MONTH` code is introduced. A full-market plan is
identified by the backend `full_market_access` semantic.

Radar aggregate counts may be public. Unauthorized identities must be omitted
from the network response, not merely hidden in the UI.

## Explicitly unchanged

- Watchlist quota and replacement math.
- Plan capacity and inheritance.
- Scanner universe membership and collection.
- Signal thresholds, RVOL definitions, auction algorithms and baseline math.
