# CCC Lovable Phase 1 Extraction Report v1.0

**Status:** READ-ONLY EXTRACTION / AUDIT

**Inspection date:** 2026-08-21 (Asia/Saigon)

**Scope:** Lovable Phase 1 visual evidence only; no redesign and no Phase 2 implementation

## 1. Authority and extraction method

This report records source evidence from the approved Lovable Phase 1 prototype. It does not replace or amend any locked CCC document. Interpretation follows the repository authority order, with Product Owner decisions and `CCC_PHASE1_DESIGN_PORT_CONTRACT_v1.0.md` taking precedence over prototype implementation details.

The Lovable project was inspected directly with read-only tools. Source reads were pinned to one stable commit. No prompt was sent to Lovable, no AI generation was requested, and no Lovable state was changed.

UI/UX Pro Max was used only after extraction as a supporting check for responsive table handling and reduced-motion accessibility. It did not create or alter the design direction.

## 2. Lovable snapshot identity

| Field | Recorded value |
|---|---|
| Project | Chợ Chứng Interactive |
| Project ID | `87f5ce1e-f52a-4933-9ee8-9c4dd3d779ab` |
| Workspace ID | `O24XK2LbuqxdNflzFDjd` |
| Project status | `ready`; enclosing operation status `completed`; agent finished |
| Visibility | Private |
| Published | No |
| Latest commit/ref used for all source reads | `4335bc50d343ce8eb5da32c3c5e5a3a76da404a8` |
| Preview URL | `https://id-preview--87f5ce1e-f52a-4933-9ee8-9c4dd3d779ab.lovable.app` |
| Existing screenshot URL from metadata | `https://screenshot2.lovable.dev/1461e289025f2c25ee87d939807ca5c5/id-preview-4335bc50--87f5ce1e-f52a-4933-9ee8-9c4dd3d779ab.lovable.app-1787294481038.png` |
| Created | `2026-08-20T21:12:17.560Z` |
| Last project update | `2026-08-21T06:41:26.137Z` |
| Last edit | `2026-08-21T06:41:00.425Z` |
| Reported stack | `tanstack_start_ts_current` |

Snapshot consistency is confirmed: `list_files` returned 97 paths with no additional page, and every `read_file` call used the commit above.

## 3. Read-only Lovable actions used

Only the following Lovable actions were used:

- `get_project`: 1 call, to establish project identity, commit, preview and screenshot metadata.
- `list_files`: 1 call, pinned to the recorded commit, limit 100; 97 files returned and `has_more` was false.
- `read_file`: 17 calls, each for one exact source path and pinned to the same commit.

The following allowed read tools were not needed and were not called: `list_messages`, `get_message`, `list_edits`, `get_diff`, `get_project_knowledge`, and `get_workspace_knowledge`.

No Lovable write or mutation action was called.

## 4. Files inspected

All Lovable paths below were read at commit `4335bc50d343ce8eb5da32c3c5e5a3a76da404a8`:

1. `src/styles.css`
2. `src/components/theme-provider.tsx`
3. `src/components/app-shell.tsx`
4. `src/components/workspace-layout.tsx`
5. `src/components/market-pulse.tsx`
6. `src/components/signal-rail.tsx`
7. `src/components/context-rail.tsx`
8. `src/components/overview-view.tsx`
9. `src/components/stock-row.tsx`
10. `src/components/scanner-view.tsx`
11. `src/components/stock-detail.tsx`
12. `src/components/demo-provider.tsx`
13. `src/lib/entitlement.ts`
14. `src/lib/mock-data.ts`
15. `src/routes/__root.tsx`
16. `src/hooks/use-mobile.tsx`
17. `package.json`

The full source tree was discovered first. Phase 2 placeholder pages and generic UI primitives were not read because the files above were sufficient to establish Phase 1 tokens, shell, component anatomy, responsive behavior, theme behavior, entitlement presentation and mock-data boundaries.

