# CCC Alpha.19 Golden UI Reference v1.0

**Product:** Chuyện Chợ Chứng (CCC)  
**Purpose:** Locked visual/product reference for frontend restoration, refactor, QA and future Codex work  
**Status:** GOLDEN VISUAL CONTRACT — Product Owner review session 23/08/2026  
**Visual source snapshot:** `v19.0-alpha.19-stabilization`  
**Source commit:** `c5125051681512378097785e4d0904ac17088cf1` (`fix: stabilize member overview and scanner`)  
**Primary staging target:** `website-next/`

---

## 0. What this document is — and is not

This document locks the **desired visible UI/UX** after reviewing the Alpha.19 snapshot screen by screen on desktop and mobile.

Alpha.19 is a **visual baseline**, not an architecture baseline.

Do **not** restore Alpha.19's old multi-writer/patch-stack frontend architecture merely to reproduce the look. Internal code may be consolidated, secured, simplified or refactored, but the visible result must conform to this reference unless the Product Owner explicitly approves a visual change.

### Authority order for visual conflicts

1. Explicit Product Owner decisions in this Golden UI Reference.
2. The “Locked exceptions / corrections” in this document.
3. Reference screenshots in `screenshots/`.
4. Alpha.19 visual styling/behavior at commit `c512505`.
5. Existing locked CCC UI/UX standards and product docs.
6. Coder/AI preference.

**If code and screenshot disagree with a locked exception below, the locked exception wins.**

---

# 1. Global product truths that the UI must preserve

## 1.1 Four CCC signals only

The four production CCC technical signals remain:

1. **Giá tăng ≥ 3%**
2. **KL ngày ≥ 200% KLTB10**
3. **Giá trên MA200**
4. **RVOL30 ≥ 200%**

Signal count is `0/4` through `4/4`.

### MA10 rule — LOCKED

**MA10 is reference data, not a fifth signal.**

Never:
- count MA10 into `x/4`;
- add a fifth segment to CCC Signal Rail;
- label MA10 as a signal.

---

## 1.2 Scanner universe rule

The backend scanner universe is independent from user display/watchlist choices.

UI actions such as:
- filter;
- sort;
- hide;
- remove from personal watchlist;
- change current watchlist;

must **not** remove a symbol from the backend scanner universe or stop backend data collection.

---

# 2. Global shell — visual contract

## 2.1 Desktop

The visual hierarchy is:

`Top Header → Left Sidebar → Main Workspace → optional Right Rail`

### Top Header

Keep the Alpha.19 proportions and hierarchy:

- CCC logo + `CHUYỆN CHỢ CHỨNG / STOCK INTELLIGENCE`;
- global stock search;
- market status (`Ngoài giờ thị trường` / live state);
- refresh/countdown;
- notification icon;
- Light/Dark toggle;
- account/login control.

Header height and density should remain compact. Do not enlarge it into a marketing header.

### Left Sidebar

Primary items:

- Tổng quan
- Nghiên cứu
- DS mã theo dõi
- Cảnh báo (disabled/locked until product feature exists)

When logged in, Account is accessible from the lower/sidebar area as in Alpha.19.

### Desktop workspace width

Use the horizontal space efficiently, but do not stretch content into giant empty tracks.

Required feel:

- left sidebar stable;
- center content visually dominant;
- right rail supportive, not heavier than main content;
- no “left light / middle empty / right heavy” composition;
- top edges of main content and right-rail blocks should align cleanly.

---

## 2.2 Mobile

At `≤767px`:

- no persistent desktop sidebar;
- compact top header;
- separate market-status row;
- global search directly below;
- content becomes one primary vertical flow;
- no desktop right rail beside content;
- right-rail information either moves into the content flow or is omitted if nonessential.

No page-level horizontal overflow.

---

# 3. Responsive checkpoints

These are mandatory QA checkpoints.

## 3.1 375–390px — mobile

Locked behavior:

- single-column page flow;
- readable body without zoom;
- stock cards instead of squeezed desktop tables;
- tabs remain tappable;
- no essential 7–9px labels;
- right rail is not displayed beside main content;
- data tables that genuinely need width (for example BCTC) may scroll **inside their own container**, not the whole page.

## 3.2 768px — tablet / transition

Required:

- intentional tablet layout, not a squeezed desktop;
- no awkward desktop table compression;
- search/filter controls remain tappable;
- industry selection remains easy to use;
- a right rail must never reduce the center column below comfortable reading width;
- if a three-column layout is too tight, supportive rail blocks must stack below or use a compact presentation.

## 3.3 1024px — desktop compact

Required:

- desktop shell/sidebar fits without overlap;
- main data workspace remains readable;
- tables keep useful column widths;
- no filler columns;
- right rail may appear where page contract requires it, but must not crush the main content;
- long Vietnamese labels do not collide.

## 3.4 1440px and wider — desktop reference

Required:

- use a restrained max working width / coherent grid;
- no giant empty gutters;
- no unnecessary spreading of numeric columns;
- main content and right rail align vertically;
- visual density should feel close to Alpha.19 reference screenshots.

---

# 4. Light & Dark mode

Both themes are first-class production UI.

## Dark

Use Alpha.19 direction:

- navy/slate surfaces;
- clear but restrained borders;
- white/off-white main text;
- semantic green/red/purple/cyan;
- avoid neon overload;
- avoid pure black everywhere.

## Light

Use Alpha.19 light direction:

- cool neutral background;
- white/light cards;
- navy/slate text;
- same hierarchy/spacing as Dark;
- semantic colors remain legible.

**Theme switching must not change layout, metric order or component dimensions.**

Reference:
- `01-overview-desktop-light.png`
- `02-overview-mobile-light.png`
- `03-overview-mobile-dark.png`

---

# 5. Typography and information density

Keep the locked CCC readability principle:

- body: roughly 14.5–16px desktop, 15–16px mobile;
- ticker/symbol prominent;
- company name readable;
- page titles clearly larger than section titles;
- metadata may be smaller but not essential information;
- tabular numerals for prices, percentages, time and ratios.

Do not shrink text merely to fit more columns.

Avoid unexplained specialist abbreviations where a plain-language helper can be shown.

---

# 6. Page contract — Tổng quan

Route: `/`

## 6.1 Desktop

Reference: `01-overview-desktop-light.png`

Structure:

1. Page title `Tổng quan` + short explanatory subtitle.
2. Main workspace + right rail.
3. `Mật độ tín hiệu hôm nay` KPI strip:
   - Đạt 4/4
   - Từ 3 tín hiệu
   - Từ 2 tín hiệu
   - RVOL30 nổi bật
4. `Tín hiệu trong phạm vi của bạn`
5. Desktop stock rows.

### Desktop row hierarchy

Keep the Alpha.19 reading order:

`Identity | Price/Change | Volume | Evidence | CCC`

Identity:
- ticker/logo;
- company name;
- exchange / industry context.

Evidence area:
- RVOL30;
- MA200 / distance;
- MA10 may appear as secondary/reference data where appropriate, but never as a signal.

CCC area:
- four-segment rail;
- `x/4`;
- status label such as `Hội tụ mạnh` / `Đang hội tụ`.

### Right rail

Keep the market-context rail pattern from Alpha.19:
- market overview/index context;
- source/data-trust context where applicable.

The rail must align with the main content, not float at an unrelated top position.

---

## 6.2 Mobile

References:
- `02-overview-mobile-light.png`
- `03-overview-mobile-dark.png`

The stock card order is **locked**:

1. **Row 1:** logo + ticker + company/exchange on left; **price + % change on right**
2. **Row 2:** `KL hiện tại` left; **volume + % KLTB10 right**
3. **Row 3:** **RVOL30 left / MA200 right**
4. **Row 4:** **CCC rail + x/4 + state left / MA10 right**

