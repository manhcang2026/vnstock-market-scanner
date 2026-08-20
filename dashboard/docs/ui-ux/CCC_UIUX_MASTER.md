# CCC UI/UX DESIGN SYSTEM v1.0

**Product:** Chuyện Chợ Chứng — Stock Market Scanner  
**Status:** LOCKED STANDARD  
**Version:** 1.0  
**Effective date:** 2026-08-20  
**Scope:** `dashboard/` and every future user-facing interface that belongs to the Chuyện Chợ Chứng scanner product.

---

## 0. Authority and usage

This document is the primary UI/UX authority for Chuyện Chợ Chứng.

When implementing or redesigning UI, apply rules in this order:

1. Explicit product requirement approved by the product owner.
2. This `CCC_UIUX_MASTER.md`.
3. `CCC_COMPONENT_RULES.md`.
4. Relevant pattern in `CCC_PAGE_PATTERNS.md`.
5. Existing production behavior and real data constraints.
6. General UI/UX references such as UI/UX Pro Max.

If an AI tool, design tool, library default, or personal preference conflicts with this standard, **CCC UI/UX Design System wins** unless the product owner explicitly approves a system change.

> **Do not redesign this product from personal preference. Design decisions must be derived from the CCC UI/UX Design System, real product data, and the user's task.**

### External design intelligence

UI/UX Pro Max by NextLevelBuilder is an important research reference for this system:
`https://github.com/nextlevelbuilder/ui-ux-pro-max-skill`

It is a source of design intelligence, not the final authority for Chuyện Chợ Chứng.

### Lovable usage rule

Lovable may be used for visual exploration or rapid prototyping when it has a clear advantage. A reserve of up to **50 Lovable credits** exists for this purpose.

**Lovable must never be called or used automatically.** Before any Lovable use:

1. Explain exactly what will be explored or generated.
2. Explain why Lovable is preferable for that task.
3. Estimate the expected credit usage when possible.
4. Receive explicit approval from the product owner.

---

# 1. Product design philosophy

## 1.1 Design direction: Calm Financial Intelligence

Chuyện Chợ Chứng is a financial information product, not a decorative marketing website.

The interface must feel:

- trustworthy;
- calm;
- data-dense without being cramped;
- understandable to non-specialists;
- efficient for repeat users;
- fast and stable;
- professional without looking like a trading terminal for experts only.

The visual direction combines:

- **Data-dense financial dashboard** for efficient scanning;
- **Minimal / Swiss discipline** for hierarchy and clarity;
- **Explainable UX** for technical stock-market concepts.

Avoid “AI dashboard” aesthetics where every number becomes a card, every state becomes a badge, and decoration competes with information.

## 1.2 North Star: the 5-second test

Within approximately five seconds, a user should be able to answer:

1. **Which stock is worth noticing?**
2. **Why is it worth noticing?**
3. **What should I inspect next?**

If a screen cannot support these three questions, its information hierarchy must be reconsidered.

## 1.3 Decision first, data second, representation third

Always design in this order:

`Decision → Data → Representation`

Do not start from UI components.

Bad:
`We have eight values → create eight cards.`

Good:
`The user must detect abnormal money flow → emphasize RVOL30 and supporting evidence → select the most suitable representation.`

---

# 2. Priority model

General-purpose UI frameworks are not sufficient for a financial scanner. Chuyện Chợ Chứng uses the following priority order.

## P0 — must not fail

1. **Data correctness and data trust**
2. **Readability and information hierarchy**
3. **Accessibility and interaction correctness**

## P1 — product efficiency

4. **Scanner workflow and task speed**
5. **Responsive behavior by device**
6. **Performance and perceived performance**

## P2 — system consistency

7. **Typography**
8. **Semantic color**
9. **Reusable components and state consistency**

## P3 — polish

10. Motion
11. Elevation / shadow
12. Decorative styling

A P3 improvement must never damage P0 or P1.

---

# 3. Current scanner truth

UI documentation must reflect real backend fields, not imagined data.

