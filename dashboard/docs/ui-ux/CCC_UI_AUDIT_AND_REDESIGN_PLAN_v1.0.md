# CCC UI AUDIT & REDESIGN PLAN v1.0

**Product:** Chuyện Chợ Chứng — Stock Market Scanner  
**Audit date:** 2026-08-20  
**Audited branch:** `main`  
**Design standard:** CCC UI/UX Design System v1.0  
**Status:** IMPLEMENTATION PLANNING  
**Scope:** Current `dashboard/` UI only. No backend/scanner-logic change is authorized by this document.

---

# 1. Executive conclusion

The current dashboard has a **good technical UI foundation** but is not yet a complete Chuyện Chợ Chứng product interface.

The strongest existing foundations are:

- semantic OKLCH color tokens;
- separate desktop table / mobile card strategy;
- normalized scanner data model;
- clear four-signal logic;
- tabular numeric utility;
- reusable scanner components;
- current route separation between Overview and Stock List.

The largest gaps against CCC UI/UX Design System v1.0 are:

1. product identity is still partly Lovable/VNStock rather than Chuyện Chợ Chứng;
2. Data Trust presentation is too large and has an incorrect initial-state risk;
3. essential labels are frequently 10–11px;
4. Overview is structurally repetitive and too section-heavy;
5. Scanner filtering is a growing wall of chips;
6. desktop table needs stronger workbench behavior and keyboard accessibility;
7. Stock Card gives too many metrics similar visual weight;
8. Stock Detail explains raw data before explaining “why this stock is notable”;
9. `0/4` signal semantics are not explicitly modeled in group metadata;
10. current `main` data source is configured as DEMO, so production-data integration must be confirmed before final QA.

The redesign should **preserve the data and component architecture where useful**, not rebuild the dashboard from zero.

---

# 2. Audit method

Each area is classified as:

- **KEEP** — already consistent with CCC direction;
- **UPGRADE** — keep architecture but improve behavior/presentation;
- **REDESIGN** — structure or hierarchy should change materially;
- **REMOVE / REPLACE** — current pattern should not continue.

Priority:

- **P0** — data trust, correctness, semantic or release-blocking issue;
- **P1** — major UX/workflow issue;
- **P2** — consistency/readability improvement;
- **P3** — visual polish.

---

# 3. Current architecture summary

Current major UI surfaces:

- `dashboard/src/routes/__root.tsx`
- `dashboard/src/routes/index.tsx`
- `dashboard/src/routes/danh-sach.tsx`
- `dashboard/src/components/scanner/AppHeader.tsx`
- `dashboard/src/components/scanner/SummaryCards.tsx`
- `dashboard/src/components/scanner/StockCard.tsx`
- `dashboard/src/components/scanner/StockTable.tsx`
- `dashboard/src/components/scanner/StockDetailDialog.tsx`
- `dashboard/src/components/scanner/signal-meta.ts`
- `dashboard/src/lib/scanner/types.ts`
- `dashboard/src/lib/scanner/filters.ts`
- `dashboard/src/lib/scanner/data-source.ts`
- `dashboard/src/styles.css`

Current real UI model supports:

- symbol;
- exchange;
- current price;
- price change;
- daily volume ratio;
- MA200 and distance;
- RVOL30;
- sample/session counts;
- four scanner conditions;
- missing-data status;
- trading/update timestamps;
- source/system metadata.

Future fields must remain future-only until real contracts exist:

- company name;
- company logo;
- industry;
- watchlist;
- user account;
- notification settings;
- fundamental analysis;
- financial reports in stock detail.

---

# 4. P0 findings — fix before visual polish

## P0.1 Product/root metadata still contains Lovable identity

### Current

`__root.tsx` contains:

- title `Lovable App`;
- description `Lovable Generated Project`;
- author `Lovable`;
- social metadata related to Lovable;
- `<html lang="en">`;
- 404/error interface in English.

Page routes also still use `VNStock Market Scanner` naming.

### Problem

This conflicts with the new product authority:

**Chuyện Chợ Chứng**

It also creates:

- inconsistent browser/share metadata;
- incorrect document language;
- product-brand leakage from the builder;
- inconsistent Vietnamese user experience.

### Action

**REDESIGN / FIX — P0**

