# AGENTS.md — Chuyện Chợ Chứng V3

These rules apply to coding/design agents working in this repository.

## 1. Current V3 sources

Active frontend:

`website-v2-react/`

Active SSI/backend runtime:

`services/ssi_realtime_shadow/`

The folder names are historical. Do not rename them unless the current task explicitly requests it.

Legacy GAS/GSheet, `website/`, `website-next/`, root legacy `src/`, and old GitHub Actions are not V3 sources of truth.

## 2. Read only what is needed

Before coding:

1. read this file;
2. read `docs/workflow/CODEX_BUDGET_MODE.md`;
3. read only the architecture/product files directly relevant to the task;
4. start from files supplied in the task.

Do not scan the whole repository or Git history merely to rebuild context already supplied.

## 3. Market-data authority

SSI is the only canonical market-data provider for V3.

Never silently mix providers.

Never use OLD Supabase market tables as a fallback.

Missing market data means NULL / unavailable.
Missing data is not zero.

## 4. Database ownership

### OLD Supabase

OLD Supabase owns user/account/product-supporting data such as:

- Auth / profiles
- Watchlist
- Plans / packages
- subscriptions / VIP
- entitlement
- symbol/company/exchange/industry metadata
- fundamental/BCTC data

OLD Supabase migration material that remains relevant lives under:

`infra/supabase-user-system/`

### NEW Supabase

The NEW project is:

`ccc-ssi-v2`

It is a temporary PostgreSQL market-data persistence and validation environment for V3.

Repository migration files for NEW belong under:

`supabase/`

Do not place OLD Supabase migrations in `supabase/`.

Do not expose NEW Supabase directly to frontend/browser code.

The NEW database must remain portable PostgreSQL so it can later migrate to VPS PostgreSQL.

## 5. Frontend/API boundary

Browser market-data requests use:

- HTTP `/api/v2/*`
- WebSocket `/api/v2/live`

The frontend must not depend on whether the backend market database is currently Supabase PostgreSQL or VPS PostgreSQL.

Database migration must not require a frontend API-contract rewrite.

## 6. Runtime preservation

The current VPS REST/WebSocket/chart runtime is already in use.

Do not delete or replace current SQLite/storage/runtime code merely because a new PostgreSQL layer is being designed.

Migration must be staged:

1. preserve working runtime;
2. build and validate NEW PostgreSQL persistence;
3. switch backend storage safely;
4. verify API/WS/chart behavior;
5. remove obsolete runtime storage only after cutover is proven.

## 7. Core logic

Do not change RVOL definitions, baseline math, MA logic, auction logic, signal thresholds, entitlement semantics or universe behavior unless explicitly requested.

Production thresholds and proprietary CCC logic remain server-side.

## 8. Security

Never commit:

- database passwords;
- service-role / secret keys;
- SSI credentials;
- private API credentials;
- access tokens.

Frontend may contain only browser-safe publishable configuration.

## 9. Scope lock

When the task provides repository, branch, HEAD/base, folder or file allowlist:

- use that scope;
- do not rediscover the whole project;
- do not edit unrelated files;
- do not perform unrelated refactors.

If an out-of-scope dependency must be changed, explain why.

## 10. Testing

Visual frontend work:
- do not start local server by default;
- do not run browser/screenshot/full-build tests by default;
- Product Owner performs real visual/runtime verification.

Core/backend/database/auth/security work:
- run focused tests;
- use broader validation when blast radius justifies it.

## 11. Git/deploy

Unless explicitly requested, do not:

- commit;
- push;
- merge;
- rebase;
- switch branch;
- deploy;
- change VPS/production state.

## 12. Completion report

Keep reports short:

1. files changed;
2. main changes;
3. validation;
4. Product Owner/runtime checks still pending;
5. diff stat;
6. necessary out-of-scope changes.

Stop when the requested task is complete.
