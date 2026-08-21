# CCC COMPONENT RULES v1.1

**Parent:** `CCC_UIUX_MASTER.md`  
**Baseline:** production v18.5  
**Status:** ACTIVE

---

# 1. General component rule

Before creating a new visual component:

1. Find whether an equivalent component already exists in v18.5.
2. Decide Keep / Upgrade / Replace.
3. Map state to semantic meaning.
4. Define Dark + Light.
5. Define desktop + mobile.
6. Define loading/missing/error if data-driven.
7. Ensure accessibility.
8. Avoid new one-off visual language.

---

# 2. Sidebar Navigation

## Current role

Primary desktop navigation.

Current routes:

- Tổng quan
- Danh sách cổ phiếu
- So sánh theo ngành
- Sàng lọc cơ bản

## Requirements

- active route unmistakable;
- 14–15px readable labels;
- clear icons;
- brand at top;
- system status should not consume excessive space;
- future account/watchlist sections only after feature exists.

## Do not

- use the sidebar as a diagnostic dashboard;
- show large decorative LIVE blocks if they push navigation down unnecessarily.

---

# 3. Mobile Bottom Navigation

## Current role

Primary mobile navigation.

## Requirements

- current route clear beyond color;
- icon + text;
- safe-area aware;
- no overlap with page content;
- important labels not <9px;
- keep tap targets comfortable.

If future routes exceed comfortable capacity, redesign IA rather than squeeze more items.

---

# 4. Brand Block

Product-facing name should become **Chuyện Chợ Chứng**.

`VNStock Market Scanner` may remain a technical/internal descriptor if needed, not the primary user brand.

Logo/mark must render consistently Dark/Light and mobile/desktop.

---

# 5. Data Trust Bar

Preferred replacement for oversized metadata panels.

Content priority:

1. LIVE / warning
2. updated time
3. total symbols
4. data completeness
5. countdown/refresh

Secondary diagnostics may open in disclosure.

States:

- loading;
- live healthy;
- degraded;
- error + cache;
- outside trading window.

---

# 6. Theme Toggle

Required feature.

Must:

- indicate target/current state clearly;
- have `aria-label`;
- persist preference;
- update theme without page reload;
- remain visible on desktop;
- remain reachable on mobile, either header/menu/settings.

---

# 7. Refresh Control

Must distinguish:

- idle;
- refreshing;
- waiting for next data;
- outside auto-refresh window.

Do not disable access to currently displayed cached data while refresh is running.

---

# 8. KPI Card

Use only for decision-relevant aggregates.

Current examples:

- RVOL30 early alerts;
- 4/4;
- ≥3;
- ≥2.

Rules:

- value is primary;
- label readable;
- technical explanation secondary;
- click behavior leads to corresponding filtered scanner;
- do not use warning/error semantics as decorative KPI color.

---

# 9. Stock Card

Used on mobile and Overview.

## Identity

When available:

- logo;
- symbol;
- exchange;
- company display name where space allows.

## Decision hierarchy

1. symbol/company;
2. price/change;
3. signal rail/count;
4. strongest evidence;
5. secondary metrics.

## Current metrics available

- KL ngày;
- MA10 distance;
- MA200 distance;
- RVOL30;
- RVOL30 sessions.

Do not display all with identical emphasis.

## Future inline actions

If Watchlist is added, do not nest interactive controls inside another `<button>`/clickable control improperly.

---

# 10. CCC Signal Rail

## Table

`● ● ● ○ 3/4`

## Card

Rail + `3/4 tín hiệu`

## Detail

Four rows with:

- condition name;
- measured value if useful;
- pass/not pass;
- explanatory label.

`0/4` has neutral style.

---

# 11. Scanner Search

Current search matches symbol.

Until company-name search is actually implemented, placeholder must not promise it.

If metadata search is added later:

`Tìm mã hoặc tên công ty…`

Requirements:

- 15–16px input on mobile;
- no freeze while typing;
- clear action;
- Enter works;
- search state persists when practical.

---

# 12. Filter Group

Current scanner groups:

- exchange;
- signal;
- sort.

Current fundamental groups:

- score;
- profit growth;
- ROE.

Rules:

- do not show all options as an unbounded wall;
- short quick filters may be chips;
- large filter sets use sheet/popover;
- active state beyond color;
- clear-all when multiple filters active.

---

# 13. Result Count

Always present near result list.

Format:

`Hiển thị 38 / 800 mã`

For industry:

`26 mã trong ngành Chứng khoán`

For fundamental:

`Hiển thị 312 / 800 mã`

---

# 14. Scanner Table

Primary desktop analysis surface.

## Alignment

- symbol/company: left;
- exchange: compact;
- numeric values: right;
- signal/status: center or compact.

## Current production fields available

- Mã
- Sàn
- Giá
- % thay đổi
- KL ngày
- Cách MA10
- Cách MA200
- RVOL30
- Phiên RVOL30
- Tín hiệu
- Trạng thái dữ liệu

## Requirements

- Phase 1 desktop public result grid uses exactly five real proportional columns: `Identity | Price | Change | Current Volume | CCC`;
- no filler column;
- Identity and Market Quote are public; CCC Technical Intelligence is entitled or professionally locked;
- additional technical fields above belong in entitled technical detail/filter/sort contexts and must not silently become public columns;
- sticky header for long table;
- readable 13.5–15px values;
- sortable state clear;
- selected row state if detail is open;
- keyboard-accessible open-detail path;
- sticky identity column may be evaluated.

Normal `Đầy đủ` state should be visually quiet; problems should stand out.

