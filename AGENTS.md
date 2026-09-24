# AGENTS.md — Chuyện Chợ Chứng V3

These rules apply to coding/design agents working in this repository.

## 1. Current V3 sources

Active V3 frontend:

`website-v2-react/`

Active SSI/backend runtime:

`services/ssi_realtime_shadow/`

The folder names are historical. Do not rename them unless the current task explicitly requests it.

## 2. Legacy production scanner — PRESERVE

The root legacy scanner is **not** the V3 source of truth, but it is still an active production dependency because the currently deployed legacy websites read market data from the OLD Supabase tables that this scanner updates.

Preserve until the Product Owner explicitly retires it:

- root `src/` scanner/runtime code needed by the old Supabase pipeline;
- `.github/workflows/intraday-scan.yml`;
- `.github/workflows/market-pulse.yml`;
- `.github/workflows/eod-finalize.yml`;
- other directly required legacy scanner workflows/config needed to keep OLD Supabase current.

Do not delete, disable, rename, or repurpose this legacy Supabase scanner merely because V3 SSI is being developed.

`website/` and `website-next/` are not required to remain tracked on `main` solely to keep the deployed legacy websites alive. Their deployed copies may continue running outside this repository. Do not restore those folders unless the Product Owner explicitly asks for the website source to be restored to `main`.

The required compatibility rule is:

`legacy scanner on main -> OLD Supabase -> currently deployed legacy websites`

V3 SSI development must not break that path.

## 3. Read only what is needed

Before coding:

1. read this file;
2. read `docs/workflow/CODEX_BUDGET_MODE.md`;
3. for any SSI/backend/market-data/database/realtime task, read:
   `docs/architecture/CCC_SSI_REALTIME_INGESTION_RECOVERY_RULES_20260924.md`;
4. read only the other architecture/product files directly relevant to the task;
5. start from files supplied in the task.

Do not scan the whole repository or Git history merely to rebuild context already supplied.

## 4. Market-data authority

SSI is the only canonical market-data provider for V3.

Never silently mix providers.

Never use OLD Supabase market tables as a fallback for V3 market data.

Missing market data means NULL / unavailable.
Missing data is not zero.

## 5. V3 realtime data-flow invariant

The locked rule is:

> STORE FIRST — CALCULATE SECOND — QUALITY LAST.

For continuous trading:
- collect SSI WebSocket events continuously;
- build the canonical one-minute bar;
- default minute-finalization grace is 3 seconds after the minute ends;
- late/correction events may update historical minute data later;
- never reject valid historical data merely because the minute was already finalized.

For ATO/ATC:
- persist explicit realtime auction evidence immediately;
- missing price or volume must not cause the whole auction event to be discarded.

Calculation, trust, baseline, signal, mirror, or UI failures must never roll back canonical SSI persistence.

## 6. Database ownership

### VPS market system — CANONICAL

The VPS is the canonical CCC V3 market-data runtime and storage owner.

Current transition:

`VPS CCC Engine -> SQLite`

Long-term target:

`VPS CCC Engine -> PostgreSQL on VPS`

### OLD Supabase

OLD Supabase owns:
- Auth / profiles;
- watchlists;
- plans / subscriptions / VIP / entitlement;
- company / symbol / exchange / industry metadata;
- fundamental / BCTC data;
- legacy market/scanner tables still required by the currently deployed legacy websites until those sites are retired or cut over.

The legacy scanner may continue writing those legacy market tables. This does not make OLD Supabase a V3 market-data fallback.

### NEW Supabase — `ccc-ssi-v2`

NEW Supabase is a remote audit mirror only.

It must never become a production dependency of the canonical VPS collector.

Mirror writes must be:
- asynchronous;
- fail-open;
- best-effort;
- retryable;
- unable to roll back or block VPS canonical writes.

Do not expose NEW Supabase directly to frontend/browser code.

## 7. Frontend/API boundary

V3 browser market-data requests use:

- HTTP `/api/v2/*`
- WebSocket `/api/v2/live`

The V3 frontend must not depend on whether the backend canonical database is currently SQLite or later PostgreSQL on VPS.

Database migration must not require a frontend API-contract rewrite.

## 8. Runtime preservation and cleanup

Do not preserve obsolete reset/replay/proof/probe/staging databases merely because they exist.

But before deleting data:
- identify active service references;
- preserve any realtime-only ATO/ATC evidence that cannot be recovered later;
- preserve canonical/recoverable data until the replacement path is proven.

Do not let cleanup remove the legacy Supabase scanner described in section 2.

## 9. Core logic

Do not change RVOL definitions, baseline math, MA logic, auction logic, signal thresholds, entitlement semantics or universe behavior unless explicitly requested.

The product direction is the full Vietnamese equity market (HOSE, HNX, UPCOM), not a permanent 800-symbol architecture limit.

Production thresholds and proprietary CCC logic remain server-side.

## 10. Security

Never commit:
- database passwords;
- service-role / secret keys;
- SSI credentials;
- private API credentials;
- access tokens.

Frontend may contain only browser-safe publishable configuration.

## 11. Scope lock

When the task provides repository, branch, HEAD/base, folder or file allowlist:
- use that scope;
- do not rediscover the whole project;
- do not edit unrelated files;
- do not perform unrelated refactors.

If an out-of-scope dependency must be changed, explain why.

## 12. Testing

Visual frontend work:
- do not start local server by default;
- do not run browser/screenshot/full-build tests by default;
- Product Owner performs real visual/runtime verification.

Core/backend/database/auth/security work:
- run focused tests;
- prioritize tests proving canonical persistence cannot be blocked by calculation failures;
- use broader validation only when blast radius justifies it.

## 13. Git/deploy

Unless explicitly requested, do not:
- commit;
- push;
- merge;
- rebase;
- switch branch;
- deploy;
- change VPS/production state.

## 14. Completion report

Keep reports short:
1. files changed;
2. main changes;
3. validation;
4. Product Owner/runtime checks still pending;
5. diff stat;
6. necessary out-of-scope changes.

Stop when the requested task is complete.
