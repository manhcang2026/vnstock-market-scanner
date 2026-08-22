# CCC 4C-8 / Alpha.18 — Overview & Scanner Experience

**Version:** `v19.0-alpha.18-overview-scanner`  
**Date:** 2026-08-22  
**Status:** Staging implementation

## Business rules locked for this build

### 7-day setup
No backend quota change in Alpha.18.

During the first 7 days of a plan, the member may add/remove/replace symbols freely without consuming monthly change quota, provided the number of simultaneously selected symbols never exceeds the plan capacity.

After the setup window:
- REMOVE costs 0.
- ADD costs 1 quota.
- Re-adding a removed symbol costs 1 quota.

### Overview
- KPI large number = whole-market count.
- KPI secondary line = count in the member's effective tracked list.
- Default state has no KPI selected.
- Default result list shows the whole effective tracked list, including symbols at 0/4.
- Selecting a KPI filters the member list.
- A visible "Xem tất cả DS mã theo dõi" action returns to default state.
- Alpha.17 mutation/render loop is removed; Alpha.18 patches idempotently.

### Scanner / tracked-list page
The sidebar item "Bộ quét" is removed from the user-facing navigation.

The sidebar item "DS mã theo dõi" becomes the real entry point to `/danh-sach`.

The page has:
1. `DS mã theo dõi` — first/default tab, full signal experience.
2. `Toàn bộ thị trường` — second tab, basic market data available to every plan.

### Effective tracked list
- Capped plans: user-selected Watchlist.
- FULL: current Scanner Universe dynamically.
- VIP Day while active: current Scanner Universe dynamically.
- Never hard-code FULL = 800; if Scanner Universe grows, effective FULL list grows automatically.

### Whole-market tab
All plans may view the whole Scanner Universe with basic columns only:
- Logo + ticker + display name + exchange
- Current price
- Price change
- Current volume
- MA200 distance
- MA10 distance where layout allows

Removed in whole-market mode:
- 4/4, >=3, >=2, RVOL30 summary chips
- Signal dropdown
- CCC rail / technical signal details
- RVOL30 high/low sorting

A symbol outside the member's tracked list does not open technical detail in Alpha.18.

### Pagination
Desktop:
- 50 symbols per page
- Previous / Next navigation

Mobile:
- Initial 20 symbols
- Explicit "Xem thêm" button

### Account links
At the end of the tracked-list tab:
- `Thay đổi DS mã` -> `/tai-khoan#ds-ma-theo-doi`
- `Nâng cấp gói` -> `/tai-khoan#goi-thanh-vien`

### Alert list
Not implemented in Alpha.18. Alert symbols will be designed later as a separate user list.
