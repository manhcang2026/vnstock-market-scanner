# CCC v19.12.0 — Golden Board / Membership / TB10

## Scope locked for this one-shot release

### 1. Golden Board becomes visible
- New route: `/bang-vang`.
- Desktop: replaces the disabled **Cảnh báo** nav placeholder with **Bảng vàng**.
- Mobile bottom navigation: **Bảng vàng** replaces **Hướng dẫn**; Guide remains available through the existing help icon in the header.
- Signed-in users use `get_my_golden_board()`.
- Guests use `get_public_golden_board()` teaser: market count + up to 2 symbols with the existing 20-minute delay.
- Historical dates are kept and selectable, including 27/08, 28/08, 03/09 and 04/09.
- Rows show: first 4/4 slot, hit count, longest streak, price change at first hit, KL/TB10, RVOL30, latest signal count, Signal V1/V2 badge.
- Weekly Gold summary is shown when the backend returns `week_summary`.

### 2. Signal history versioning
- Existing Golden Board history is `CCC_SIGNAL_V1`.
- New rows default to V1 until a future V2 cutover.
- Historical rows are not rewritten when thresholds change.

### 3. Paid offer display simplified
Public paid offers now present only:
- **VIP DAY — 100.000đ / 24 giờ**
- **FULL — 1.000.000đ / tháng**

BASIC / PLUS / PRO are not offered to new users. Existing legacy subscriptions remain valid in backend.

### 4. VIP / Watchlist UI matches production backend
- VIP DAY includes unlimited saved Watchlist while active.
- FULL includes unlimited saved Watchlist.
- When temporary/full entitlement ends, symbols are retained.
- Symbols beyond the base technical entitlement are decorated as saved-but-locked instead of being deleted.
- The release contains a compatibility bridge for the current v19.7 frontend so VIP unlimited state is not incorrectly re-capped by the old base-plan UI fallback.

### 5. Same-Time VOL10 UI terminology
Short UI naming becomes:
- `KL/TB10`
- `TB10 tham chiếu`
- signal label: `KL ≥ 200% TB10`

Help text:
> Trong giờ giao dịch, TB10 so sánh khối lượng tích lũy hiện tại với trung bình khối lượng tích lũy tại cùng mốc thời gian của tối đa 10 phiên trước. Ngoài giờ giao dịch, TB10 là trung bình khối lượng cả phiên.

This keeps the interface compact while making the new Same-Time semantics explicit where users need the explanation.

## Rollback design
The frontend change is additive. Restoring the previous `index.html` immediately disables the new release assets without touching backend production data.
