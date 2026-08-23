# CCC v19.1.3 — Visual Baseline Restore

**Date:** 2026-08-23  
**Branch:** `feature/user-auth-foundation`  
**Scope:** Visual baseline restoration on the consolidated v19.1 runtime.

## Authority used

1. Product Owner's latest explicit requirements.
2. `CCC_PHASE1_DESIGN_PORT_CONTRACT_v1.0.md`.
3. `CCC_UIUX_MASTER.md`.
4. `CCC_LOVABLE_PHASE1_DESIGN_REFERENCE_v1.0.md`.
5. `CCC_COMPONENT_RULES.md`.
6. Pre-Codex v18.5 / pre-refactor staging behavior.

No external UI/UX skill is treated as authoritative.

## Restored baseline

- Body/readable text raised to the locked 14.5–16px range.
- Table text raised to the locked 13.5–15px range.
- Symbols/company names restored to readable hierarchy.
- KPI values restored to 28–36px range.
- KPI hover/active effects restored, with restrained semantic accents.
- CCC Signal Rail:
  - fixed four positions;
  - 3/4 subtle breathing;
  - 4/4 one-time sweep;
  - reduced-motion disables decorative motion.
- Overview rows now show `RVOL30 + MA10 + MA200`.
- Overview right rail restores:
  - compact Market Pulse;
  - CCC four-signal explanation legend;
  - Data Trust/source card.
- Market Pulse restores dominant VN-INDEX hierarchy with supporting instruments kept compact.
- Research desktop returns to table/row presentation.
- Research mobile remains card-first.
- Research data request is reduced to only the financial fields currently used by the UI.
- Research is warmed during browser idle time to reduce first-navigation waiting.

## Architecture intentionally unchanged

- one consolidated app renderer;
- one data adapter;
- one stylesheet;
- no MutationObserver repair system;
- no Alpha runtime assets;
- no business-rule change;
- no Supabase migration;
- no scanner-universe change.

## Not part of this pass

- Phase 3 Scanner / Toàn bộ thị trường implementation.
- Alert list.
- Payment/billing.
- New business logic.

## Staging QA

Check at minimum:

1. Overall typography no longer feels undersized.
2. KPI cards visibly respond to hover/selection.
3. Overview right rail includes signal legend.
4. Market Pulse hierarchy resembles the approved pre-refactor direction.
5. Overview evidence contains MA10.
6. Industry/Fundamental research is table-first on desktop.
7. Research does not freeze the page while loading.
8. Mobile research uses cards.
9. Light/Dark.
10. No flicker regression.