### Critical MA rule

On mobile:

**MA10 must be on the row below MA200 and aligned on the right side of the card.**

Do not return to:
- three equal MA/RVOL columns;
- MA10 next to RVOL30;
- MA10 above MA200;
- MA10 inside the four CCC signals.

---

# 7. Page contract — DS mã theo dõi

Route: `/danh-sach`

This page has **two different product modes** and they must not be visually/semantically mixed.

## 7.1 Tab order and names — FINAL

Preferred final order:

1. **Watchlist của tôi**
2. **Toàn thị trường**

The legacy label `Toàn bộ tín hiệu` is **not** the final product concept for the whole-market tab.

---

## 7.2 Watchlist của tôi — FULL CCC MODE

References:
- `11-watchlist-desktop-my-watchlist.png`
- `13-watchlist-mobile-my-watchlist.png`

This tab may show the complete CCC intelligence available to the user:

- ticker/company/exchange;
- price;
- % change;
- current volume;
- KLTB10 / relative daily volume;
- RVOL30;
- MA200;
- MA10;
- CCC rail;
- `x/4`;
- convergence state;
- signal filters;
- sorting/filtering relevant to CCC.

Quick signal filters may include:
- Toàn bộ
- 4/4
- ≥3
- ≥2
- RVOL30

---

## 7.3 Toàn thị trường — BASIC 800-SYMBOL MODE

Alpha.19 screenshots:
- `10-watchlist-desktop-whole-market-alpha19.png`
- `12-watchlist-mobile-whole-market-alpha19.png`

**These two Alpha.19 screenshots are visual-layout references only. Their signal content is NOT the final product rule.**

### LOCKED CORRECTION #1

`Toàn thị trường` is the broad basic-data view for the ~800-symbol universe.

Show:

- ticker;
- company name;
- exchange;
- current price;
- % change;
- current volume;
- MA200;
- MA10.

Remove from this tab:

- CCC Signal Rail;
- `x/4`;
- `Hội tụ mạnh` / `Đang hội tụ`;
- RVOL30;
- signal-specific KLTB10 ratio presentation;
- quick filters `4/4`, `≥3`, `≥2`, `RVOL30`;
- signal dropdown/filter.

Allowed controls:
- symbol/company search;
- exchange filter;
- sort by basic displayed fields such as price, % change, volume, MA200, MA10;
- pagination / mobile “Xem thêm”.

### Mobile whole-market card

Keep the same calm Alpha.19 card language, but strip CCC/signal content.

The card must not look identical to the full Watchlist card.

---

# 8. Page contract — Nghiên cứu

Research is visually and conceptually separate from CCC technical signals.

It must not mix:
- CCC rail;
- technical signal count;
- RVOL30 signal UI;
- MA technical signal language

into the public fundamental research tables.

---

## 8.1 So sánh theo ngành — Desktop

References:
- `20-research-desktop-industry-top.png`
- `21-research-desktop-industry-results.png`

Structure:

1. Hero:
   - `NGHIÊN CỨU CƠ BẢN CÔNG KHAI`
   - `So sánh theo ngành`
   - short explanation
2. Tabs:
   - Theo ngành
   - Sàng lọc cơ bản
3. Industry selector grid.
4. Selected industry results.
5. Right rail:
   - research context;
   - data source / freshness.

Desktop industry selector may use the multi-column grid seen in Alpha.19.

Results table keeps the hierarchy:

- Mã cổ phiếu
- Điểm cơ bản / coverage
- Tăng trưởng lợi nhuận
- ROE
- P/E
- P/B
- Dữ liệu / freshness

---

## 8.2 So sánh theo ngành — Mobile

References:
- `25-research-mobile-industry-top-alpha19.png`
- `26-research-mobile-industry-results.png`

### LOCKED CORRECTION #2

Alpha.19 shows all industries as a long two-column vertical list. **Do not keep that behavior.**

Final mobile behavior:

- industry choices are a **horizontal scroll rail / chip-card carousel**;
- selected industry is visually clear;
- name + symbol count remain readable;
- user reaches company results quickly without scrolling through every industry.

Industry company results should use the compact mobile card language shown in Alpha.19.

---

## 8.3 Sàng lọc cơ bản — Desktop

References:
- `22-research-desktop-screener-method.png`
- `23-research-desktop-screener-thresholds.png`
- `24-research-desktop-screener-results.png`

Keep:

- clear methodology explanation before the results;
- four scoring groups:
  1. Tăng trưởng — tối đa 35
  2. Hiệu quả sinh lời — tối đa 30
  3. Sức khỏe tài chính — tối đa 20
  4. Định giá — tối đa 15
- plain-language ROE / ROA / P/E / P/B helper cards;
- expandable detailed scoring thresholds;
- filter groups:
  - Mức Điểm cơ bản
  - Tăng trưởng lợi nhuận sau thuế
  - ROE
- result table with score coverage.

Missing-data symbols remain visible according to the product rule; missing data must not silently become fake zeroes.

---

## 8.4 Sàng lọc cơ bản — Mobile

References:
- `27-research-mobile-screener-method.png`
- `28-research-mobile-screener-results.png`

Keep:
- single-column methodology cards;
- filter groups large enough to tap;
- result cards rather than a squeezed desktop table;
- score/coverage prominent;
- core fundamental metrics in a readable 2-column arrangement when width permits.

---

# 9. Page contract — Stock Detail

Stock detail has four tabs:

1. Tổng quan
2. Kỹ thuật
3. Cơ bản
4. BCTC

The ticker header remains persistent inside the detail workspace.

---

## 9.1 Shared ticker header

Keep Alpha.19 hierarchy:

- logo;
- ticker;
- exchange;
- industry;
- company name;
- current volume context;
- current price;
- % change.

Desktop: price block may sit at the far right of the detail header.

Mobile: price moves to its own strong row below ticker/company identity.

---

## 9.2 Desktop layout

Alpha.19 content references:
- `30-stock-detail-desktop-overview.png`
- `31-stock-detail-desktop-technical.png`
- `32-stock-detail-desktop-fundamental.png`
- `33-stock-detail-desktop-financials.png`

### LOCKED CORRECTION #3

Alpha.19 lets Stock Detail stretch almost full workspace width.

Final desktop layout must instead use:

`Left Sidebar → Center/Main Stock Detail → Right Rail`

The center block contains the four tabs and all primary detail content.

### Right rail requirement

A right rail is **required** on desktop Stock Detail.

Its exact card contents are **not yet fully locked**. Suitable content can include:
- symbol context;
- data source/freshness;
- entitlement/plan state;
- watchlist action;
- related context.

Do not invent a large new rail product without Product Owner approval. The **presence and alignment of the rail** are locked; the final specific rail cards remain a controlled follow-up decision.

---

## 9.3 Tab: Tổng quan

Desktop reference: `30-stock-detail-desktop-overview.png`  
Mobile reference: `36-stock-detail-mobile-overview.png`

Keep two distinct sections:

### Báo giá công khai
- Sàn
- Giá hiện tại
- % thay đổi
- KL hiện tại

### Bối cảnh cơ bản
- Điểm cơ bản
- Ngành
- P/E
- ROE
- other public fundamental summary as approved

Technical CCC content is not dumped into this tab.

---

## 9.4 Tab: Kỹ thuật

Desktop reference: `31-stock-detail-desktop-technical.png`  
Mobile references:
- `34-stock-detail-mobile-technical-top.png`
- `35-stock-detail-mobile-technical-stats.png`

Top block:

- CCC four-segment rail;
- `x/4`;
- convergence status.

The four signal cards:

- Giá tăng ≥3%
- KL ngày ≥200% KLTB10
- Trên MA200
- RVOL30 ≥200%

On mobile: **2 × 2 grid**.

Below: `Số liệu kỹ thuật`.

