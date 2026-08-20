# CCC COMPONENT RULES v1.0

**Parent standard:** `CCC_UIUX_MASTER.md`  
**Status:** ACTIVE  
**Version:** 1.0

This document defines reusable UI behavior. It does not replace the master design principles.

---

# 1. Shared component rule

Before creating a new feature component:

1. Check whether an equivalent shared component exists.
2. Check whether an existing scanner component can be extended.
3. Use semantic tokens.
4. Define loading/empty/error/disabled/focus states where applicable.
5. Verify desktop and mobile behavior.
6. Avoid page-specific visual inventions that should be system-level.

---

# 2. App Header / App Shell

## Purpose

Provide product identity, primary navigation, account entry points and compact system/data trust context.

## Required behavior

- Product brand should be **Chuyện Chợ Chứng**.
- Avoid exposing internal/project-development naming as the primary product title.
- Data trust must remain visible but compact.
- Navigation must scale to future Watchlist, Notifications, Account and Admin roles.
- Role-specific navigation must not affect the backend scanner universe.

## Desktop

Preferred long-term pattern:

- brand/product area;
- primary navigation;
- compact trust/status region;
- user/account area.

## Mobile

- preserve brand identity;
- do not crowd the header with all desktop metadata;
- move secondary navigation to an appropriate compact pattern.

## Do not

- turn status metadata into a large dashboard before the actual scanner content;
- use tiny text for critical status;
- duplicate navigation in multiple competing areas.

---

# 3. Data Trust Bar

## Purpose

Communicate freshness and reliability without stealing attention from market data.

## Minimum information when applicable

- LIVE/DEMO/state;
- market update time;
- missing/stale state;
- access to more diagnostics.

## Variants

- healthy;
- degraded;
- error;
- demo;
- stale.

Use icon/text/state in addition to color.

---

# 4. Search Input

## Purpose

Find stocks quickly.

## Requirements

- comfortably readable font;
- clear placeholder;
- keyboard focus visible;
- no UI freeze while typing;
- search icon is decorative unless independently interactive;
- clear control should be available when it materially improves use.

## Future behavior

When company-name data exists, search may match:

- symbol;
- company name.

Do not advertise company-name search before that data exists.

---

# 5. Scanner Command Bar

## Purpose

Contain search, filtering, sorting and later watchlist selection without growing into a wall of chips.

## Desktop

Preferred structure:

`[Search................................] [Bộ lọc] [Sắp xếp] [Watchlist]`

Active filters appear below or adjacent as removable chips.

## Mobile

Preferred structure:

`[Search................................]`

`[Bộ lọc •N] [Sắp xếp] [Watchlist]`

Complex filter controls open in a bottom sheet/sheet.

## Rules

- active filter count should be visible;
- clear-all action appears when useful;
- current result count should be visible near results;
- changing sort must not silently clear filters;
- opening stock detail must not reset the current scanner state.

---

# 6. Filter Chip

## Purpose

Represent an active, removable filter or a small set of mutually exclusive quick choices.

## Use for

- currently active filter summary;
- a small number of high-frequency presets.

## Do not use for

- every possible filter when the set is large;
- long technical descriptions;
- controls that require multi-field configuration.

## Requirements

- readable text;
- clear active state beyond color;
- touch-friendly on mobile;
- removable chips need an accessible remove action.

---

# 7. Button

## Variants

- primary;
- secondary;
- outline;
- ghost;
- destructive;
- icon-only.

## Requirements

- visible focus;
- disabled state;
- loading state when action is asynchronous;
- icon-only buttons require accessible labels;
- important mobile targets approximately 44–48px.

Do not make every action primary.

---

# 8. Tooltip / Helper

## Purpose

Explain technical concepts without filling the scanner with instructional paragraphs.

## Good candidates

- RVOL30;
- MA200;
- KLTB10;
- signal logic;
- data freshness definitions.

## Rules

- essential actions cannot be tooltip-only;
- essential information must also work on touch devices;
- helper copy must use plain Vietnamese before technical detail.

---

# 9. CCC Signal Rail

## Compact table form

Show signal strength using shape + count.

Example:

`● ● ● ○  3/4`

## Card form

Show:

- `3/4 tín hiệu`;
- compact reason labels when space allows.

## Detail form

Show each condition with:

- state;
- understandable name;
- relevant measured value when useful.

## State language

Preferred:

- `Tín hiệu rất mạnh`
- `Tín hiệu mạnh`
- `Đang hình thành`
- `Tín hiệu ban đầu`

These describe scanner convergence only.

---

# 10. Stock Table

## Purpose

Primary desktop analysis surface.

## Column principles

- identity columns left aligned;
- comparable numeric columns right aligned;
- status/signal may be centered;
- use tabular numerals;
- avoid verbose cell copy;
- detailed audit data belongs in detail view.

## Minimum current information candidates

The exact final column set is page-specific, but the current data model supports:

- Mã;
- Sàn;
- Giá;
- % thay đổi;
- KL ngày / tỷ lệ;
- khoảng cách MA200;
- RVOL30;
- phiên RVOL30;
- tín hiệu;
- trạng thái dữ liệu.

Future company name/logo may enrich the identity column once real data exists.