The current core scanner exposes four signal conditions:

1. **Giá tăng ≥ 3%**
2. **Khối lượng ngày ≥ 200% mức trung bình**
3. **Giá nằm trên MA200**
4. **RVOL30 ≥ 200%**

The current product also has:

- HOSE / HNX / UPCOM exchange data;
- current price and price change;
- accumulated daily volume;
- average volume;
- MA200 and distance from MA200;
- 30-minute volume and RVOL30;
- sample/session counts;
- missing-data state;
- data status;
- trading date, time slot and update time;
- data source;
- system mode/status metadata.

### Future-ready data

The design system may reserve patterns for future data such as:

- company name;
- company logo;
- industry;
- MA10;
- fundamental scoring;
- financial reports;
- user watchlists;
- notifications;
- membership/subscription;
- account settings.

However, **never display or prototype future data as if it already exists in production**. A future field must be clearly labeled as planned/mock during design work and must only enter production UI after a real data contract exists.

---

# 4. Data Trust Layer

Financial UX must always communicate enough information for a user to judge data freshness and reliability.

When relevant, every data-heavy screen must answer:

- When was market data updated?
- Is the system LIVE, DEMO, stale, degraded, or in an error state?
- Is any data missing?
- What source supplied the data?

## 4.1 Compact trust presentation

Trust information should be visible but must not dominate the page.

Preferred compact pattern:

`● LIVE · Cập nhật 14:15 · 800 mã · Dữ liệu đầy đủ`

Degraded example:

`⚠ 17 mã chưa cập nhật · Cập nhật gần nhất 14:10 · Xem chi tiết`

## 4.2 Trust states

At minimum design for:

- `LIVE / OK`
- `DEMO`
- `DEGRADED`
- `ERROR`
- `MISSING DATA`
- `STALE DATA`
- `OUT OF SESSION / TEST` when applicable

Never silently replace stale data with a blank screen if usable previous data exists.

---

# 5. Information hierarchy

## 5.1 Three information levels

### Level A — decision information
Must be discoverable immediately.

Examples:

- stock symbol;
- company name when available;
- current price and change;
- CCC signal strength;
- early money-flow alert;
- strongest reason the stock is notable.

### Level B — supporting evidence
Visible without deep navigation where space allows.

Examples:

- daily volume ratio;
- distance to MA200;
- RVOL30;
- sample/session count.

### Level C — detail / audit information
Progressively disclosed.

Examples:

- exact volume values;
- averages;
- data source;
- detailed session count;
- trading date/time slot;
- notes;
- raw status diagnostics.

Do not give A, B, and C equal visual weight.

## 5.2 Remove color test

A screen's hierarchy must still make sense if all semantic colors are removed.

Color reinforces meaning. It must not create the entire meaning.

---

# 6. CCC Signal Rail

The **CCC Signal Rail** is a signature product component and the standard visual language for scanner signals.

## 6.1 Compact form

Example:

`● ● ● ○   3/4`

Use in:

- stock table;
- compact watchlist;
- dense desktop views.

## 6.2 Medium form

Example:

`3/4 tín hiệu`

with the four signal states available via readable labels or disclosure.

Use in:

- stock cards;
- overview groups.

## 6.3 Explainable form

Example:

- ✓ Giá tăng ≥ 3%
- ✓ Khối lượng ngày ≥ 200%
- ✓ Trên MA200
- ○ RVOL30 chưa đạt 200%

Use in:

- stock detail;
- onboarding/help;
- tooltips or expanded explanation.

## 6.4 Signal rules

- Never communicate signal state by color alone.
- Pair color with text, icon, shape, count, or state.
- `4/4` means convergence of four scanner conditions, not a buy recommendation.
- `1/4`, `2/4`, `3/4`, `4/4` must not use language implying guaranteed investment outcome.
- Prefer understandable wording over jargon.

---

# 7. Financial terminology and explainability

The product serves users with different knowledge levels.

## 7.1 Naming rule

