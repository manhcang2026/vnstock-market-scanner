# CCC UI/UX MASTER v1.1

**Product:** Chuyện Chợ Chứng  
**Status:** LOCKED STANDARD  
**Version:** 1.1  
**Baseline:** HawkHost static frontend `v18.5-final800-near-ma`  
**Scope:** Toàn bộ giao diện người dùng của Chuyện Chợ Chứng; `website/` là production và `website-next/` là v19 staging implementation target.

---

# 0. Authority

Tài liệu này là chuẩn UI/UX nền tảng cấp cao của sản phẩm. Với Phase 1, locked Port Contract là đặc tả chuyên biệt đã được Product Owner duyệt.

Khi có xung đột, áp dụng theo thứ tự:

1. Yêu cầu sản phẩm được Product Owner phê duyệt rõ ràng.
2. `CCC_PHASE1_DESIGN_PORT_CONTRACT_v1.0.md` cho Phase 1 implementation.
3. `CCC_UIUX_MASTER.md`.
4. `CCC_LOVABLE_PHASE1_DESIGN_REFERENCE_v1.0.md` cho visual direction đã duyệt.
5. `CCC_COMPONENT_RULES.md`.
6. `CCC_PAGE_PATTERNS.md`.
7. Hành vi production và data contract thật.
8. UI/UX Pro Max hoặc các nguồn tham khảo khác.
9. Sở thích cá nhân của designer/coder/AI.

> Do not redesign Chuyện Chợ Chứng from personal preference.  
> Design decisions must follow real product data, CCC standards, and the user's task.

---

# 1. Production reality — LOCKED

## 1.1 Frontend thật

Production frontend hiện tại là static website chạy trên HawkHost:

```text
website/
├── index.html
├── .htaccess
├── VERSION.txt
├── favicon.ico
├── favicon.svg
├── robots.txt
└── assets/
    ├── app-v18.5.js
    └── styles-v18.5.css
```

Không được giả định có React/TanStack/Lovable runtime nếu chưa có quyết định migration riêng.

`website-next/` là v19 staging/next-generation implementation target. Nó không thay thế production source of truth cho tới khi QA đạt và Product Owner duyệt promotion.

## 1.2 Routes thật

| Route | Vai trò |
|---|---|
| `/` | Tổng quan tín hiệu |
| `/danh-sach` | Scanner / danh sách cổ phiếu |
| `/so-sanh-theo-nganh` | So sánh doanh nghiệp cùng ngành |
| `/sang-loc-co-ban` | Sàng lọc nền tảng doanh nghiệp |

Mọi redesign phải bao phủ đủ cả 4 route hiện có.

## 1.3 Data sources thật

Frontend hiện đọc dữ liệu Supabase qua publishable frontend key:

- `stock_snapshot`
- `financial_latest`
- `stock_metadata`
- `financial_quarterly`

Ngoài ra, chi tiết cổ phiếu có link BCTC tới VietstockFinance.

### `stock_snapshot`

Dùng cho:

- mã;
- sàn;
- giá;
- % thay đổi;
- khối lượng lũy kế;
- KLTB10;
- MA10;
- MA200;
- khoảng cách MA10/MA200;
- RVOL30;
- số phiên RVOL30;
- bốn tín hiệu kỹ thuật;
- trạng thái dữ liệu;
- thời gian cập nhật.

### `financial_latest`

Dùng cho:

- nhóm ngành / `website_group`;
- lợi nhuận so cùng kỳ;
- thu nhập/doanh thu so cùng kỳ;
- tăng trưởng quý;
- ROE;
- ROA;
- nợ/vốn;
- nợ/tài sản;
- P/E;
- P/B;
- trạng thái freshness;
- Điểm cơ bản.

### `stock_metadata`

Dùng cho:

- tên công ty đầy đủ;
- tên hiển thị;
- nhóm ngành metadata.

### `financial_quarterly`

Dùng cho lịch sử quý trong Stock Detail.

Không được trình bày field chưa tồn tại như dữ liệu production thật.

## 1.4 Product data/access hierarchy — LOCKED

