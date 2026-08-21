# CCC PHASE 1.6 — PRODUCT OWNER REVIEW v1.0

**Product:** CHUYỆN CHỢ CHỨNG  
**Status:** LOCKED REVIEW DECISIONS  
**Review date:** 2026-08-21  
**Reviewed artifact:** `CCC_LOVABLE_PHASE1_EXTRACTION_REPORT_v1.0.md`  
**Reviewed Lovable snapshot:** `4335bc50d343ce8eb5da32c3c5e5a3a76da404a8`

---

## 1. Purpose

This document records Product Owner review decisions after the read-only Lovable Phase 1 extraction.

It does **not** replace:

- `CCC_PHASE1_DESIGN_PORT_CONTRACT_v1.0.md`
- `CCC_LOVABLE_PHASE1_DESIGN_REFERENCE_v1.0.md`
- `CCC_UIUX_MASTER.md`

It resolves specific ambiguities or transcription issues found in the Phase 1.6 extraction report before Phase 2A implementation begins.

Authority order remains:

1. Explicit Product Owner decisions
2. `CCC_PHASE1_DESIGN_PORT_CONTRACT_v1.0.md`
3. `CCC_UIUX_MASTER.md`
4. `CCC_LOVABLE_PHASE1_DESIGN_REFERENCE_v1.0.md`
5. This Phase 1.6 review for the specific clarifications below
6. `CCC_LOVABLE_PHASE1_EXTRACTION_REPORT_v1.0.md`
7. Component/Page rules and supporting UI/UX skill guidance

---

## 2. Correction — CCC Signal Rail Price semantic

The Phase 1.6 extraction report contains one wording error in the CCC Signal Rail section.

Incorrect wording:

> Price / negative

Correct locked semantic:

> **Price / Giá → positive / green**

The four ordered CCC Signal Rail segments remain:

1. **Price / Giá** → positive / green
2. **Volume / KL** → volume / cyan-blue
3. **Trend / MA200** → trend / blue
4. **RVOL** → rvol / purple

This correction does **not** change scanner logic.

The four technical signals remain exactly:

1. Giá tăng ≥ 3%
2. KL ngày ≥ 200% KLTB10
3. Giá trên MA200
4. RVOL30 ≥ 200%

MA10 remains reference/sort data only and is not a fifth signal.

---

## 3. Theme behavior decision for `website-next`

Lovable Phase 1 source evidence shows:

- Light / Dark / System theme support
- prototype default = System
- prototype persistence key = `chuyenchochung-theme`

This is accepted as **prototype evidence only**.

For Phase 2A implementation in `website-next/`, keep the current production product behavior unless separately approved later:

> **Default theme = Dark when the user has no saved preference.**

Requirements:

- Dark remains the first-load default for a user with no saved preference.
- User can switch to Light.
- Saved theme preference persists across reloads.
- Light and Dark must both use the locked Lovable Phase 1 design tokens.
- Do not silently switch the product default to System merely because Lovable used System.
- A future System/Auto option may be evaluated separately, but it is not part of Phase 2A unless explicitly approved.

Therefore:

```text
Lovable theme colors/tokens
→ PORT

Lovable Light/Dark visual language
→ PORT

Lovable default = System
→ DO NOT PORT AS DEFAULT BEHAVIOR

website-next default = Dark
→ KEEP
```

---

## 4. Font clarification

### Be Vietnam Pro

Phase 1.6 confirms that Lovable actually loads:

- Be Vietnam Pro
- weights 400, 500, 600, 700, 800

Phase 2A should use **Be Vietnam Pro** as the primary UI font, subject to normal loading/performance validation.

### JetBrains Mono

Phase 1.6 only proves that JetBrains Mono is declared in a fallback stack.

It does **not** prove that the font is actually loaded.

Decision:

- Do not add JetBrains Mono merely to achieve nominal parity.
- Use the existing monospace fallback where code/technical text requires it.
- Adding JetBrains Mono later requires a concrete UI need and normal implementation review.
- Financial numeric presentation should use Be Vietnam Pro with tabular numerals as specified in the locked design reference.

---

## 5. Source-confirmed visual details accepted for Phase 2A

The following Phase 1.6 source evidence may be consumed directly during implementation because it is consistent with the locked Phase 1 direction:

### Typography

- `num-hero-lg`: 34px / 700 / 1.08 / -0.02em
- `num-hero`: 30px / 700 / 1.10 / -0.02em
- `num-decision`: 18px / 600 / 1.20 / -0.01em
- `num-decision-sm`: 16px / 600 / 1.25
- `num-support`: 14px / 500 / 1.35
- `label-meta`: 12px / 500 / 1.35 / 0.01em
- financial numerals use tabular figures