Keep metrics such as:
- KLTB10
- KL ngày / KLTB10
- MA10 tham chiếu
- Cách MA10
- MA200
- Cách MA200
- RVOL30
- Số phiên RVOL30

Display the copy:

**`MA10 chỉ là tham chiếu, không phải tín hiệu`**

prominently enough to prevent confusion.

---

## 9.5 Tab: Cơ bản

Desktop reference: `32-stock-detail-desktop-fundamental.png`  
Mobile reference: `37-stock-detail-mobile-fundamental.png`

Keep:

- Điểm cơ bản prominent;
- score coverage;
- LNST so cùng kỳ;
- ROE;
- P/E;
- P/B;
- score component breakdown below.

Mobile:
- score card first;
- supporting metrics in 2 columns where readable.

---

## 9.6 Tab: BCTC

Desktop reference: `33-stock-detail-desktop-financials.png`  
Mobile references:
- `38-stock-detail-mobile-financials-top.png`
- `39-stock-detail-mobile-financials-bottom.png`

Keep quarterly table and external document/source block.

On mobile:

- table may horizontally scroll **inside the table container**;
- page itself must not horizontally overflow;
- `Tài liệu công bố doanh nghiệp` remains below;
- external BCTC CTA remains explicit.

---

# 10. Page contract — Tài khoản

## 10.1 Login modal

Reference: `40-login-modal-desktop.png`

Keep:

- centered modal;
- strong dim/blur background;
- Google sign-in first;
- divider;
- Email + password;
- primary Login CTA;
- close control;
- compact, calm visual hierarchy.

---

## 10.2 Account — Desktop

References:
- `41-account-desktop-top.png`
- `42-account-desktop-watchlist-plan.png`
- `43-account-desktop-watchlist-security.png`

Layout:

`Left Sidebar → Main Account Content → Right Rail`

### Main content

- page title + description;
- personal information form;
- current profile completion state;
- `Danh sách mã theo dõi` editor;
- watchlist usage;
- change quota;
- next reset date;
- free initialization banner;
- search/add symbol;
- tracked-symbol cards;
- Undo / Save actions.

### Right rail

Keep the Alpha.19 pattern:

- user identity card;
- current plan;
- CCC allowance;
- remaining changes;
- alert entitlement;
- billing/current cycle;
- VIP Day block if applicable;
- upgrade options;
- security/session;
- data source context.

---

## 10.3 Account — Mobile

References:
- `44-account-mobile-profile.png`
- `45-account-mobile-current-plan.png`
- `46-account-mobile-upgrade-watchlist.png`
- `47-account-mobile-watchlist-stats.png`
- `48-account-mobile-watchlist-list.png`
- `49-account-mobile-security.png`
- `50-account-mobile-source.png`

Locked behavior:

- one vertical flow;
- no side-by-side right rail;
- desktop rail cards move naturally into the content sequence;
- profile form inputs full-width;
- Save button full-width;
- plan metrics stack;
- plan upgrade cards may use 2 columns;
- watchlist usage metrics stack;
- tracked symbols become **one card per row**;
- remove button stays on the right of each symbol card;
- logout action full-width and visually destructive;
- source/data trust block at bottom.

---

# 11. Right rail — global rule

The correct term is **Right Rail**.

Pages using it on desktop:

- Tổng quan
- Nghiên cứu
- Tài khoản
- Stock Detail (required final correction)

Rules:

- supportive, not dominant;
- top alignment with corresponding main content;
- consistent width and card rhythm;
- no unexplained vertical offset;
- no giant independent visual weight;
- on mobile, convert to inline/stacked sections rather than a side column.

---

# 12. Locked exceptions / corrections summary

These rules intentionally override raw Alpha.19 screenshots.

## EX-01 — Whole Market is basic-only

`Toàn thị trường` shows basic 800-symbol data:
- name/ticker;
- exchange;
- price;
- % change;
- volume;
- MA200;
- MA10.