```text
PUBLIC LAYER
Market Quote + Fundamental Research

MEMBERSHIP LAYER
CCC Technical Intelligence

PERSONALIZATION LAYER
Watchlist + Alerts + Account
```

Public Market Quote cho mọi mã gồm ticker, company/display name, exchange, current price, percentage change và current accumulated volume.

Public Fundamental Research gồm các field tài chính thật đã liệt kê ở trên, score + coverage, freshness, quarterly history và BCTC link khi tồn tại. Missing-data principle không đổi.

Protected CCC Technical Intelligence gồm KLTB10, KL ngày/KLTB10, MA10/MA200 và khoảng cách, RVOL30/sessions, bốn signals, signal count, CCC Signal Rail, technical discovery identities và technical alerts.

> Market quote is public.
>
> Fundamental research is public.
>
> CCC technical intelligence is protected.

Fundamental Research không được trộn trực quan với protected technical intelligence chỉ vì hai nhóm dữ liệu cùng tồn tại cho một mã.

---

# 2. Scanner universe — LOCKED PRODUCT RULE

Frontend không quản lý scanner universe.

Hiện production kỳ vọng khoảng **800 mã**.

Việc:

- ẩn mã khỏi giao diện;
- xóa khỏi watchlist;
- bỏ theo dõi cá nhân;
- filter;
- sort;

**không được xóa mã khỏi scanner universe và không được làm backend ngừng lấy dữ liệu cho mã đó.**

Thay đổi scanner universe là backend/config operation riêng, không phải UI action bình thường.

---

# 3. Current signal truth — LOCKED

Bốn tín hiệu kỹ thuật production hiện tại:

1. **Giá tăng ≥ 3%**
2. **Khối lượng ngày ≥ 200% KLTB10**
3. **Giá trên MA200**
4. **RVOL30 ≥ 200%**

`signalCount` nằm trong khoảng `0/4` đến `4/4`.

MA10 hiện là chỉ số tham khảo và có sort “Gần MA10 nhất”; MA10 không phải một trong bốn tín hiệu cốt lõi.

Không thay đổi threshold/tín hiệu trong một task chỉ mang tính UI.

---

# 4. Fundamental scoring truth — LOCKED UNTIL BUSINESS RULE CHANGES

Website production hiện có **Điểm cơ bản** dựa trên phần dữ liệu có thể chấm.

Tối đa theo mô hình hiện tại:

- Tăng trưởng: 35 điểm
- Hiệu quả sinh lời: 30 điểm
- Sức khỏe tài chính: 20 điểm
- Định giá: 15 điểm

Tổng tối đa: 100 điểm khi đủ dữ liệu phù hợp.

## Missing-data principle

Mã thiếu dữ liệu:

- không tự động bị loại;
- không được biến phần dữ liệu thiếu thành điểm 0 giả;
- chỉ chấm trên phần có dữ liệu;
- phải hiển thị rõ “điểm đạt / điểm có thể chấm” hoặc coverage tương đương.

Các ngành có mô hình tài chính đặc thù như ngân hàng/chứng khoán/bảo hiểm có thể chưa chấm đủ phần sức khỏe tài chính nếu dữ liệu chuyên ngành chưa đầy đủ.

UI không được che giấu việc này.

---

# 5. Product design philosophy

## 5.1 Design direction

**Calm Financial Intelligence**

Giao diện phải:

- chuyên nghiệp;
- rõ ràng;
- giàu dữ liệu nhưng không ngợp;
- dễ hiểu với người dùng không chuyên;
- đủ nhanh cho người dùng thường xuyên;
- tạo cảm giác dữ liệu đáng tin;
- ưu tiên quyết định hơn trang trí.

Không biến website thành:

- bảng điện neon;
- terminal dành cho developer;
- dashboard AI với hàng chục card ngang trọng lượng;
- landing page marketing.

## 5.2 North Star — 5-second test

Một người dùng phải có thể trả lời rất nhanh:

1. Mã nào đáng chú ý?
2. Vì sao đáng chú ý?
3. Nên xem tiếp dữ liệu gì?

Đối với trang cơ bản/ngành:

1. Doanh nghiệp nào nổi bật?
2. Điểm mạnh/yếu chính là gì?
3. Dữ liệu có đủ để tin vào so sánh không?

