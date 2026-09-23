# CCC SSI V2 — Temporary Market PostgreSQL

This directory is reserved exclusively for migrations and database material
belonging to the NEW Supabase project:

`ccc-ssi-v2`

Purpose:

- temporary PostgreSQL persistence for CCC V3 market data;
- schema and data inspection during stabilization;
- SQL auditing and verification;
- later PostgreSQL-to-PostgreSQL migration to the VPS.

Do not place OLD Supabase Auth, Watchlist, VIP, entitlement, metadata or
fundamental migrations here.

OLD Supabase user-system material belongs under:

`infra/supabase-user-system/`

Do not expose NEW Supabase privileged credentials to browser/frontend code.
