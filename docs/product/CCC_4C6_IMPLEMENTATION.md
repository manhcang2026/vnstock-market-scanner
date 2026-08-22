# CCC 4C-6 — Member Experience, Market KPI & VIP Day

**Date:** 2026-08-22  
**Frontend:** `v19.0-alpha.17-member-experience`  
**Branch target:** `feature/user-auth-foundation`  
**Staging target:** `zoom.chuyenchochung.com`

## Scope

4C-6 connects the locked membership/watchlist rules to the next user experience layer:

1. `Watchlist` user-facing copy becomes **DS mã theo dõi**.
2. Account desktop hierarchy becomes:
   - main: Profile → DS mã theo dõi;
   - right rail: Current Plan / Upgrade → Security.
3. Mobile hierarchy becomes:
   - Profile → Current Plan → DS mã theo dõi → Security.
4. Symbol selection no longer preloads 800 metadata rows; it searches on demand and renders logo + ticker + display name.
5. Overview KPI cards keep **whole-market counts**, while each card also shows the number matching the user's DS.
6. Capped users receive detailed technical rows only for their DS through the new Overview RPC.
7. FULL and active VIP Day receive whole-market detailed technical rows from the Overview RPC.
8. VIP Day product foundation: 100,000 VND / 24 hours, FULL overlay without mutating base subscription state.
9. Product, user-guide and sales/marketing source-of-truth documents are added.

## Backend migration already applied

`20260822084213_add_vip_day_and_overview_entitlement`

Do not execute the database reference file blindly against production. It documents an already-applied change.

## New database objects

- `ccc_private` schema
- `public.temporary_access_passes`
- `ccc_private.active_vip_day_end(uuid)`
- `public.get_my_access_context()`
- `public.get_my_overview_state()`
- updated `public.get_my_watchlist_state()` with metadata `items`
- authenticated read policy for public `stock_metadata`

## Verified

A transaction-only VIP test was run against an existing user:

- base state resolved;
- temporary VIP Day inserted;
- `get_my_overview_state()` returned 800 entitled technical rows;
- transaction rolled back, leaving no test pass.

## Known security boundary before production

The new Overview RPC enforces identity-aware technical entitlement server-side. However, the legacy `app-v19.0-alpha.6-shell.js` still performs direct anonymous reads of the full `stock_snapshot` for older staging surfaces.

Therefore:

- 4C-6 improves the new authenticated Overview path;
- it is **not yet permission to claim all technical data is production-locked**;
- before production entitlement enforcement is declared complete, legacy technical surfaces must migrate away from unrestricted `stock_snapshot`, then public access can be revoked safely.

## VIP billing status

VIP Day entitlement data model is ready, but payment activation is not connected yet. Alpha.17 only previews the offer; purchase buttons remain disabled until billing is implemented.
