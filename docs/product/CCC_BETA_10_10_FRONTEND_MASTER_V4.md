# CCC Beta 10/10 — Frontend & Product Master V4

**Ngày cập nhật:** 2026-10-02  
**Mốc public dự kiến:** 2026-10-10  
**Repo:** `manhcang2026/vnstock-market-scanner`  
**Frontend:** `website-v2-react/`  
**Backend / SSI runtime:** `services/ssi_realtime_shadow/`  
**Branch triển khai V4:** `feat/ccc-v4-beta-1010`  
**Trạng thái:** PRODUCT + UX SOURCE OF TRUTH cho Beta 10/10.

---

# 0. Quy tắc nguồn chuẩn

Tài liệu này khóa kiến trúc sản phẩm/frontend V4.

Khi có xung đột:

1. `AGENTS.md` vẫn là authority về repository safety, market-data ownership và invariant backend.
2. Signal Engine V2 config hiện hành trong:
   `services/ssi_realtime_shadow/config/ccc_signal_v2_beta_config.yaml`
   là source of truth cho canonical signal/state thresholds và contract.
3. Tài liệu này là source of truth cho:
   - IA/navigation;
   - UX;
   - presentation;
   - Community;
   - News/Articles;
   - Notification;
   - Account/Settings;
   - VIP personalization UX;
   - responsive behavior;
   - release scope.
4. Frontend không được tự dựng lại signal bằng threshold.
5. Missing data != zero.

Các wording V3/V4 cũ trái với tài liệu này được xem là superseded.

---

# 1. Product loop của CCC Beta

CCC không cố trở thành một website chứng khoán “có mọi thứ”.

Vòng lặp sản phẩm chính:

**Quan sát thị trường  
→ phát hiện mã đáng chú ý  
→ hiểu trạng thái CCC và lý do  
→ theo dõi mã  
→ đi sâu Stock Detail  
→ thảo luận / hỏi AI  
→ nhận alert khi có thay đổi có ý nghĩa.**

Các trụ cột Beta:

1. Tổng quan.
2. Thị trường.
3. Đã theo dõi.
4. Khám phá:
   - AI Search;
   - Bộ lọc;
   - Sàng lọc CCC.
5. Stock Detail.
6. CCC State Engine V2 presentation.
7. Cộng đồng.
8. Tin tức / Bài viết.
9. Notification.
10. Account & Settings.
11. Mod Dashboard.
12. Admin Dashboard.
13. Auth / package / VIP / entitlement.
14. Responsive desktop/mobile.
15. Data freshness / missing / stale / degraded.

---

# 2. App Shell V4

## 2.1 Một shell duy nhất

Tất cả route chính dùng cùng một `AppShell`.

Shell sở hữu:

- top header;
- global left sidebar;
- center workspace;
- contextual right rail;
- mobile drawer;
- mobile bottom navigation;
- global search;
- notification entry;
- settings/account entry.

Stock Detail là một route/context bên trong shell, không có shell riêng.

## 2.2 Desktop geometry

```text
TOP BAR: 52–56px

LEFT SIDEBAR | CENTER WORKSPACE        | RIGHT CONTEXT
~224px       | minmax(0, 1fr)         | ~288–320px
```

Target:

- >= 1440px: full 3-column.
- 1280–1439px: compact 3-column.
- 1024–1279px: left + center; right context chuyển inline/panel/drawer.
- <= 900px: không có permanent left/right rail; center 100%.

Center luôn là vùng chính.

Không dùng route-level max-width gây gutter lớn hoặc route jitter.

---

# 3. Visual identity

## 3.1 Một dark theme duy nhất

Beta 10/10 không làm Light/Dark toggle.

## 3.2 DNA màu CCC cũ

Giữ cảm giác quen thuộc với user cũ:

- page background: navy-black rất tối;
- surface/panel: dark navy/near-black;
- elevated surface: sáng hơn nhẹ;
- border: mảnh, trung tính;
- primary text: off-white;
- secondary text: gray/blue-gray;
- positive price: green;
- negative price: red/coral;
- public technical/action/link: blue/cyan;
- CCC intelligence / AI: violet/purple;
- warning/weakening: amber/yellow.

