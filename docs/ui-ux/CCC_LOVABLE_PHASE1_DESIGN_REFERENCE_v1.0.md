# CCC LOVABLE PHASE 1 DESIGN REFERENCE v1.0

**Status:** LOCKED VISUAL REFERENCE

**Project:** CHUYỆN CHỢ CHỨNG / Chợ Chứng Interactive

**Lovable project ID:** `87f5ce1e-f52a-4933-9ee8-9c4dd3d779ab`

**Phase 1:** DESIGN DIRECTION LOCKED · PHASE 1 CLOSED

## 1. Authority and boundary

This document is the read-only design snapshot approved by the Product Owner after Lovable Phase 1. It lets future agents port the approved visual direction without reopening Lovable.

Lovable Phase 1 is **visual/design reference only**. It is not production source code, runtime architecture, a frontend framework source of truth, backend, authentication, billing, security, or entitlement implementation. Phase 2 is not approved. The implementation target remains the static vanilla JS/CSS staging frontend in `website-next/`; production remains `website/`.

Extract the visual system, not the prototype runtime or mock data.

## 2. Design philosophy

**CALM FINANCIAL INTELLIGENCE**

Characteristics:

- professional;
- trustworthy;
- analytical;
- data-dense but readable;
- fast to scan;
- modern financial SaaS;
- restrained;
- not decorative-first.

Use the hierarchy **Decision → Evidence → Detail/Audit**.

Avoid neon-crypto aesthetics, excessive gradients, glassmorphism everywhere, large collections of cards, heavy shadows, generic admin-dashboard styling, and equal visual weight for every metric.

## 3. Typography target

Primary UI font:

```css
"Be Vietnam Pro", system-ui, -apple-system, BlinkMacSystemFont, sans-serif
```

Mono/reference font:

```css
"JetBrains Mono", ui-monospace, monospace
```

Financial/tabular numeric target: Be Vietnam Pro with tabular numerals.

| Token | Size | Weight | Line height | Letter spacing |
|---|---:|---:|---:|---:|
| `num-hero-lg` | 34px | 700 | 1.08 | -0.02em |
| `num-hero` | 30px | 700 | 1.1 | -0.02em |
| `num-decision` | 18px | 600 | 1.2 | — |
| `num-decision-sm` | 16px | 600 | 1.25 | — |
| `num-support` | 14px | 500 | 1.35 | — |
| `label-meta` | 12px | 500 | 1.35 | 0.01em |

The Lovable stylesheet declares these font families, but this reference does not prove how or where their binaries are loaded in production. Phase 2 must verify actual loading before claiming pixel-level fidelity. Do not add font files during Phase 1.5.

## 4. Shape and surface language

- Base radius: `0.5rem` / `8px`.
- Small internal rail segments: `2px–3px` radius.
- Surface hierarchy: `surface-1`, `surface-2`, `surface-3`, `elevated`.
- Borders perform most structural work.
- Shadows are minimal; `shadow-sm` is approximately a subtle 1px separation and `shadow-md` approximately 1–2px elevation.
- Establish hierarchy through tone, spacing, and typography—not floating cards everywhere.

## 5. Light theme core tokens

| Token | Locked value |
|---|---|
| `background` | `oklch(0.98 0.002 270)` |
| `foreground` | `oklch(0.18 0.02 270)` |
| `surface-1` | `oklch(1 0 0)` |
| `surface-2` | `oklch(0.97 0.005 270)` |
| `surface-3` | `oklch(0.94 0.008 270)` |
| `border` | `oklch(0.88 0.01 270)` |
| `positive` | `oklch(0.55 0.15 145)` |
| `negative` | `oklch(0.55 0.18 25)` |
| `rvol` | `oklch(0.55 0.18 300)` |
| `volume` | `oklch(0.55 0.13 220)` |
| `trend` | `oklch(0.55 0.12 250)` |
| `warning` | `oklch(0.65 0.14 80)` |
| `neutral` | `oklch(0.55 0.02 270)` |

## 6. Dark theme core tokens

| Token | Locked value |
|---|---|
| `background` | `oklch(0.13 0.02 270)` |
| `foreground` | `oklch(0.93 0.005 270)` |
| `surface-1` | `oklch(0.16 0.02 270)` |
| `surface-2` | `oklch(0.18 0.02 270)` |
| `surface-3` | `oklch(0.22 0.02 270)` |
| `border` | `oklch(1 0 0 / 0.10)` |
| `positive` | `oklch(0.65 0.16 145)` |
| `negative` | `oklch(0.70 0.18 25)` |
| `rvol` | `oklch(0.70 0.18 300)` |
| `volume` | `oklch(0.70 0.13 220)` |
| `trend` | `oklch(0.70 0.12 250)` |
| `warning` | `oklch(0.75 0.14 80)` |
| `neutral` | `oklch(0.70 0.02 270)` |

Semantic meanings are fixed: positive price/change is green, negative price/change red, RVOL purple, volume cyan/blue, trend/MA blue, warning/stale/degraded amber, and ordinary information neutral. Color must never be the only signal.

## 7. Global App Shell reference