## 5. Confirmed typography

### 5.1 Fonts and loading evidence

| Item | Source evidence | Classification |
|---|---|---|
| Sans family | `"Be Vietnam Pro", system-ui, -apple-system, BlinkMacSystemFont, sans-serif` | **MATCH** |
| Be Vietnam Pro loading | Root route loads Google Fonts weights 400, 500, 600, 700 and 800 with `display=swap` | **MATCH — ACTUALLY LOADED** |
| Mono family | `"JetBrains Mono", ui-monospace, monospace` is declared for `code`, `kbd`, `pre` and `samp` | **REFERENCE NEEDS CLARIFICATION — DECLARED ONLY** |
| JetBrains Mono loading | No import, stylesheet or package evidence was found in the inspected snapshot | **REFERENCE NEEDS CLARIFICATION — NOT PROVEN LOADED** |
| Tabular family | Be Vietnam Pro stack with `font-variant-numeric: tabular-nums` and `letter-spacing: -0.01em` | **MATCH** |

Implementation must preserve the distinction between a declared font stack and an actually loaded web font. It must not claim JetBrains Mono is loaded unless Phase 2A explicitly adds and validates that resource.

### 5.2 Numeric and metadata hierarchy

| Utility | Size | Weight | Line height | Letter spacing |
|---|---:|---:|---:|---:|
| `.num-hero` | 30px | 700 | 1.10 | -0.02em |
| `.num-hero-lg` | 34px | 700 | 1.08 | -0.02em |
| `.num-decision` | 18px | 600 | 1.20 | -0.01em |
| `.num-decision-sm` | 16px | 600 | 1.25 | inherited/default |
| `.num-support` | 14px | 500 | 1.35 | inherited/default |
| `.label-meta` | 12px | 500 | 1.35 | 0.01em |

The numeric hierarchy and tabular treatment are **MATCH** items. The explicit `-0.01em` on `.num-decision` is **MISSING FROM REFERENCE** and should be treated as source evidence for implementation review, not as an automatic locked-reference amendment.

## 6. Confirmed color and theme tokens

Values below are copied from `src/styles.css` without conversion.

### 6.1 Light theme

| Token | Exact value |
|---|---|
| `--background` | `oklch(0.98 0.002 270)` |
| `--foreground` | `oklch(0.18 0.02 270)` |
| `--card` / `--popover` / `--surface-1` / `--surface-elevated` | `oklch(1 0 0)` |
| `--card-foreground` / `--popover-foreground` / `--surface-elevated-foreground` | `oklch(0.18 0.02 270)` |
| `--primary` | `oklch(0.28 0.04 270)` |
| `--primary-foreground` | `oklch(0.98 0.002 270)` |
| `--secondary` | `oklch(0.95 0.01 270)` |
| `--secondary-foreground` | `oklch(0.28 0.04 270)` |
| `--muted` | `oklch(0.94 0.008 270)` |
| `--muted-foreground` | `oklch(0.55 0.03 270)` |
| `--accent` | `oklch(0.94 0.01 270)` |
| `--accent-foreground` | `oklch(0.28 0.04 270)` |
| `--destructive` | `oklch(0.55 0.18 25)` |
| `--destructive-foreground` | `oklch(0.98 0.002 270)` |
| `--border` | `oklch(0.88 0.01 270)` |
| `--input` | `oklch(0.9 0.01 270)` |
| `--ring` | `oklch(0.55 0.04 270)` |
| `--positive` / muted / background | `oklch(0.55 0.15 145)` / `oklch(0.7 0.1 145)` / `oklch(0.95 0.04 145)` |
| `--negative` / muted / background | `oklch(0.55 0.18 25)` / `oklch(0.7 0.12 25)` / `oklch(0.95 0.04 25)` |
| `--rvol` / muted / background | `oklch(0.55 0.18 300)` / `oklch(0.7 0.12 300)` / `oklch(0.95 0.04 300)` |
| `--volume` / muted / background | `oklch(0.55 0.13 220)` / `oklch(0.7 0.09 220)` / `oklch(0.95 0.03 220)` |
| `--trend` / muted / background | `oklch(0.55 0.12 250)` / `oklch(0.7 0.08 250)` / `oklch(0.95 0.03 250)` |
| `--warning` / muted / background | `oklch(0.65 0.14 80)` / `oklch(0.78 0.09 80)` / `oklch(0.95 0.04 80)` |
| `--neutral` / muted / background | `oklch(0.55 0.02 270)` / `oklch(0.7 0.02 270)` / `oklch(0.92 0.01 270)` |
| `--surface-2` | `oklch(0.97 0.005 270)` |
| `--surface-3` | `oklch(0.94 0.008 270)` |

