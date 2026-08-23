# CCC v19 Phase 2 — Overview Report

**Release:** `v19.1.1-overview`  
**Repository:** `manhcang2026/vnstock-market-scanner`  
**Branch:** `feature/user-auth-foundation`  
**Date:** 2026-08-23  
**Target:** `website-next/` staging only

## Scope completed

Phase 2 restores the real Overview experience on top of the consolidated v19.1 runtime without reintroducing the Alpha patch stack.

### Overview behavior

- Four KPI cards are restored:
  - Đạt 4/4
  - Từ 3 tín hiệu
  - Từ 2 tín hiệu
  - RVOL30 nổi bật
- Large KPI number = whole-market count.
- Compact secondary copy = `DS của bạn: X mã`.
- Default state has no KPI selected.
- Signed-in capped member with a tracked list sees the complete tracked list by default, including 0/4 rows.
- Selecting a KPI filters the member's effective tracked list.
- `← Xem tất cả DS mã theo dõi` restores the default list.
- KPI-specific upsell card returns under the results and exposes only aggregate opportunity count outside entitlement.
- FULL/VIP uses the whole current Scanner Universe dynamically through the existing `get_my_overview_state()` contract.

### Empty/new/guest onboarding

When there is no personal tracked list, Overview shows the six locked fixed demo symbols:

- VCB
- FPT
- HPG
- VIC
- VNM
- GAS

The demo is clearly labeled as fixed product onboarding, not a recommendation and not the user's tracked list.

Each sample row shows the rich CCC presentation:
- price / change
- current volume
- daily volume ratio
- RVOL30
- MA200 distance
- CCC four-position signal rail
- signal count

CTA:
- guest -> opens login/register dialog
- signed-in empty member -> `/tai-khoan#ds-ma-theo-doi`

Once a signed-in capped member has at least one real tracked symbol, the sample state disappears.

### Layout

Desktop keeps the approved structure:

`LEFT SIDEBAR + FULL-WIDTH PAGE HEADER + MAIN CONTENT + RIGHT RAIL`

Overview right rail contains:
- live/current market context from `market_pulse_current`
- data update / scanner-universe context

Mobile keeps the single-flow shell and card-first rows.

Desktop tracked-list pagination:
- 50 rows/page

Mobile:
- first 20 rows
- explicit `Xem thêm`

## Data/security

### Existing authenticated RPC retained

`get_my_overview_state()`

Provides:
- whole-market aggregate KPI counts
- entitled technical rows only
- dynamic FULL/VIP whole-universe rows
- fixed sample rows for a signed-in capped member with zero selected symbols

### New guest-safe RPC applied

Migration:

`add_public_overview_demo_state`

Adds:

`public.get_public_overview_state()`

The RPC returns only:
- whole-market aggregate KPI counts
- total scanner count
- latest snapshot timestamp
- technical rows for exactly the six fixed sample symbols

It does **not** expose technical identities for the rest of the market.

Permissions verified:
- anon execute `get_public_overview_state()` = true
- authenticated execute `get_public_overview_state()` = true
- anon execute `get_my_overview_state()` = false

Current guest test result:
- market total: 800
- sample rows: 6
- market counts: 5 / 36 / 149 / 164 for 4/4 / >=3 / >=2 / RVOL30 respectively at verification time

Authenticated fixture test against an existing FREE member returned:
- real tracked rows only
- real tracked KPI counts
- no sample rows when the member has a real tracked list

No direct authenticated/guest technical-table permission was opened for this feature.

## Runtime architecture

Phase 2 stays inside the consolidated runtime:

- `data-v19.1.1.js`
- `app-v19.1.1.js`
- `styles-v19.1.1.css`

No Alpha runtime asset is loaded.
No `MutationObserver` is introduced.
No normal-page polling/repair loop is introduced.
No stylesheet patch stack is reintroduced.

## Static checks

- `node --check data-v19.1.1.js` — PASS
- `node --check app-v19.1.1.js` — PASS
- `MutationObserver` — 0
- `setInterval` — 0
- `!important` — 0
- Alpha runtime references in Phase 2 index — 0
- user-facing `phạm vi` wording in active v19.1.1 app — removed

## Not included in Phase 2

The following remain for the next scanner phase:
- full `DS mã theo dõi` scanner UI
- `Toàn bộ thị trường` tab implementation
- server-paged nearest MA10/MA200 sort
- non-entitled stock technical detail behavior
- separate alert-symbol list

No scanner-universe logic was changed.
No four-signal formula was changed.

## Suggested commit

`feat(frontend): restore v19.1.1 overview experience`

**DO NOT MERGE MAIN YET.**
