# CCC UI AUDIT & REDESIGN PLAN v1.1

**Product:** Chuyện Chợ Chứng  
**Production frontend audited:** `website/`  
**Version audited:** `v18.5-final800-near-ma`  
**Design standard:** CCC UI/UX Design System v1.1  
**Audit date:** 2026-08-20  
**Status:** APPROVAL / MOCKUP PLANNING  
**Scope:** UI/UX + frontend presentation behavior. This document does not authorize changes to scanner thresholds or backend universe logic.

---

# 1. Executive conclusion

The current v18.5 website is the correct production baseline and has a much stronger functional foundation than the obsolete React/Lovable frontend.

The right redesign strategy is:

> **Preserve the working data logic and static HawkHost architecture; redesign information hierarchy, product identity, data trust, readability, filtering, detail presentation and responsive behavior in controlled releases.**

Do **not** rebuild the product from zero.

Do **not** migrate framework merely for visual redesign.

Do **not** change the four scanner signals.

Do **not** change the scanner universe from frontend UI.

---

# 2. What is already good and should be preserved

## 2.1 Production architecture — KEEP

The current website is a small static deployment:

```text
website/
├── index.html
├── .htaccess
├── VERSION.txt
└── assets/
    ├── app-v18.5.js
    └── styles-v18.5.css
```

Advantages:

- easy HawkHost deployment;
- easy rollback;
- low runtime overhead;
- no framework dependency;
- direct control over responsive behavior.

A UI redesign does not justify replacing this architecture.

---

## 2.2 Four routes — KEEP

Production has four real product workflows:

1. `/` — Tổng quan
2. `/danh-sach` — Danh sách cổ phiếu
3. `/so-sanh-theo-nganh` — So sánh theo ngành
4. `/sang-loc-co-ban` — Sàng lọc cơ bản

All four remain part of the redesigned product.

---

## 2.3 Real data integration — KEEP

Current frontend already integrates:

- `stock_snapshot`
- `financial_latest`
- `stock_metadata`
- `financial_quarterly`

This is sufficient for a strong product UI.

The redesign should use these contracts before requesting new backend fields.

---

## 2.4 Cache / refresh behavior — KEEP, improve presentation

Good existing behavior:

- expects the full 800-symbol universe;
- keeps the previous complete cache if the live request is incomplete;
- checks for newer market data;
- does not erase existing data when the lightweight version poll fails;
- shows outside-session countdown behavior;
- supports manual refresh.

This logic is valuable.

The primary weakness is **how system state is communicated**, not the existence of the logic.

---

## 2.5 Dark + Light — KEEP

Both themes already exist and preference persists through `localStorage`.

This is now a production feature, not a future enhancement.

The redesigned visual system must support both modes simultaneously.

---

## 2.6 Desktop table + mobile cards — KEEP

This is the correct responsive strategy for a financial scanner.

Do not replace it with:

- a squeezed desktop table on mobile;
- cards everywhere on desktop.

---

## 2.7 Logo fallback — KEEP

Current logo system:

- attempts local `/assets/logos/{SYMBOL}.jpg`;
- falls back to ticker letters;
- removes failed images cleanly.

This should remain.

---

# 3. Audit severity model

## P0 — Correctness / trust / release blocker

Misleading state, unreadable important information, major performance risk, broken theme state, hidden critical failure.

## P1 — Core workflow

Major effect on speed, comprehension, scanning or navigation.

## P2 — Consistency / scalability

Should be fixed in redesign, but does not immediately invalidate data.

## P3 — Polish

Motion, shadow, micro visual refinement.

---

# 4. P0 findings

# P0.1 — Initial system state can falsely appear healthy

## Current behavior

`headerHtml()` derives:

```js
var m = state.meta || {};
var good = !state.error && (!m.systemStatus || m.systemStatus === "OK");
```

Before market data has loaded:

- `state.meta` is null;
- `state.error` is empty;
- therefore `good === true`.

The Header can display:

> HỆ THỐNG ĐANG HOẠT ĐỘNG

while there is not yet real market metadata.

There is also a `liveText` variable intended to distinguish loading but it is currently not used by the rendered header.

## Risk

Financial UI is asserting trust before verification.

## Required redesign

Explicit trust state machine:

```text
INITIAL_LOADING
LIVE_OK
LIVE_DEGRADED
LIVE_ERROR_WITH_CACHE
LIVE_ERROR_NO_DATA
OUTSIDE_SESSION
WAITING_FOR_NEW_DATA
```

Before first verification:

> Đang kiểm tra dữ liệu…

Never green “healthy” by default.

**Decision:** REDESIGN — P0.

---

# P0.2 — Sidebar always communicates LIVE even outside session/error