### 6.2 Dark theme

| Token | Exact value |
|---|---|
| `--background` | `oklch(0.13 0.02 270)` |
| `--foreground` | `oklch(0.93 0.005 270)` |
| `--card` / `--surface-1` | `oklch(0.16 0.02 270)` |
| `--card-foreground` | `oklch(0.93 0.005 270)` |
| `--popover` / `--surface-2` | `oklch(0.18 0.02 270)` |
| `--primary` | `oklch(0.85 0.03 270)` |
| `--primary-foreground` | `oklch(0.13 0.02 270)` |
| `--secondary` / `--muted` / `--surface-3` | `oklch(0.22 0.02 270)` |
| `--muted-foreground` | `oklch(0.65 0.02 270)` |
| `--accent` | `oklch(0.24 0.02 270)` |
| `--destructive` | `oklch(0.65 0.18 25)` |
| `--destructive-foreground` | `oklch(0.98 0.002 270)` |
| `--border` | `oklch(1 0 0 / 0.1)` |
| `--input` | `oklch(1 0 0 / 0.12)` |
| `--ring` | `oklch(0.55 0.04 270)` |
| `--positive` / muted / background | `oklch(0.65 0.16 145)` / `oklch(0.75 0.1 145)` / `oklch(0.2 0.05 145)` |
| `--negative` / muted / background | `oklch(0.7 0.18 25)` / `oklch(0.8 0.12 25)` / `oklch(0.2 0.05 25)` |
| `--rvol` / muted / background | `oklch(0.7 0.18 300)` / `oklch(0.8 0.12 300)` / `oklch(0.2 0.05 300)` |
| `--volume` / muted / background | `oklch(0.7 0.13 220)` / `oklch(0.8 0.09 220)` / `oklch(0.2 0.04 220)` |
| `--trend` / muted / background | `oklch(0.7 0.12 250)` / `oklch(0.8 0.08 250)` / `oklch(0.2 0.04 250)` |
| `--warning` / muted / background | `oklch(0.75 0.14 80)` / `oklch(0.85 0.09 80)` / `oklch(0.25 0.04 80)` |
| `--neutral` / muted / background | `oklch(0.7 0.02 270)` / `oklch(0.8 0.02 270)` / `oklch(0.22 0.02 270)` |
| `--surface-elevated` | `oklch(0.2 0.02 270)` |
| `--surface-elevated-foreground` | `oklch(0.93 0.005 270)` |

The core palette is a **MATCH**. The complete contextual families for RVOL, volume, trend, warning and neutral, including muted/background variants in both themes, are **MISSING FROM REFERENCE** where the locked reference only summarizes core colors. These values should be consumed as implementation evidence pending Product Owner review; they do not silently amend the reference.

Theme behavior is Light/Dark/System, defaults to System, follows `prefers-color-scheme`, and persists the choice under `chuyenchochung-theme`. Light/Dark support is a **MATCH**; the exact default and persistence behavior is **MISSING FROM REFERENCE**.

## 7. Shape, depth and surface hierarchy

