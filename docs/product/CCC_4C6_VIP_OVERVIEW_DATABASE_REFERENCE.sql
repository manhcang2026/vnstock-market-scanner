-- CCC 4C-6 DATABASE REFERENCE
-- Date: 2026-08-22
-- IMPORTANT: the migration described here has ALREADY BEEN APPLIED to production Supabase.
-- Do not blindly execute this reference again.
-- Applied migration name: add_vip_day_and_overview_entitlement

-- PURPOSE
-- 1) authenticated users can search public stock_metadata;
-- 2) VIP_DAY is a temporary 24-hour FULL overlay, never a base-plan replacement;
-- 3) overview market KPI counts are market-wide while detailed technical rows are entitlement-aware;
-- 4) get_my_watchlist_state now returns metadata items in addition to the existing symbols array.

-- NEW SCHEMA
-- ccc_private
-- Browser roles have no schema privileges.

-- NEW TABLE
-- public.temporary_access_passes
--   id uuid PK
--   user_id uuid -> auth.users
--   pass_code = VIP_DAY
--   status ACTIVE|CANCELLED|EXPIRED
--   price_vnd default 100000
--   starts_at timestamptz
--   ends_at timestamptz
--   payment_reference text
--   created_at / updated_at
-- RLS: authenticated can SELECT own rows only; direct browser writes revoked.

-- NEW PRIVATE FUNCTION
-- ccc_private.active_vip_day_end(user_id)
-- Returns the latest currently-active VIP_DAY end timestamp.
-- EXECUTE revoked from public/anon/authenticated.

-- NEW AUTHENTICATED RPC
-- public.get_my_access_context()
-- Returns base plan + effective access context + VIP Day status.
-- VIP does NOT update subscriptions.plan_id, quota, anchor, expiry, or Watchlist.

-- NEW AUTHENTICATED RPC
-- public.get_my_overview_state()
-- Returns:
--   market_counts: four_of_four, three_plus, two_plus, rvol30
--   watchlist_counts: same four KPI counts for the user's DS
--   market_total
--   watchlist_count
--   VIP/effective FULL state
--   rows:
--      FULL or active VIP -> all market technical rows
--      capped plan        -> only user_watchlist technical rows
-- The identities of non-entitled technical rows are NOT enumerated by this RPC.

-- UPDATED RPC
-- public.get_my_watchlist_state()
-- Preserves `symbols` and additionally returns `items`:
--   symbol, display_name, company_name, exchange, added_at, add_source

-- METADATA ACCESS
-- authenticated role granted SELECT on public.stock_metadata with RLS SELECT policy USING(true).
-- stock_metadata is public company identity metadata and is used for type-ahead symbol search.

-- VERIFIED TEST
-- A transaction-only test inserted an active VIP_DAY for an existing user,
-- get_my_overview_state() returned 800 entitled rows, then the transaction was rolled back.

-- SECURITY DEBT BEFORE PRODUCTION LOCKDOWN
-- The legacy website-next shell still performs direct anonymous reads from stock_snapshot.
-- The new Overview entitlement RPC is server-side safe, but production technical-data lockdown
-- requires migrating the remaining legacy technical surfaces away from unrestricted stock_snapshot
-- before revoking that public access. Do not claim the legacy shell is a complete security boundary yet.