When a technical abbreviation first matters to a user's decision, provide an understandable label.

Preferred:

- `Khối lượng ngày / KLTB10`
- `RVOL30 — khối lượng 30 phút tương đối`
- `Khoảng cách tới MA200`

Avoid presenting unexplained abbreviations as the only label.

## 7.2 Progressive explanation

Use three levels:

1. Short label in scanner/table.
2. Helper or tooltip in context.
3. Full explanation in stock detail/help.

Do not fill the scanner with long educational text.

---

# 8. Typography

## 8.1 Target family

Target product typography:

- Primary UI: **IBM Plex Sans** or an approved equivalent with strong Vietnamese readability.
- Numeric data: same UI font with **tabular numerals** by default.
- Monospace is reserved for rare technical/audit contexts; do not make the product look like a developer terminal.

Font migration must be implemented only after loading/performance and Vietnamese rendering are verified.

## 8.2 Minimum practical sizes

Essential readable content must not rely on 10–11px text.

Target ranges:

| Role | Desktop | Mobile |
|---|---:|---:|
| Main body | 15–16px | 16px |
| Table primary data | 14–15px | n/a |
| Stock symbol | 15–16px bold | 16px+ |
| Secondary label | 13px | 13–14px |
| Section title | 18–20px | 18px |
| Page title | 24–28px | 21–24px |
| Primary KPI | 24–32px | 22–28px |

Very small text may be used only for non-essential metadata when contrast and readability remain acceptable.

## 8.3 Numeric typography

Use:

`font-variant-numeric: tabular-nums;`

for prices, percentages, time, volume ratios, and comparable table columns.

---

# 9. Color system

## 9.1 Semantic, not decorative

Use semantic tokens rather than raw visual colors in feature components.

Core semantic roles:

- `background`
- `surface`
- `card`
- `foreground`
- `muted-foreground`
- `border`
- `primary`
- `market-up`
- `market-down`
- `market-neutral`
- `early-alert`
- `signal-1`
- `signal-2`
- `signal-3`
- `signal-4`
- `success`
- `warning`
- `error`
- `info`

The current OKLCH token system is the correct architectural direction and should be extended rather than replaced with ad-hoc hex values.

## 9.2 Market colors

- Green describes positive market movement.
- Red describes negative market movement.
- Neutral describes unchanged/unknown/reference state.
- These colors **must not imply investment advice**.

## 9.3 Light theme

Default direction:

- cool off-white background;
- clean white/light surfaces;
- navy/slate foreground;
- restrained semantic accents.

## 9.4 Dark theme

Direction:

- dark navy/slate rather than pure black;
- controlled contrast;
- avoid neon terminal styling;
- preserve semantic differentiation.

## 9.5 Forbidden

Do not:

- create random new hex colors inside components;
- use gradients as the default information surface;
- use glassmorphism behind dense financial data;
- make large blocks red/green when a small semantic accent is sufficient.

---

# 10. Design-token architecture

Use three layers:

`Primitive → Semantic → Component`

Example:

`green primitive → market-up → stock-change-positive`

`violet primitive → early-alert → rvol-alert-border`

Components should consume semantic/component tokens rather than primitive values.

Tokens must cover at least:

- color;
- typography;
- spacing;
- radius;
- shadow;
- motion;
- z-index where needed.

### Locked principle

No feature component may invent its own visual language if an equivalent system token or shared component already exists.

---

# 11. Layout and spacing

## 11.1 Spacing system

Prefer a consistent 4px base rhythm.

Common values:

`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48`

Avoid arbitrary one-off spacing unless a documented visual reason exists.

## 11.2 Content width

Dense scanner screens may use wider layouts than editorial pages.

Do not artificially constrain data tables to a narrow marketing-site column.

## 11.3 Grouping

Use spacing before borders.

Use borders before heavy shadows.

Use heavy surfaces only when they clarify structure.

---

# 12. Responsive strategy

Responsive design is not “desktop made smaller.”

Required design checkpoints:

- **375px** mobile
- **768px** tablet
- **1024px** small desktop/tablet landscape
- **1440px** desktop

## 12.1 Desktop ≥ 1024px

Primary pattern: **Scanner Workbench**

Use:

- data table;
- command/filter bar;
- sticky table header when helpful;
- stock detail side panel/drawer when detail grows;
- dense but readable spacing.

## 12.2 Tablet

Use a deliberate hybrid layout.

Do not assume the desktop table always remains the best presentation.

## 12.3 Mobile

Primary pattern: **Decision Cards**

Use:

- full-width search;
- compact filter/sort actions;
- stock cards;
- bottom sheet or dedicated detail page;
- 44–48px touch targets for important actions.

Avoid forcing a 10-column table into horizontal scrolling as the main mobile experience.

---

# 13. Scanner interaction principles

## 13.1 Search

- Search must feel immediate.
- Search input must not freeze UI.
- Search state should be preserved when returning from detail when practical.
- Future company-name search must only be enabled after company-name data exists.

## 13.2 Filters

As filters grow, use a **Scanner Command Bar** instead of an ever-growing wall of chips.

Desktop concept:

`[Search] [Bộ lọc] [Sắp xếp] [Watchlist]`

Then active filters:

`[HOSE ×] [≥2 tín hiệu ×] [RVOL30 ≥200% ×]  Xóa tất cả`

Mobile:

`[Search]`
`[Bộ lọc •3] [Sắp xếp] [Watchlist]`

Open complex filters in a sheet/bottom sheet.

## 13.3 Sorting

Sorting must have:

- clear active state;
- understandable labels;
- deterministic tie behavior;
- no unexpected reset when opening stock detail.

## 13.4 Selection

Rows/cards that open detail must support the expected device input:

- mouse;
- touch;
- keyboard where applicable.

Focusable table rows must respond to Enter/Space or use a semantic interactive control.

---

# 14. Loading, empty, error and stale states

Every data component must specify its states before implementation is considered complete.

## Loading

- Prefer skeletons that preserve layout.
- Avoid clearing already usable data during a refresh.
- Refresh icon/spinner may indicate background fetching.

## Empty

Explain whether:

- no data exists;
- no stock matches filters;
- no signal currently qualifies.

Provide a recovery action when useful.

## Error

Show:

- what failed in user language;
- whether previous data remains usable;
- a retry action when appropriate.

## Missing / stale data

Differentiate:

- missing field;
- missing stock row;
- stale snapshot;
- system error.

Do not use one generic “error” state for all four.

---

# 15. Accessibility

Accessibility is a release requirement.

## Required

- visible keyboard focus;
- semantic HTML where possible;
- Enter/Space activation for keyboard-focusable actions;
- labels for icon-only buttons;
- sufficient contrast;
- touch targets appropriate for mobile;
- state not conveyed by color only;
- sensible reading order;
- dialog/sheet focus management;
- no essential hover-only information.

## Tables

- Use table semantics for actual tables.
- Numeric headers/columns should align with their data.
- Interactive rows must be keyboard operable.
- Sorting state should be communicated accessibly.

---

# 16. Performance UX

Performance is part of the design specification.

## Data-list strategy

Suggested thresholds are implementation guidance, not hard backend contracts:

- small list: normal rendering;
- medium list: evaluate pagination/windowing;
- large list: virtualization or equivalent strategy;
- expensive search/filter: debounce or optimized computation.

## Required UX behavior

- keep previous data during refresh when safe;
- avoid layout shift;
- avoid re-rendering the full page for minor filter changes;
- large data sets must not make search inputs stutter;
- detail opening should not wait on unrelated page work.

Do not add animation that makes data interaction slower.

---

# 17. Motion

Motion is functional, restrained, and optional.

Allowed uses:

- refresh state;
- drawer/sheet/dialog transition;
- lightweight state transition;
- subtle data-change acknowledgment when it adds clarity.

Avoid:

- looping decorative animation;
- bouncing KPI cards;
- unnecessary parallax;
- aggressive number animation;
- motion that delays reading.