- set document language to `vi`;
- replace Lovable root metadata;
- establish Chuyện Chợ Chứng product title/description;
- localize global error/404 states;
- align page metadata with CCC naming.

### Lovable

Not needed.

---

## P0.2 AppHeader can show false status before metadata loads

### Current logic

The header currently effectively treats:

- `meta?.systemStatus !== "OK"` as a system problem;
- `meta?.mode !== "LIVE"` as DEMO.

When `meta` is initially `undefined`, both conditions evaluate into negative states.

### User risk

During initial query loading, the UI can temporarily communicate:

- “Hệ thống có sự cố”
- “DEMO”

before real metadata is available.

This is a **Data Trust violation**.

### Action

**REDESIGN — P0**

Introduce explicit trust states:

- `loading`;
- `live-ok`;
- `live-degraded`;
- `live-error`;
- `demo`;
- optional `stale`.

Never infer DEMO/error from missing metadata.

### Acceptance

Before metadata loads:

`Đang kiểm tra dữ liệu…`

or equivalent neutral loading state.

### Lovable

Not needed.

---

## P0.3 Signal group metadata does not explicitly support 0/4

### Current

`StockRow.signalCount` correctly allows:

`0 | 1 | 2 | 3 | 4`

But `GROUPS` contains only:

`1 | 2 | 3 | 4`

and `groupOf()` falls back to the 1/4 group.

### Risk

A `0/4` stock can inherit 1/4 styling even though its displayed count remains `0/4`.

This is semantically misleading.

### Action

**UPGRADE — P0**

Create explicit neutral `0/4` metadata or return a neutral group for zero.

Example:

- `0/4 — Chưa có tín hiệu`
- neutral surface/border/text;
- never signal-1 color.

### Lovable

Not needed.

---

## P0.4 Final UI QA cannot rely only on current DEMO source

### Current repo state

`data-source.ts` currently has:

`DATA_MODE = "demo"`

and an empty GAS endpoint.

### Meaning

The UI architecture can be redesigned now, but final acceptance must not be based only on local demo data if the actual deployed product uses another live/Supabase integration.

### Action

**ENVIRONMENT CHECK — P0 before final QA**

Do not change the source as part of UI work.

Before final production QA:

1. confirm which frontend/data integration is currently deployed;
2. confirm the production data contract;
3. run UI using realistic/full universe data;
4. test missing/stale/problem rows.

---

# 5. App Shell / Header audit

## Classification

**REDESIGN — P1**

## Keep

- refresh action;
- LIVE/DEMO concept;
- system status;
- data update time;
- source information;
- route navigation concept.

## Change

Current header places four metadata blocks plus statuses and navigation before primary page content.

On mobile this consumes too much vertical space.

### New target

**CCC App Shell + compact Data Trust Bar**

Desktop concept:

`[Chuyện Chợ Chứng] [Tổng quan] [Scanner] ... [User]`

Trust line:

`● LIVE · Cập nhật 14:15 · 800 mã · Dữ liệu đầy đủ`

Mobile concept:

- compact brand/header;
- only essential trust state visible;
- deeper diagnostics via disclosure.

## Future readiness

Navigation architecture should support later:

- Watchlist;
- Notifications;
- Account;
- Admin (role gated).

Do not show these routes before implementation.

---

# 6. Typography audit

## Classification

**UPGRADE — P1**

## Strong issue

10–11px text appears throughout important scanner UI.

Examples include:

- metric labels;
- exchange badges;
- signal chips;
- section labels;
- status metadata;
- summary hints;
- table signal badges.

This directly conflicts with CCC's locked “no essential tiny text” rule.

## Target

During redesign:

- important label: 13px minimum target;
- mobile body/data: approximately 16px where appropriate;
- table data: 14–15px;
- symbol: 15–16px+ bold;
- section title: 18–20px;
- tabular figures retained.

## Font

Current system uses Arial/Helvetica stack.

CCC target is IBM Plex Sans or approved equivalent, but migration should be done once globally, not ad hoc per component.

### Action

**Foundation task**

- introduce approved typography token scale;
- test Vietnamese rendering;
- test loading/performance;
- then remove local tiny-size patterns.

---

# 7. Color/token audit

## Classification

**KEEP + UPGRADE — P2**

## Keep

Current architecture is good:

- OKLCH;
- semantic background/card/border tokens;
- market up/down/neutral;
- early alert;
- signal 1–4;
- light/dark token definitions;
- `tabular` numeric utility.

Do not replace this with raw Tailwind/hex styling.

## Upgrade

Rename/extend semantic meanings where needed:

- trust healthy/degraded/error;
- signal zero;
- stale data;
- info/warning if required;
- component-level tokens only after a real shared need appears.

## Important

Do not change market colors into “buy/sell” colors.

---

# 8. Overview audit

## Classification

**REDESIGN — P1**

## Current strengths

- early RVOL30 is prioritized;
- summary cards link directly into scanner filters;
- 4/4 through 1/4 grouping has understandable logic;
- 1/4 group is already preview-limited.

## Current problems

### A. Equal-weight summary cards

Current summary cards place:

- early RVOL alert;
- 4/4;
- ≥3;
- data error count

in the same visual pattern.

These values do not have equal decision meaning.

### B. Duplicate information

Early RVOL appears as:

- a summary card;
- then a full alert section.

### C. Long sequential grouping

The page proceeds through:

- early;
- 4/4;
- 3/4;
- 2/4;
- 1/4.

This can become a long “stack of lists” rather than a discovery dashboard.

## New target hierarchy

1. compact trust state;
2. “Có gì đáng chú ý lúc này?” attention summary;
3. early money-flow alerts;
4. strong convergence 4/4 + 3/4;
5. forming signals 2/4;
6. 1/4 only preview/secondary.

## Keep business semantics

Do not change how signals are calculated.

---

# 9. Summary Cards audit

## Classification

**REDESIGN — P2**

## Keep

Clickable aggregate → filtered scanner is a good pattern.

## Change

Use KPI cards only for genuinely decision-relevant aggregates.

Data-quality problems should preferably be part of trust/status UI unless the user is in an admin/diagnostic workflow.

Avoid four colored cards merely because four numbers exist.

---

# 10. Scanner / Stock List audit

## Classification

**REDESIGN controls + KEEP result architecture — P1**

## Current strengths

- search;
- exchange filtering;
- signal filtering;
- sorting;
- visible result count;
- desktop table;
- mobile cards;
- route search state for signal filter.

## Main issue: chip wall

Current UI renders separate chip groups for:

- exchange;
- signal;
- sorting.

This is manageable today but will not scale when adding:

- industry;
- watchlists;
- fundamentals;
- additional technical indicators;
- personalized views.

## New target: Scanner Command Bar

Desktop:

`[Tìm mã...] [Bộ lọc] [Sắp xếp] [Watchlist]`

Active filters:

`[HOSE ×] [≥3 tín hiệu ×] [RVOL30 ×]   Xóa tất cả`

Mobile:

`[Tìm mã...]`

`[Bộ lọc •N] [Sắp xếp]`

Watchlist enters only when the feature exists.

## Current search

Search correctly only advertises stock-symbol search.

Do not add company-name placeholder until real company-name data enters the UI contract.

## State preservation

During redesign preserve:

- search;
- filters;
- sort;
- detail open/close context;
- ideally scroll position.

---

# 11. Stock Table audit

## Classification

**UPGRADE — P1**

The table architecture should be preserved.

## Keep

- real table semantics;
- right-aligned numeric columns;
- tabular numerals;
- dedicated signal/status columns;
- click-to-detail behavior.

## Fixes

### P0/P1 — keyboard interaction

Rows are focusable with `tabIndex={0}` but current code does not implement Enter/Space activation.

Fix using either:

- semantic interactive content, or;
- proper `onKeyDown` handling.

### P1 — workbench behavior

Add/evaluate:

- sticky header;
- explicit selected row state when side detail opens;
- stronger column hierarchy;
- sortable headers or a clearly linked sort system;
- sticky identity column if required by final width;
- horizontal strategy at 1024px.

### P2 — Signal Rail

Replace plain `3/4` pill as the sole compact signal representation with CCC Signal Rail.

### P2 — data status

Data status should be compact and secondary unless there is a problem.

Normal “Đầy đủ” should not compete visually with signal/price data.

---

# 12. Stock Card audit

## Classification

**UPGRADE — P1**

## Keep

- semantic `<button>`;
- full-card touch target;
- responsive metric grid;
- signal flag availability;
- clear price/change identity.

