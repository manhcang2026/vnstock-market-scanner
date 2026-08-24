# Chuyện Chợ Chứng (CCC) — Product & Development Roadmap

**Project:** Stock Market Scanner / Chuyện Chợ Chứng  
**Repository:** `manhcang2026/vnstock-market-scanner`  
**Current working branch:** `feature/user-auth-foundation`  
**Status:** Phase 4 LOCKED / PASS  
**Roadmap baseline:** after Phase 4 completion

---

## 0. Product rules currently locked

### Membership plans

| Plan | Watchlist limit | ADD quota / cycle | Technical market scope |
|---|---:|---:|---|
| FREE | 10 | 10 | Personal watchlist only |
| BASIC | 20 | 20 | Personal watchlist only |
| PLUS | 50 | 50 | Personal watchlist only |
| PRO | 100 | 100 | Personal watchlist only |
| FULL | Unlimited | Unlimited | Full market |

Rules:

- A new plan gets an **initial 7-day setup window**.
- During that setup window, the user can complete the initial watchlist without consuming ADD quota.
- After setup: each newly added symbol costs **1 ADD quota**.
- REMOVE costs **0 quota**.
- Remove then re-add the same symbol after setup costs **1 ADD quota**.
- Normal renewal does **not** reopen a new 7-day setup window.
- Upgrade free capacity applies only to newly gained plan capacity under the current backend rule.

### VIP DAY

- Product label: **VIP DAY**
- Price baseline: **100,000 VND / 24h**
- VIP DAY is a temporary entitlement overlay, not a base-plan replacement.
- It opens full-market CCC technical access for its active period.
- It does **not** change:
  - base plan;
  - personal watchlist;
  - watchlist quota;
  - plan cycle.
- UI shows both states, for example: `FREE · VIP DAY`.
- Expiry must show **time + date**.
- When VIP DAY expires:
  - user stays signed in;
  - frontend re-checks entitlement automatically;
  - full-market technical rows are cleared;
  - Market Scanner returns to public/basic mode for capped plans;
  - personal watchlist and quota remain unchanged.

### Paid-plan expiry / GRACE

- When a paid plan reaches its paid-through date, it enters **GRACE**.
- GRACE lasts **2 days**.
- During GRACE:
  - the member keeps the existing watchlist;
  - the member keeps full rights of that paid plan;
  - no new quota cycle is granted merely because GRACE started.
- If payment is completed during GRACE:
  - return to ACTIVE;
  - keep the original billing/cycle anchor date;
  - the new cycle is calculated from the original anchor, not the late payment date.
- If GRACE expires without payment:
  - paid subscription becomes EXPIRED;
  - paid watchlist is removed;
  - system creates a new FREE term.

---

# Phase 4 — Membership / Overview / Scanner Foundation

**Status: PASS / LOCKED**

## Phase 4 foundation

### Guest
- Guest is not a FREE member.
- Guest receives a fixed 10-symbol public demo.
- Guest CTA is FREE-first:
  - create/login free account;
  - create own 10-symbol watchlist.
- Paid options are secondary.

### Account / membership
- Profile and account foundation.
- Watchlist management.
- Product-plan display.
- Quota state.
- Password flow for email/password accounts.
- Google-auth account semantics.
- Placeholder alert channels.
- VIP DAY state.
- Effective access context shared by UI.

### Overview
Overview is a **discovery screen**, not a full scanner.

Locked behavior:
- maximum **10 rows**;
- no pagination;
- default group = `Tất cả`;
- exactly 4 CCC signal concepts;
- KPI quick filters:
  - 4/4
  - ≥3
  - ≥2
  - Dòng tiền
- if more results exist, `Xem toàn bộ...` hands off to Scanner and preserves the selected signal filter.

Scope:
- capped plan -> Overview rows come from entitled/personal scope;
- FULL / active VIP DAY -> Overview rows come from MARKET technical scope.

### Scanner

Two independent scopes:

#### `DS của tôi`
- always means the user's actual personal watchlist;
- never becomes 800 symbols because of VIP/FULL;
- technical CCC data for personal symbols;
- full technical filter/sort toolset;
- universal stock row/card shared with Overview.

#### `Toàn bộ thị trường`
- Guest/capped plans without FULL entitlement:
  - public/basic market information.
- FULL or active VIP DAY:
  - full technical Market Scanner;
  - same technical filters as `DS của tôi`;
  - universal stock row/card shared with Overview.

### Scanner performance
Technical Scanner is server-side paginated.

- scope: PERSONAL or MARKET;
- search;
- signal filter;
- exchange;
- sort;
- pagination;
- **50 rows/page**;
- MARKET technical scope requires effective FULL entitlement.

### Phase 4 invariant
Membership entitlement and the user's personal watchlist are separate concepts.

---

# Phase 5A — Stock Detail

**Goal:** restore the canonical per-symbol detail experience from the approved Golden / Alpha.19 UI.  
**Rule:** restore first; do not broadly redesign.

## Layout
Desktop:
- center content;
- right context rail.

Mobile:
- no right rail;
- use the approved responsive language.

## Tabs
- Tổng quan
- Kỹ thuật
- Cơ bản
- BCTC

## Entitlement behavior
Guest:
- technical detail only for allowed demo symbols.

Capped member:
- technical detail only for symbols within entitled/personal scope.

FULL / VIP DAY:
- technical detail available across the market.

Fundamental/public areas:
- stay public according to product rules;
- must not accidentally inherit technical entitlement restrictions.

## Performance
- one symbol detail request must load one-symbol detail data;
- never fetch 800 technical rows just to render one stock.

## UI consistency
- preserve Golden UI;
- stock identity and signal representation must match Overview/Scanner semantics.