Current sidebar contains a permanent block:

```text
LIVE SCAN
Quét theo chu kỳ thị trường
Cập nhật liên tục
```

while other parts of the application may report:

- outside operating hours;
- API error;
- waiting for new data.

## Risk

Conflicting trust messages on the same screen.

## Required redesign

Remove the permanent decorative LIVE block.

Use one centralized **Data Trust Bar** driven by actual state.

**Decision:** REMOVE/REPLACE — P0.

---

# P0.3 — Financial and metadata API errors are not surfaced

Current code stores:

```js
state.financialError = "Không tải được dữ liệu cơ bản.";
state.metadataError = "Không tải được tên công ty.";
```

but these states are not presented to the user.

Consequences:

- `/so-sanh-theo-nganh` may simply appear empty if `financial_latest` fails;
- `/sang-loc-co-ban` may appear empty/incomplete without explaining the failure;
- missing company names can look like a design/data choice instead of a metadata-fetch failure.

## Required redesign

Route-level Data Trust state:

```text
Market data: OK
Financial data: ERROR
Metadata: OK
```

But do not turn this into a large diagnostic panel.

Example:

> ⚠ Dữ liệu cơ bản tạm thời chưa tải được · Thử lại

**Decision:** FIX — P0.

---

# P0.4 — Light-mode company name color rule is malformed

In the v18.5 CSS, this sequence exists:

```css
html[data-theme="light"] 
html[data-theme="light"] .dialog-company .company-full{...}
```

Because the first selector is left hanging, the browser effectively receives a descendant selector that cannot match the root HTML as intended.

In addition, mobile `.company-short` has a fixed dark-theme light text color and no clear light-mode override.

## Risk

Company name in Stock Detail may have very low contrast in Light mode.

## Required fix

Create proper semantic theme tokens rather than one-off overrides:

```text
--text-primary
--text-secondary
--text-muted
```

and make company labels consume those tokens.

**Decision:** FIX BEFORE/AS PART OF THEME FOUNDATION — P0.

---

# P0.5 — Fundamental screener can render hundreds of rows/cards at once

`fundamentalHtml()` builds the full filtered result:

```js
rows.map(...)
```

for both:

- desktop table rows;
- mobile cards.

There is no pagination for the fundamental screener.

With a large financial universe this can create hundreds of DOM elements in one render.

Because the app rebuilds `app.innerHTML` on state changes, filter operations can rebuild the entire large result set.

## Risk

- slower filter response;
- mobile jank;
- large DOM;
- unnecessary logo/image work after future identity enhancements;
- increasing cost as financial coverage expands.

## Required redesign

Add a result strategy.

Recommended initial:

- Desktop: 50 rows/page
- Mobile: 20 rows/page

matching Scanner behavior.

No need to add virtualization until profiling shows a need.

**Decision:** FIX — P0/P1.

---

# P0.6 — Major UI state must not be mistaken for backend truth

Current production already has:

- 4 technical signals;
- MA10 reference;
- fundamental scoring;
- data freshness.

The redesign must not accidentally:

- turn MA10 into signal #5;
- normalize incomplete fundamental score to 100;
- convert frontend hide/watchlist action into scanner-universe deletion;
- change signal thresholds.

**Decision:** LOCKED — P0.

---

# 5. Global App Shell audit

## Current strengths

- fixed desktop sidebar;
- bottom mobile navigation;
- theme toggle;
- refresh;
- countdown;
- system metadata.

## Current problems

The app communicates system status in too many simultaneous places:

1. Sidebar `LIVE SCAN`
2. Sidebar “Cập nhật gần nhất”
3. Sidebar “HỆ THỐNG ỔN ĐỊNH”
4. Header market-status pill
5. Header countdown
6. Four-card metadata grid
7. Error banner

The user sees system diagnostics before the actual product content.

On mobile the four metadata cards consume substantial vertical height before Overview/Scanner content begins.

## Target

### Desktop

```text
Sidebar:
Chuyện Chợ Chứng
Navigation

Header:
● LIVE · Cập nhật 15:20 · 800 mã · Dữ liệu đầy đủ
                         [Light/Dark] [↻ Làm mới]
```

### Mobile

```text
Chuyện Chợ Chứng                  [↻] [Theme]
● LIVE · 15:20 · 800 mã
```

Deeper diagnostics through a disclosure only when needed.

## Decision

**REDESIGN — P1**

---

# 6. Product branding audit

## Current

User-facing product identity is still:

```text
VNStock
Market Scanner
```

in:

- desktop sidebar;
- mobile header;
- HTML title;
- boot text.

The data-source metadata already uses “Chuyện Chợ Chứng”, creating mixed branding.

## Target