---

# 6. Decision hierarchy

Thiết kế theo:

`Decision → Evidence → Detail/Audit`

Không thiết kế theo:

`Có bao nhiêu field → tạo bấy nhiêu card`

## Level A — Decision

Ví dụ:

- mã;
- tên công ty;
- giá và % thay đổi;
- signal strength;
- RVOL30 alert;
- Điểm cơ bản;
- rank/position trong ngành.

## Level B — Evidence

Ví dụ:

- KL ngày / KLTB10;
- MA10/MA200 distance;
- ROE;
- profit YoY;
- P/E, P/B;
- data coverage.

## Level C — Detail/Audit

Ví dụ:

- exact raw values;
- session counts;
- updated_at;
- source;
- quarterly history;
- score component breakdown;
- freshness diagnostics.

Level C không được lấn át Level A.

---

# 7. Data Trust Layer — LOCKED

Mỗi màn hình dữ liệu phải giúp user hiểu:

- dữ liệu vừa cập nhật khi nào;
- hệ thống đang hoạt động hay có cảnh báo;
- dữ liệu nào thiếu/cũ;
- nguồn dữ liệu chính;
- website đang hiển thị snapshot cũ hay mới.

Production hiện có:

- market updated time;
- dashboard checked time;
- total symbols;
- Supabase source;
- system status;
- countdown tới lần kiểm tra tiếp;
- cached fallback khi request lỗi.

## Target presentation

Trust data nên **gọn hơn hiện tại** nhưng luôn sẵn có.

Ví dụ:

`● LIVE · 15:20 · 800 mã · Dữ liệu đầy đủ`

Khi lỗi:

`⚠ Nguồn dữ liệu tạm gián đoạn · đang giữ bản cập nhật gần nhất 15:15`

Không được xóa dữ liệu đang xem chỉ vì refresh tạm lỗi nếu cache hợp lệ còn tồn tại.

---

# 8. Light & Dark mode — LOCKED FEATURE

Production hiện có cả Light và Dark mode.

Current behavior:

- default theme: Dark nếu chưa lưu preference;
- preference lưu trong `localStorage`;
- toggle Light/Dark ở UI.

Redesign phải hỗ trợ **cả hai mode ngay từ đầu**.

Không thiết kế Light trước rồi “đảo màu” để ra Dark sau.

## Dark direction

- navy/slate;
- độ tương phản rõ;
- không pure black toàn trang;
- không neon overload;
- giữ khả năng đọc lâu.

## Light direction

- cool neutral;
- trắng/xám lạnh;
- primary text navy/slate;
- màu tín hiệu tiết chế.

Tất cả semantic state phải có token tương ứng ở cả Light và Dark.

---

# 9. Typography — LOCKED READABILITY PRINCIPLE

## Current baseline

Production đang dùng:

`Inter, system UI, Segoe UI, Arial`

Điều này phù hợp và có thể giữ nếu render tiếng Việt tốt.

Không bắt buộc đổi font chỉ vì xu hướng.

## Readability rule

Essential information không được phụ thuộc vào 9–11px.

Target:

| Role | Desktop | Mobile |
|---|---:|---:|
| Body | 14.5–16px | 15–16px |
| Main table data | 13.5–15px | n/a |
| Symbol | 16–19px | 17–20px |
| Company name | 13–15px | 12.5–14px |
| Important label | ≥12.5–13px | ≥12.5–13px |
| Page title | 24–30px | 21–24px |
| Section title | 17–20px | 16–18px |
| KPI number | 28–36px | 24–30px |

9–11px chỉ được dùng cho metadata thật sự phụ và vẫn phải đọc được.

## Numbers

Giá, %, time, ratios và comparable numeric columns phải dùng tabular numerals.

---

# 10. Semantic color — LOCKED

Color truyền tải trạng thái, không truyền tải “khuyến nghị đầu tư”.

## Core meanings

- Green: positive/up/success/data healthy
- Red: negative/down/error
- Purple: early alert/RVOL emphasis
- Orange: caution/intermediate
- Blue/cyan: informational/technical
- Neutral: no signal/no change/missing-neutral

