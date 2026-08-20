# CCC PAGE PATTERNS v1.0

**Parent standard:** `CCC_UIUX_MASTER.md`  
**Status:** ACTIVE  
**Version:** 1.0

This document defines page-level information architecture. Exact visuals may evolve while the purpose and hierarchy remain consistent.

---

# 1. App Shell

## Primary job

Let users move between core product areas while continuously understanding system/data state.

## Long-term navigation model

Expected product areas:

- Tổng quan
- Scanner / Danh sách cổ phiếu
- Watchlist
- Thông báo
- Tài khoản
- Admin — role-gated only

Only show routes that actually exist.

## Desktop

Recommended:

- persistent product identity;
- horizontal navigation or sidebar depending on final information architecture;
- compact Data Trust Bar;
- user/account access.

## Mobile

Recommended:

- compact top bar;
- reduced primary navigation;
- drawer/bottom navigation only after testing route count and task frequency.

Do not put every future route into mobile navigation before it exists.

---

# 2. Overview

## Primary job

Answer:

**“Hiện tại có gì đáng chú ý?”**

Overview is a discovery surface, not a full scanner replacement.

## Recommended hierarchy

### A. Data trust / market state
Compact.

### B. Attention summary
Examples based on real current data:

- number of strong-signal stocks;
- number of early RVOL30 alerts.

### C. Cảnh báo dòng tiền sớm
High priority.

### D. Tín hiệu mạnh
Prefer 4/4 and 3/4.

### E. Đang hình thành
2/4.

### F. Thị trường rộng
1/4 should normally be previewed rather than allowed to dominate the page.

## Avoid

- five equally weighted sections stacked endlessly;
- exposing every stock when Scanner already exists;
- overusing KPI cards;
- technical metadata taking precedence over opportunities/alerts.

## Transition target from current UI

Current grouped logic is useful and should be preserved semantically, but redesigned into stronger information hierarchy.

---

# 3. Scanner / Danh sách cổ phiếu

## Primary job

Find, filter, compare and open stocks efficiently.

This is the product's main analysis workbench.

## Desktop structure

1. App Shell / Data Trust.
2. Scanner Command Bar.
3. Active filter summary.
4. Result count.
5. Stock Table.
6. Contextual stock detail side panel when implemented.

Suggested command bar:

`[Tìm mã...] [Bộ lọc] [Sắp xếp] [Watchlist]`

Only show Watchlist after the feature exists.

## Mobile structure

1. Search.
2. Filter/sort actions.
3. Active filter summary if needed.
4. Result count.
5. Decision-oriented Stock Cards.
6. Detail bottom sheet/page.

## Current filters

Current production UI supports:

- exchange;
- 4/4;
- ≥3/4;
- exactly 2/4;
- exactly 1/4;
- RVOL30 ≥200%;
- price ≥3%;
- daily volume ≥200%;
- above MA200;
- missing data.

These should be reorganized into a scalable filter experience instead of an indefinitely growing chip wall.

## Current sorting

Current production sorting supports:

- signal priority;
- RVOL30;
- price change;
- daily volume ratio;
- symbol A–Z.

The UI must not claim additional sort options until implemented.

## State preservation

When opening and closing stock detail, preserve when practical:

- search;
- filters;
- sort;
- scroll position.

---

# 4. Stock Detail

## Primary job

Answer:

**“Vì sao mã này được chú ý, và dữ liệu nào chứng minh điều đó?”**

## Header

When data exists:

- logo;
- stock symbol;
- company name;
- exchange;
- current price;
- change.

Currently symbol/exchange/price are real; company name/logo must only appear after the data contract is available.

## Section 1 — CCC Signal Rail

Show:

- signal count;
- each signal condition;
- active/inactive state.

## Section 2 — Why notable?

Plain-language explanation derived only from real scanner conditions.

Example:

- Price increased ≥3%.
- Daily volume ratio exceeded 200%.
- Price is above MA200.
- RVOL30 is below threshold.

## Section 3 — Money flow