Không dùng:

- neon dashboard;
- glassmorphism;
- gradient lòe loẹt;
- màu user chat ngẫu nhiên;
- green/red cho UI không mang semantic thị trường.

## 3.3 Palette direction

Reference direction:

```text
background   #0A0D16
surface      #0B0F18
surface-2    #11141E
elevated     #171A24
border       #25272F
text         #F7F7F7
muted        #9F9F9F
blue         #61A3E6
purple       #B180FC
green        #43A84C
red          #E7454A
yellow       #E4B84F
```

Đây là visual direction, không phải bắt buộc hard-code y hệt ở mọi component.

---

# 4. Global navigation

## 4.1 Primary navigation Beta

Desktop sidebar:

1. **Tổng quan**
2. **Thị trường**
3. **Đã theo dõi**
4. **Khám phá**
5. **Tin tức / Bài viết**
6. **Cộng đồng**
7. **Học viện** — chỉ public nếu có nội dung thật; không để dead route.

Stock Detail không phải menu item.

## 4.2 Workspace cá nhân

Section:

**DANH SÁCH CỦA TÔI**

Có thể hiển thị:

- Danh sách theo dõi;
- Bluechip;
- Ngân hàng;
- Thép;
- các list custom trong tương lai.

Nếu backend multi-watchlist chưa có, UI không được giả vờ có chức năng thật.

## 4.3 Role navigation

Chỉ render khi user có quyền:

- **Mod Dashboard**
- **Admin Dashboard**

User thường không thấy hai mục này.

## 4.4 Không có menu “Công cụ”

Các công cụ thị trường được tích hợp trong **Thị trường**.

---

# 5. Header

Desktop header:

```text
CCC Logo / Brand
→ Global Search
→ AI shortcut
→ Market status / VN time
→ Notification
→ Help
→ Settings
→ Account
```

Rules:

- Notification có chức năng thật.
- Settings không dùng cho theme toggle.
- Settings + Account dẫn vào cùng một hub.
- Không render dead icon.
- Global Search tìm ticker/company; có thể mở Stock Detail trực tiếp.
- AI shortcut mở `Khám phá / AI Search`.

Mobile:

```text
☰  CCC        Search   Notification   Account
```

---

# 6. Mobile navigation

Bottom navigation chính:

1. Tổng quan
2. Thị trường
3. Theo dõi
4. Khám phá
5. Thêm

`Thêm` mở:

- Tin tức / Bài viết;
- Cộng đồng;
- Học viện;
- Tài khoản & Cài đặt;
- Mod Dashboard nếu có quyền;
- Admin Dashboard nếu có quyền.

Hamburger vẫn là navigation đầy đủ.

Không co desktop table xuống mobile.

---

# 7. Tổng quan — Dashboard

Tổng quan là dashboard thật, không phải Watchlist page.

Center priority:

## 7.1 AI Search Hero

Đặt cao, dễ thấy:

**Hỏi CCC AI**

Ví dụ prompt:

- “RVOL30 tăng nhưng giá chưa chạy”
- “Mã gần MA200”
- “Ngân hàng có dòng tiền xuất hiện”

AI không phải nguồn dữ liệu.
AI dịch câu hỏi thành intent/filter/action; backend CCC query dữ liệu thật.

## 7.2 Trạng thái CCC hôm nay

Hiển thị phân bố canonical state:

- WATCHING
- FLOW_APPEARING
- FLOW_PRICE_CONFIRMED
- MOMENTUM_MAINTAINED
- MOMENTUM_WEAKENING
- SELLING_PRESSURE

NORMAL có thể không cần chiếm nhiều diện tích nếu không hữu ích.

Không hiển thị “đạt 2/4 / 3/4 / 4/4 tín hiệu”.

## 7.3 Chuyển trạng thái mới

Hiển thị event/state transition có ý nghĩa:

```text
$FPT
WATCHING → FLOW_APPEARING
Reason: RVOL30_STRONG · PRICE15_UP
```

## 7.4 Watchlist snapshot

