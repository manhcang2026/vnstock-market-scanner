<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

# CCC UI/UX mandatory instructions

These instructions apply to all work under `dashboard/`.

## Before modifying user-facing UI

Read, in this order:

1. `docs/ui-ux/CCC_UIUX_MASTER.md`
2. `docs/ui-ux/CCC_COMPONENT_RULES.md`
3. the relevant section in `docs/ui-ux/CCC_PAGE_PATTERNS.md`
4. before completion, run through `docs/ui-ux/CCC_UIUX_QA_CHECKLIST.md`

The CCC UI/UX Design System is authoritative for product UI decisions.

## Core rules

- Do not redesign from personal preference.
- Do not introduce arbitrary colors, font sizes, spacing, shadows or component visual languages when a system pattern exists.
- Do not use essential 10–11px text as a default financial-data pattern.
- Do not communicate financial/signal state by color alone.
- Do not invent backend data or functionality in production UI.
- Do not advertise future fields before a real data contract exists.
- Keep scanner terminology understandable to non-specialists.
- Preserve desktop table / mobile decision-card strategy unless the product owner explicitly approves a system change.
- Treat accessibility, data trust and performance as release requirements.
- UI actions affecting display/watchlists must not remove symbols from or stop collection in the backend scanner universe.

## Lovable approval gate

Lovable is optional design/prototyping support.

**Never call or use Lovable automatically.**

Before using Lovable:

1. propose the exact task;
2. explain why Lovable is advantageous;
3. estimate credit usage when practical;
4. wait for explicit product-owner approval.

A reserve of up to 50 Lovable credits exists, but the reserve is not permission to spend them.

## Design-system changes

Do not silently change a LOCKED rule in `CCC_UIUX_MASTER.md`.

A LOCKED rule change requires:

- explicit product-owner approval;
- design-system version update;
- changelog entry;
- review of affected component/page documents.

## Existing production behavior

Preserve real scanner logic while redesigning presentation.

The current core signal model is:

- Giá tăng ≥ 3%
- Khối lượng ngày ≥ 200%
- Trên MA200
- RVOL30 ≥ 200%

Any change to signal definitions is a product/business-logic change, not a visual redesign.

## Completion

A UI change is not complete solely because it builds successfully or looks correct in one screenshot.

It must pass the relevant items in `docs/ui-ux/CCC_UIUX_QA_CHECKLIST.md`.
