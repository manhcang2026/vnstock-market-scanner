# AGENTS.md — Chuyện Chợ Chứng repository instructions

These rules apply to all coding/design agents working in this repository.

## 1. Production frontend source of truth

The current production frontend is:

```text
website/
```

It is a static HawkHost frontend.

Do **not** assume the old React/Lovable `dashboard/` project exists or is production.

The obsolete `dashboard/` frontend was intentionally removed on 2026-08-20.

Before any frontend task, inspect:

- `website/index.html`
- `website/VERSION.txt`
- current versioned JS in `website/assets/`
- current versioned CSS in `website/assets/`

## 2. UI/UX standard

Before modifying user-facing UI, read:

1. `docs/ui-ux/CCC_UIUX_MASTER.md`
2. `docs/ui-ux/CCC_COMPONENT_RULES.md`
3. relevant section in `docs/ui-ux/CCC_PAGE_PATTERNS.md`
4. before completion: `docs/ui-ux/CCC_UIUX_QA_CHECKLIST.md`

CCC UI/UX Design System is authoritative.

## 3. Current production routes

- `/`
- `/danh-sach`
- `/so-sanh-theo-nganh`
- `/sang-loc-co-ban`

Do not delete or silently replace a production route during visual redesign.

## 4. Real frontend data

Current website uses Supabase frontend data including:

- `stock_snapshot`
- `financial_latest`
- `stock_metadata`
- `financial_quarterly`

Do not fabricate production fields.

## 5. Scanner core logic

Current four scanner signals:

- Giá tăng ≥ 3%
- KL ngày ≥ 200% KLTB10
- Trên MA200
- RVOL30 ≥ 200%

MA10 is reference/sort data, not a fifth signal.

A visual redesign must not modify this logic.

## 6. Scanner universe

Frontend actions must never remove a symbol from or stop collection in the backend scanner universe.

Filter/hide/watchlist operations are display/personalization only.

## 7. Fundamental score

Do not normalize an incomplete score to 100 unless the approved business rule explicitly changes.

Show score coverage / points available clearly.

## 8. Light and Dark

Both are production features.

All major UI changes must support and QA both themes.

## 9. Mockup approval gate

For a major visual redesign:

- create PC mockup;
- create mobile mockup;
- include Light/Dark direction;
- obtain Product Owner approval before implementing the major visual change.

## 10. Lovable gate

Lovable is optional.

Never call/use Lovable without explicit Product Owner approval.

A reserve of up to 50 credits exists but is not permission to spend it.

Before using Lovable:

1. propose exact task;
2. explain advantage;
3. estimate credits;
4. wait for approval.

## 11. Secrets

Never place:

- Supabase service-role key;
- database password;
- secret API credentials

inside public frontend source.

Do not replace a publishable frontend key with a privileged secret.

## 12. Deployment/versioning

For a production website release:

- update `website/VERSION.txt`;
- use explicit JS/CSS asset versioning/cache busting;
- commit source to Git before/with deployment;
- keep rollback possible.

Do not make permanent HawkHost-only changes that are absent from Git.

## 13. Completion

A UI task is not complete because it looks good in one screenshot.

Run the relevant items in `docs/ui-ux/CCC_UIUX_QA_CHECKLIST.md`.