5–8 mã quan trọng.

## 7.5 Chợ chung

Module chat chung đủ lớn để có giá trị:

- user chưa login được đọc;
- login mới gửi;
- realtime;
- `$FPT` click mở Stock Detail;
- `@username` tạo mention.

## 7.6 Right rail

Có thể gồm:

- chỉ số / toàn cảnh thị trường;
- mã đang được nhắc nhiều;
- tin nổi bật;
- notification nhỏ.

Không nhồi tất cả widget cùng lúc.

---

# 8. Thị trường

Thị trường là workspace chung của toàn market.

Sub-navigation:

```text
Danh sách | Ngành | So sánh | Biểu đồ
```

Đây là nơi tích hợp “Công cụ” cũ.

Center:

- market breadth;
- filter;
- sort;
- column settings;
- dense table desktop;
- card mobile.

Row ưu tiên:

- identity;
- current price;
- change;
- basic volume;
- MA10/MA200 / distance;
- CCC state nếu entitled;
- row action.

Mã ngoài entitlement:

- vẫn thấy public layer;
- protected CCC data phải khóa thật ở backend;
- không blur cả dòng;
- có CTA thêm Watchlist nếu phù hợp.

---

# 9. Đã theo dõi

Watchlist là nơi user thấy đầy đủ CCC Intelligence theo entitlement.

Center:

- summary;
- alert summary;
- filter/sort;
- table/card;
- state meter;
- state name;
- public market metrics;
- protected metrics.

Right rail:

- recent state transitions;
- personal lists;
- watchlist alerts.

---

# 10. Khám phá

Một top-level route duy nhất:

```text
AI Search | Bộ lọc | Sàng lọc CCC
```

## 10.1 AI Search

Ví dụ:

> “Khối lượng 30 phút tăng nhưng giá chưa tăng, cách MA200 dưới 5%.”

UI phải cho user thấy AI đã hiểu thành điều kiện gì.

Kết quả phải hiển thị:

- symbol;
- dữ liệu khớp;
- lý do khớp;
- phạm vi quyền.

## 10.2 Bộ lọc

Public filter toàn market:

- exchange;
- industry;
- price;
- change;
- basic volume;
- above/below MA10/MA200;
- distance MA10/MA200.

Protected filter:

- Day RVOL;
- RVOL15;
- RVOL30;
- Price5 / Price15;
- canonical CCC State;
- ATO/ATC intelligence.

Protected field chỉ query trong effective entitlement.

## 10.3 Sàng lọc CCC

Preset/state-based discovery:

- Theo dõi;
- Dòng tiền xuất hiện;
- Dòng tiền + giá xác nhận;
- Động lượng duy trì;
- Động lượng suy yếu;
- Áp lực bán;
- ATO/ATC conditions khi backend hỗ trợ/trust.

“Gần MA200” là filter theo distance MA, không phải canonical CCC state.

---

# 11. CCC State Engine V2 — frontend contract

## 11.1 Engine mới là state machine

Không còn frontend concept:

- 4 tín hiệu độc lập;
- đạt 2/4;
- đạt 3/4;
- đạt 4/4.

Canonical states:

| State | Level | Direction | UX label |
|---|---:|---|---|
| `NORMAL` | 0 | NEUTRAL | Bình thường |
| `WATCHING` | 1 | NEUTRAL | Theo dõi |
| `FLOW_APPEARING` | 2 | BULLISH | Dòng tiền xuất hiện |
| `FLOW_PRICE_CONFIRMED` | 3 | BULLISH | Dòng tiền + giá xác nhận |
| `MOMENTUM_MAINTAINED` | 4 | BULLISH | Động lượng duy trì |
| `MOMENTUM_WEAKENING` | 2 | NEUTRAL | Động lượng suy yếu |
| `SELLING_PRESSURE` | 3 | BEARISH | Áp lực bán |

Frontend phải dùng backend output:

- `signal_state`;
- `signal_level`;
- `signal_direction`;
- `reason_codes`;
- `signal_summary_vi`;
- `quality`;
- `config_version`;
- `engine_version`.

