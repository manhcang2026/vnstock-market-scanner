# CCC Beta 10/10 — Frontend Master V4

**Ngày chốt nền:** 2026-10-01  
**Mốc public dự kiến:** 2026-10-10  
**Repo audit:** `manhcang2026/vnstock-market-scanner`  
**Frontend branch đối chiếu:** `feat/ccc-v3-beta` @ `80cd98b7146f3e2428b483ed5dbca31bda19a9e3`  
**Frontend hiện hành:** `website-v2-react/`  
**Trạng thái tài liệu:** MASTER DRAFT để khóa nền trước khi đi chi tiết Figma/code.

---

## 1. Mục tiêu sản phẩm Beta 10/10

CCC Beta phải thể hiện rõ vòng lặp chính:

**Quan sát thị trường → tìm mã đáng chú ý → hiểu dữ liệu/tín hiệu CCC → theo dõi mã → đi sâu Stock Detail.**

Không cố biến Beta thành website chứng khoán có mọi chức năng. Ưu tiên:

1. Market / danh sách cổ phiếu.
2. Watchlist.
3. Bộ lọc.
4. Stock Detail.
5. CCC Intelligence.
6. AI Search.
7. Auth / package / VIP / entitlement.
8. Data freshness / missing / stale states.
9. Responsive desktop-mobile hoàn chỉnh.

Các phần Community, News/Articles, Academy, Tools, Admin CMS có thể chuẩn bị chỗ trong kiến trúc nhưng không được làm trễ core Beta.

---

## 2. Nguyên tắc kiến trúc UI mới

### 2.1. Một App Shell duy nhất

Beta V4 phải dùng **một shell thống nhất cho tất cả route chính**, không tiếp tục tình trạng generic `AppShell` cho một số route và `StockDetailShell` cho Scanner/Stock Detail/Account.

Shell gồm:

- Top bar.
- Left global sidebar.
- Center workspace.
- Right contextual rail.

Stock Detail là một route/context bên trong shell, không có shell riêng.

### 2.2. Desktop là workspace 3 cột thật

Hướng thiết kế lấy cấu trúc từ mockup mới, nhưng giữ visual DNA/màu CCC cũ.

**Khuyến nghị geometry:**

```text
TOP BAR: 52–56px

LEFT SIDEBAR | CENTER WORKSPACE            | RIGHT CONTEXT
220–232px    | minmax(0, 1fr)             | 288–320px
```

CSS direction:

```css
grid-template-columns: 224px minmax(0, 1fr) clamp(288px, 19vw, 320px);
gap: 10px/12px;
```

Mục tiêu gần mockup:

- 1680px: left ~224, right ~310, center ~1100.
- 1440px: left ~208–220, right ~280–300, center ~880–920.
- Center luôn nhận phần lớn không gian.
- Right rail rộng hơn rail V3 cũ 240px vì AI/Search/Market Index/News cần đọc được thật.
- Không dùng max-width container tạo gutter lớn và route jitter.

### 2.3. Breakpoint

**>= 1440px:** full 3 cột.  
**1280–1439px:** compact 3 cột, left ~200–208, right ~260–280.  
**1024–1279px:** left + center; right rail chuyển thành drawer/panel/context tab.  
**<= 900px:** center 100%; left và right không tồn tại thường trực.

Mobile không được co table desktop xuống màn hình nhỏ.

---

## 3. Left sidebar / menu

### 3.1. Beta 10/10

Tạm giữ route/menu hiện tại để tránh lan scope:

- Tổng quan.
- Bộ quét / Danh sách.
- Nghiên cứu / So sánh ngành.
- Sàng lọc cơ bản.
- Tài khoản.

Stock Detail không phải primary menu item.

### 3.2. Workspace cá nhân

Left sidebar có vùng **Danh sách của tôi** khi dữ liệu/watchlist hỗ trợ:

- Danh sách theo dõi.
- Các danh sách riêng khác trong tương lai.

Không bắt buộc phải hoàn thiện multi-watchlist trước 10/10 nếu backend chưa có contract.

### 3.3. Menu tương lai

Kiến trúc phải chừa chỗ cho:

