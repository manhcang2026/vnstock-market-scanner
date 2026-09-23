# Chuyện Chợ Chứng — CCC V3

This repository contains the active V3 codebase for Chuyện Chợ Chứng.

## Active source tree

- `website-v2-react/`
  - Current React V3 frontend.
  - Despite the historical folder name, this is the active V3 frontend source.
  - Do not use legacy `website/` or `website-next/`; those versions are preserved in Git history/tags only.

- `services/ssi_realtime_shadow/`
  - Current SSI market-data backend/runtime.
  - Contains SSI collector, market calculations, REST API and WebSocket runtime.
  - Folder name is historical; do not rename it while VPS deployment still depends on it.

- `infra/supabase-user-system/`
  - Migrations/contracts that belong to the existing Supabase user/account system.
  - This is the OLD Supabase project used for Auth, Watchlist, Package/VIP and entitlement.

- `supabase/`
  - Reserved exclusively for the NEW `ccc-ssi-v2` temporary market PostgreSQL project.
  - Never place OLD market migrations or OLD user-system migrations here.

- `tools/financial/`
  - Metadata / industry / fundamental / BCTC utility pipeline for the OLD Supabase project.

## V3 architecture

### Market data

SSI FastConnect is the only canonical market-data provider.

Do not mix providers.
Do not fall back to legacy Supabase market data.
Missing data is NULL / unavailable; missing data is never zero.

Runtime path:

Browser
→ VPS REST `/api/v2/*` and WebSocket `/api/v2/live`
→ SSI collector / CCC engine
→ market persistence

During V3 stabilization, market persistence is the NEW Supabase PostgreSQL project:

`ccc-ssi-v2`

This database is temporary and must remain portable PostgreSQL.

When V3 is stable, schema/data will be migrated PostgreSQL-to-PostgreSQL to the VPS.
Frontend API and WebSocket contracts must not change because of that migration.

### OLD Supabase

The existing Supabase project remains responsible for:

- Auth / sessions
- Profiles
- Watchlist
- Plans / packages
- Subscription / VIP access
- Entitlement
- Stock/company metadata
- Industry metadata
- Fundamental data
- `financial_latest`
- `financial_quarterly`
- BCTC research

It is not a market-data fallback for V3.

### NEW Supabase

`ccc-ssi-v2` is used only as a temporary V3 market database so the database can be inspected, audited and stabilized easily.

Do not expose NEW Supabase directly to browser code.

Do not put its privileged credentials in React/Vite source.

## Frontend

The current frontend is:

`website-v2-react/`

Browser-facing market requests remain same-origin:

- `/api/v2/*`
- `/api/v2/live`

Do not point browser market-data code directly at the NEW Supabase project.

The frontend may continue to use OLD Supabase for its approved user/account/public metadata/fundamental responsibilities.

## Historical code

Legacy GAS/GSheet, V1 frontend, V2 static frontend, old VNStock scanner and old market-data workflows were removed from the active V3 tree.

They remain recoverable from Git history and safety tags.

## Agent workflow

Read:

1. `AGENTS.md`
2. `docs/workflow/CODEX_BUDGET_MODE.md`
3. only the current architecture/product documents relevant to the task

Do not scan historical Git branches unless explicitly requested.
