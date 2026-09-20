# CCC Codex Budget Mode

**Purpose:** reduce unnecessary Codex context, commands and test cycles while preserving engineering quality.

The normal CCC workflow is:

```text
Product Owner describes issue
        ↓
ChatGPT analyzes and narrows scope
        ↓
Codex edits a small, explicit scope
        ↓
ChatGPT reviews code/diff
        ↓
Product Owner tests the real runtime/UI
```

This document defines the default execution behavior for Codex tasks in this repository.

## 1. Core rule

Prefer the smallest amount of repository reading and validation that is sufficient to complete the task safely.

Do not spend context or compute on work that does not materially improve confidence.

This is not permission to skip necessary engineering checks for high-risk changes.

## 2. Task startup

When the task already provides repository path, branch, current HEAD/base commit, exact component/module, file allowlist, error location, screenshot or concrete defect, use that information directly.

Default order:

1. Read root `AGENTS.md`.
2. Read this file.
3. Open the files listed by the task.
4. Open additional files only when a direct dependency requires them.
5. Make the change.

Avoid broad repository exploration.

## 3. Scope Lock

A task may include:

```text
SCOPE LOCK:
- file A
- file B
- file C
```

Treat this as an allowlist whenever practical.

- Do not scan the whole repository.
- Do not open many adjacent files merely to understand the project.
- Read an out-of-scope file only when a direct dependency or contract requires it.
- Do not refactor unrelated code.
- Do not fix unrelated warnings.
- Do not rename/reorganize modules unless requested.
- If an out-of-scope file must be edited, explain why in the final report.

## 4. Frontend visual work

Examples: CSS, spacing, font size, mobile layout, chart sizing, responsive breakpoints, dark/light fixes, toolbar/button dimensions and cosmetic alignment.

Do not automatically run:

```text
npm run dev
vite
npm start
browser test
screenshot test
full test suite
full production build
```

The Product Owner performs the real visual/runtime check.

Use lightweight static validation when helpful, for example:

```bash
git diff --check
```

If the visual change also modifies runtime logic, upgrade validation to the frontend-logic level.

## 5. Frontend logic work

Examples: state, filtering, formatter logic, permission rendering, data mapping, WebSocket behavior, request/auth behavior and interaction logic.

Prefer focused tests for the changed behavior and focused lint/type validation when available.

Do not run the entire suite merely “to be safe” unless the change has broad impact.

## 6. High-risk/core work

Do not aggressively cut validation for:

- SSI realtime;
- canonical market history;
- scanner calculations;
- RVOL/baseline logic;
- MA logic;
- ATO/ATC logic;
- auth;
- entitlement/VIP;
- Supabase data contracts;
- database/storage;
- migrations;
- payment/billing;
- scheduled/finalization jobs;
- security-sensitive code.

For these areas:

1. run focused tests for the changed behavior;
2. include regression cases for the relevant bug/contract;
3. run broader/full validation when blast radius justifies it.

Saving Codex usage must never take priority over correctness of data, authorization or money-related behavior.

## 7. When full test/build is justified

Full validation is appropriate when:

- shared/core logic changes;
- a shared module affects many features;
- dependency/config/build settings change;
- auth/access-control changes have broad reach;
- database schema/migration changes;
- a large branch is about to merge;
- a release/deploy checkpoint is being prepared;
- focused tests cannot provide adequate confidence;
- the current task explicitly requests it.

A small CSS change is not, by itself, a reason to run a full suite/build.

## 8. Local/dev server policy

Default: do not start it.

Do not start a local server unless runtime verification is specifically needed or explicitly requested.

This includes:

```bash
npm run dev
npm start
vite
next dev
uvicorn ...
python app.py
```

For frontend visual work, the Product Owner is the primary runtime/UI tester.

## 9. Git policy

Unless the task explicitly requests an action, do not:

- commit;
- push;
- merge;
- rebase;
- switch branches;
- deploy;
- modify remote or production state.

Read-only Git commands are allowed when needed.

If branch/HEAD/base are already supplied, avoid unnecessary Git-history exploration.

## 10. Keep command count low

Before running a command, ask whether its result is needed to complete or validate the current task.

Prefer one focused command over multiple exploratory commands.

Avoid repeated `git status`, full-directory listings, whole-repo searches and repeated test/build cycles when nothing relevant changed.

After a failed validation, fix the specific cause and rerun the smallest affected check first.

## 11. Documentation reading budget

Do not read every document under `docs/` for every task.

Choose the relevant category:

- `docs/architecture/` — data/core/runtime/storage architecture;
- `docs/product/` — product contracts, permissions, membership/watchlist;
- `docs/ui-ux/` — design system and UI rules;
- `docs/workflow/` — agent/workflow operating rules.

If the task prompt provides a newer explicit product decision, follow the current task and note any conflict with older documentation rather than loading many old documents.

## 12. Final report budget

Keep the final report short:

```text
Files changed
- ...

Main changes
- ...

Validation
- ...

Not tested
- Product Owner runtime/UI check: pending

git diff --stat
...

Out-of-scope
- None
```

Do not produce a long narrative of every exploratory step.

## 13. Recommended prompt template

```text
Repository:
D:\github\vnstock-market-scanner

Branch:
<branch>

Current HEAD:
<sha if useful>

TASK:
<specific task>

SCOPE LOCK:
Read/edit only if possible:
- <file 1>
- <file 2>
- <file 3>

Do not scan the whole repository unless a direct dependency requires it.
Do not refactor outside this task.
Do not commit/push/deploy unless explicitly requested.

VALIDATION:
- Do not start the local/dev server.
- Do not run browser/UI tests for visual-only changes.
- Do not run full test/full build unless the change justifies it.
- Run only focused validation needed for this change.
- `git diff --check` is sufficient for a pure visual/CSS task unless another issue is found.

After completion report only:
1. files changed;
2. main changes;
3. validation run;
4. not tested / Product Owner runtime check;
5. git diff --stat;
6. reason for any out-of-scope file.

Stop after the requested task is complete.
```

## 14. Priority order

If instructions conflict, use this order:

1. explicit instruction in the current task;
2. root `AGENTS.md`;
3. this workflow document;
4. relevant current product/architecture/UI documents;
5. older historical notes.

For security, authorization, data integrity and migrations, choose the safer validation path even if it costs more Codex usage.