## Signal colors

`0/4` phải có neutral style riêng.

`1/4…4/4` có thể có semantic progression, nhưng không được dùng wording hoặc màu ngụ ý chắc chắn mua/bán.

## Color-alone prohibition

Không dùng màu là dấu hiệu duy nhất.

Phải kết hợp:

- text;
- count;
- icon;
- label;
- shape;
- status copy.

---

# 11. CCC Signal Rail v1.1

CCC Signal Rail là ngôn ngữ trực quan chính thức của bốn tín hiệu.

## Compact

`● ● ● ○  3/4`

Dùng trong:

- bảng;
- card;
- comparison.

## Explainable

- ✓ Giá tăng ≥ 3%
- ✓ KL ngày ≥ 200% KLTB10
- ✓ Trên MA200
- ○ RVOL30 chưa đạt 200%

Dùng trong Stock Detail.

## 0/4

`○ ○ ○ ○  0/4 — Chưa có tín hiệu`

Không fallback về style 1/4.

---

# 12. Fundamental Score presentation

Điểm cơ bản phải luôn thể hiện được **mẫu số/coverage**.

Preferred:

`72 / 85 điểm có thể chấm`

Hoặc:

`72/85 · độ phủ 85%`

Không chỉ hiển thị `72` nếu user có thể hiểu nhầm đó là 72/100.

## Supporting states

- Good
- Mid
- Low
- Not enough data

Không được chỉ dùng màu.

---

# 13. Responsive strategy

Production hiện có:

- sidebar desktop;
- bottom navigation mobile;
- desktop tables;
- mobile cards/lists.

Đây là hướng kiến trúc đúng và được giữ.

Required validation:

- 375px
- 768px
- 1024px
- 1440px

## Desktop

Data-workbench mindset:

- sidebar;
- compact trust/header;
- tables;
- detail dialog/panel;
- filters rõ.

## Mobile

Decision-card mindset:

- bottom navigation;
- search/filter dễ chạm;
- không ép bảng ngang làm trải nghiệm chính;
- detail full-height modal/sheet nếu cần.

## Tablet

Thiết kế có chủ đích, không phải desktop bị co lại.

---

# 14. Navigation

Current main navigation:

- Tổng quan
- Danh sách cổ phiếu
- So sánh theo ngành
- Sàng lọc cơ bản

Future-ready:

- Watchlist
- Notifications
- Account
- Admin

Không hiển thị route tương lai trước khi chức năng thật tồn tại.

Mobile bottom nav không nên vượt quá số lượng mục dễ chạm/đọc; khi số route tăng phải đánh giá lại IA.

---

# 15. Search, filter, sort

## Current production capabilities

Scanner có:

- tìm theo mã;
- lọc sàn;
- lọc signal;
- sort signal;
- RVOL30 cao/thấp;
- % tăng cao/thấp;
- KL ngày cao/thấp;
- gần MA10;
- gần MA200;
- A–Z.

Fundamental có filter:

- Điểm cơ bản;
- lợi nhuận tăng;
- lợi nhuận tăng ≥20%;
- ROE ≥15%;
- ROE ≥20%.

## UX rule

Không tăng vô hạn số chip trên màn hình.

Khi filter tăng:

- group theo mục;
- dùng command bar/popover/sheet;
- hiển thị active filters;
- có clear-all rõ;
- không reset state bất ngờ.

---

# 16. Industry comparison

Industry page là **Public Fundamental Research** và phải ưu tiên **comparison clarity**.

Các cột cốt lõi hiện tại:

- company identity;
- Điểm cơ bản;
- score coverage;
- profit YoY;
- revenue/income YoY;
- quarterly growth;
- ROE;
- ROA;
- debt/equity;
- debt/assets;
- P/E;
- P/B;
- freshness.

Không đưa signal count, CCC Signal Rail, RVOL30, MA10, MA200 hoặc technical signal columns vào research comparison.

Industry selector phải:

- nhìn thấy đầy đủ ngành trên desktop;
- dễ scroll/chọn trên mobile;
- không cắt tên ngành;
- cho user biết số mã trong ngành.