Frontend không apply canonical thresholds.

## 11.2 “4 cục màu” được giữ nhưng đổi semantic

CCC giữ visual 4 block quen thuộc.

Ý nghĩa mới:

**4 block = `signal_level` 0–4.**

Không phải “4 điều kiện”.

Direction/color:

- NORMAL: gray;
- WATCHING: blue;
- bullish states: green;
- MOMENTUM_WEAKENING: amber;
- SELLING_PRESSURE: red.

Ví dụ:

```text
□□□□  Bình thường
■□□□  Theo dõi
■■□□  Dòng tiền xuất hiện
■■■□  Dòng tiền + giá xác nhận
■■■■  Động lượng duy trì
■■□□  Động lượng suy yếu
■■■□  Áp lực bán
```

Table/list:
- meter + compact state label.

Stock Detail:
- meter;
- state label;
- level;
- direction;
- summary;
- reason codes;
- data quality/trust.

## 11.3 Reason codes

Reason codes là giải thích deterministic của backend.

Frontend có thể map code → Vietnamese label/tooltip, nhưng không dùng code để tự reconstruct state.

## 11.4 MA context

MA10/MA200 là public technical context.

`ABOVE_MA10`, `BELOW_MA10`, `ABOVE_MA200`, `BELOW_MA200` có thể xuất hiện trong reason/context.

Không tự tạo `NEAR_MA10/NEAR_MA200` canonical reason nếu backend chưa bật.

---

# 12. ATO / ATC Intelligence

ATO/ATC không phải một hệ signal riêng ở frontend.

ATO/ATC là:

- auction metrics;
- reason/evidence;
- context có thể dẫn tới canonical state.

UX có thể hiển thị:

- opening/closing RVOL;
- gap / price impact;
- volume share;
- baseline quality;
- reason codes;
- resulting state.

Không infer khi evidence thiếu.

---

# 13. VIP — CCC cá nhân / ngưỡng cá nhân

Đây là feature quan trọng trong **Tài khoản & Cài đặt**.

Route/tab:

**CCC cá nhân (VIP)**

## 13.1 Hai lớp state

### Canonical CCC State

- dùng shared server-side config;
- giống nhau cho toàn hệ thống;
- dùng cho Market state / public state contract;
- không bị user chỉnh.

### VIP personalization overlay

- chỉ áp dụng cho user;
- phục vụ personal scanner/filter/alert;
- không mutate canonical state;
- không thay đổi shared market state.

## 13.2 UX mode

```text
[ Theo chuẩn CCC ]   [ Tùy chỉnh VIP ]
```

Nếu dùng chuẩn CCC:
- không show raw canonical threshold;
- chỉ ghi “Đang sử dụng ngưỡng chuẩn CCC”.

Nếu dùng VIP:
user có thể lưu override riêng.

## 13.3 Nhóm ngưỡng cá nhân

- Day RVOL;
- RVOL15;
- RVOL30;
- Price5;
- Price15;
- ATO:
  - RVOL;
  - gap;
- ATC:
  - RVOL;
  - volume share;
  - price impact;
- state/alert preferences.

Exact fields/validation phải bám backend implementation khi làm case riêng.

## 13.4 Security

Canonical thresholds không expose raw ra browser.

User chỉ thấy:
- override của chính họ;
- preset/mode;
- validation range được backend cho phép.

VIP thresholds phải lưu server-side.

---

# 14. Alert / Notification

Beta notification chỉ ưu tiên:

1. mention trong chat;
2. meaningful Signal/Watchlist state transition;
3. System/Admin announcement.

## 14.1 Anti-noise là requirement

Không spam.

Signal/watchlist alert cần:

- event/state-change based;
- dedupe;
- cooldown;
- grouping theo symbol/event;
- không lặp nếu state chưa thay đổi có ý nghĩa.

Ví dụ tốt:

```text
$FPT
WATCHING → FLOW_APPEARING
2 phút trước
```

Không gửi 5 notification chỉ vì metric refresh nhiều lần trong cùng state.

## 14.2 Notification Center

Tabs có thể gồm:

- Tất cả;
- Mention;
- Tín hiệu;
- Hệ thống.

Unread counter phải tiết chế.

---

# 15. Stock Detail

Center priority:

1. identity;
2. quote + freshness;
3. session summary;
4. chart;
5. tabs:
   - Tổng quan;
   - CCC Intelligence;
   - Cơ bản;
   - BCTC.

CCC Intelligence:

- Day RVOL;
- RVOL15;
- RVOL30;
- Price5;
- Price15;
- MA10;
- MA200;
- distance;
- ATO/ATC;
- baseline/quality;
- current canonical state.

Right context:

- session/data status;
- canonical CCC state;
- state summary;
- reason codes;
- **Thảo luận `$SYMBOL`**;
- **Hỏi AI về `$SYMBOL`**.

Discovery mode:
- quote/chart/public MA/Fundamental/BCTC vẫn xem;
- protected CCC panel khóa thật theo entitlement;
- không redirect ra khỏi Stock Detail.

---

# 16. Community / Chat — Beta architecture

## 16.1 Không cần mua thêm chat SaaS cho Beta

Dùng hạ tầng hiện có:

**OLD Supabase** cho:
- Auth;
- Postgres community tables;
- Realtime;
- RLS;
- Storage nếu có attachment/avatar sau này.

Không đặt chat vào CCC market engine.
Community failure không được ảnh hưởng SSI/market runtime.

## 16.2 Beta chat model

Hai context chính:

### Chợ chung
Room global.

### Phòng theo mã
Mỗi symbol có room:

```text
symbol:FPT
symbol:HPG
...
```

User chưa login:
- đọc được.

User login:
- gửi message;
- reply;
- mention;
- reaction;
- report.

## 16.3 Stock tag

Ticker syntax:

```text
$FPT
$HPG
$MBB
```

Parser:
- nhận known symbol;
- render blue/cyan;
- click mở Stock Detail;
- không auto-link text không phải ticker hợp lệ.

## 16.4 Mention

Syntax:

```text
@username
```

Mention:
- màu purple;
- tạo notification;
- server validates target user.

## 16.5 Chat color rules

Không dùng bubble rainbow/random user color.

Semantic:

- message text: off-white;
- metadata/time: muted gray;
- `$TICKER`: blue/cyan;
- `@mention`: purple;
- link: blue;
- Mod badge: amber;
- Admin badge: purple;
- report/warning action: red only when relevant.

Green/red được ưu tiên giữ semantic cho market direction/state; không dùng làm màu trang trí chat.

## 16.6 Layout

Desktop:
- feed row, không bắt buộc speech bubble;
- avatar nhỏ;
- username + timestamp;
- body;
- reply/reaction/report actions.

Mobile:
- full-width message feed;
- sticky/comfortable composer;
- `$TICKER` vẫn tap được.

## 16.7 Moderation

Mod:

- report queue;
- hide/delete message;
- mute user;
- ban user;
- review moderation history;
- duyệt bài viết.

Admin:
- có toàn quyền Mod;
- role management;
- user management;
- system broadcast.

Mọi moderation action cần audit log.

## 16.8 Anti-spam

Beta cần tối thiểu:

- authenticated write;
- RLS;
- message rate limit;
- duplicate spam guard;
- report;
- mute/ban;
- length limits;
- sanitized content;
- server-side permission checks.

---

# 17. News / Articles / CMS — Beta architecture

## 17.1 Có trong Beta

Không để sau 10/10.

Public:

- article feed;
- category;
- article detail;
- featured article;
- related articles;
- optional article discussion link.

Admin/Mod:

- draft;
- review;
- approve;
- publish;
- edit;
- unpublish;
- category/tag;
- audit.

## 17.2 CMS approach

Không cần cài WordPress/Strapi/Sanity/Contentful cho Beta.

Dùng:

- existing React frontend;
- Supabase Postgres;
- Supabase Storage;
- internal Admin Dashboard.

Rich-text editor khuyến nghị:

**TipTap**

Lý do:
- React-friendly;
- extensible;
- có heading/list/quote/link/image;
- dễ thêm custom `$TICKER` node/link sau này;
- tránh phải dựng editor từ zero.