- Base radius is `0.5rem` (8px).
- Derived radii are base minus 4px (`sm`), base minus 2px (`md`), base (`lg`), base plus 4px (`xl`), plus 8px (`2xl`) and plus 12px (`3xl`).
- Cards and rail cards use one-pixel borders; separators are primarily border lines or one-pixel grid gaps showing the border color.
- Light shadows are `0 1px 0 oklch(0.7 0 0 / 0.08)` and `0 1px 2px oklch(0.7 0 0 / 0.06)`.
- Dark shadows are `0 1px 0 oklch(0 0 0 / 0.25)` and `0 1px 2px oklch(0 0 0 / 0.2)`.
- Surface hierarchy is background → surface 1/card → surface 2 → surface 3/elevated, with token values recorded above.
- A rail card uses 8px rounding, a 40px header with 14px horizontal padding, and content padding of 14px horizontally and 12px vertically.

These items are **MATCH** except the fully enumerated shadow and derived-radius formulas, which are **MISSING FROM REFERENCE** where not already specified.

## 8. Confirmed layout dimensions and breakpoints

### 8.1 App shell and workspace

| Element | Source-confirmed behavior | Classification |
|---|---|---|
| Top header | Sticky, 56px high | **MATCH** |
| Desktop navigation | Hidden below `lg`; 56px collapsed and 224px at `xl` | **MATCH** |
| Page padding | 16px; 24px at `lg` | **MATCH** |
| Standard content width | Maximum 1400px | **MATCH** |
| Wide layout | Maximum 1680px when the contextual rail is present at `2xl` | **MATCH** |
| Main/right split | `minmax(0, 1fr) 300px`, 24px gap at `2xl` | **MATCH** |
| Right rail | 300px; sticky at 72px from top; 16px internal card gap | **MATCH** |
| Below `2xl` | Context cards move below main content, one column then two at `sm` | **MATCH** |
| Global search | Desktop from `md`; separate mobile search row below the main header | **MATCH** |
| Mobile navigation | Sticky bottom navigation with five labeled destinations | **MATCH** |

Source uses Tailwind default responsive thresholds: `sm` 640px, `md` 768px, `lg` 1024px, `xl` 1280px and `2xl` 1536px. `use-mobile.tsx` specifically treats widths below 768px as mobile.

The current `WorkspaceLayout` puts the page header inside the main column after the main/right split. This is **PROTOTYPE DEFECT — DO NOT PORT** under PORT-01.

### 8.2 Responsive implementation concerns

- No explicit safe-area inset handling was found for the mobile bottom navigation. **REFERENCE NEEDS CLARIFICATION.**
- Mobile bottom-navigation labels use an 11px size. Confirm legibility and target sizing during Phase 2A QA. **REFERENCE NEEDS CLARIFICATION.**
- UI/UX Pro Max independently flags wide data tables as a mobile overflow risk and recommends either a mobile card presentation or a controlled horizontal scroll area. The Port Contract remains authoritative.

## 9. Confirmed component anatomy

### 9.1 Market Pulse

- One bordered, 8px-radius surface contains a wrapped header, a primary VN-Index block and six secondary instruments.
- Header padding is 16px horizontally and 12px vertically, with a bottom separator, live indicator, title, update time and breadth/count context.
- At `lg`, the body is a three-column grid: VN-Index occupies one column; secondary instruments occupy two columns in a three-by-two sub-grid.
- Below `lg`, the body is one column; secondary instruments become two columns at `sm` and one column below `sm`.
- One-pixel grid gaps expose the border color as separators; blocks use surface 1.
- VN-Index uses 16px padding, `.num-hero-lg` for the index, `.num-decision` for change, and a three-column breadth strip with 8px gaps.
- Secondary instruments use 12px padding, `.num-decision` for price and `.num-support` for change.
- State badges pair color with text: live/positive, degraded/warning and neutral fallback.
- Skeleton evidence is approximately 44px for the header, 208px for the primary block and 96px for each secondary block.

