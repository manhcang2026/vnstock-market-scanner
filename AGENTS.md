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
3. read `docs/architecture/CCC_VPS_CANONICAL_SUPABASE_MIRROR_DECISION_20260924.md`;
4. read only the architecture/product files directly relevant to the task;
5. start from files supplied in the task.

Do not scan the whole repository or Git history merely to rebuild context already supplied.

## 3. Market-data authority

SSI is the only canonical market-data provider for V3.

Never silently mix providers.

Never use OLD Supabase market tables as a fallback.

Missing market data means NULL / unavailable.
Missing data is not zero.

Trust SSI as the provider, but do not make the runtime unnecessarily fragile:
- short transient feed silence should prefer reconnect/recovery over killing the whole system;
- calculation/mirror failures must not stop raw SSI ingest;
- degraded quality must be explicit instead of fabricated.

## 4. Database ownership

### VPS market system — CANONICAL

The VPS is the canonical CCC market-data runtime and long-term infrastructure destination.

Current transition:

`VPS CCC Engine -> SQLite`

Long-term target:

`VPS CCC Engine -> PostgreSQL on VPS`

Do not move the canonical market runtime to NEW Supabase.

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

### NEW Supabase — `ccc-ssi-v2`

The NEW project is a **remote audit mirror only**.

Repository migration files for the mirror belong under:

`supabase/`

The mirror exists for:
- remote inspection/audit;
- troubleshooting;
- comparison of raw vs calculated values;
- signal/state history checks;
- ingest/EOD/data-gap/health inspection.

The mirror is NOT canonical and must never be a production dependency.

Mirror writes must be:
- asynchronous;
- fail-open;
- best-effort;
- retryable;
- unable to roll back or block VPS canonical writes.

Do not expose NEW Supabase directly to frontend/browser code.

Keep the mirror schema portable PostgreSQL.

## 5. Mirror coverage

Mirror data from 01/09/2026 onward as capacity allows.

Preferred coverage:
- live quotes;
- 1-minute bars;
- daily bars;
- reference prices;
- ATO/ATC;
- volume baselines;
- Day RVOL / RVOL15 / RVOL30;
- Price5 / Price15;
- MA-related state;
- stock_state_current;
- signal events;
- ingest/finalize/data-gap/reconciliation/health records.

Historical/event tables append.
Current-state tables upsert.

Supabase capacity problems must never stop the VPS runtime.

## 6. Frontend/API boundary

Browser market-data requests use:

- HTTP `/api/v2/*`
- WebSocket `/api/v2/live`

The frontend must not depend on whether the backend market database is SQLite (transition) or PostgreSQL on VPS (target).

The frontend must not read NEW Supabase mirror tables directly.

Database migration must not require a frontend API-contract rewrite.

## 7. Runtime preservation and hardening

Do not delete useful collector/calculation logic merely because storage is being modernized.

Preserve and review:
- SSI collector normalization;
- market-session logic;
- Day RVOL / RVOL15 / RVOL30;
- Price5 / Price15;
- ATO/ATC;
- baseline logic;
- MA logic.

The 23/09/2026 incident showed that runtime/orchestration can fail even when VPS CPU/RAM/disk are healthy.

Before production reliance:
- eliminate lock-order/deadlock risk;
- keep SSI callback lightweight;
- isolate ingest from heavy calculation/storage work;
- use heartbeat/watchdog that detects “alive but not progressing”;
- reconnect SSI on stale feed;
- prevent duplicate collectors;
- keep data-gap/quality state explicit.

Do not remove existing SQLite files/runtime until PostgreSQL on VPS is proven.

## 8. Operational monitoring

The Product Owner should not be required to understand VPS internals.

Add Telegram operational notifications for important states such as:
- MARKET READY;
- SSI FEED DELAYED;
- SSI RECOVERED;
- COLLECTOR DOWN/HUNG;
- DATABASE ERROR;
- SUPABASE MIRROR DELAYED;
- SUPABASE MIRROR CAPACITY WARNING;
- EOD/finalize failure.

Alerts must be deduplicated/rate-limited to avoid spam.

## 9. Core logic

Do not change RVOL definitions, baseline math, MA logic, auction logic, signal thresholds, entitlement semantics or universe behavior unless explicitly requested.

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
- use broader validation when blast radius justifies it.

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
