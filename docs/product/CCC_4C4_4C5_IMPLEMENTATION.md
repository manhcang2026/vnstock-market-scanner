# CCC 4C-4 / 4C-5 Implementation Notes

**Project:** Chuyện Chợ Chứng / Stock Market Scanner  
**Branch:** `feature/user-auth-foundation`  
**Date:** 2026-08-22  
**Status:** Supabase foundation applied; frontend staging integration added.

## 1. Source of truth

Business rules are defined in:

- `docs/product/CCC_WATCHLIST_MEMBERSHIP_RULES.md`

If implementation and business rules conflict, stop and reconcile the business rule first.

## 2. Supabase migrations already applied

- `20260822072337_harden_auth_membership_foundation`
- `20260822072819_create_watchlist_membership_foundation`

These migrations were applied directly to project `vnstock-scanner` (`wevtlkowpbmpdggcfbvn`).

## 3. Security hardening

Applied:

- FREE plan quota corrected to `watchlist_limit = 10`, `change_limit = 3`.
- `public.handle_new_user()` is no longer executable by `anon` or `authenticated` browser roles.
- `public.save_my_profile(...)` remains intentionally callable only by `authenticated` users and validates `auth.uid()` internally.
- `profiles_select_own` and `subscriptions_select_own` RLS policies use `(select auth.uid())`.
- covering indexes added for membership foreign keys.
- frontend Supabase JS is pinned to `2.112.3` in staging HTML.
- staging Apache headers add frame protection, restrictive permissions policy, `nosniff`, referrer policy and a minimal safe CSP for frame/base/object restrictions.

### Intentional Security Advisor warnings

The following browser-facing RPCs use `SECURITY DEFINER` intentionally:

- `public.save_my_profile(...)`
- `public.get_my_watchlist_state()`
- `public.replace_my_watchlist(text[])`

They are callable only by signed-in users and derive the acting user from `auth.uid()`; clients cannot provide another `user_id`.

`public.ccc_resolve_membership(uuid)` and `public.ccc_plan_cycle_boundary(...)` are internal helpers and are not executable by browser roles.

The remaining `Leaked Password Protection Disabled` Auth warning must be enabled in Supabase Dashboard manually.

## 4. Watchlist schema

### `public.user_watchlist`

Current active Watchlist rows per user.

Key properties:

- primary key `(user_id, symbol)`;
- symbol references `public.stock_metadata(symbol)` — current 800-symbol universe;
- authenticated user may SELECT only own rows via RLS;
- browser roles cannot directly INSERT/UPDATE/DELETE;
- writes go through `replace_my_watchlist`.

### `public.watchlist_change_log`

Immutable-style audit trail for ADD/REMOVE activity and quota cost.

Stores:

- user;
- subscription;
- plan;
- symbol;
- action;
- quota cost;
- source/reason;
- timestamp.

## 5. Subscription lifecycle fields

Added to `public.subscriptions`:

- `plan_started_at`
- `anchor_day`
- `quota_cycle_index`
- `setup_window_end`
- `entitlement_end_at`
- `grace_started_at`
- `grace_end_at`
- `upgrade_free_additions_end_at`
- `upgrade_free_peak_count`

`GRACE` is now a supported subscription status.

## 6. Monthly cycle behavior

`public.ccc_plan_cycle_boundary(...)` calculates quota boundaries in `Asia/Ho_Chi_Minh`.

Special day-31 rule verified:

- `31/01 -> 01/03 -> 31/03 -> 01/05`

The anchor remains 31; rolling to day 1 does not permanently change the anchor.

## 7. Membership resolver

`public.ccc_resolve_membership(user_id)` is an internal atomic resolver.

It handles:

- lazy quota-month advancement;
- quota reset without resetting Watchlist;
- setup window expiry;
- upgrade-free window expiry;
- ACTIVE -> GRACE at paid entitlement end;
- GRACE -> EXPIRED after 2 days without payment;
- deletion of paid Watchlist after expired grace;
- creation of a fresh FREE subscription from downgrade time.

During GRACE no new monthly quota is issued before payment.

## 8. Watchlist RPCs

### `get_my_watchlist_state()`

Returns the signed-in user's current:

- plan;
- subscription status;
- Watchlist symbols;
- capacity;
- quota used/remaining;
- next reset;
- setup window;
- upgrade-free window;
- grace deadline.

### `replace_my_watchlist(p_symbols text[])`

Atomic Watchlist replacement.

Rules enforced server-side:

- user identity from `auth.uid()`;
- symbols normalized/deduplicated;
- symbols must exist in `stock_metadata`;
- capacity enforced by plan;
- REMOVE costs 0;
- ADD after free windows costs 1 per symbol;
- xóa rồi ADD lại cùng mã costs 1;
- request exceeding quota fails as a whole;
- FULL has no capacity/quota limit;
- initial 7-day setup is free;
- upgrade free capacity is tracked separately so old Watchlist replacements cannot consume free upgrade slots incorrectly.

## 9. Universe decision

Do **not** validate Watchlist against legacy `public.stocks`.

Current counts at implementation time:

- `stock_metadata`: 800 symbols;
- `stock_snapshot`: 800 symbols;
- legacy `stocks`: only 257 rows / 256 active.

Therefore `stock_metadata(symbol)` is the authoritative FK/validation source for the current scanner universe.

## 10. Frontend staging files

Added:

- `website-next/assets/supabase-bridge-v19.0-alpha.16.js`
- `website-next/assets/watchlist-v19.0-alpha.16.js`
- `website-next/assets/watchlist-v19.0-alpha.16.css`

Updated:

- `website-next/index.html`
- `website-next/VERSION.txt`
- `website-next/.htaccess`

The Watchlist script upgrades the existing placeholder card on `/tai-khoan` without redesigning the rest of 4C-3.4.

UI supports:

- real Watchlist state;
- symbol/company search over `stock_metadata`;
- add/remove locally then save atomically;
- capacity indicator;
- quota indicator;
- next quota reset;
- setup notice;
- upgrade-free notice;
- grace warning;
- backend error mapping.

## 11. Verification already performed

Database transaction tests were run and rolled back so existing user data was not polluted.

Verified:

- initial setup can reach FREE capacity 10 without quota charge;
- REMOVE does not consume quota;
- replacing one symbol after setup increments `change_used` by 1;
- removing then re-adding the same symbol costs 1 ADD quota;
- day-31 cycle behavior matches the locked rule.

## 12. Next work after staging QA

After browser QA of this staging build:

1. apply Watchlist entitlement to scanner views;
2. implement paid plan activation / upgrade / renewal admin flows;
3. connect Email/Telegram alert destinations and entitlement;
4. implement billing/grace notices;
5. derive user-facing Help content from `CCC_WATCHLIST_MEMBERSHIP_RULES.md`.