---

# 15. Fundamental Table

Used by Industry and Fundamental Screener as **Public Fundamental Research**.

Core columns:

- Symbol
- Industry when relevant
- Fundamental Score
- Score Coverage
- Profit YoY
- Revenue/Income YoY when available
- Quarterly Growth when available
- ROE
- ROA
- Debt/Equity
- Debt/Assets
- P/E
- P/B
- Freshness
- Quarterly History/BCTC access where appropriate

Do not include signal count, CCC Signal Rail, RVOL30, MA10, MA200, or technical signal columns in this table.

## Score cell

Must show:

- numerator;
- available denominator/coverage.

Avoid only showing a colored score badge.

## Header

Technical term + plain-language sublabel.

Example:

`ROE`
`Lợi nhuận / vốn chủ`

---

# 16. Industry Selector

Desktop:

- all common industry choices should be easy to scan;
- wrap/grid intentionally;
- no truncated industry names.

Mobile:

- horizontal scroll is acceptable;
- selected chip clearly anchored;
- count visible but secondary.

---

# 17. Fundamental Filter Panel

Must communicate:

- filter name;
- user-friendly meaning;
- selected value;
- result effect.

Use progressive disclosure for score methodology.

Do not place the entire 100-point methodology before actionable results unless user explicitly opens it.

---

# 18. Fundamental Score Badge

States:

- High
- Medium
- Low
- Not enough data

Must include readable text/number, not color only.

Tooltip/title alone is insufficient for important coverage meaning.

---

# 19. Freshness Tag

Current semantic values:

- CURRENT → Mới nhất
- LAGGING → Chậm 1 kỳ
- STALE → Dữ liệu cũ
- NO_DATA → Chưa có dữ liệu

Must remain explicit text.

---

# 20. Company Logo

Behavior:

- async image;
- ticker fallback;
- image error must not break layout;
- fixed visual size per context;
- accessible alt when meaningful.

Contexts:

- table;
- card;
- detail.

---

# 21. Company Name

Desktop:

- full name when room exists;
- secondary to symbol;
- truncate only with access to full value.

Mobile:

- short display name preferred;
- max two lines or controlled truncation.

---

# 22. Detail Dialog / Panel

Current production uses a wide dialog.

Short term it may be retained.

Long term desktop option:

- right detail panel if it improves scanner continuity.

Mobile:

- full-height dialog/sheet.

Required:

- close button;
- Escape;
- scroll management;
- clear sections;
- no enormous raw metric grid at top.
- public identity/quote remain visible;
- tabs are Tổng quan, Kỹ thuật, Cơ bản, BCTC;
- Kỹ thuật is entitled or locked before protected content renders;
- Cơ bản/BCTC research is public when real data exists;
- public fundamentals and protected technical intelligence remain visually separated.

---

# 23. “Why notable?” Block

New standard component for Stock Detail.

Generated only from real data.

Example:

- `Giá tăng +4.2% — đạt ngưỡng ≥3%`
- `KL ngày 235% KLTB10 — đạt`
- `Giá cao hơn MA200 6.4% — đạt`
- `RVOL30 174% — chưa đạt ngưỡng 200%`

This is interpretive presentation, not investment advice.

---

# 24. Fundamental Summary

This is a public research component. Top fundamental detail should show:

- score / available;
- coverage;
- industry;
- profit growth;
- revenue/income and quarterly growth when available;
- ROE;
- ROA;
- debt/equity and debt/assets;
- P/E;
- P/B;
- freshness.

Then show badges and breakdown.

---

# 25. Score Breakdown

Each part:

- criterion;
- measured value;
- earned / max available;
- explanation.

Missing criterion:

- say unavailable;
- do not silently show 0 unless business rule truly defines it as 0.

---

# 26. Quarterly History

Table or responsive list.

Fields currently:

- period;
- income/revenue;
- net profit;
- YoY profit growth;
- ROE.

Requirements:

- numeric alignment;
- readable period;
- loading/error/empty distinct;
- mobile horizontal strategy intentional.

---

# 27. BCTC Access Card

Must show:

- `Báo cáo tài chính`;
- stock symbol;
- external source `VietstockFinance`;
- external-link indicator.

Button/link:

`Xem BCTC trên Vietstock ↗`

Do not label as internal library.

---

# 28. Empty State

Different states:

- no scanner match;
- no signal candidate;
- no financial data;
- no quarterly history;
- no industry selection;
- no search result.

Each must explain why and, when useful, recovery.

---

# 29. Error Banner

For API failure:

- clear user language;
- if cache retained, say so;
- never replace usable page with raw exception text;
- allow refresh/retry.

---

# 30. Loading State

Initial load and refresh are different.

Initial:

- stable skeleton/boot.

Refresh:

- keep current data;
- spinner/status only.

Financial/metadata/quarterly fetch may have independent loading states.

---

# 31. Pagination

Production currently:

- desktop 50 rows/page;
- mobile 20 rows/page based on viewport.

Rules:

- preserve context;
- clear current page;
- buttons sufficiently large;
- result count remains visible.

If virtualization replaces pagination later, require performance evidence.

---

# 32. Component acceptance

- [ ] Dark defined.
- [ ] Light defined.
- [ ] Desktop defined.
- [ ] Mobile defined.
- [ ] Real field contract known.
- [ ] Loading state defined if needed.
- [ ] Missing/error defined if needed.
- [ ] State not color-only.
- [ ] Important text readable.
- [ ] Keyboard path exists.
- [ ] No scanner-universe side effect.