Primary brand:

> **Chuyện Chợ Chứng**

Possible secondary descriptor:

> Stock Scanner

or:

> Bộ quét cổ phiếu

“VNStock” can remain an internal technology/data reference only when appropriate, not primary product branding.

## Required places

- `<title>`
- boot/loading
- desktop brand
- mobile brand
- favicon/mark if redesigned
- metadata/share copy later.

**Decision:** REDESIGN — P1.

---

# 7. Typography audit

v18.5 contains a later readability patch, which significantly improved text sizes.

However, essential text is still often too small.

Examples from current CSS include approximately:

- exchange: 9–10px;
- signal tags: 8–9.5px;
- meta labels: 9.5–11px;
- table header sublabels: 9.5px;
- score coverage: 10px;
- freshness: 10.5px;
- mobile fundamental metric labels: 9.5px;
- BCTC helper text: 10.5px.

## Main problem

Some of these are not “decorative metadata”; they explain financial meaning.

Examples:

- score coverage;
- metric definition;
- freshness;
- stock signals.

These should not be tiny.

## Target

### Desktop

- table data: 13.5–15px;
- important table headers: 12.5–13.5px;
- header explanation: ≥11.5–12px;
- score coverage: ≥12px;
- signal labels: ≥11.5–12px.

### Mobile

- body/data: 14–16px;
- metric labels: ≥11.5–12.5px;
- important financial definitions: ≥12px.

## Decision

**UPGRADE — P1.**

---

# 8. Color semantics audit

## Current strengths

Distinct colors exist for:

- market up;
- market down;
- early alert;
- 1–4 signal groups;
- fundamental score states;
- freshness.

## Main issue

Some signal colors can conflict semantically with market colors.

Example:

`4/4` Overview uses a red-toned KPI.

Red already has a strong meaning in Vietnamese stock UX:

- price decline;
- negative;
- error.

A very strong scanner convergence should not visually resemble a negative-price state.

## Target

Separate:

### Market direction colors

- green = up
- red = down

### Scanner-signal system

Use a dedicated progression:

- neutral 0/4;
- cool blue 1/4;
- amber 2/4;
- violet/indigo 3/4;
- stronger violet/purple or brand highlight 4/4.

The color must be paired with count/icon.

## Decision

**REDESIGN — P1/P2.**

---

# 9. CCC Signal Rail audit

## Current

Signal is represented mainly by:

```text
3/4
```

plus four small text tags on cards.

The four conditions do exist in data but are not visually expressed as a unified signature system.

## Target

Introduce CCC Signal Rail:

```text
● ● ● ○   3/4
```

Stock Detail:

```text
✓ Giá tăng ≥ 3%                   +4.1%
✓ KL ngày ≥ 200% KLTB10           245%
✓ Giá trên MA200                  +6.2%
○ RVOL30 ≥ 200%                    174%
```

## Benefit

- fast recognition;
- does not rely on color;
- explains the 3/4 number;
- consistent across all four pages.

**Decision:** NEW CORE COMPONENT — P1.

---

# 10. Company identity audit

## Current reality

`stock_metadata` is already loaded.

Stock Detail already uses:

- `company_name`
- `display_name`
- `website_group`.

But scanner table, stock cards, Industry table and Fundamental screener generally show only the ticker.

## This wastes data already available.

## Target

### PC / tablet

Identity cell:

```text
[LOGO] FPT
       CTCP FPT
```

or:

```text
[LOGO] FPT · CTCP FPT
```

depending on table width.

### Mobile

```text
[LOGO] FPT
       FPT Corp / short name
```

Use `display_name` first.

## Search enhancement

Current search only matches:

```js
r.symbol
```

Once metadata is loaded, search should also match:

- symbol;
- `display_name`;
- `company_name`.

Placeholder can then become:

> Tìm mã hoặc tên công ty…

## Decision

**UPGRADE — P1.**

---

# 11. Tổng quan `/` audit

## Current structure

1. 4 KPI cards
2. all RVOL30 early cards
3. all 4/4 cards
4. all 3/4 cards
5. all 2/4 cards
6. first 6 of 1/4

## Strengths

- clear signal grouping;
- direct links to scanner;
- early RVOL has priority;
- 1/4 is already limited.

## Problems

### 11.1 Duplicate stocks

A stock with RVOL30 signal and 4/4 may appear:

- in “Cảnh báo dòng tiền sớm”
- then again under 4/4.

Overview can repeat the same opportunity.

### 11.2 Unlimited high-signal sections

4/4, 3/4 and 2/4 render all matching cards.

This can create very long Overview pages during active sessions.

### 11.3 Too much detail inside discovery cards

Each card contains:

- MA10;
- 4 metrics;
- 4 signal text tags;
- signal pill.

Overview is for discovery, not full analysis.

### 11.4 No company name

Ticker identity is weaker than it needs to be.

## Target role

Overview should answer:

> **Có gì đáng chú ý lúc này?**

### Proposed hierarchy

1. Data Trust
2. Attention summary
3. Dòng tiền sớm — Top 6/8
4. Tín hiệu rất mạnh — Top 6/8
5. Tín hiệu mạnh/đang hình thành — previews
6. Links to Scanner for full lists

### Card target

- logo;
- ticker;
- company short name;
- price/change;
- Signal Rail;
- one or two strongest reasons.

Not four equally weighted metrics plus four tags.

## Decision

**REDESIGN — P1.**

---

# 12. Danh sách cổ phiếu `/danh-sach` audit

## Current functionality — GOOD

Search, exchange filter, signal filter, sorting and pagination all exist.

Current sorts include:

- signal priority;
- RVOL30 high/low;
- price high/low;
- day-volume high/low;
- nearest MA10;
- nearest MA200;
- A–Z.

## Main problem: filter wall

The screen currently exposes simultaneously:

- 4 exchange choices;
- 9 signal choices;
- 10 sorting choices.

On mobile all chips wrap.

This makes the control panel long before user reaches results.

## Target — Scanner Command Bar

### Desktop

```text
[Tìm mã hoặc tên công ty…] [Bộ lọc ▾] [Sắp xếp ▾]

Đang lọc:
[HOSE ×] [≥3 tín hiệu ×] [RVOL30 ≥200% ×]      Xóa tất cả
```

### Mobile

```text
[Tìm mã hoặc tên công ty…]

[Bộ lọc •3] [Sắp xếp]
```

Complex choices use bottom sheet.

## Result information

Keep:

> Hiển thị 38 / 800 mã

## Decision

**REDESIGN CONTROLS / KEEP DATA LOGIC — P1.**

---

# 13. Scanner table audit

## Current strengths

- sticky header;
- pagination;
- tabular numeric support exists;
- key fields are present;
- logo already present.

## Problem 1 — v18.3 forces all cells centered

Current CSS explicitly applies:

```css
.scanner-table th,
.scanner-table td {
  text-align:center!important;
}
```

including numeric columns.

This was an intentional previous alignment fix, but for dense financial comparison it reduces the visual alignment of numbers with different lengths.

## Recommended redesign rule

Suggested:

- Logo/Mã/Tên: left or deliberate identity alignment
- Sàn: center
- Price/numeric metrics: right
- Signal: center
- Status: center/left depending final copy

Because previous product feedback asked for cleaner centered columns, final choice should be judged visually in mockup rather than changed blindly.

## Problem 2 — company name missing

Metadata exists and should enrich the identity column.

## Problem 3 — normal data status is too prominent

Every row currently says:

> Đầy đủ

Normal states should be quiet.

Only exceptions should pull attention:

- Thiếu dữ liệu
- Chậm
- Lỗi

## Decision

**UPGRADE — P1.**

---

# 14. Mobile Stock Card audit

## Current strengths

- full-width list cards;
- 2-column metric grid after readability patch;
- logo;
- price/change;
- MA10;
- signal count.

## Main problem

Too many labels have similar priority:

- KL ngày
- MA200
- RVOL30
- RVOL30 sessions
- MA10
- four signal tags.

A mobile user must decode too much.

## Target

Card priority:

1. Identity
2. Price/change
3. Signal Rail
4. RVOL30 / strongest money-flow evidence
5. MA context
6. Detail tap

No need to show the full four-condition wording on every list card.

## Decision

**UPGRADE — P1.**

---

# 15. So sánh theo ngành audit

## Current strengths

The latest version already improved many earlier issues:

- industry selector uses a desktop grid rather than clipped chips;
- counts are visible;
- long names can wrap;
- mobile uses horizontal industry scrolling;
- table labels include explanations;
- score coverage is visible;
- freshness is visible.

These are good and should not be lost.

## Current weaknesses

### 15.1 No company name in comparison table/card

Only symbol + industry context.

Add company identity.

### 15.2 All metric cells centered

Financial comparison is easier when numeric values align consistently.

Mockup should test mixed alignment.

### 15.3 Score normalized rank can visually overpower coverage

Sort currently compares:

```text
earned / available
```

This is consistent with existing business logic.

But:

```text
64/70
```

may rank above:

```text
88/100
```

depending ratio.

The UI must make coverage obvious so users do not mistake ranking confidence.

Do not change ranking algorithm in UI redesign without separate approval.

### 15.4 Industry selection may become large

Desktop full visibility is desired.