- Thị trường.
- Đã theo dõi.
- Sàng lọc CCC.
- AI Search.
- Tin tức / Bài viết.
- Cộng đồng.
- Công cụ.
- Học viện.

Không cần public tất cả ở Beta.

---

## 4. Right contextual rail

Right rail không phải navigation chính. Nó đổi nội dung theo route.

### Scanner / Watchlist

Ưu tiên:

- Market indices / market context.
- AI Search.
- Sau này: Tin nổi bật / bài viết.
- Sau này: quick tools / community.

### Stock Detail

Ưu tiên:

- Context giá/phiên.
- CCC context / Radar liên quan.
- AI "Hỏi về mã này" khi AI được triển khai.
- Signal / data trust compact context nếu phù hợp.

### Quy tắc

- Không nhồi mọi widget vào right rail.
- Không có dead button giả chức năng.
- Module chưa có backend thì bỏ hoặc ghi rõ coming soon ở nơi không gây hiểu lầm.

---

## 5. Filter / Sort / Column controls

V4 không dùng left contextual rail thường trực chỉ để chứa filter như Scanner hiện tại.

Trên desktop, thao tác danh sách đặt trong toolbar phía trên bảng:

- Bộ lọc.
- Sắp xếp.
- Tùy chỉnh cột.
- Thêm mã (khi ở Watchlist).

Filter mở popover/panel/drawer phù hợp.

Trên mobile:

- Bộ lọc → bottom sheet/full-height sheet.
- Sắp xếp → bottom sheet.
- Tùy chỉnh cột không cần ưu tiên nếu mobile dùng card.

---

## 6. Mobile UX

### 6.1. Top bar

Mobile phải có hamburger hoạt động:

```text
☰   CCC / Logo        Search      Account
```

Bấm hamburger mở drawer chứa toàn bộ primary navigation.

### 6.2. Bottom navigation

Có thể giữ 4–5 tác vụ/route quan trọng nếu hữu ích, nhưng hamburger là nơi chứa navigation đầy đủ.

Bottom nav không thay thế hamburger.

### 6.3. Right rail

Không có right rail thường trực trên mobile.

Chuyển thành:

- tabs;
- section trong content;
- bottom sheet;
- action button;
- horizontal market strip.

### 6.4. Danh sách

Desktop dùng table, mobile dùng card.

Card tối thiểu:

- Symbol/company.
- Giá và % thay đổi.
- Volume.
- MA/distance public.
- CCC protected state nếu user được entitlement.

---

## 7. Theme và visual identity

### 7.1. Chỉ một theme cho Beta

**Beta 10/10 chỉ dùng một dark theme chuẩn.**

Không làm Light/Dark toggle trong scope này.

Phải xóa/hủy presentation của theme toggle khỏi:

- top bar;
- settings nếu chỉ phục vụ đổi theme;
- mobile sheet.

Không cần QA 2 theme trong tuần release.

### 7.2. Giữ DNA màu CCC cũ

Không copy nguyên màu mockup tham khảo.

Giữ phong cách:

- background navy/black;
- panel navy đậm;
- border blue-gray mảnh;
- primary text off-white;
- secondary text blue-gray;
- positive green;
- negative red/coral;
- MA/link/action blue/cyan;
- RVOL / CCC Intelligence purple-violet;
- màu semantic chỉ dùng khi có ý nghĩa.

Tránh dashboard neon hoặc generic Tailwind admin style.

---

## 8. Data access / entitlement chính thức

### 8.1. Public market layer

Được xem với mã ngoài Watchlist:

- Mã / tên / sàn.
- Giá hiện tại.
- % thay đổi.
- Khối lượng cơ bản.
- MA10 / MA200.
- Khoảng cách MA10 / MA200.

Stock Detail public hiện giữ các quyền đã được duyệt trước đó nếu backend hỗ trợ:

- chart giá/lịch sử/live;
- các indicator chart public như MA/Bollinger/RSI/MACD;
- Fundamental Research;
- BCTC public research.

### 8.2. CCC Intelligence protected

Ngoài entitled scope không trả/không hiển thị:

- Day RVOL.
- RVOL15.
- RVOL30.
- CCC Price5 / Price15.
- CCC State.
- Signal / level / direction / reason / explanation.
- ATO / ATC Intelligence / ATC impact.
- Historical CCC signal journey.
- Alerts/automation thuộc CCC.