## Problems

### Tiny labels

Current metrics and chips use 10–11px extensively.

### Equal-weight evidence

Four metrics are shown with similar visual importance:

- KL ngày;
- cách MA200;
- RVOL30;
- phiên RVOL30.

A mobile card should answer the decision first rather than present four mini-columns equally.

### Whole card as button

Currently good for a single action, but future inline actions such as:

- add/remove watchlist;
- alert toggle;

cannot be nested inside a button.

The redesigned card should anticipate this before user features are added.

## New target

Card hierarchy:

1. symbol / company identity;
2. price + change;
3. CCC Signal Rail;
4. strongest 1–2 supporting reasons;
5. disclosure to detail.

Do not remove technical data; move secondary evidence into detail.

---

# 13. Stock Detail audit

## Classification

**REDESIGN — P1**

## Current strengths

- complete current scanner values;
- price/trend;
- daily volume;
- RVOL30;
- data audit details;
- signal flags;
- disclaimer.

## Current problem

The content answers:

`What are all the values?`

before answering:

`Why is this stock notable?`

That is the wrong order for CCC's explainability-first principle.

## New target order

1. stock identity;
2. price/change;
3. CCC Signal Rail;
4. **Vì sao mã này đáng chú ý?**
5. money-flow evidence;
6. trend evidence;
7. future fundamentals/reports only when real;
8. data audit/trust information.

## Container strategy

Current modal is acceptable for today's size but should not be the permanent structure.

Target:

- desktop: right-side detail panel/drawer;
- mobile: full-height sheet or dedicated detail view.

This preserves scanner context while allowing future growth.

---

# 14. Global error / empty UX audit

## Classification

**UPGRADE — P1/P2**

## Current

Global error and 404 are still English.

Scanner has useful empty text for no matching rows.

## New standard

Localize global states and distinguish:

- loading;
- no results;
- no qualifying signal;
- missing data;
- stale data;
- fetch/system error.

Do not display raw technical backend exceptions as primary user copy.

---

# 15. Responsive audit

## Classification

**KEEP strategy + UPGRADE implementation — P1**

## Strong existing decision

Desktop uses table and smaller screens use cards.

This aligns with CCC and should stay.

## Required test checkpoints

- 375px
- 768px
- 1024px
- 1440px

## Specific risks

### 375px

Header/data metadata currently consumes too much vertical space.

### 768px

Current card design is generally appropriate, but filter controls may become bulky.

### 1024px

Ten-column table begins at `lg`; verify real widths because it may become cramped.

### 1440px

`max-w-7xl` may be acceptable for Overview but Scanner may benefit from a wider workbench container depending on the final table columns.

---

# 16. Accessibility audit

## Classification

**UPGRADE — P0/P1**

Required changes:

- keyboard activation for interactive table rows;
- visible focus on custom links/chips;
- ensure color is never the sole signal cue;
- maintain actual table semantics;
- localize `lang`;
- verify dialogs/sheets focus management after migration;
- do not make technical explanations hover-only.

Good existing elements:

- stock card is a semantic button;
- refresh has an aria-label;
- input has aria-label;
- overview sections use headings/labels.

---

# 17. Performance audit

## Classification

**VERIFY + UPGRADE — P1**

Current filtering uses in-memory arrays and `useMemo`, which is structurally reasonable for a moderate universe.

Before expanding to a much larger display set:

- profile search/filter responsiveness;
- avoid unnecessary whole-page rerenders;
- evaluate virtualization for long desktop lists;
- retain current data during refresh;
- avoid expensive per-row visual effects.

No virtualization should be added blindly before measurement.

---

# 18. KEEP / UPGRADE / REDESIGN matrix