### Shape / depth

- base radius: 8px
- low-depth one-pixel borders
- minimal shadows
- restrained surface hierarchy
- RailCard header approximately 40px
- RailCard horizontal content padding approximately 14px

### App Shell

- top header: 56px
- desktop nav: approximately 56px collapsed / 224px expanded
- page padding: 16px, 24px at large desktop
- normal max working width: approximately 1400px
- wide max working width: approximately 1680px
- contextual right rail: 300px
- main/right gap: 24px
- right rail appears beside main at approximately 1536px / 2XL

### Breakpoint evidence

Reference thresholds:

- 640px
- 768px
- 1024px
- 1280px
- 1536px

These are implementation reference values, not permission to ignore the required CCC QA breakpoints:

- 375
- 768
- 1024
- 1440

---

## 6. Accessibility and responsive findings — accepted as implementation requirements

Phase 1.6 identified several prototype limitations.

These are not reasons to redesign the approved Phase 1 language.

They are implementation-quality requirements for `website-next`:

- preserve `prefers-reduced-motion` behavior;
- give icon-only actions accessible names;
- do not rely only on native `title` for important CCC Signal help;
- ensure visible focus states;
- ensure mobile bottom navigation respects safe area;
- verify 44px+ practical touch targets;
- avoid unreadable 11px navigation labels where they harm legibility;
- ensure Scanner mobile behavior is card-first or otherwise intentionally mobile;
- preserve logical keyboard and screen-reader order;
- test Light/Dark semantic contrast in the real static implementation.

UI/UX Pro Max may help improve these implementation details but may not override locked CCC product/design rules.

---

## 7. Prototype defects remain mandatory DO-NOT-PORT items

The following Phase 1 prototype defects remain explicitly rejected:

### PORT-01 — Page Header

Do not place the Page Header inside the main column after the right-rail split.

Required:

```text
PAGE HEADER — full working width

CONTENT GRID
├── MAIN
└── OPTIONAL RIGHT RAIL
```

### PORT-02 — Overview stock row

Do not port `flex + justify-between`.

Required desktop grid:

```text
Identity | Price/Change | Volume | CCC Signal Rail
```

### PORT-03 — Scanner

Do not port:

- combined Change/Volume column
- empty filler column

Required desktop grid:

```text
Identity | Price | Change | Current Volume | CCC
```

All three remain mandatory implementation corrections.

---

## 8. Mock/demo values remain non-authoritative

Do not port Lovable hard-coded values as production truth, including:

- `LIVE 14:35`
- hard-coded `800 mã`
- mock breadth counts
- mock stock/financial values
- mock plan/capacity/quota values
- localStorage entitlement logic
- demo authentication
- incomplete BCTC/fundamental placeholders
- placeholder Phase 2 routes

Real `website-next` data contracts, Supabase data, scanner logic, Data Trust, refresh/cache/error behavior and dynamic counts remain authoritative.

---

## 9. Phase 2A readiness decision

Phase 1.6 review is considered:

> **PASS ✅**

Phase 2A may begin after this review document is committed.

Phase 2A scope should be limited to:

> **Design Tokens + App Shell**

It may port:

- typography
- Light/Dark tokens
- surface/border/shadow system
- basic spacing/radius language
- top header
- desktop navigation
- mobile shell/navigation
- working-width system
- contextual right-rail shell
- theme styling/behavior

Phase 2A must **not** yet redesign or implement page-specific content logic for:

- Overview
- Scanner
- Stock Detail
- Research
- Watchlist
- Alerts
- Account

Those remain later checkpoints.

---

## 10. Lovable access rule remains unchanged

Lovable remains an external **read-only design reference by default**.

This review does not grant any write permission.

No Lovable write action may be performed without explicit Product Owner approval for that specific action.

UI/UX Pro Max remains a supporting reference only; locked CCC rules win whenever there is a conflict.

---

## Final locked summary

```text
PHASE 1 LOVABLE
CLOSED / DESIGN DIRECTION LOCKED

PHASE 1.5
PRODUCT + DESIGN PORT CONTRACT LOCKED

PHASE 1.6
READ-ONLY SOURCE EXTRACTION PASSED

CCC SIGNAL RAIL
Price = positive/green

WEBSITE-NEXT THEME DEFAULT
Dark

LOVABLE SYSTEM DEFAULT
Prototype evidence only — do not port as product default

NEXT IMPLEMENTATION STEP
Phase 2A — Design Tokens + App Shell
```
