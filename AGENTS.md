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

For the approved Phase 1 implementation, also read:

- `docs/ui-ux/CCC_LOVABLE_PHASE1_DESIGN_REFERENCE_v1.0.md`
- `docs/ui-ux/CCC_PHASE1_DESIGN_PORT_CONTRACT_v1.0.md`

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

Lovable Phase 1 is a design reference only, not production/runtime source or implementation architecture.

Never call/use Lovable without explicit Product Owner approval.

A reserve of up to 50 credits exists but is not permission to spend it.

Before using Lovable:

1. propose exact task;
2. explain advantage;
3. estimate credits;
4. wait for approval.

## LOVABLE ACCESS POLICY — HARD GATE

For this repository, Lovable is an external DESIGN REFERENCE.

DEFAULT POLICY:

Lovable access is READ-ONLY unless the Product Owner explicitly approves a specific write action in the current conversation.

### READ-ONLY ALLOWED WITHOUT NEW APPROVAL

Only for inspecting the already-approved Phase 1 reference:

- `get_project`
- `list_files`
- `read_file`
- `list_messages`
- `get_message`
- `list_edits`
- `get_diff`
- `get_project_knowledge`
- `get_workspace_knowledge`

These actions may only be used to extract/reference existing Lovable data.

### FORBIDDEN WITHOUT EXPLICIT PRODUCT OWNER APPROVAL

Never perform any Lovable action that can create, edit, mutate, publish, deploy, configure, upload, delete, connect, provision or otherwise change Lovable state unless the Product Owner explicitly approves THAT action.

This includes, but is not limited to:

- `send_message`
- `create_project`
- deploy / publish actions
- `set_project_knowledge`
- `set_workspace_knowledge`
- `enable_database`
- database `INSERT` / `UPDATE` / `DELETE` / DDL
- project visibility changes
- connector changes
- workspace/project skill updates
- uploads
- edits
- deletes
- any future Lovable tool with write/mutation semantics

IMPORTANT:

- Plugin presence is NOT permission to write.
- Previous approval for a different Lovable action is NOT reusable.
- Previous Phase 1 approval is NOT permission for future writes.
- Available Lovable credits are NOT permission to spend them.
- Plan mode is NOT automatically read-only if the action can modify Lovable.
- Never use `send_message` merely to inspect or analyze the project.
- Never ask Lovable itself to perform extraction when read tools can retrieve the data.
- If uncertain whether an action is read-only, treat it as WRITE and STOP.

### REQUIRED WRITE APPROVAL

Before any Lovable write action:

1. Explain exactly what Lovable action is proposed.
2. Explain what it will change.
3. Wait for explicit Product Owner approval in the current conversation.
4. Perform only the specifically approved action.

If approval is absent:

STOP and do not call the write action.

### PHASE 1 EXTRACTION SPECIAL RULE

For Lovable Phase 1 extraction:

READ existing source/files/messages only.

Do NOT:

- send prompts/messages to Lovable
- request Lovable to redesign anything
- modify code
- modify knowledge
- deploy
- publish
- connect backend
- use Lovable credits

The extraction exists only to transfer the already-approved Phase 1 design reference into this repository.

## UI/UX PRO MAX SKILL — SUPPORTING REFERENCE ONLY

This repository may use the local UI/UX Pro Max skill under `.agent/`.

The skill is a supporting design-intelligence tool only.

It MUST NOT override:

1. explicit Product Owner decisions;
2. `CCC_PHASE1_DESIGN_PORT_CONTRACT_v1.0.md`;
3. `CCC_LOVABLE_PHASE1_DESIGN_REFERENCE_v1.0.md`;
4. `CCC_UIUX_MASTER.md`;
5. `CCC_COMPONENT_RULES.md`;
6. `CCC_PAGE_PATTERNS.md`.

Use the skill to improve implementation quality, accessibility, responsive behavior, spacing, typography, usability and visual polish.

Do NOT use the skill to reinterpret locked product rules, change the approved Phase 1 design direction, introduce a new design language, or redesign pages from personal preference.

When the skill conflicts with a locked CCC rule:

CCC rules win.

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