The visual anatomy is **MATCH**. Instrument values, update time and state in the prototype are mock data and must not be treated as production truth.

### 9.2 CCC Signal Rail

The signal order is locked and source-confirmed:

1. Price increase ≥ 3% (`price`)
2. Current daily volume ≥ 200% of average volume 10 (`volume`)
3. Price above MA200 (`trend`)
4. RVOL30 ≥ 200% (`rvol`)

MA10 remains reference/sort data and is not a fifth signal.

| Size | Segment dimensions | Gap | Outer padding |
|---|---|---|---|
| `sm` | 12px × 14px | 3px | 3px |
| `md` | 16px × 16px | 4px | 4px |
| `lg` | 24px × 24px | 4px | 4px |

- Outer radius is 3px; segment radius is 2px.
- Active segments use the exact semantic color tokens for price/negative, volume, trend and RVOL.
- Inactive segments use the semantic foreground at 12% opacity plus a 20% inset ring.
- Count is shown as `N/4`; optional text labels are hidden below `sm`.
- At 3/4, the rail uses warning background/ring, active segments breathe, and the state text is `Đang hội tụ`.
- At 4/4, it uses positive background/ring, runs one sweep, and shows `Hội tụ mạnh`.
- Locked state uses a dashed border, translucent surface 2, lock icon and `Ngoài phạm vi` copy.

Motion timings:

- Live pulse: 2s, ease-in-out, infinite, opacity 1 → 0.4 → 1.
- Ticker scroll: 40s, linear, infinite.
- Confluence sweep: 1s, `cubic-bezier(0.4, 0, 0.2, 1)`, once.
- Convergence breathing: 3.2s, ease-in-out, infinite, opacity 0.55 → 0.9 → 0.55.
- Segment activation: 0.45s ease-out, `scaleY(0.4) → 1.12 → 1`.
- Segment deactivation: 0.5s ease-out to opacity 0.25.

All listed animations are disabled under `prefers-reduced-motion: reduce`; the sweep is also hidden. Signal Rail anatomy and reduced-motion behavior are **MATCH**.

The prototype uses visible count/text so meaning is not conveyed by color alone. However, individual signal segments are generic spans carrying `aria-label`, and the full-rule help is supplied through a `title` tooltip. Reliable screen-reader naming and keyboard-accessible help are not proven. This is **REFERENCE NEEDS CLARIFICATION** and an implementation accessibility risk, not a request to redesign the component.

### 9.3 Overview

Source section order is:

1. Page header
2. Market Pulse
3. Market density block
4. In-scope signal/results block
5. Contextual rail containing Signal legend/state, plan/scope and data trust

The density grid is one column, two at `sm`, and four at `lg`, with 16px card padding. In-scope rows are sorted by signal count and then volume; up to eight mock rows are shown. Protected remainder is a dashed aggregate block with count only, so protected identities are not exposed.

The current `StockRow` is a `flex`/`justify-between` row. Its effective desktop order is identity | volume | price/change | CCC, and mobile hides volume and CCC. This is **PROTOTYPE DEFECT — DO NOT PORT**. PORT-02 requires the desktop order Identity | Price/Change | Volume | CCC Signal Rail. The current flex row must not be copied.

The header placement inside the split also triggers PORT-01. Overview anatomy otherwise provides useful spacing, hierarchy and public/protected-state evidence.

### 9.4 Scanner

- Filter surface uses 12px padding and contains text search plus two select controls; it stacks before becoming horizontal at `lg`.
- Public identity and quote data remain visible; technical signal data switches between entitled and locked presentations.
- Row horizontal padding is 16px and vertical padding is 10px.
- Current source grid definitions are:
  - Mobile: `minmax(0,1fr) auto`
  - `sm`: `minmax(0,1fr) 6rem 6.5rem auto`
  - `lg`: `minmax(0,17rem) 6.5rem 7.5rem auto minmax(0,1fr)`
  - `2xl`: `minmax(0,22rem) 7rem 8rem auto minmax(0,1fr)`