Keep full names and counts, but improve grouping/spacing rather than hiding items.

## Decision

**KEEP ARCHITECTURE / UPGRADE VISUAL HIERARCHY — P1/P2.**

---

# 16. Sàng lọc cơ bản audit

## Current strengths

- transparent methodology;
- beginner-friendly definitions;
- explains missing-data policy;
- filters are understandable;
- result coverage shown.

## Main UX problem

The full **Cách tính Điểm cơ bản** block appears before filters and results.

A user entering a screener usually wants:

1. choose criteria;
2. see results;
3. learn scoring methodology if needed.

Current page reverses part of that workflow.

## Target hierarchy

1. Short intro
2. Filter panel
3. Result count
4. Results
5. Collapsible “Cách tính Điểm cơ bản”
6. Full scoring methodology

A small `Điểm cơ bản là gì?` helper can remain next to filters.

## Performance

Add pagination:

- 50 desktop
- 20 mobile

## Decision

**REDESIGN INFORMATION ORDER + PAGINATION — P0/P1.**

---

# 17. Fundamental terminology audit

This page has made real progress by explaining:

- ROE
- ROA
- P/E
- P/B.

Keep these explanations.

However, table sublabels and card labels are often still 9.5–11px.

## Target

Use concise primary headers:

```text
ROE
P/E
P/B
```

with:

- tooltip/help icon;
- secondary explanation ≥11.5–12px;
- full explanation in methodology.

Do not force long definitions into every table header if it makes the header too tall.

**Decision:** UPGRADE — P2.

---

# 18. Fundamental score audit

## What is correct

`financialScore()`:

- skips unavailable metrics;
- tracks `earned`;
- tracks `available`;
- does not normalize display to fake 100 points.

This is good.

## Presentation issue

The main score badge may visually dominate while coverage is rendered in much smaller text.

Example:

```text
72/85
Chấm được 85/100 điểm tối đa
```

The second line is essential context, not minor metadata.

## Target

Use a combined visual:

```text
72 / 85
Điểm cơ bản
Độ phủ: 85%
```

For special financial models:

> Chưa đủ chỉ tiêu chuyên ngành để chấm phần sức khỏe tài chính

must remain visible.

**Decision:** UPGRADE — P1.

---

# 19. Freshness audit

Current labels:

- Mới nhất
- Chậm 1 kỳ
- Dữ liệu cũ
- Chưa có dữ liệu

This is good.

Keep text labels.

Do not collapse freshness into color dots only.

Potential improvement:

show freshness as secondary status unless it is lagging/stale.

**Decision:** KEEP / POLISH.

---

# 20. Stock Detail audit

## Current structure

1. Symbol + signal count + company
2. 12 technical metric cards
3. Fundamental score
4. Fundamental KPI block
5. badges
6. score parts
7. quarterly history
8. BCTC access

## Strengths

This is already a rich detail view.

It uses real:

- metadata;
- financial data;
- quarterly history;
- BCTC source.

## Main problem

It starts with:

> “Here are 12 values.”

rather than:

> “Why is this stock interesting?”

## Target order

### Header
Logo + symbol + company + exchange + price/change.

### 1. Why notable?
Explain real active/inactive signals.

### 2. CCC Signal Rail

### 3. Technical evidence
Compact.

### 4. Fundamental summary
Score + coverage + top metrics.

### 5. Fundamental score breakdown

### 6. Quarterly history

### 7. BCTC

### 8. Data audit/source

## Container

Short-term: dialog can remain.

Desktop future:
evaluate right-side panel only if it clearly improves scanning workflow.

Mobile:
full-height sheet/dialog.

## Decision

**REDESIGN HIERARCHY — P1.**

---

# 21. Stock Detail accessibility audit

Current:

- close button exists;
- Escape closes dialog;
- `role="dialog"` and `aria-modal=true`.

Missing/weak:

- no clear focus trap;
- focus is not explicitly restored to the triggering stock after close;
- click-to-open `<tr>` and `<article>` elements do not provide keyboard activation by themselves.

## Required

For row/card detail:

- semantic button/link inside identity/action cell, OR
- keyboard Enter/Space support + appropriate role/tabindex.

For dialog:

- initial focus;
- focus trap;
- restore focus.

**Decision:** FIX — P1.

---

# 22. Mobile navigation audit

Current bottom navigation has 4 items.

This is appropriate.

Strengths:

- icon + text;
- safe-area work exists;
- active route state.

Keep 4-item architecture for now.

Future Watchlist/User will require an IA decision rather than simply adding more icons.

**Decision:** KEEP.

---

# 23. Dark mode audit

## Strengths

Dark is already coherent:

- navy background;
- surface hierarchy;
- clear positive/negative colors;
- no pure-black terminal.

