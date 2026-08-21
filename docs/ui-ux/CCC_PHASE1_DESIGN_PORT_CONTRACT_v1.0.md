# CCC PHASE 1 DESIGN PORT CONTRACT v1.0

**Status:** LOCKED

**Approved direction:** CALM FINANCIAL INTELLIGENCE

**Visual reference:** `CCC_LOVABLE_PHASE1_DESIGN_REFERENCE_v1.0.md`

## 1. Source-of-truth contract

- `website/` is the production frontend source of truth.
- `website-next/` is the v19 staging and Phase 1 implementation target.
- Lovable Phase 1 is visual reference only.
- The target remains static vanilla JS/CSS. Do not copy the prototype’s React, TanStack, Tailwind, or shadcn runtime architecture.
- Do not modify or promote `website/` until staging passes QA and the Product Owner explicitly approves promotion.
- Phase 1.5 defines documentation and contract only; it does not authorize UI implementation or Phase 2.

## 2. Locked product data layers

### A. Public Market Quote

Public for every stock:

- ticker;
- display/company name;
- exchange;
- current price;
- percentage change;
- current accumulated volume.

### B. Public Fundamental Research

Public when real fields exist:

- industry / `website_group`;
- fundamental score and score coverage;
- profit growth;
- revenue/income growth;
- quarterly growth;
- ROE;
- ROA;
- debt/equity;
- debt/assets;
- P/E;
- P/B;
- financial freshness;
- quarterly financial history;
- BCTC link.

Existing missing-data rules remain unchanged. Never fabricate unavailable values or normalize an incomplete fundamental score to 100.

### C. Protected CCC Technical Intelligence

Protected according to technical entitlement:

- KLTB10;
- KL ngày/KLTB10;
- MA10 and distance to MA10;
- MA200 and distance to MA200;
- RVOL30 and RVOL30 sessions;
- four technical signals;
- signal count;
- CCC Signal Rail;
- technical discovery identities;
- technical alerts.

The following wording is locked:

> Market quote is public.
>
> Fundamental research is public.
>
> CCC technical intelligence is protected.

Fundamental Research must never be visually mixed with protected technical intelligence merely because both exist for the same stock.

## 3. Signal and scanner truth

Exactly four signals remain authoritative:

1. Giá tăng ≥ 3%;
2. KL ngày ≥ 200% KLTB10;
3. Giá trên MA200;
4. RVOL30 ≥ 200%.

MA10 is reference/sort data and is not a fifth signal. The scanner universe, collection behavior, source data, score calculation, refresh/cache behavior, and missing-data behavior are unchanged by this contract.

## 4. Membership and entitlement contract

Commercial plans and inheritance remain unchanged: FREE, BASIC, PLUS, PRO, FULL.

The labels 10 / 20 / 50 / 100 / Full Market describe the scope of **CCC Technical Intelligence**, not access to public quote or Fundamental Research.

For FREE, BASIC, PLUS, and PRO, the Watchlist determines the active technical entitlement set. Full Market grants market-wide technical viewing scope, but does not automatically enable alerts for every market symbol. Alerts remain a separate personalization and permission concern.

A stock outside a user’s technical Watchlist still exposes public identity, quote, and Fundamental Research. Only its CCC Technical Intelligence is locked.

## 5. Visual/data hierarchy

The implementation must preserve three visibly distinct layers:

1. **PUBLIC LAYER** — Market Quote + Fundamental Research;
2. **MEMBERSHIP LAYER** — CCC Technical Intelligence;
3. **PERSONALIZATION LAYER** — Watchlist + Alerts + Account.

Public data must not be dimmed, obscured, or described as outside plan scope. Protected technical content must be authorized before rendering and must not flash before the locked state is established.

Prototype copy is not data truth. Hard-coded demo timestamps, session states, stock counts, breadth values, plan counts, company values, or financial figures must not replace real production-derived state. Existing Supabase, refresh, cache, error, session, Data Trust, and dynamic count behavior remains authoritative.

## 6. Page contracts

### Global App Shell

The page header spans the full working width before the content divides into main and optional right rail. Right rail content is contextual.

### Overview `/`

Desktop result rows use one deterministic grid shared by every row:

```text
Identity | Price/Change | Volume | CCC Signal Rail
```

Identity and public quote stay visible. CCC Signal Rail and technical discovery identity obey technical entitlement.

### Scanner `/danh-sach`

Desktop results use five real proportional columns:

```text
Identity | Price | Change | Current Volume | CCC
```

There is no filler column. Desktop is table-first and mobile is card-first. Public identity and quote are visible for every stock; CCC is entitled or professionally locked.

### Industry Comparison `/so-sanh-theo-nganh`

This route is Public Fundamental Research. It focuses only on real fundamental fields and their freshness/coverage. It must not require or present technical signal count, CCC Signal Rail, RVOL30, MA10, MA200, or technical signal columns as research criteria.

### Fundamental Screener `/sang-loc-co-ban`

This route is Public Fundamental Research. It focuses on real fundamental filters, score with coverage, financial metrics, freshness, history, and BCTC access where real data exists. It must not require or present technical signal count, CCC Signal Rail, RVOL30, MA10, MA200, or technical signal columns as research criteria.

### Stock Detail

Public identity and quote stay visible: ticker, company, exchange, current price, percentage change, and current accumulated volume. The tabs are Tổng quan, Kỹ thuật, Cơ bản, and BCTC.

- Kỹ thuật is fully entitled or professionally locked without protected-content flash.
- Cơ bản and BCTC research are public when real fields/links exist.
- Technical and fundamental evidence remain visually separated.

## 7. Mandatory Phase 1 porting debt

These items are required implementation debt, not optional visual polish:

### PORT-01 — FULL-WIDTH PAGE HEADER

The page header spans the working width before the main/right-rail split.

### PORT-02 — OVERVIEW FOUR-ZONE GRID

Replace the prototype’s flex/`justify-between` desktop stock row with:

```text
Identity | Price/Change | Volume | CCC Signal Rail
```

All rows share the same column tracks.

### PORT-03 — SCANNER FIVE-COLUMN GRID

Remove the filler column and use:

```text
Identity | Price | Change | Current Volume | CCC
```

All five columns contain real content and use sensible proportional tracks within a restrained working width.

## 8. Phase 1 visual obligations

The future port must preserve:

- the approved Calm Financial Intelligence language;
- Decision → Evidence → Detail/Audit;
- the exact visual tokens and type targets in the locked reference;
- Light and Dark modes;
- desktop, tablet, and mobile behavior;
- a restrained surface/border/shadow system;
- the exact four-position CCC Signal Rail semantics and accessible non-color meaning;
- reduced-motion behavior;
- desktop tables and mobile cards where specified;
- clear loading, error, stale, degraded, missing, and locked states.

## 9. What this contract does not authorize

This contract does not authorize backend, scanner, Python, GAS, Supabase, schema, authentication, payment, Watchlist, Alert, Account, framework migration, or production changes. It does not authorize Lovable access or API use. Any implementation mismatch found during Phase 1.5 is recorded for Phase 2; it is not fixed here.

## 10. Phase 2 acceptance gate

Before promotion, the implementation must:

- resolve `PORT-01`, `PORT-02`, and `PORT-03`;
- pass the repository UI/UX QA checklist in Light and Dark modes and required breakpoints;
- preserve all four routes and real data/error/cache behavior;
- demonstrate that public quote and fundamentals stay public while technical intelligence is correctly protected;
- show no protected technical-content flash;
- preserve scanner universe and four-signal logic;
- pass Product Owner review before any production promotion.

Until then, `website-next/` remains staging and `website/` remains production source of truth.
