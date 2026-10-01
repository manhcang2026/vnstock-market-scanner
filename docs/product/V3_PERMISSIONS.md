# CCC V4 Permissions — Beta 10/10

**Status:** Product Owner approved direction, 2026-10-01  
**Scope:** Market/Watchlist/Stock Detail/Filter/AI entitlement presentation and API boundary.

This document supersedes older V3 permission wording where it conflicts with the rules below.

## 1. Public market layer

A symbol does not need to be in the user's Watchlist for the following data to be public when the backend has valid data:

- symbol / company identity / exchange;
- current price;
- change value / change percent;
- basic volume;
- MA10 / MA200;
- distance to MA10 / MA200.

Stock Detail public access keeps the previously approved public features when available:

- market quote;
- chart history and live candles;
- chart resolutions already supported by the API;
- zoom/pan/fullscreen/candle inspection;
- public chart indicators such as MA/Bollinger/RSI/MACD;
- Fundamental Research;
- quarterly financial/BCTC public research.

## 2. CCC Intelligence protected layer

Outside effective technical entitlement, the backend must not return protected CCC fields.

Protected fields include:

- Day RVOL;
- RVOL15;
- RVOL30;
- CCC Price5 / Price15;
- CCC State;
- signal state/level/direction;
- reason codes and explanations;
- ATO/ATC Intelligence and ATC price impact;
- historical CCC signal journey;
- CCC alerts/automation.

Raw engine/config thresholds remain server-side.

Signal logic must never be rebuilt in browser JavaScript.

## 3. Access semantics

Frontend components should consume one simple semantic access state:

```text
DISCOVERY
TRACKED
FULL_MARKET
```

### DISCOVERY
Public market layer only.

### TRACKED
Public layer + CCC Intelligence for symbols inside the user's effective Watchlist/technical entitlement.

### FULL_MARKET
Public layer + CCC Intelligence for the full entitled market universe.

The backend remains the authority for plan inheritance, VIP/full-market semantics and active Watchlist scope.

Do not scatter package/watchlist/VIP logic across individual UI components.

## 4. Server-side enforcement

Protected data must be removed by backend authorization/serializer logic.

Do not send premium values to the browser and only hide them with CSS.

Unauthorized identities or protected values must not be inferable from network responses.

## 5. Market / Scanner behavior

Outside Watchlist, users may still browse public rows.

Do not blur or hide the entire row.

A Discovery row may show a compact locked state for CCC Intelligence and an action such as adding the symbol to Watchlist.

## 6. Filter entitlement and anti-leak rule

Public filters may run across the full public market universe for public fields such as:

- exchange;
- metadata/industry when available;
- price;
- change percent;
- volume;
- above/below MA10/MA200;
- distance MA10/MA200.

If any condition uses a CCC-protected field such as RVOL, Price5/15, Signal or ATO/ATC:

- non-full-market users may only search their effective entitled scope;
- full-market users may search the full entitled universe.

Filter results must not leak protected intelligence for unauthorized symbols.

## 7. AI Search entitlement

AI is not a market-data source.

AI may translate Vietnamese natural language into a validated CCC intent/filter/action. The CCC backend then queries real CCC data.

Rules:

- queries using only public fields may search the public market universe;
- queries using protected fields must be scoped to the user's effective entitlement;
- full-market users may use protected-field search across the full entitled universe;
- deep analysis/explanation must respect the same data entitlement;
- AI must not bypass the serializer/API permission boundary.

AI quota policy is defined separately by the AI Core Plan.

## 8. Unchanged business rules

This amendment does not by itself change:

- Watchlist capacity/quota math;
- package inheritance;
- upgrade/downgrade rules;
- scanner collection universe;
- RVOL definitions;
- baseline math;
- MA logic;
- ATO/ATC algorithms;
- signal thresholds.

Missing data remains missing/NULL and must not be converted to zero.
