# CODEX VISUAL GUARDRAIL — CCC

Before touching `website-next/`, read:

`CCC_ALPHA19_GOLDEN_UI_REFERENCE_v1.0.md`

## Hard rule

**Logic/security/refactor work is NOT permission to redesign the UI.**

The Alpha.19 snapshot at commit:

`c5125051681512378097785e4d0904ac17088cf1`

is the visual baseline, with the Golden Reference corrections.

## Never change without Product Owner approval

- global layout;
- desktop main/right-rail pattern;
- mobile stacking;
- card metric order;
- tab order/labels;
- typography scale;
- spacing/density;
- signal count/colors/rail semantics;
- MA10/MA200 placement;
- Watchlist vs Whole Market information model;
- Research industry mobile selector behavior.

## Three critical corrections over raw Alpha.19

1. Whole Market = basic-only; no CCC/signal UI.
2. Mobile industry selector = horizontal scroll rail.
3. Desktop Stock Detail = center main content + right rail.

## Required visual QA

375 / 768 / 1024 / 1440, Light + Dark.

If a code fix appears to require a visual change, stop and ask the Product Owner first.