This is close to CCC “Calm Financial Intelligence”.

## Improvements

- reduce heavy gradient usage;
- reduce decorative colored card backgrounds;
- use signal color more locally;
- simplify shadows;
- strengthen readable secondary text.

Dark should become **calmer**, not brighter.

**Decision:** KEEP DIRECTION / REFINEMENT.

---

# 24. Light mode audit

Light exists but was added through many override rules on top of dark-first CSS.

This creates maintenance risk and has already produced at least one company-name contrast rule problem.

## Target

Do not continue stacking:

```css
html[data-theme="light"] .x { ... }
```

for every individual component.

Create semantic theme tokens:

```text
--bg
--surface-1
--surface-2
--text-primary
--text-secondary
--border
--interactive
--signal...
```

and let shared components consume tokens.

## Decision

**THEME TOKEN REFACTOR — P0/P1.**

---

# 25. CSS maintainability audit

`styles-v18.5.css` contains layers of appended patches:

- base
- v17.x readability/mobile fixes
- v18.1 fundamentals
- v18.2 metadata/BCTC
- v18.3 alignment
- v18.4 Vietstock
- v18.5 near-MA

This history is useful in Git, but production CSS no longer needs to preserve every patch chronologically.

## Risk

Later rules silently override earlier intent.

The malformed Light-mode company rule is an example of this risk.

## Redesign recommendation

For the next major UI release:

- create a clean new versioned CSS file;
- consolidate tokens;
- consolidate responsive rules;
- do not modify v18.5 CSS in place.

Example:

```text
styles-v19.css
```

Keep `styles-v18.5.css` untouched for rollback.

**Decision:** NEW CLEAN CSS RELEASE — P1.

---

# 26. JS maintainability audit

The current `app-v18.5.js` is around 655 lines and still understandable.

No framework migration is required.

However, major UI redesign will make one giant render file harder to maintain.

## Possible controlled improvement

Remain vanilla JS but split production source:

```text
assets/
  app-v19.js
  ui-v19.js
  styles-v19.css
```

or keep one JS if the implementation remains simple.

This is optional.

Do not create architecture work that delays the redesign.

**Decision:** EVOLVING — P2.

---

# 27. Search-state / URL-state audit

Current URL reads:

- signal filter;
- industry group.

Other scanner state such as:

- search;
- exchange;
- sort;

does not survive page refresh/share through URL.

## Opportunity

For future usability:

```text
/danh-sach?q=fpt&exchange=hose&signal=3plus&sort=rvol30
```

Benefits:

- bookmark;
- share;
- back/forward consistency.

Not required for first visual release.

**Decision:** BACKLOG — P2.

---

# 28. Responsive audit — 375px

## Good

- bottom nav;
- mobile cards;
- full-width Scanner cards;
- safe-area padding;
- chips wrap;
- smaller 20-row page size.

## Problems

- Header metadata still large;
- Overview horizontal cards can require lots of swiping;
- text under ~10px still exists;
- Fundamental page can become extremely long;
- entire methodology precedes filters;
- unlimited financial cards are possible.

## Target

- compact trust header;
- full-width decision cards;
- filter bottom sheet;
- paginated fundamentals;
- fewer metrics per card.

**Decision:** REDESIGN — P1.

---

# 29. Responsive audit — 768px

Current CSS switches major navigation at 900px.

768 therefore uses mobile/tablet navigation pattern.

Main risks:

- two-column layouts may still feel card-heavy;
- industry chips;
- detail width;
- fundamental method grid.

## Target

Treat 768 as true tablet:

- compact header;
- 2-column cards where appropriate;
- larger sheet/dialog;
- no forced mobile micro typography.

**Decision:** UPGRADE.

---

# 30. Responsive audit — 1024px

1024 still has desktop sidebar.

Current sidebar decreases to 210px under 1180.

Risks:

- Scanner's 11 columns;
- long fundamental table headers;
- content width.

Horizontal scrolling is acceptable inside data table, but controls and page title must remain stable.

## Target

- narrower but clear sidebar;
- scanner identity column sticky if needed;
- table shell scroll;
- compact filters.

**Decision:** UPGRADE.

---

# 31. Responsive audit — 1440px+

Current max content width 1480px is appropriate for data tables.

Keep wide workspace.

Avoid turning wide space into oversized cards.

**Decision:** KEEP.

---

# 32. Performance audit

## Scanner

Good:

- pagination 50/20.

## Overview

Potential risk:

- early list unlimited;
- 4/4 unlimited;
- 3/4 unlimited;
- 2/4 unlimited.

Cap preview groups.

## Industry

Usually moderate, but selected sector may still be large.