Numeric columns cần alignment nhất quán.

---

# 17. Fundamental screener

Sàng lọc cơ bản là một **Public Fundamental Research analysis workflow**, không phải collection of cards.

Cần:

1. tiêu chí lọc rõ;
2. giải thích ngắn gọn;
3. result count;
4. bảng/card kết quả;
5. score coverage;
6. link sang chi tiết.

Phần “Cách tính Điểm cơ bản” cần progressive disclosure:

- summary trước;
- rule chi tiết sau.

Không bắt user đọc toàn bộ phương pháp trước khi xem kết quả.

Không đưa technical signal/rail/RVOL/MA columns vào Fundamental Research.

---

# 18. Stock Detail

Production detail hiện bao gồm:

- identity + logo + company name;
- signal kỹ thuật;
- market metrics;
- Điểm cơ bản;
- score parts;
- analysis badges;
- quarterly history;
- Vietstock BCTC link.

Target hierarchy:

1. Public identity + Market Quote: ticker, company, exchange, price/change/current volume
2. Tabs: Tổng quan / Kỹ thuật / Cơ bản / BCTC
3. Technical tab: entitled evidence or professional locked state, without protected-content flash
4. Public Fundamental summary
5. Public Fundamental score + coverage/breakdown
6. Public quarterly history
7. Public BCTC link
8. Data trust/audit

Không bắt đầu detail bằng raw metric dump.

---

# 19. Company identity

Khi metadata tồn tại:

Desktop:

`LOGO · MÃ · Tên công ty đầy đủ`

Mobile:

`LOGO · MÃ`
`Tên hiển thị ngắn / tên công ty truncated hợp lý`

Không để logo thất bại làm vỡ layout.

Ticker fallback là bắt buộc.

---

# 20. BCTC access

BCTC hiện đi qua VietstockFinance.

UI phải nói rõ:

- nguồn;
- đây là external link;
- mở tab mới;
- không giả vờ tài liệu đang được host nội bộ nếu chưa có.

Nếu sau này có kho BCTC riêng, phải cập nhật data/source contract trước khi đổi UI copy.

---

# 21. Performance UX — LOCKED

Website hiện là vanilla JS static và render HTML theo state.

Do đó:

- tránh render DOM khổng lồ không cần thiết;
- pagination/list strategy phải tồn tại;
- giữ page size hợp lý;
- không làm search input lag;
- không tải lại toàn bộ financial data cho mỗi click;
- giữ cache/fallback behavior;
- asset versioning phải rõ;
- tránh visual effects nặng cho hàng trăm card.

Không migration framework chỉ để “làm đẹp UI” nếu chưa chứng minh lợi ích.

---

# 22. Accessibility — LOCKED

Required:

- keyboard focus visible;
- button/link semantics đúng;
- dialog có close/Escape;
- color không phải cue duy nhất;
- icon-only có accessible label;
- touch target mobile đủ lớn;
- table dùng semantics thật;
- heading hierarchy hợp lý;
- không thông tin thiết yếu chỉ hover;
- Light/Dark đều đủ contrast.

Clickable `<tr>`/`article` nếu dùng như control phải có keyboard path hoặc chứa control semantic phù hợp.

---

# 23. Loading / error / stale / missing

Phải phân biệt:

- đang tải lần đầu;
- đang refresh;
- API lỗi;
- đang hiển thị cache;
- row thiếu field;
- fundamental chưa có;
- fundamental stale;
- quarterly chưa có;
- logo missing.

Không gộp tất cả thành “Lỗi dữ liệu”.

---

# 24. Product language

Ưu tiên tiếng Việt dễ hiểu.

Ví dụ:

- `KL ngày / KLTB10`
- `Khối lượng 30 phút tương đối (RVOL30)`
- `Khoảng cách MA200`
- `Lợi nhuận sau thuế so cùng kỳ`
- `Điểm đạt / điểm có thể chấm`

Các từ viết tắt như ROE, ROA, P/E, P/B phải có helper/context ở nơi phù hợp.

Không dùng copy:

- “nên mua”
- “mua ngay”
- “chắc chắn tăng”
- “cổ phiếu tốt nhất”

