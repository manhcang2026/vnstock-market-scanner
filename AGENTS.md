# AGENTS.md — Chuyện Chợ Chứng repository instructions

These rules apply to coding/design agents working in this repository.

## 1. Read this first

Use a cost-conscious workflow.

Before coding, read:

- `docs/workflow/CODEX_BUDGET_MODE.md`

Then read only the project documents directly relevant to the current task.

Do not scan the whole repository just to rebuild context that is already provided in the task.

## 2. Current frontend source for V3 work

For Stock Detail V3 and the current React frontend work, use:

```text
website-v2-react/
```

Do not treat the older `website/` tree as the source of truth for V3 tasks unless the task explicitly says to work there.

For V3 dev/VPS proxy and deployment behavior, use:

- `website-v2-react/DEPLOY_VPS.md`

For UI work, consult only the relevant files under:

- `docs/ui-ux/`

Common references:
- `docs/ui-ux/CCC_UIUX_MASTER.md`
- `docs/ui-ux/CCC_COMPONENT_RULES.md`
- `docs/ui-ux/CCC_PAGE_PATTERNS.md`

Do not automatically read every UI/UX document for a small scoped task.

## 3. Product and permission boundary

For Stock Detail V3 permissions, use:

- `docs/product/CCC_STOCK_DETAIL_V3_PERMISSION_AMENDMENT_v1.0.md`

Public/free includes chart/quote/live market display and the public indicators described there.

CCC entitlement-protected data includes CCC-specific RVOL, price-engine, auction intelligence, signal state/reasons, protected radar identities, alerts and automation.

Do not move protected engine logic or raw thresholds into browser code.

## 4. Market-data ownership

SSI is the canonical market-data source for the current V2/V3 market pipeline.

Do not silently mix market-data providers or add a Supabase market-data fallback.

Missing data is missing/NULL; missing data is not zero.

Supabase remains appropriate for areas such as Auth, Watchlist, Package/VIP, metadata and fundamentals according to the current product/data contracts.

For changes involving data ownership or canonical history, read the relevant files under `docs/architecture/`, especially:

- `docs/architecture/CCC_DATA_SOURCE_OWNERSHIP.md`
- `docs/architecture/CCC_MARKET_STORAGE_SCHEMA_V2.md`

## 5. Scanner/core logic

Do not change scanner thresholds, RVOL definitions, MA logic, auction logic, baseline math, entitlement semantics or scanner-universe behavior unless the current task explicitly requests that change.

Frontend filter/hide/watchlist behavior must not remove symbols from backend collection.

For core/backend changes, use appropriate targeted tests. Do not reduce validation merely to save Codex usage when data integrity, auth, permissions or calculations are involved.

## 6. Scope lock

When a task supplies a repository, branch, HEAD/base commit, folder or file allowlist:

- trust and use that scope;
- start from the listed files;
- do not rediscover the entire repository;
- do not inspect Git history deeply unless required;
- do not edit outside the allowlist unless a direct dependency makes it necessary.

If an out-of-scope file must be changed, state why in the final report.

Do not perform unrelated refactors.

## 7. Runtime and testing defaults

For visual-only frontend work such as CSS, spacing, responsive sizing, themes or layout:

- do not start the local/dev server by default;
- do not run browser/UI/screenshot tests by default;
- do not run the full test suite or full production build by default;
- use lightweight validation such as `git diff --check` when useful;
- leave real visual/runtime verification to the Product Owner unless the task explicitly requests otherwise.

For frontend logic, run focused validation when available.

For backend/realtime/auth/database/entitlement/scanner work, run the targeted tests needed for safety.

Run full test/build only when justified by blast radius, release/merge readiness, shared configuration/dependency changes, or an explicit task instruction.

## 8. Git and deployment

Unless explicitly requested, do not:

- commit;
- push;
- merge;
- rebase;
- change branches;
- deploy;
- modify production/VPS state.

Do not rewrite migration history.

## 9. Lovable and external mutation

Lovable is a design/reference tool unless the Product Owner explicitly approves a specific write action.

Do not spend Lovable credits, mutate a Lovable project, publish, deploy or change external state without explicit approval for that action.

## 10. Secrets

Never place privileged secrets in public frontend source, including:

- Supabase service-role keys;
- database passwords;
- private API credentials.

## 11. Completion report

Keep completion reports concise.

Report only:

1. files changed;
2. main changes;
3. validation run;
4. what was intentionally not tested and should be tested by the Product Owner;
5. `git diff --stat`;
6. any necessary out-of-scope file and the reason.

Stop when the requested task is complete.