### 8.3. Access modes

Frontend nên nhận một semantic đơn giản từ backend:

```text
DISCOVERY
TRACKED
FULL_MARKET
```

- `DISCOVERY`: chỉ public layer.
- `TRACKED`: public + CCC Intelligence cho mã thuộc watchlist/effective entitlement.
- `FULL_MARKET`: public + CCC Intelligence trên toàn market (VIP/full-market semantic).

Không rải logic package/watchlist/VIP khắp component.

### 8.4. Security

Khóa dữ liệu phải thực hiện ở backend serializer/authorization.

Không được trả premium field xuống browser rồi chỉ hide bằng CSS.

---

## 9. Filter entitlement

### Public filter — toàn market

Cho phép ít nhất:

- exchange;
- industry/metadata khi có;
- price;
- change %;
- volume;
- above/below MA10/MA200;
- distance MA10/MA200.

### CCC filter

Bất kỳ điều kiện có CCC-protected field (RVOL, Price5/15, Signal, ATO/ATC...) phải giới hạn universe theo entitlement:

- non-full-market → watchlist/effective technical scope;
- VIP/full-market → toàn thị trường.

Không được dùng kết quả filter để leak premium intelligence của mã ngoài scope.

---

## 10. AI Search entitlement

AI không phải nguồn số liệu. AI chỉ chuyển ngôn ngữ tự nhiên thành intent/filter/action hợp lệ, backend CCC query dữ liệu thật.

### Non-VIP

- Query chỉ dùng public fields có thể scan toàn market.
- Nếu query chứa CCC protected fields, search universe phải giới hạn vào entitled/watchlist scope.
- Deep analysis từng mã chỉ trong scope được quyền.

### VIP / full-market

- Có thể scan CCC Intelligence trên toàn market.
- Các intent nâng cao theo AI product plan/quota.

Quota chi tiết tiếp tục theo AI Core Plan; master frontend này chỉ khóa **scope data**, không khóa số lượt.

---

## 11. Market / Watchlist screen

### Desktop

Center table là trọng tâm.

Header/action area:

- title + count;
- filter;
- sort;
- column settings;
- add symbol (watchlist).

Row có thể gồm:

- identity;
- price/change;
- volume;
- MA/distance;
- quick CCC metrics nếu entitled;
- signal/state if entitled;
- row actions.

Outside watchlist:

- vẫn nhìn được public market data;
- protected data dùng lock state gọn, không blur cả dòng;
- CTA thêm vào watchlist khi phù hợp.

### Mobile

Card layout; không horizontal-scroll table làm UX chính.

---

## 12. Stock Detail

Thứ tự thông tin ưu tiên:

1. Identity + quote + freshness.
2. Session summary.
3. Chart.
4. CCC Intelligence.
5. Signal/reasons.
6. Fundamental.
7. BCTC.

Nếu mã ở Discovery mode:

- quote/chart/public technical/fundamental/BCTC vẫn xem theo public permission;
- CCC Intelligence hiện lock panel + CTA theo dõi/nâng scope.

Không redirect user ra khỏi Stock Detail chỉ vì mã chưa thuộc watchlist.

---

## 13. Data trust / stale / missing

Frontend tài chính phải có state rõ:

- Loading.
- Live.
- Outside market hours.
- Stale.
- Missing/unavailable.
- Degraded/data warning.
- Locked/entitlement.
- Error.

`NULL`/missing không biến thành zero.

Nếu trading date cũ hơn expected current session, không được trình bày như dữ liệu live bình thường.

---

## 14. Data ownership / API boundary

### Canonical market data

SSI + CCC Engine trên VPS là canonical market-data owner.

Browser market traffic:

```text
Frontend
  -> /api/v2/*
  -> /api/v2/live
  -> CCC backend/engine
  -> canonical VPS storage
```

Frontend không biết database table nào đứng phía sau API.

### OLD Supabase

Giữ:

- Auth/session/profile.
- Watchlist.
- Plans/subscriptions/VIP/entitlement.
- company/symbol/exchange/industry metadata.
- Fundamental/BCTC.

Không dùng OLD Supabase market tables làm fallback cho V3 market data.