Scanner không phải recommendation engine.

---

# 25. Lovable approval gate — LOCKED

Có ngân sách dự phòng tối đa 50 Lovable credits.

Không được tự ý gọi Lovable.

Trước khi dùng:

1. nêu rõ task;
2. giải thích vì sao Lovable có lợi thế;
3. ước lượng credit;
4. chờ Product Owner duyệt.

Lovable output luôn phải được review lại theo CCC system.

Lovable Phase 1 đã đóng và chỉ là visual/design reference. Không được xem prototype là production/runtime source. Phase 1 implementation phải đọc:

- `CCC_LOVABLE_PHASE1_DESIGN_REFERENCE_v1.0.md`;
- `CCC_PHASE1_DESIGN_PORT_CONTRACT_v1.0.md`.

Điều này không cho phép gọi lại Lovable hoặc làm Phase 2; approval gate ở trên vẫn giữ nguyên.

---

# 26. Design workflow

Mọi major UI change đi qua:

## 00 — Verify production source
Xác minh `website/` là production source of truth. Với Phase 1 đã duyệt, implementation target là `website-next/`; không sửa `website/` trước promotion approval.

## 01 — Product intent
1 primary job + tối đa 3 secondary jobs.

## 02 — Data contract
Field thật, source, missing state, freshness.

## 03 — Current-state audit
Giữ / nâng cấp / redesign / bỏ.

## 04 — Wireframe
PC + mobile.

## 05 — Theme pass
Light + Dark.

## 06 — Component/token mapping
Không style tự phát.

## 07 — Mockup
Mockup trước khi major visual redesign.

## 08 — Product Owner review
Không code major redesign trước khi mockup được duyệt.

## 09 — Implementation
Sửa đúng target được duyệt. Phase 1 port thực hiện tại `website-next/`.

## 10 — Responsive/accessibility/performance QA
375 / 768 / 1024 / 1440.

## 11 — Production data QA
800-universe + missing/stale/fundamental cases.

## 12 — Deploy package
Version bump + asset references + HawkHost deployment.

---

# 27. Versioning for website redesign

Mọi production UI release phải:

- cập nhật `VERSION.txt`;
- tạo asset version mới hoặc cache-busting version;
- giữ bản release trước trên Git;
- không sửa production-only trên HawkHost mà không đồng bộ Git.

Ví dụ:

```text
v18.5 → v19.0-ui-foundation
```

Tên version thực tế sẽ được chốt trước release.

---

# 28. LOCKED vs EVOLVING

## LOCKED

- production source is `website/`;
- Phase 1 staging implementation target is `website-next/`;
- 4 route hiện tại;
- scanner universe không bị frontend xóa;
- 4 tín hiệu;
- fundamental missing-data honesty;
- Data Trust;
- Light & Dark;
- explainability;
- no essential tiny text;
- semantic color;
- CCC Signal Rail;
- desktop table/mobile card principle;
- accessibility;
- Lovable approval gate;
- mockup approval before major redesign.
- Public Market Quote + Public Fundamental Research;
- protected CCC Technical Intelligence;
- Phase 1 visual reference + port contract;
- `PORT-01`, `PORT-02`, `PORT-03` là implementation debt bắt buộc.

## EVOLVING

Có thể tinh chỉnh:

- exact colors;
- exact radius;
- exact shadows;
- spacing;
- sidebar width;
- table column widths;
- dialog width;
- transition duration;
- exact breakpoints khi có evidence;
- font family nếu không làm giảm readability/performance.

---

# 29. Changelog

## v1.1 — 2026-08-20

Rebuilt from the real production frontend v18.5.

Changes vs v1.0:

- removed assumptions about React/Lovable dashboard;
- production source changed to `website/`;
- added all four real routes;
- added Light/Dark as existing production feature;
- added 800-symbol production universe context;
- added MA10;
- added fundamental scoring;
- added financial_latest/financial_quarterly/stock_metadata contracts;
- added industry-comparison rules;
- added BCTC/Vietstock rules;
- added static-HawkHost performance/deployment rules;
- retained CCC design philosophy and Lovable approval gate.

v1.0 is obsolete and must not be used for implementation.
