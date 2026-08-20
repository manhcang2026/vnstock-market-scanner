# CCC PAGE PATTERNS v1.1

**Parent:** `CCC_UIUX_MASTER.md`  
**Production baseline:** v18.5  
**Status:** ACTIVE

---

# 1. Global App Shell

## Primary job

Navigate product areas while keeping system/data state understandable.

## Desktop

Current architecture to retain initially:

- fixed sidebar;
- top status/actions;
- main content.

Target refinement:

- Chuyện Chợ Chứng brand;
- compact Data Trust;
- reduce duplicate status blocks;
- clear route active state;
- Light/Dark;
- refresh/countdown.

## Mobile

- compact top identity/status;
- bottom navigation;
- safe-area;
- page content not hidden under nav.

---

# 2. Tổng quan `/`

## Primary job

Answer:

**“Hiện tại có gì đáng chú ý trong scanner?”**

## Current data

- RVOL30 early list;
- counts 4/4, 3/4, 2/4, 1/4;
- stock cards;
- links to filtered scanner.

## Target hierarchy

### A. Compact trust bar

### B. Attention Summary

Show no more than a few decision KPIs:

- RVOL30 early alerts
- 4/4
- ≥3
- optionally ≥2

### C. Cảnh báo dòng tiền sớm

Priority discovery section.

Do not duplicate every item excessively between KPI and cards.

### D. Tín hiệu mạnh

4/4 + 3/4.

### E. Đang hình thành

2/4.

### F. Tín hiệu ban đầu

1/4 preview only.

## Mobile

- KPI grid 2 columns or compact horizontal pattern;
- cards full width;
- 1/4 heavily limited;
- no tiny 4-column micro-metrics if unreadable.

## Dark/Light

Both must be mocked before major redesign approval.

---

# 3. Danh sách cổ phiếu `/danh-sach`

## Primary job

Find, filter, sort and compare scanner data efficiently.

## Current real controls

### Search
Symbol.

### Exchange
- all
- HOSE
- HNX
- UPCoM

### Signal filters
- all
- 4/4
- ≥3
- ≥2
- RVOL30 ≥200%
- price ≥3%
- volume ≥200%
- above MA200
- missing data

### Sort
- signal priority
- RVOL30 high/low
- price change high/low
- daily volume high/low
- nearest MA10
- nearest MA200
- A–Z

## Desktop target

1. compact trust/app shell;
2. Scanner Command Bar;
3. active filter summary;
4. result count;
5. table;
6. detail dialog/panel.

Avoid three huge blocks of chips.

## Mobile target

1. search;
2. filter button + count;
3. sort button;
4. active filter chips;
5. stock cards;
6. detail sheet.

## Table identity

When metadata integration is added to list:

`Logo + Mã`
`Tên công ty`

Do not sacrifice key numeric columns just to fit long company names.

---

# 4. So sánh theo ngành `/so-sanh-theo-nganh`

## Primary job

Answer:

**“Trong cùng một ngành, doanh nghiệp nào nổi bật hơn theo các chỉ tiêu đang có?”**

## Current real fields

- website_group;
- score;
- profit YoY;
- ROE;
- P/E;
- P/B;
- technical signal;
- freshness.

## Target desktop

### Page intro
Short.

### Industry selector
Full visibility and wrapping.

### Comparison context
Show:

- industry name;
- number of companies;
- sort basis.

### Table
Priority:

1. Company identity
2. Score + coverage
3. Profit growth
4. ROE
5. Valuation
6. Technical
7. Freshness

All table columns centered only if appropriate; numeric comparison may be right aligned for faster scanning.

## Mobile

- horizontally scrollable industry choices;
- cards;
- company identity + score first;
- 4 key metrics;
- detail on tap.

## Explainability

Score denominator/coverage visible.

Freshness labels must remain.

---

# 5. Sàng lọc cơ bản `/sang-loc-co-ban`

## Primary job

Answer:

**“Doanh nghiệp nào phù hợp với các tiêu chí cơ bản tôi chọn?”**

## Current real filters

- minimum score ratio
- profit growth
- ROE

## Target hierarchy

### A. Page intro
One short paragraph.

### B. Filter Controls
Immediately usable.

### C. Result Count

### D. Result table/cards

### E. “Cách tính Điểm cơ bản”
Collapsed/secondary by default or positioned so it does not block the workflow.

## Why

User comes to screen to screen companies, not to read methodology first.

Methodology remains fully available for trust.

## Table/card

Always show score coverage.

---

# 6. Stock Detail — shared across pages

## Primary job

Answer:

**“Mã này có gì đáng chú ý về kỹ thuật và cơ bản?”**

## Header

- logo;
- symbol;
- company name;
- exchange;
- price/change;
- score/signal summary.

## Section 1 — Why notable

Plain Vietnamese.

## Section 2 — Technical

- signal rail;
- KL/KLTB10;
- MA10;
- MA200;
- RVOL30;
- sample count.

## Section 3 — Fundamental Summary

- score/available;
- coverage;
- industry;
- profit YoY;
- ROE;
- P/E;
- P/B;
- freshness.

## Section 4 — Score breakdown

Progressively disclosed.

## Section 5 — Quarterly

## Section 6 — BCTC

External Vietstock source.

## Section 7 — Data trust/audit

Only when necessary.

---

# 7. Dark Mode page pattern

Dark is not a separate product.

All four routes must share:

- same IA;
- same hierarchy;
- same semantics;
- token-swapped surfaces;
- equivalent contrast.

Avoid unique dark-only decorations.

---

# 8. Light Mode page pattern

Light is not a simplified mode.

All features and data remain identical.

Avoid pale semantic colors that lose state distinction.

---

# 9. Future Watchlist

When implemented:

## Rule

Watchlist only controls personalized display.

Removing from watchlist never changes scanner universe.

## Likely route

To be decided.

Do not add route before backend/user model exists.

---

# 10. Future User/Account

Future-ready only.

Potential:

- profile;
- password;
- membership;
- notification preferences;
- logout.

Do not add fake account UI to production.

---

# 11. Future Notifications

Potential scanner alerts:

- Email;
- Telegram;
- in-app.

Channel appears only after backend support.

Avoid alert spam.

---

# 12. Future Admin

Admin controls must distinguish:

- user/display/watchlist;
- backend scanner universe.

Dangerous backend actions separate and explicit.

---

# 13. Page design review template

For each page change, write:

## Primary job

## Current production behavior

## Real data fields

## User problems

## Keep

## Upgrade

## Redesign

## Desktop wireframe

## Mobile wireframe

## Dark mode

## Light mode

## Loading/error/missing

## Accessibility

## Performance

## Approval status

No major implementation before approval of mockup/wireframe.