Có thể thay TipTap bằng editor khác nếu repo đã có dependency phù hợp, nhưng không cần thêm external CMS SaaS.

## 17.3 Article image support

Bài viết **có hình ảnh**.

Tối thiểu:

### Cover image
- optional nhưng khuyến khích cho featured article;
- target ratio 16:9;
- khoảng 1200×675 hoặc tương đương;
- responsive;
- alt text.

### Inline image
- cho phép trong body;
- charts / screenshots / company visuals;
- max-width theo article body;
- caption optional;
- alt text.

### Thumbnail
- dùng cover image hoặc thumbnail riêng;
- feed card không bắt buộc mọi bài phải có ảnh.

## 17.4 Storage

Ảnh bài viết lưu ở Supabase Storage.

Không base64 vào DB.

DB chỉ lưu:

- storage path/public URL;
- alt;
- caption;
- dimensions nếu hữu ích.

Khuyến nghị resize/compress:
- WebP/JPEG;
- tránh upload file ảnh nhiều MB;
- max article width khoảng 1200–1600px.

Không cần Cloudflare Images trong Beta trừ khi sau này có nhu cầu CDN/image transforms lớn.

## 17.5 External source links

Beta hỗ trợ:

- source title;
- source name;
- URL;
- optional note/thumbnail;
- nhập thủ công bởi Admin/Mod.

Không auto-crawl/re-publish full article bên ngoài.

---

# 18. Account & Settings Hub

Một hub chung:

```text
Hồ sơ
Gói & quyền
Thông báo
Trải nghiệm
Bảo mật
CCC cá nhân (VIP)
```

## Hồ sơ
- display name;
- avatar;
- basic profile.

## Gói & quyền
- current package;
- Watchlist quota;
- VIP/full-market;
- expiration;
- upgrade/manage plan.

## Thông báo
- mention;
- signal/watchlist;
- system/admin;
- channel preferences sau này.

## Trải nghiệm
- table density;
- default list;
- other non-theme UX settings.

Không có Light/Dark.

## Bảo mật
- auth/session security settings phù hợp Supabase Auth.

## CCC cá nhân (VIP)
- personal thresholds/presets/alert rules.

---

# 19. Mod Dashboard

Role-gated.

Beta scope:

- report queue;
- message hide/delete;
- mute;
- ban;
- article review;
- article approve/reject;
- moderation audit.

Không expose cho user thường.

---

# 20. Admin Dashboard

Role-gated.

Beta scope:

- users;
- roles;
- packages;
- VIP/full-market entitlement;
- article CMS;
- categories;
- draft/published;
- community moderation;
- system/admin broadcast;
- notification management;
- audit.

Admin action có ảnh hưởng entitlement/role phải có confirmation + audit trail.

---

# 21. Permissions / Entitlement

## 21.1 Public layer

Ngoài Watchlist vẫn xem:

- symbol/name/exchange;
- current price;
- change;
- basic volume;
- MA10;
- MA200;
- distance MA10/MA200;
- public chart;
- public indicators;
- Fundamental;
- BCTC.

## 21.2 Protected CCC layer

Ngoài effective entitlement không trả:

- Day RVOL;
- RVOL15;
- RVOL30;
- Price5;
- Price15;
- canonical CCC state;
- state level/direction/reasons/summary;
- ATO/ATC Intelligence;
- historical signal journey;
- CCC alerts/personalization.

## 21.3 Semantic access

Frontend nên nhận:

```text
DISCOVERY
TRACKED
FULL_MARKET
```

Không rải package/watchlist/VIP logic ở từng component.

## 21.4 Server-side lock

Không gửi premium data xuống browser rồi hide CSS.

---

# 22. AI entitlement

AI không bypass permission.

Public-field query:
- có thể scan public universe.

Protected-field query:
- non-full-market chỉ scan effective entitled scope;
- full-market/VIP scan full entitled universe.

Deep explanation theo symbol cũng phải respect entitlement.

---

# 23. Data source ownership

Canonical market data:

```text
SSI
→ VPS CCC Engine
→ canonical VPS storage
→ /api/v2/*
→ /api/v2/live
→ Frontend
```

OLD Supabase giữ:

- Auth;
- profiles;
- watchlists;
- plans;
- subscriptions;
- VIP/entitlement;
- metadata;
- Fundamental;
- BCTC;
- Community;
- Article CMS;
- Storage.

NEW Supabase `ccc-ssi-v2`:
- audit mirror only nếu còn sử dụng;
- không phải browser dependency.

---

# 24. Data states

UI phải phân biệt:

- Loading;
- Live/current;
- Outside market hours;
- Stale;
- Missing;
- Degraded;
- Locked;
- Error.

Không biến NULL thành zero.

Không trình bày trading date cũ như live.

---

# 25. P0 data cutover

Trước public phải verify:

- `/api/v2/quote/{symbol}`;
- `/api/v2/stock-detail/{symbol}`;
- `/api/v2/ccc/{symbol}`;
- `/api/v2/scanner`;
- `/api/v2/live`.

Frontend không biết DB table vật lý.

Legacy stale state không được trở thành source của Beta V4.

---

# 26. Beta route map

Direction:

```text
/                         Tổng quan
/thi-truong               Thị trường
/danh-sach                Đã theo dõi
/kham-pha                 Khám phá
/tin-tuc                  Tin tức / Bài viết
/tin-tuc/:slug            Article Detail
/cong-dong                Cộng đồng
/co-phieu/:symbol         Stock Detail
/tai-khoan                Account & Settings
/mod                      Mod Dashboard
/admin                    Admin Dashboard
```

Exact route migration có thể reuse route cũ trong từng implementation case để tránh phá deploy.
Không cần đổi toàn bộ URL trong một lần nếu có compatibility risk.

---

# 27. Component hierarchy

Shared:

- `AppShell`
- `GlobalHeader`
- `GlobalSidebar`
- `MobileNav`
- `RightContext`
- `CCCStateMeter`
- `CCCStateBadge`
- `DataFreshness`
- `LockedField`
- `StockTag`
- `MentionTag`
- `NotificationBell`
- `NotificationCenter`

Feature:

- Overview;
- Market;
- Watchlist;
- Discover;
- StockDetail;
- Community;
- Articles;
- AccountSettings;
- Mod;
- Admin.

---

# 28. Release scope priority

## P0 — phải hoạt động

- unified shell;
- navigation;
- dark theme;
- Market;
- Watchlist;
- Stock Detail;
- current CCC state presentation;
- State Meter;
- filter;
- AI Search;
- public/protected entitlement;
- Community basic realtime chat;
- `$TICKER`;
- per-stock chat;
- Articles feed/detail;
- basic internal CMS;
- Notification Center;
- mention notification;
- state/watchlist alert anti-noise;
- Account & Settings;
- Mod basic moderation;
- Admin users/roles/CMS/community;
- mobile nav;
- data freshness states.

## P1 — có thể giảm sâu nếu release risk

- advanced article scheduling;
- advanced reactions;
- media attachments trong chat;
- rich community profiles;
- complex Academy content;
- highly advanced multi-watchlist management;
- personalized VIP threshold engine nếu backend chưa kịp — nhưng UI/contract phải khóa đúng và không fake chức năng.

Nếu VIP personal thresholds chưa backend-ready:
- giữ UI gated/coming-soon rõ ràng;
- không present như working feature.

---

# 29. Technical recommendation — Community

Beta implementation recommendation:

```text
Supabase Auth
+ Supabase Postgres
+ Supabase Realtime
+ RLS
+ optional Supabase Storage
```

Không thêm Firebase/Pusher/Ably/Stream Chat trong Beta.

Lý do:
- auth đã ở Supabase;
- 200-user target chưa cần thêm realtime vendor;
- dễ role/moderation;
- giảm số hệ thống phải vận hành.

Community không được phụ thuộc market engine.

---

# 30. Technical recommendation — Articles

Beta implementation recommendation:

```text
React
+ TipTap editor
+ Supabase Postgres
+ Supabase Storage
+ Admin/Mod role
```