| Area | Decision | Priority | Key reason |
|---|---|---:|---|
| Semantic token architecture | KEEP | P2 | Good foundation |
| OKLCH light/dark values | KEEP/UPGRADE | P2 | Consistent system |
| Tabular numeric utility | KEEP | P1 | Correct financial pattern |
| Global root metadata | REDESIGN | P0 | Lovable/en branding leakage |
| AppHeader | REDESIGN | P0/P1 | Data trust + density |
| Navigation concept | KEEP/UPGRADE | P1 | Must scale to users |
| Summary cards | REDESIGN | P2 | Equal-weight KPI problem |
| Overview structure | REDESIGN | P1 | Too sequential/repetitive |
| Search | KEEP/UPGRADE | P1 | Correct today, future-ready later |
| Filter chips | REPLACE pattern | P1 | Won't scale |
| Sort logic | KEEP | P1 | Existing logic useful |
| Result count | KEEP | P1 | Good feedback |
| Desktop StockTable | KEEP/UPGRADE | P1 | Good architecture |
| Mobile StockCard | KEEP/UPGRADE | P1 | Correct device strategy |
| Stock Detail Dialog | REDESIGN | P1 | Explainability + growth |
| Four-signal business logic | KEEP | P0 | Product truth |
| Signal metadata | UPGRADE | P0 | Add explicit 0/4 |
| Tiny 10/11px labels | REPLACE | P1 | Readability |
| Global error/404 | REDESIGN | P1 | English/generic |
| Current data-source mode | DO NOT TOUCH in UI | P0 QA note | Integration must be confirmed |

---

# 19. Recommended implementation sequence

## Phase 0 — correctness and product identity

Small but important groundwork:

1. Chuyện Chợ Chứng root metadata;
2. `lang="vi"`;
3. Vietnamese global error/404;
4. explicit loading state in Data Trust;
5. explicit neutral `0/4` signal state.

**Goal:** remove false/misleading product states before visual work.

---

## Phase 1 — Foundation + App Shell

Implement:

- CCC typography tokens;
- brand identity;
- compact Data Trust Bar;
- new App Shell;
- responsive shell behavior;
- preserve refresh;
- preserve existing routes.

**No business logic changes.**

---

## Phase 2 — Overview v2

Implement:

- attention summary;
- early alerts;
- strong signals;
- forming signals;
- limited low-signal preview;
- reduce duplication.

---

## Phase 3 — Scanner Workbench v2

Implement:

- Scanner Command Bar;
- scalable filter sheet/popover;
- active filter summary;
- upgraded StockTable;
- upgraded StockCard;
- CCC Signal Rail;
- state preservation.

---

## Phase 4 — Stock Detail v2

Implement:

- explainability-first hierarchy;
- desktop side panel;
- mobile sheet;
- current data sections;
- future extension slots without fake data.

---

## Phase 5 — QA and production-data validation

Run:

- CCC QA checklist;
- 375/768/1024/1440;
- keyboard;
- realistic/full data;
- missing/problem rows;
- performance profiling.

---

## Phase 6 — Member UX

Only after the core scanner is stable:

1. Watchlist;
2. Notifications;
3. Account;
4. Membership/subscription;
5. Payment/top-up;
6. User guide;
7. Admin.

All must reuse the existing system.

---

# 20. First implementation batch recommendation

The first code batch should be deliberately small.

## Batch A — Foundation / no scanner behavior change

Files likely involved:

- `dashboard/src/routes/__root.tsx`
- `dashboard/src/styles.css`
- `dashboard/src/components/scanner/AppHeader.tsx`
- `dashboard/src/components/scanner/signal-meta.ts`

Potential new shared components:

- `DataTrustBar.tsx`
- optional product brand component

## What Batch A must NOT change

- signal thresholds;
- filter logic;
- sort logic;
- backend scanner universe;
- data fetching integration;
- stock calculations;
- watchlist/user behavior.

## Acceptance

- no false DEMO/error state during load;
- Chuyện Chợ Chứng branding;
- Vietnamese document/root states;
- 0/4 has neutral semantics;
- header is materially more compact;
- existing Overview/Scanner still function.

---

# 21. Lovable decision

**Do not use Lovable yet.**

Current work is architecture, correctness and component-system work, where Lovable provides little advantage.

A possible future Lovable proposal may be appropriate **after the App Shell wireframe is stable**, if we want to compare 2–3 high-fidelity visual treatments quickly.

Any such use still requires explicit approval and a credit estimate.

---

# 22. Audit decision

The redesign should proceed.

The current frontend should **not** be thrown away.

Recommended strategy:

> Preserve scanner data architecture and useful components, replace the information hierarchy and product shell in controlled batches.

The next implementation target is:

**Phase 0 + Phase 1: Product identity, Data Trust, signal-zero semantics, typography foundation, and App Shell.**