**Checkpoint commit:** `phase-5a-stock-detail`

---

# Phase 5B — Research

**Goal:** restore the Research experience and preserve the approved visual language.

## Main areas
- So sánh theo ngành
- Sàng lọc cơ bản

## Product rules
- fundamental research remains public;
- do not tie fundamental visibility to CCC technical entitlement.

## Desktop
- center content + right rail;
- readable tables;
- aligned columns;
- avoid excessive abbreviations.

## Mobile
- responsive cards/content;
- industries use a compact/horizontal-scroll pattern rather than a long vertical stack.

## Terminology
- prioritize clear Vietnamese labels;
- minimize unexplained specialist abbreviations.

**Checkpoint commit:** `phase-5b-research`

---

# Phase 5C — Cross-route Check

**Goal:** all product entry points resolve to one canonical stock-detail behavior.

Test paths:
- Header search -> Stock Detail
- Overview row -> Stock Detail
- Market Scanner row -> Stock Detail
- Personal Scanner row -> Stock Detail
- Research -> Stock Detail

Also verify:
- deep links;
- browser back navigation;
- same entitlement regardless of entry route;
- no duplicate legacy detail component/route.

**Checkpoint commit:** `phase-5c-cross-route`

---

# Phase 6 — Full QA / Release Candidate

**Goal:** no major new feature work. Validate the full product.

## User/access matrix
- Guest
- FREE
- capped paid plan representative (PLUS)
- VIP DAY
- FULL
- GRACE

## UI matrix
- desktop
- tablet
- mobile
- light
- dark

## Routes
- Overview
- Scanner / Toàn bộ thị trường
- Scanner / DS của tôi
- Stock Detail
- Research
- Account

## Functional QA
- email/password auth
- Google auth
- login/logout
- direct links
- search/autocomplete
- filters
- sort
- pagination
- watchlist save
- quota behavior
- VIP activation/expiry
- GRACE behavior
- plan entitlement

## Performance QA
- no request storms;
- lazy-load stock logos;
- no accidental 800-row client load;
- MARKET technical page = 50 server rows;
- one-stock detail = one-stock data;
- route/tab switching does not freeze browser.

## Responsive checkpoints
Approximate:
- 375
- 768
- 1024
- 1440

## Visual baseline
Compare to CCC Alpha.19 Golden UI Reference.

**Checkpoint commit:** `phase-6-qa-release-candidate`

---

# Phase 7 — Admin / Moderator Dashboard

**Goal:** manage users, staff authorization, plans and commercial settings without editing code/database manually.

## Identity model

One account can simultaneously have:

### Membership entitlement
- FREE
- BASIC
- PLUS
- PRO
- FULL
- VIP DAY overlay

### Staff role
- MEMBER
- MODERATOR
- ADMIN
- SUPER_ADMIN

These two axes are independent.

**Important:** Admin/Moderator status must not automatically grant FULL market technical entitlement.

---

## Phase 7A — Membership Console

Admin view for:
- user/profile;
- current plan;
- subscription status;
- activation date;
- expiry date;
- GRACE status/end;
- watchlist count;
- quota used/remaining;
- VIP DAY status/end;
- payment/history.

---

## Phase 7B — Roles & Permissions

Possible permission model:

- `member.view`
- `member.edit`
- `subscription.renew`
- `subscription.change_plan`
- `vip_day.grant`
- `content.create`
- `content.edit`
- `content.publish`
- `staff.manage`
- `plan.manage`
- `audit.view`

Rules:
- Moderator sits below Admin.
- Staff cannot self-escalate.
- Permissions should be explicit, not inferred only from role labels.

---

## Phase 7C — Product & Plan Configuration

Admin-configurable plan settings:

- price;
- watchlist limit;
- ADD quota;
- initial setup grace days;
- full-market flag;
- email alert entitlement;
- Telegram/Zalo entitlement;
- active/hidden state;
- display order;
- short description.

VIP DAY configuration:
- price;
- duration;
- status;
- effective rights.

Target:
business values should increasingly come from configuration rather than frontend hard-code.

---

## Phase 7D — Plan Versioning

Changing plan commercial rules must not silently rewrite historical/current contracts.

A plan version should support:
- version;
- effective date;
- price;
- limits;
- setup days;
- entitlements.

Default policy:
- changes can apply from the **next renewal** for existing paid members;
- new subscriptions can use the new active version;
- historical subscriptions retain their original plan-version reference where needed.

---

## Phase 7E — Audit Log

Record:
- who changed;
- what changed;
- previous value;
- new value;
- timestamp;
- reference/reason.

Examples:
- plan price change;
- quota change;
- manual VIP grant;
- manual subscription adjustment;
- staff permission change.

---

## Phase 7F — Payment / Renewal

When payment integration is implemented:

### ACTIVE renewal
- extend entitlement based on existing billing anchor.

### GRACE renewal
- restore ACTIVE;
- preserve original anchor date;
- calculate next paid-through date from the existing anchor;
- do not reset the monthly billing day based on the late payment date.

### Grace expired
- paid subscription EXPIRED;
- watchlist removed;
- new FREE term already becomes the active baseline.

Payment events and admin overrides must be audited.

---

# Development discipline

1. Work on feature branches/checkpoints.
2. End each major phase with a tested commit + push.
3. Do not merge to `main` merely because a partial phase works.
4. Preserve rollback checkpoints.
5. Treat Phase 4 as frozen; return only for confirmed bugs.
6. Restore Golden UI before attempting any redesign in Phase 5.
7. Keep scanner universe backend-controlled.
8. Frontend/user actions must never remove symbols from scanner universe.