It does **not** show CCC/signal filters or signal content.

## EX-02 — Mobile Industry selector scrolls horizontally

Do not render the complete industry set as a long two-column vertical wall.

Use horizontal scroll chips/cards.

## EX-03 — Stock Detail desktop has a Right Rail

Do not keep the Alpha.19 almost-full-width detail panel.

Use center main content + right rail.

## EX-04 — Mobile Overview MA10 position

MA10 stays on the row **below MA200**, aligned to the **right**.

## EX-05 — Watchlist and Whole Market are different experiences

Do not reuse one full-CCC card/filter system for both tabs.

## EX-06 — Alpha.19 visual target, not Alpha.19 architecture

Do not restore polling/DOM patch loops, MutationObserver repair behavior or CSS override stacking simply to achieve visual parity.

---

# 13. Codex visual guardrail

Any Codex task touching `website-next/` must treat this document as a visual contract.

## Codex MAY

- refactor internal state/data flow;
- improve auth/security;
- consolidate JavaScript;
- consolidate CSS architecture;
- fix APIs/RPC/data loading;
- improve performance;
- fix accessibility;
- remove duplicate DOM writers;

**provided the visible product contract remains unchanged.**

## Codex MUST NOT without explicit Product Owner approval

- redesign page layout;
- reorder major blocks;
- remove a right rail;
- add a new right rail;
- change tab order/labels;
- change metric order inside stock cards;
- move MA10/MA200/RVOL positions;
- add/remove CCC signals;
- change typography scale materially;
- change global spacing/density materially;
- replace cards with tables or tables with cards;
- change mobile stacking;
- introduce a new visual style;
- “clean up CSS” by deleting rules before visual parity is proven.

## If a logic fix requires visual change

Stop and report:

1. what visual change is necessary;
2. why it cannot be avoided;
3. which screen/breakpoint changes;
4. before/after screenshots;
5. wait for Product Owner approval before making the final visual change.

---

# 14. Mandatory visual QA gate

A UI-changing task is not complete until checked at:

- **375px**
- **768px**
- **1024px**
- **1440px**

Key screens:

- Tổng quan
- Watchlist của tôi
- Toàn thị trường
- So sánh theo ngành
- Sàng lọc cơ bản
- Stock Detail — all 4 tabs
- Tài khoản / login

Themes:

- Dark
- Light

Minimum visual regression checks:

- no page horizontal overflow;
- no text overlap;
- no clipped Vietnamese labels;
- no giant empty center tracks;
- right rail alignment correct;
- no desktop table squeezed into unreadability;
- no mobile desktop-table imitation where cards are required;
- MA10/MA200 placement correct;
- signal count/rail remains exactly 4 signals;
- Whole Market remains signal-free/basic-only.

---

# 15. Screenshot reference index

All reference images are stored in `screenshots/`.

Important interpretation:

- files containing `alpha19` in the name may intentionally show an Alpha.19 behavior that is corrected by this document;
- the **written locked correction wins** over the screenshot when they conflict.

---

# 16. Release discipline

Before promoting staging:

1. preserve a restorable Git commit;
2. record `VERSION.txt`;
3. compare with Golden screenshots;
4. run visual QA at 375/768/1024/1440;
5. verify Light + Dark;
6. verify route refresh/direct URL;
7. verify current user/auth/watchlist logic;
8. only then promote to production.

Every Product Owner-approved visual milestone should be tagged/recorded as a new Golden baseline rather than silently replacing this one.

---

# 17. Short implementation instruction for future agents

> Restore/refactor CCC using `CCC_ALPHA19_GOLDEN_UI_REFERENCE_v1.0` as the visual contract.  
> Do not redesign.  
> Preserve Alpha.19 visual language, but apply all locked exceptions.  
> Internal architecture may change; visible hierarchy, responsive behavior and page semantics may not change without Product Owner approval.  
> Run visual regression QA at 375/768/1024/1440 in Dark and Light before declaring completion.