### NEW Supabase `ccc-ssi-v2`

Chỉ là remote audit mirror/best-effort mirror nếu còn sử dụng.

Không là production dependency của frontend.

---

## 15. P0 data issue đã xác nhận 2026-10-01

Production DB audit cho thấy:

- legacy `market.stock_state_current` dừng ở trading date `2026-09-24`;
- `shadow.minute_bars` đã có `2026-10-01`;
- `ccc_engine.current_state` đã có `2026-10-01`, khoảng 800 rows và các metric RVOL/MA/Price5/15 đang cập nhật.

Do đó trước public phải kiểm tra toàn bộ `/api/v2/quote`, `/api/v2/stock-detail`, `/api/v2/ccc`, `/api/v2/scanner` để đảm bảo đọc state/current contract đúng của engine mới, không dựa vào lớp legacy stale.

Đây là P0 riêng với redesign UI.

---

## 16. Admin / Articles future architecture

Không đưa vào P0 Beta 10/10, nhưng shell/menu/data model phải không chặn mở rộng.

### Public future

- News / Bài viết.
- Bài phân tích/giải thích CCC.
- Tin nổi bật ở right rail.

### Admin future

Route riêng ví dụ `/admin`, chỉ hiển thị cho admin role.

Dashboard admin dự kiến quản lý:

- users;
- package/subscription/VIP state theo policy;
- article/post content;
- draft/published status;
- category/tag;
- cover image/excerpt/body;
- publish schedule;
- audit trail cơ bản.

Admin không trộn vào public user navigation nếu user không có admin role.

---

## 17. Repo audit — mâu thuẫn và tài liệu cần supersede/rewrite

### 17.1. `docs/architecture/V3_SHELL_LAYOUT.md` — **MÂU THUẪN TRỰC TIẾP**

Hiện lock:

```text
48px compact navigation | 240px left rail | center | 240px right rail
```

V4 chuyển sang true 3-column workspace:

```text
~224px global sidebar | center | ~288–320px contextual rail
```

Filter/Radar không còn mặc định chiếm permanent left rail theo từng route.

**Action:** rewrite file theo Master V4.

### 17.2. `docs/product/V3_PERMISSIONS.md` — **PHẦN LỚN PHÙ HỢP, CẦN BỔ SUNG**

Đã đúng với quyết định mới ở các điểm:

- quote/company public;
- MA10/MA200 + distance public;
- RVOL/Price5/15/ATO/ATC/signal protected;
- entitlement enforce server-side;
- no raw signal thresholds in browser.

Cần bổ sung:

- Discovery / Tracked / Full-market semantic;
- public Market/Scanner basic rows;
- filter scope anti-leak;
- AI Search scope theo public/protected field.

**Action:** amend/rewrite version mới, không đảo ngược các quyền public đã duyệt.

### 17.3. `docs/architecture/V3_DATA_SOURCE_OWNERSHIP.md` — **ĐÃ LỖI THỜI**

File cũ còn mô tả NEW Supabase `ccc-ssi-v2` là temporary V3 market persistence rồi migrate sang VPS PostgreSQL.

Repo `AGENTS.md` hiện hành đã khóa lại:

- VPS CCC Engine + SQLite là canonical hiện tại;
- PostgreSQL VPS là target dài hạn;
- NEW Supabase chỉ remote audit mirror, async/fail-open/best-effort.

**Action:** rewrite `V3_DATA_SOURCE_OWNERSHIP.md` để khớp AGENTS/current runtime.

### 17.4. Theme — **CODE HIỆN TẠI MÂU THUẪN VỚI QUYẾT ĐỊNH MỚI**

`website-v2-react/src/styles/globals.css` vẫn có `html[data-theme="light"]`.

`AppShell.jsx` và `StockDetailShell.jsx` vẫn có:

- `theme` state;
- localStorage `ccc-theme`;
- light/dark toggle;
- mobile theme action.

**Action khi code V4:** bỏ dual-theme behavior, giữ one canonical dark theme.

Các tài liệu/phase report cũ yêu cầu Light/Dark được coi là historical và bị Master V4 supersede cho Beta 10/10.

### 17.5. Shell implementation — **CẦN HỢP NHẤT**