Không thêm external CMS SaaS nếu không có lý do rõ.

Article content ưu tiên lưu structured editor JSON + metadata.
Renderer phải sanitize/whitelist node types.

---

# 31. Figma source

File UX master:

`CCC Beta V4 — IA & UX Master`

Figma file key:

`WBRUSKjrRarAqmRf5nE3lx`

Figma là visual/interaction reference.
Tài liệu này là product/architecture reference.

Nếu Figma và Master xung đột:
- product/data/security/state contract theo Master + backend config;
- visual spacing/composition theo Figma sau khi Product Owner duyệt.

---

# 32. Implementation order mới

## Foundation
1. Update Master V4 này.
2. Lock State Engine V2 presentation + State Meter.
3. Lock IA/routes/header/mobile.
4. Update Figma.

## Frontend shell
5. Reconcile current uncommitted `V4-SHELL-01` với IA mới.
6. Implement final global sidebar/header.
7. Implement mobile bottom nav + More menu.

## Core market
8. Market.
9. Watchlist.
10. Stock Detail.
11. CCC State Meter/state presentation.
12. Entitlement.
13. Data freshness/cutover.

## Discovery
14. AI Search.
15. Filter.
16. CCC state screening.

## Community/content
17. Community schema + Realtime + moderation.
18. `$TICKER` / `@mention`.
19. per-stock room.
20. Notification integration.
21. Articles schema + Storage + TipTap.
22. Article feed/detail.
23. Admin CMS.

## Account/roles
24. Account & Settings.
25. VIP personalization contract/UI.
26. Mod Dashboard.
27. Admin Dashboard.

## Release
28. responsive QA.
29. auth/package/VIP QA.
30. community moderation QA.
31. CMS image QA.
32. deploy/cache smoke test.
33. 09/10 feature freeze/regression.
34. 10/10 public.

---

# 33. Definition of Done — Beta 10/10

- one shared shell;
- one dark theme;
- menu matches approved IA;
- Header search/AI/notification/settings/account functional;
- Market/Watchlist/Stock Detail use current data;
- no stale 24/09 shown as live;
- State Engine V2 presentation correct;
- no old “2/4, 3/4, 4/4 signal” wording;
- four-block meter means `signal_level`;
- canonical state/reasons come from backend;
- MA public rules preserved;
- protected CCC fields server-enforced;
- AI/filter cannot leak premium fields;
- Community readable by guest, writable by login;
- `$TICKER` works;
- Stock Detail has symbol discussion;
- mention notification works;
- state alert dedupe/cooldown/grouping implemented;
- article feed + detail works;
- article images work;
- CMS role permission works;
- Mod moderation works;
- Admin users/roles/content works;
- Account & Settings unified;
- VIP threshold UX does not mutate canonical state;
- mobile 375/390 usable;
- no dead buttons;
- missing != zero;
- 09/10 is regression day, not architecture day.

---

# 34. Explicitly superseded concepts

The following are no longer valid V4 product concepts:

- permanent 48px icon rail;
- route-specific Scanner left filter rail as global layout;
- separate StockDetailShell;
- dual Light/Dark theme;
- “Nghiên cứu” as primary navigation;
- “Sàng lọc cơ bản” as separate primary navigation;
- separate “Công cụ” primary navigation;
- old `2/4`, `3/4`, `4/4` signal score;
- “Tích lũy”, “RVOL cao”, “Gần MA200” used as canonical CCC state labels;
- frontend signal reconstruction;
- external CMS/chat SaaS as a Beta requirement.

---

# 35. Final product principle

CCC V4 phải cho cảm giác:

**quen màu sắc, mới cách tổ chức, rõ dữ liệu, rõ trạng thái, ít nhiễu, có cộng đồng, có nội dung, và AI thực sự nằm trong workflow.**

Mọi phần mới phải phục vụ một trong ba việc:

1. giúp user phát hiện điều đáng chú ý;
2. giúp user hiểu tại sao;
3. giúp user tiếp tục theo dõi/thảo luận mà không bị spam hoặc rối.