Can keep no pagination initially if measured size is small; otherwise paginate.

## Fundamental

Must paginate.

## Full rerender model

Current `render()` replaces `app.innerHTML` entirely after many state changes.

For current scale this can remain if result counts are controlled.

Avoid rendering 800 cards then rerendering them on every filter.

**Decision:** P1.

---

# 33. Loading and error state audit

## Market data

Reasonable error banner + cache behavior.

## Financial data

Error hidden.

## Metadata

Error hidden.

## Quarterly

Loading/error/empty are visible in Detail.

This is good.

## Target

Create source-specific but concise states.

Example:

```text
● Thị trường: OK
● Dữ liệu cơ bản: OK
● Metadata: OK
```

Only expand failed states.

Do not show three green diagnostic badges continuously.

**Decision:** UPGRADE — P0/P1.

---

# 34. KEEP / UPGRADE / REDESIGN matrix

| Area | Decision | Priority |
|---|---|---:|
| Static HawkHost architecture | KEEP | P0 |
| Supabase data contracts | KEEP | P0 |
| 800-symbol universe behavior | KEEP | P0 |
| Cache/fallback | KEEP | P0 |
| 4 technical signals | KEEP | P0 |
| MA10 reference/sort | KEEP | P0 |
| Dark + Light feature | KEEP | P0 |
| Brand `VNStock Market Scanner` | REDESIGN → Chuyện Chợ Chứng | P1 |
| Permanent sidebar LIVE card | REMOVE | P0 |
| Initial false healthy state | FIX | P0 |
| Financial/metadata hidden error | FIX | P0 |
| Light company-name contrast bug | FIX | P0 |
| Large 4-card metadata header | REDESIGN | P1 |
| Sidebar nav | KEEP / restyle | P1 |
| Mobile bottom nav | KEEP | P1 |
| Typography | UPGRADE | P1 |
| Signal palette | REDESIGN | P1 |
| CCC Signal Rail | ADD | P1 |
| Company names in list/cards | ADD | P1 |
| Search company name | ADD | P1 |
| Overview | REDESIGN hierarchy | P1 |
| Scanner filters | REDESIGN controls | P1 |
| Scanner table | UPGRADE | P1 |
| Stock mobile cards | UPGRADE | P1 |
| Industry picker | KEEP / polish | P2 |
| Industry table | UPGRADE | P1 |
| Fundamental methodology position | REDESIGN | P1 |
| Fundamental pagination | ADD | P0/P1 |
| Fundamental score coverage | UPGRADE prominence | P1 |
| Stock Detail | REDESIGN hierarchy | P1 |
| BCTC Vietstock access | KEEP | P1 |
| CSS append-patch architecture | REFACTOR for new release | P1 |
| Framework migration | DO NOT DO | — |

---

# 35. Proposed visual redesign architecture

## App shell

### Desktop

```text
┌────────────────────┬────────────────────────────────────────────┐
│ Chuyện Chợ Chứng   │ ● LIVE · 15:20 · 800 mã · Dữ liệu đầy đủ │
│                    │                            Theme · Làm mới │
│ Tổng quan          ├────────────────────────────────────────────┤
│ Danh sách          │                                            │
│ Theo ngành         │             PAGE CONTENT                   │
│ Cơ bản             │                                            │
│                    │                                            │
└────────────────────┴────────────────────────────────────────────┘
```

### Mobile

```text
Chuyện Chợ Chứng                    Theme · ↻
● LIVE · 15:20 · 800 mã
─────────────────────────────────────────────
PAGE CONTENT
─────────────────────────────────────────────
Tổng quan · Danh sách · Theo ngành · Cơ bản
```

---

# 36. Proposed Overview architecture

```text
CÓ GÌ ĐÁNG CHÚ Ý LÚC NÀY?

[RVOL30 sớm] [4/4] [≥3] [≥2]

DÒNG TIỀN SỚM
Top candidates → Xem tất cả

TÍN HIỆU RẤT MẠNH
Top candidates → Xem tất cả

ĐANG HÌNH THÀNH
Preview

THỊ TRƯỜNG RỘNG
1/4 preview
```

Prevent repeated long card lists.

---

# 37. Proposed Scanner architecture

## Desktop

```text
Danh sách cổ phiếu

[Tìm mã hoặc tên công ty........] [Bộ lọc] [Sắp xếp]

[HOSE ×] [≥3 tín hiệu ×] [RVOL30 ×]   Xóa tất cả

Hiển thị 38 / 800

TABLE
```

## Mobile

```text
[Tìm mã hoặc tên công ty............]

[Bộ lọc •3] [Sắp xếp]

[HOSE ×] [≥3 ×]

38 / 800 mã

STOCK CARDS
```