Current data can support:

- accumulated daily volume;
- average volume;
- daily volume ratio;
- 30-minute volume;
- average 30-minute same-slot volume;
- RVOL30;
- sample count.

## Section 4 — Trend

Current data can support:

- MA200;
- distance from MA200;
- MA200 sample/session count.

MA10 may be added only when the frontend data contract supports it.

## Section 5 — Fundamentals — future

Only after real fundamental data is available.

## Section 6 — Reports / BCTC — future

Only after a real link/data model exists.

## Section 7 — Data audit

- trading date;
- time slot;
- updated time;
- data source;
- status;
- missing-data note.

Keep this below decision/supporting data unless there is a trust issue.

---

# 5. Watchlist — future-ready

## Primary job

Let a user monitor a personal subset without modifying the backend scanner universe.

## Critical product rule

Removing a symbol from a watchlist or user display **must never delete or stop scanning that symbol in the backend scanner universe**.

## Planned structure

### Desktop

- watchlist selector;
- search/add symbol;
- stock table;
- quick remove/hide action;
- detail side panel.

### Mobile

- watchlist selector;
- add/search action;
- stock cards;
- detail sheet.

## States

- empty watchlist;
- symbol not found;
- symbol already added;
- loading;
- sync/error.

---

# 6. Login / Register — future-ready

## Primary job

Provide secure account entry with minimal friction.

## Principles

- simple;
- large readable controls;
- password visibility control;
- clear error messages;
- no scanner-like visual density.

Do not redesign auth with unrelated branding or decorative effects.

---

# 7. Account — future-ready

## Primary job

Manage personal identity, preferences and account status.

Potential sections:

- profile;
- password/security;
- notification preferences;
- membership;
- logout.

Only display functionality that backend/auth supports.

---

# 8. Notifications — future-ready

## Primary job

Review and configure meaningful alerts.

Potential categories:

- scanner signal;
- system/data status;
- account/payment.

Potential channels such as Email/Telegram must only appear after backend support exists.

Avoid turning every scan event into a notification.

---

# 9. Subscription / Membership — future-ready

## Primary job

Understand current plan and upgrade/downgrade consequences.

Required clarity:

- current plan;
- included limits/features;
- price;
- billing period;
- effective date;
- action/result state.

Avoid manipulative countdowns or dark patterns.

---

# 10. Payment / Top-up — future-ready

## Primary job

Complete a payment confidently and understand transaction state.

Must design for:

- pending;
- successful;
- failed;
- cancelled/expired where applicable;
- retry;
- transaction reference.

Payment UI must not reuse market up/down colors in a confusing way.

---

# 11. User Guide — future-ready

## Primary job

Teach the scanner without requiring financial expertise.

Recommended organization:

- Scanner works how?
- Four core signals.
- RVOL30.
- MA200.
- Volume ratio.
- How to use filters.
- Data freshness.
- What the scanner does not mean.

Use examples, not large walls of theory.

---

# 12. Admin — future-ready

## Primary job

Manage user/display configuration and operational controls that the role is authorized to manage.

## Critical scanner-universe rule

Admin UI must distinguish:

- user/watchlist/display configuration;
- scanner-universe/backend configuration.

Normal Admin/user actions must not delete a scanner-universe symbol or stop data collection unless a separately authorized backend operation explicitly exists.

## Design principles

- dangerous actions visually and semantically separated;
- confirmation for destructive operations;
- audit-friendly labels;
- role-based visibility.

---

# 13. Page review template

Before implementing a page, document:

## Primary user job
One sentence.

## Secondary jobs
Maximum three.

## Real data inputs
List fields/source.

## Future-only data
List fields explicitly.

## Decision hierarchy
A / B / C information levels.

## Desktop layout
Describe.

## Tablet layout
Describe.

## Mobile layout
Describe.

## States
Loading / empty / error / stale / missing / permission.

## Accessibility risks
Describe.

## Performance risks
Describe.

## QA
Run `CCC_UIUX_QA_CHECKLIST.md`.