- Current headers are Identity, Price, combined Change/Volume, CCC and an empty final track.
- On mobile, the div-grid becomes two columns and CCC drops to a second row spanning both columns.
- Contextual plan/data cards use the shared right-rail treatment.

The empty final `minmax(0,1fr)` track is **PROTOTYPE DEFECT — DO NOT PORT**. PORT-03 requires five real desktop columns: Identity | Price | Change | Current Volume | CCC, with no filler column.

The scanner is implemented as div grids rather than a semantic table, and only ticker links are inherently keyboard-focusable. Semantics, row/card reading order and keyboard behavior are **REFERENCE NEEDS CLARIFICATION** for Phase 2A accessibility QA. Mobile must use the contract-approved card/controlled-overflow behavior rather than allow a wide desktop grid to break the viewport.

### 9.5 Stock Detail

- Page uses 16px padding and 24px from `lg`, with 20px vertical section gaps.
- Quote header stacks on mobile and becomes a horizontal identity/price composition at `sm`.
- Ticker is 24px extra-bold; primary price uses the 34px hero numeric style and change uses the 18px decision style.
- Tabs are `Tổng quan`, `Kỹ thuật`, `Cơ bản`, and `BCTC`.
- Public overview includes quote metrics and basic context.
- Entitled technical state shows the large Signal Rail, a four-signal grid (one column then four from `sm`) and technical metrics (two columns, three at `sm`, four at `lg`).
- Locked technical state is a centered dashed surface-2 panel with a circular lock mark, title, explanatory copy and CTA.
- Fundamental content is a two-column grid and expands to four columns at `sm`.

The quote/tabs/locked-panel anatomy is **MATCH**. The prototype header contains ticker, exchange/sector and a short company name but does not establish a logo/full legal-name rule; this is **REFERENCE NEEDS CLARIFICATION**.

Fundamental content is demonstrative and incomplete: it lacks score coverage/available points, debt-ratio detail, quarterly history and a real BCTC path. The BCTC tab is a placeholder. These omissions are prototype limitations and must not become product requirements or production truth. Equal-weight metric cards are evidence of the prototype only; Phase 2A must apply the locked CCC hierarchy and score-coverage rules.

### 9.6 Context rail and locked states

- Rail card anatomy is shared across plan/scope, Data Trust and contextual guidance.
- Locked content uses dashed borders, muted surfaces, a lock icon, explicit scope copy and aggregate counts where appropriate.
- Copy describes technical scope rather than implying that a symbol is removed from the scanner universe.

The visual locked-state language is a **MATCH**. Hard-coded plan price, capacity, universe size, timestamps and source status are mock/demo only.

## 10. Confirmed responsive behavior

- The app shell moves from mobile top/search/bottom navigation to desktop top/side navigation at the documented breakpoints.
- The workspace contextual rail stays beside content only at `2xl`; otherwise its cards flow below the main content.
- Market Pulse moves from one-column mobile to a two-column secondary grid at `sm` and a three-column desktop composition at `lg`.
- Density and metric cards progressively expand from one/two columns to wider desktop grids.
- Stock Detail quote composition changes from vertical to horizontal at `sm`.
- Signal labels are suppressed below `sm`, while the `N/4` count remains visible.
- Overview's current mobile row hides volume and CCC; this is prototype behavior, not approved port behavior.
- Scanner's current mobile div-grid wraps CCC below the row; Phase 2A must validate the approved mobile card/read-order treatment.

Responsive evidence is generally **MATCH** for shell, Market Pulse, contextual rail and Stock Detail. Overview and Scanner row behavior remains subject to PORT-02/PORT-03 and is not a pattern to copy literally.

## 11. Motion and accessibility details

Confirmed positive evidence:

- The document language is Vietnamese (`lang="vi"`).
- Viewport metadata is present.
- Theme responds to system preference and supports explicit Light/Dark selection.
- Signal and market states pair semantic color with visible text/counts.
- Tabular numerals are used for financial data alignment.
- All custom prototype animations are suppressed for reduced-motion preference.

Implementation risks requiring Phase 2A validation:

- Header icon-only actions, including refresh/alerts/theme/avatar controls, do not all show explicit accessible names in the inspected component source.
- Signal help relies on native `title` behavior and generic segment spans.
- Scanner rows lack semantic table structure and a proven full-row keyboard interaction model.
- Mobile bottom navigation needs target-size, 11px-label legibility and safe-area checks.
- Focus-visible behavior must be verified in rendered primitives; it cannot be established from the custom component files alone.
- Light and Dark semantic contrasts must be tested in the real static implementation rather than assumed from token values.

The UI/UX Pro Max support check classified reduced-motion compliance as high-severity and responsive table overflow/card handling as medium-severity. This corroborates the existing CCC QA/Port Contract; it does not supersede them.

## 12. Visual baseline and screenshot availability

Lovable metadata exposes both a live preview URL and one existing static screenshot URL for the pinned project snapshot.

The environment attempted to download that already-existing screenshot without invoking any Lovable write action. Local PowerShell/curl attempts failed at the TLS credential layer, and a direct Python request received HTTP 403. No image file was retained. No prompt was sent to Lovable and no project/source change was attempted.

**AUTOMATED SCREENSHOT CAPTURE UNAVAILABLE.**

No local viewport screenshots were created. The Product Owner may supply approved 1440px/375px Light/Dark captures later. The metadata URL above remains recorded as snapshot evidence.

## 13. Comparison with locked Phase 1 design reference

| Important item | Classification | Finding |
|---|---|---|
| Be Vietnam Pro sans stack and weights | **MATCH** | Declared and actually loaded through Google Fonts |
| JetBrains Mono | **REFERENCE NEEDS CLARIFICATION** | Declared as fallback stack; actual loading not proven |
| Numeric hierarchy and tabular numerals | **MATCH** | Exact source utilities confirmed |
| `.num-decision` letter spacing | **MISSING FROM REFERENCE** | Source explicitly uses `-0.01em` |
| Core Light/Dark palette | **MATCH** | Exact OKLCH values confirmed |
| Complete semantic muted/background palette | **MISSING FROM REFERENCE** | Source contains more exact RVOL/volume/trend/warning/neutral variants |
| System-theme default and local persistence | **MISSING FROM REFERENCE** | Default is System; key is `chuyenchochung-theme` |
| Radius/surface hierarchy | **MATCH** | 8px base, low-depth borders/shadows confirmed |
| Full derived radius and shadow formulas | **MISSING FROM REFERENCE** | Exact formulas/values are source evidence |
| App shell dimensions | **MATCH** | 56px header, 56/224px nav, 1400/1680px widths, 300px rail |
| Page header placement | **PROTOTYPE DEFECT — DO NOT PORT** | Violates PORT-01 |
| Market Pulse anatomy | **MATCH** | Primary VN block plus six secondary instruments and responsive grid confirmed |
| Signal Rail order, dimensions and states | **MATCH** | Four signals, exact sizes, 3/4 and 4/4 states confirmed |
| Signal Rail tooltip/segment semantics | **REFERENCE NEEDS CLARIFICATION** | Accessible interaction is not fully established by source |
| Overview stock row | **PROTOTYPE DEFECT — DO NOT PORT** | Flex order/hiding violates PORT-02 |
| Scanner desktop grid | **PROTOTYPE DEFECT — DO NOT PORT** | Combined field plus filler violates PORT-03 |
| Scanner semantic/mobile treatment | **REFERENCE NEEDS CLARIFICATION** | Div-grid semantics and mobile card behavior need implementation proof |
| Stock Detail quote/tabs/locked panel | **MATCH** | Visual anatomy confirmed |
| Stock Detail identity logo/full-name rule | **REFERENCE NEEDS CLARIFICATION** | Prototype only proves ticker, short name, exchange and sector |
| Fundamental/BCTC completeness | **PROTOTYPE DEFECT — DO NOT PORT** | Demonstrative content is incomplete relative to locked CCC requirements |
| Locked/aggregate presentation | **MATCH** | Scope is explicit; protected identities are not exposed |
| Hard-coded Data Trust/plan/universe values | **PROTOTYPE DEFECT — DO NOT PORT** | Mock-only values must be replaced by real frontend state |