- Top header: `56px` high.
- Page horizontal padding: `16px` normally and `24px` on large desktop.
- Desktop navigation: compact left rail around `56px`, expanding around XL to approximately `224px`.
- Mobile: top identity/search plus bottom navigation.
- Main working width: approximately `1400px` max.
- Wide desktop: approximately `1680px` max; main plus `300px` right rail with `24px` gap.
- Wide right-rail breakpoint: approximately `1536px` / 2XL.

Mandatory porting correction: do not reproduce the Lovable hierarchy in which the page header becomes part of the main column after the main/right-rail split. The approved hierarchy is:

```text
PAGE HEADER — full working width
CONTENT GRID — MAIN + OPTIONAL RIGHT RAIL
```

This is `PORT-01` and is required.

## 8. Right rail reference

The right rail is contextual, not another permanent dashboard. Reference width: `300px`.

`RailCard` anatomy:

- 8px outer radius;
- subtle border on `surface-1`;
- approximately 40px header;
- compact header/meta;
- approximately 14px content padding;
- no heavy shadow.

Phase 1 examples include CCC Signal Rail explanation, Plan & Scope, Data Trust, and result context. Their wording and data are not authoritative; only the anatomy is reference.

## 9. Market Pulse reference

Market Pulse must immediately communicate a stock-market intelligence product. The exact primary instruments are:

- VN-INDEX;
- S&P 500;
- HANG SENG;
- DXY;
- GOLD;
- WTI;
- BTC.

VN-Index is dominant: approximately one third of the desktop area, with the other six instruments in a compact 3 × 2 arrangement. Do not use seven giant equal cards.

The primary index uses strong numeric hierarchy, semantic change color, state badge, optional breadth context, and exchange/time metadata. Other instruments stay compact with name, state, price, change, and local/time context.

Supported state language includes LIVE, Đóng cửa, Chưa mở, Nghỉ trưa, Dữ liệu trễ, and Không có dữ liệu.

Hard-coded prototype values such as `LIVE 14:35`, `800 mã`, breadth figures, and session states are mock/reference copy only. The implementation must preserve real Data Trust, refresh, session, cache, and error behavior. Factual production data wins over prototype copy.

## 10. CCC Signal Rail — signature component

Exactly four ordered segments:

1. Price / Giá — positive green;
2. Volume / KL — cyan/blue;
3. Trend / MA200 — blue;
4. RVOL — purple.

Reference dimensions:

| Size | Segment | Gap | Inner padding | Segment radius |
|---|---|---|---|---|
| Small | approximately 12 × 14px | 3px | 3px | 2px |
| Medium | approximately 16 × 16px | proportional | proportional | 2–3px |
| Large | approximately 24 × 24px | proportional | proportional | 2–3px |

The rail remains understandable without color through filled/empty states, fixed four-position structure, numeric `N/4`, and accessible labels/tooltips where appropriate.

- `3/4`: “Đang hội tụ”, subtle warning treatment, restrained breathing animation on the rail only.
- `4/4`: “Hội tụ mạnh”, positive emphasis, one restrained one-time sweep.
- Reduced-motion preference disables decorative motion.
- Locked state uses the same family with dashed/subtle border, lock icon, and “Ngoài phạm vi”.

Never turn the rail into a flashing trading-terminal animation.

## 11. Overview reference

Reference hierarchy: page identity/header, Market Pulse, market/signal density context, signals in the user’s technical scope, compact locked remainder, and optional contextual right rail.

Mandatory correction: do not port Lovable’s `flex + justify-between` stock-row implementation. Every desktop row must use the same deterministic four-zone grid:

```text
IDENTITY | PRICE / CHANGE | VOLUME | CCC SIGNAL RAIL
```

This is `PORT-02` and is required.

## 12. Scanner reference

Scanner retains prominent search, compact filters, sort, public/protected result context, financial-table density, and the CCC Signal Rail.

Do not port the empty/filler final column. The approved deterministic desktop grid is:

```text
IDENTITY | PRICE | CHANGE | CURRENT VOLUME | CCC
```

Use five real proportional columns and a sensible working width so data does not spread unnaturally on ultra-wide screens. Desktop is table-first; mobile is card-first. Do not squeeze the desktop table into mobile. This is `PORT-03` and is required.

## 13. Stock Detail reference

Public stock identity and quote remain visible: ticker, company, exchange, current price, percentage change, and current accumulated volume.

Tabs:

- Tổng quan;
- Kỹ thuật;
- Cơ bản;
- BCTC.

The Kỹ thuật tab is either fully entitled or professionally locked. Protected technical content must not flash before its lock state is known. Entitled technical hierarchy includes CCC Signal Rail, four-signal explanation, KLTB10, KL ngày/KLTB10, MA10 and its distance, MA200 and its distance, RVOL30, and RVOL30 sessions. MA10 is reference data, never signal number five.

The Cơ bản tab is public. Use visual hierarchy rather than twenty equally weighted metric cards.

## 14. What not to copy from Lovable

The following are explicitly not authoritative:

- React architecture;
- TanStack Router;
- Tailwind class implementation;
- shadcn implementation details;
- Lovable mock database;
- demo authentication or entitlement security;
- hard-coded market time, status, or `800` values where real data exists;
- mock company or financial values;
- Phase 2 placeholder pages;
- literal wording that conflicts with real product behavior.

This reference governs appearance and hierarchy. Existing real data contracts govern factual content and state.