`AppShell.jsx` hiện dùng generic shell cho một số route nhưng lại chuyển `Stock Detail`, `Scanner`, `Account` sang `StockDetailShell`.

Điều này tạo hai shell/hệ nav cùng tồn tại.

**Action:** V4 dùng một App Shell chung.

### 17.6. Mobile hamburger — **CODE HIỆN TẠI CHƯA KHỚP**

Trong `stock-detail-shell.css`, mobile hiện hide `.stock-menu-button`.

Trong khi V4 yêu cầu hamburger mobile là navigation đầy đủ.

**Action:** mobile header giữ hamburger; bottom nav chỉ là shortcut.

### 17.7. Scanner left rail — **CẦN CHUYỂN VAI TRÒ**

`ScannerShell.jsx` hiện dùng:

- left rail = filter/sort;
- center = results;
- right rail = AI/community.

V4 yêu cầu:

- left = global navigation/workspace;
- filter/sort = center toolbar + panel/sheet;
- right = contextual utilities.

`Scanner` mobile card implementation hiện tại có thể tái sử dụng và polish, không cần viết lại từ zero.

---

## 18. Những thứ nên giữ từ code hiện tại

- React/Vite codebase `website-v2-react/`.
- `/api/v2/*` and `/api/v2/live` boundary.
- Auth context.
- stock search logic.
- chart engine/lazy history/live WS.
- stock logo.
- scanner data normalize/merge/filter/sort utilities sau khi entitlement contract được chuẩn hóa.
- mobile card direction.
- fundamental/BCTC clients.
- loading/error/unavailable patterns có thể tái sử dụng.

Không rewrite frontend từ đầu.

---

## 19. Những thứ cần refactor cho V4

1. One unified App Shell.
2. True 3-column desktop geometry.
3. Full left sidebar + current menu.
4. Wider contextual right rail.
5. Filter/sort moves out of permanent left rail.
6. Working hamburger mobile.
7. One dark theme, remove theme toggle.
8. Button/tag/status hierarchy.
9. Entitlement semantic centralized.
10. Data freshness state.
11. Connect P0 market/API state to current CCC Engine.
12. AI Search route/panel wiring according to entitlement.

---

## 20. Beta 10/10 Definition of Done

- Current-session data visible; no stale 24/09 presentation as live.
- Market/Watchlist/Stock Detail share consistent API contracts.
- Public vs CCC-protected fields enforce server-side.
- MA10/MA200 + distance public.
- RVOL/Price5/15/Signal/ATO-ATC protected outside entitlement.
- VIP/full-market sees full CCC intelligence across universe.
- Filter scope cannot leak premium fields.
- AI scope cannot leak premium fields.
- Desktop shell stable at 1440/1680.
- Mobile 375/390 usable without desktop-table shrink.
- Hamburger works.
- No theme toggle/light-theme QA in Beta.
- No dead buttons presented as working controls.
- Stock Detail cards/tabs are wired or explicitly unavailable.
- Loading/error/stale/missing/locked states are intentional.
- Cache/deploy smoke check complete.
- 09/10 is release-candidate/regression day, not feature-development day.

---

## 21. Recommended implementation order

### Foundation

1. Rewrite/lock docs in section 17.
2. Figma: Desktop Shell + Mobile Shell.
3. Implement unified shell/theme/navigation.
4. Lock responsive breakpoints.

### Core product

5. Market/Watchlist table + mobile cards.
6. Entitlement display/access semantics.
7. Stock Detail wiring and stale-data handling.
8. Scanner/filter/sort/column controls.
9. Right rail context.
10. AI Search.

### Release hardening

11. Auth/package/VIP QA.
12. Mobile QA.
13. Data freshness/degraded QA.
14. Regression/deploy/cache QA.

---

## 22. Source-of-truth rule

Sau khi Product Owner duyệt Master V4 này:

- Các yêu cầu trong Master V4 **supersede** layout/theme/permission wording cũ nếu có xung đột.
- `AGENTS.md` vẫn là repository safety/architecture authority.
- Backend core logic/RVOL/baseline/signal thresholds không thay đổi chỉ vì redesign frontend.
- Mọi thay đổi sản phẩm mới sau đây phải cập nhật Master trước hoặc tạo amendment rõ ràng.