Respect reduced-motion preferences when applicable.

---

# 18. Product language and investment neutrality

The scanner is an information tool.

Use language such as:

- `đáng chú ý`;
- `tín hiệu quét`;
- `đang hình thành`;
- `cảnh báo dòng tiền`;
- `cần theo dõi thêm`.

Avoid language such as:

- `chắc chắn tăng`;
- `nên mua`;
- `kèo ngon`;
- `mua ngay`;
- `cam kết`;
- any UI copy that transforms a scanner condition into investment advice.

Maintain a concise disclaimer where appropriate:

`Công cụ quét dữ liệu, không đưa ra khuyến nghị mua/bán.`

---

# 19. Locked vs evolving rules

## LOCKED

The following require explicit product-owner approval to change:

- data-first design;
- 5-second North Star;
- Data Trust Layer;
- explainability for technical signals;
- no essential tiny text;
- semantic color;
- color is never the only state cue;
- CCC Signal Rail;
- desktop table / mobile decision-card strategy;
- accessibility as release requirement;
- real-data-first implementation;
- Lovable approval requirement.

## EVOLVING

These may be tuned during implementation while preserving the locked principles:

- exact radius;
- exact shadow;
- fine spacing;
- animation duration;
- exact page padding;
- specific drawer width;
- exact breakpoints when technical evidence supports change;
- exact font choice if the target font fails performance/rendering validation.

---

# 20. Standard design workflow

Every meaningful new screen or major redesign follows this workflow.

## 00 — Product Intent
Define one primary user job and up to three secondary jobs.

## 01 — Data Inventory
List real fields, source, freshness, missing-data behavior and future-only fields.

## 02 — Decision Map
Separate primary decision information, supporting evidence and audit/detail data.

## 03 — Design Research
Use CCC standards first; consult UI/UX Pro Max or other references only as supporting intelligence.

## 04 — Wireframe
Define mobile, tablet and desktop information hierarchy before visual polish.

## 05 — Token Mapping
Map visual decisions to CCC tokens.

## 06 — Component Design
Reuse shared components and define all states.

## 07 — Responsive Design
Validate 375 / 768 / 1024 / 1440 behavior.

## 08 — Explainability Pass
Remove unexplained jargon and ensure signals can be understood.

## 09 — Accessibility Pass
Keyboard, focus, semantics, contrast, target sizes, reading order.

## 10 — Performance Pass
Large lists, search/filter responsiveness, refresh behavior, layout stability.

## 11 — Visual Polish
Only after the previous gates pass.

## 12 — Acceptance QA
Run `CCC_UIUX_QA_CHECKLIST.md` using realistic data.

---

# 21. Definition of Done

A screen is not UI/UX complete until:

- the primary purpose is understandable quickly;
- hierarchy works without semantic color;
- freshness/trust information is available when needed;
- important jargon is explained;
- essential text is comfortably readable;
- comparable numeric data uses tabular figures and consistent alignment;
- loading, empty, error, stale and missing-data states exist where applicable;
- desktop/tablet/mobile layouts are deliberate;
- keyboard and touch interactions work;
- no core interaction relies on hover;
- large lists have a performance strategy;
- tokens are used instead of arbitrary visual values;
- realistic product data has been tested;
- the UI remains useful to both newer and repeat users;
- the final QA checklist passes.

---

# 22. Change management

This document is versioned.

Any change to a **LOCKED** principle requires:

1. explicit approval from the product owner;
2. version increment;
3. changelog entry;
4. review of affected component/page documents.

## Changelog

### v1.0 — 2026-08-20

- Established Calm Financial Intelligence direction.
- Defined the 5-second North Star.
- Established Data Trust Layer.
- Established CCC Signal Rail.
- Defined data-first information hierarchy.
- Defined responsive desktop workbench / mobile decision-card strategy.
- Defined semantic token and accessibility rules.
- Defined Lovable approval gate.
- Established standard 00–12 design workflow.