---

# 38. Proposed Industry architecture

```text
So sánh theo ngành

[Industry selector — full readable names]

Chứng khoán · 26 mã
Sắp xếp: Điểm cơ bản

Mã + Tên công ty | Điểm/coverage | LN YoY | ROE | P/E | P/B | Signal | Freshness
```

No hidden/truncated desktop industry choices.

---

# 39. Proposed Fundamental architecture

```text
Sàng lọc cơ bản

[Bộ lọc điểm]
[Bộ lọc tăng trưởng]
[Bộ lọc ROE]

312 / 800 mã

RESULTS

[?] Cách tính Điểm cơ bản
    collapsed by default
```

Methodology remains fully available.

---

# 40. Proposed Stock Detail architecture

```text
[Logo] FPT · CTCP FPT
Price + Change
3/4 tín hiệu

VÌ SAO MÃ NÀY ĐÁNG CHÚ Ý?
CCC SIGNAL RAIL

Dòng tiền
Xu hướng

ĐIỂM CƠ BẢN
72 / 85 · Coverage 85%

Tăng trưởng | ROE | P/E | P/B

Breakdown
Quarter history
BCTC Vietstock
```

---

# 41. Mockup plan — before any code

No major UI implementation should start until the following mockups are reviewed.

## Round A — Core product language

Eight core mockups:

1. Overview — PC — Dark
2. Overview — PC — Light
3. Overview — Mobile — Dark
4. Overview — Mobile — Light
5. Scanner — PC — Dark
6. Scanner — PC — Light
7. Scanner — Mobile — Dark
8. Scanner — Mobile — Light

Why eight?

These establish:

- brand;
- shell;
- trust bar;
- typography;
- color system;
- signal rail;
- cards;
- tables;
- filter pattern;
- both themes;
- both main device families.

## Round B — Analysis workflows

After Round A is approved:

9. Industry — PC
10. Industry — Mobile
11. Fundamental — PC
12. Fundamental — Mobile

These can initially use the approved primary theme because Dark/Light component tokens are already established by Round A.

## Round C — Detail

13. Stock Detail — PC
14. Stock Detail — Mobile

Then verify both themes during implementation.

---

# 42. Lovable decision for mockups

**Do not use Lovable for Round A by default.**

Reason:

- product/data structure is now well defined;
- the main need is faithful CCC design, not open-ended visual ideation.

Potential Lovable use later:

- comparing 2–3 alternate visual treatments for one difficult component;
- only after explicit approval.

Current Lovable reserve remains untouched.

---

# 43. Recommended implementation releases after mockup approval

## Release A — UI Foundation

- Chuyện Chợ Chứng branding
- semantic theme tokens
- Light contrast fixes
- Data Trust Bar
- typography
- signal palette
- CCC Signal Rail
- accessibility foundation

## Release B — Overview

- redesigned discovery hierarchy
- capped previews
- company identity

## Release C — Scanner

- command bar
- filter/sort sheet
- company-name search
- table upgrade
- mobile card upgrade

## Release D — Industry + Fundamentals

- industry comparison upgrade
- fundamental filter flow
- pagination
- methodology reposition

## Release E — Stock Detail

- explainability-first
- technical/fundamental hierarchy
- quarterly/BCTC polish

## Release F — QA

- Dark + Light
- 375 / 768 / 1024 / 1440
- keyboard
- 800-symbol data
- missing/stale/error
- performance
- HawkHost deployment package

---

# 44. What must NOT happen during redesign

- Do not edit only HawkHost and forget Git.
- Do not overwrite v18.5 assets in place.
- Do not delete v18.5 rollback.
- Do not call Lovable without approval.
- Do not add framework migration to the visual redesign.
- Do not change signal thresholds.
- Do not turn MA10 into a core signal.
- Do not normalize incomplete fundamental score to 100.
- Do not hide fundamental coverage.
- Do not let Watchlist/UI actions alter scanner universe.
- Do not remove Light mode.
- Do not remove Dark mode.
- Do not ship major redesign before PC/mobile mockup approval.

---

# 45. Final audit decision

v18.5 should remain the stable rollback baseline.

The redesign should move forward as a new version rather than modifying production assets destructively.

Recommended next step:

> **Create Round A mockups: Overview + Scanner, PC + Mobile, Dark + Light.**

After visual approval, implement a new versioned UI foundation while preserving all current scanner/data logic.

---

## Audit source files

Primary source inspected:

- `website/index.html`
- `website/VERSION.txt`
- `website/assets/app-v18.5.js`
- `website/assets/styles-v18.5.css`

This audit supersedes the obsolete audit written against the removed React/Lovable `dashboard/` frontend.