No locked reference was edited. Items marked missing or needing clarification require Product Owner review before any reference update.

## 14. Mandatory corrections for any future port

These rules remain authoritative regardless of current prototype source:

### PORT-01 — Page Header

Place the Page Header at full content width before the main/right-rail split. Do not copy the current `WorkspaceLayout` placement inside the main column.

### PORT-02 — Overview desktop result row

Use: **Identity | Price/Change | Volume | CCC Signal Rail**. Do not copy the current flex/`justify-between` row, its effective order, or its mobile hiding as the desktop pattern.

### PORT-03 — Scanner desktop columns

Use: **Identity | Price | Change | Current Volume | CCC**. Do not combine Change/Volume and do not preserve the empty filler track.

## 15. Mock/demo-only evidence that must not become production truth

- All market, stock, financial and signal values in `mock-data.ts`.
- The 15-symbol mock list and the hard-coded 800-symbol universe copy.
- Hard-coded market timestamp `14:35`, LIVE/degraded state and source status.
- Local clock usage as a stand-in for real source update time.
- Mock plan names, prices, quotas, capacity and upgrade state.
- LocalStorage demo entitlement and first-N-symbol access logic.
- Client-only demo authentication/plan behavior.
- Any apparent security boundary in the prototype; it is presentation evidence only.
- Incomplete fundamental metrics, score, coverage and BCTC placeholders.
- Future navigation destinations and placeholder routes.
- Prototype Supabase/backend assumptions; no real backend integration was inspected or approved here.

The four scanner signals and MA10/MA200 roles match the repository contract, but prototype values and entitlement logic must never replace production data/business logic.

## 16. Recommended Phase 2A implementation inputs

This is an evidence list, not a Phase 2A design or implementation plan. Future Phase 2A work should consume:

1. Product Owner decisions and the locked Port Contract, including PORT-01/02/03.
2. Exact source-confirmed typography, OKLCH tokens, radius, shadow and surface values in this report.
3. Source-confirmed shell dimensions and responsive thresholds.
4. Market Pulse and CCC Signal Rail anatomy, including Light/Dark and reduced-motion states.
5. Locked/public/aggregate visual treatments without copying demo entitlement logic.
6. Existing `website-next/` real data, routes, cache/refresh behavior, four-signal logic and permission model.
7. CCC component/page patterns and the complete UI/UX QA checklist.
8. Accessibility validation for names, focus, semantics, contrast, target sizes and responsive data rows/cards.
9. Product Owner clarification for JetBrains Mono loading, Stock Detail identity detail, mobile navigation safe area and any item classified above as missing or unclear.

Phase 2A must not consume prototype mock values, placeholder routes, localStorage entitlement, incomplete fundamentals or any of the three known layout defects.

## 17. Extraction safety confirmation

- No `send_message` was used.
- No Lovable write or mutation action was used.
- No Lovable project state was changed.
- No Lovable credits were intentionally spent.
- No Lovable prompt/AI generation was requested.
- No production code was changed.
- No `website/` file was changed.
- No `website-next/` JS/CSS or other implementation file was changed.
- No backend, scanner, Python, GAS, Supabase, schema, authentication or billing file was changed.
- No scanner logic, scanner universe, signal rule or data behavior was changed.
- Phase 2 and Phase 2A were not started.
- No file was staged.
- No commit was performed.
- No push was performed.
