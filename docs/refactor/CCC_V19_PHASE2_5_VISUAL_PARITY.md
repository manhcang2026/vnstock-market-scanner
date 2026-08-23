# CCC v19.1.2 — Visual Parity Pass

**Date:** 2026-08-23  
**Branch:** `feature/user-auth-foundation`  
**Scope:** visual parity only, on top of the consolidated v19.1 runtime.

## Goal

Restore the approved pre-refactor CCC visual language without restoring the Alpha runtime stack.

Reference used:
- compact 56px top bar;
- labeled left sidebar;
- full-width working area;
- compact page heading;
- MAIN + RIGHT RAIL desktop layout;
- restrained neutral financial palette;
- 6–12px radii and compact table density;
- old Overview hierarchy: KPI strip -> tracked-list table -> market context rail.

## What changed

- Restored compact 56px top bar and old brand proportions.
- Restored neutral navy/white financial palette in Light/Dark.
- Restored compact 210px desktop sidebar and neutral active state.
- Increased usable working width to match the former wide desktop shell.
- Restored compact page headings instead of large marketing-style headings.
- Restored smaller panel radii, borders and dense spacing.
- Overview KPI strip now visually matches the former compact four-card band.
- Overview table restored to five information columns:
  Company / Price / Volume / Highlights / CCC.
- Signal rail again displays `Hội tụ mạnh` / `Đang hội tụ` labels when applicable.
- Right rail market-context card restored to compact stacked quote rows.
- Mobile remains card-first and responsive.
- No Alpha JS/CSS is loaded.
- No MutationObserver, repair loop or additional patch runtime was added.
- No backend/database change.

## Runtime

- `data-v19.1.2.js`: same data adapter behavior as v19.1.1.
- `app-v19.1.2.js`: small markup changes needed for visual parity only.
- `styles-v19.1.2.css`: single consolidated stylesheet, still the only style owner.

## Important

This pass does NOT implement Phase 3 Scanner functionality. `/danh-sach` remains the current consolidated safe state until the next product phase.

## QA focus

1. Compare Overview at 1440/1920 desktop against the approved pre-refactor screenshots.
2. Verify header is compact and stable.
3. Verify sidebar remains labeled and stable.
4. Verify right rail is visible and aligned.
5. Verify KPI band/table density resembles the old staging UI.
6. Verify Account and Research remain usable after common visual-token changes.
7. Verify Light/Dark and mobile.
8. Confirm there is no flicker and no old Alpha runtime is loaded.