## Desktop behavior

- sticky header when the table scrolls significantly;
- hover/selected state;
- clear sort state;
- optionally sticky stock identity column when horizontal density requires it;
- row detail interaction.

## Accessibility

A focusable row that opens detail must respond to keyboard activation. Prefer semantic controls when practical.

## Performance

For large universes, design and implementation must evaluate virtualization or another scalable list strategy.

---

# 11. Stock Card

## Purpose

Primary mobile stock representation and secondary overview representation.

## Content priority

1. Stock identity.
2. Price/change.
3. CCC Signal Rail.
4. Most important supporting evidence.
5. Secondary technical detail.

## Mobile card rule

A user should not need to decode eight equal-weight metrics.

Prefer a compact summary and disclose deeper metrics in stock detail.

## Current migration concern

Existing very small 10px/11px metric labels and badges should be upgraded during redesign. Do not reproduce this pattern in new components.

---

# 12. KPI / Summary Card

## Purpose

Summarize a genuinely decision-relevant aggregate.

Use a KPI card only when the number answers a meaningful overview question.

Good examples:

- number of stocks with strong convergence;
- early money-flow alerts;
- scanner universe/data health when needed.

Bad pattern:

- converting every available field into a KPI card.

## Rules

- label must be understandable;
- primary number prominent;
- supporting copy short;
- cards in one row should have comparable semantic weight.

---

# 13. Stock Detail

## Purpose

Explain why a stock is notable and expose supporting/audit data.

## Long-term desktop pattern

Prefer a right-side panel/drawer when detail becomes richer.

## Mobile

Use a full-height bottom sheet or dedicated detail screen depending on content growth.

## Information order

1. identity: logo/name/symbol/exchange when available;
2. price/change;
3. CCC Signal Rail;
4. “Vì sao mã này đáng chú ý?” explanation;
5. money flow;
6. trend;
7. fundamentals when available;
8. signal history when available;
9. data trust/audit information.

Do not lead with raw technical tables before explaining the signal.

---

# 14. Drawer / Side Panel

## Purpose

Desktop contextual detail without losing scanner position/filter state.

## Requirements

- clear close control;
- focus management;
- keyboard Escape behavior where appropriate;
- main scanner state preserved;
- width sufficient for readable data, not a narrow tooltip column.

---

# 15. Bottom Sheet

## Purpose

Mobile filter/detail interaction.

## Requirements

- large enough touch targets;
- clear handle/title/close behavior;
- no important content hidden beneath browser/system UI;
- support long content scrolling;
- preserve scanner state after closing.

---

# 16. Dialog

Use dialog for bounded tasks or relatively short detail.

Do not keep expanding a dialog indefinitely as stock detail grows.

A large, multi-section stock profile should migrate to side panel/sheet/page patterns.

---

# 17. Data Metric

A reusable data metric should define:

- label;
- formatted value;
- null/missing behavior;
- optional semantic tone;
- optional helper text.

## Rules

- label should generally be at least 13px when important;
- value should use tabular numerals;
- null is not zero;
- “Chưa đủ dữ liệu” is distinct from “0%”.

---

# 18. Empty State

Types:

- no qualifying stocks;
- no search matches;
- no watchlist items;
- no notification history;
- no data available.

Each empty state should say what happened and, where useful, what the user can do next.

Avoid decorative illustration unless it adds meaningful value.

---

# 19. Loading State

Use layout-preserving skeletons for meaningful content areas.

During refresh:

- retain previous usable data when safe;
- indicate fetching in the relevant control;
- avoid flashing to an empty state.

---

# 20. Error State

Minimum structure:

- plain-language problem;
- impact;
- retry or recovery action;
- preserved previous data state when available.

Do not expose raw backend exceptions as primary user copy.

---

# 21. Missing / Stale Data Indicator

Missing and stale states must be distinguishable.

Examples:

- `Thiếu dữ liệu`
- `Chưa đủ phiên`
- `Dữ liệu cũ — cập nhật gần nhất 14:10`

Use color + icon/text.

---

# 22. Notification UI — future-ready

When notifications are implemented:

- distinguish system, scanner signal and account/payment messages;
- provide read/unread state without relying only on color;
- avoid notification overload;
- allow channel settings when backend supports Email/Telegram or future channels.

This is a pattern reservation only; do not fabricate notification functionality.

---

# 23. Account / Membership UI — future-ready

Account pages should reuse the same typography, surfaces, buttons and states.

Subscription/payment interfaces must prioritize:

- current plan/state;
- price and billing meaning;
- action consequence;
- transaction status;
- error/retry clarity.

Do not introduce a separate “marketing site” visual language inside the app.

---

# 24. Component acceptance checklist

Before a shared component is accepted:

- [ ] Purpose is clear.
- [ ] Real data contract is known.
- [ ] Responsive behavior is defined.
- [ ] Keyboard/touch behavior is defined.
- [ ] Loading state exists if asynchronous.
- [ ] Empty/error state exists where relevant.
- [ ] Missing/stale behavior is defined for data components.
- [ ] Semantic tokens are used.
- [ ] Essential text is readable.
- [ ] State is not color-only.
- [ ] Component has not duplicated an existing shared pattern.
