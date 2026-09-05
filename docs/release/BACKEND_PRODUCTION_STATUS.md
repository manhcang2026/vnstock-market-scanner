# Backend production status — CCC v19.12.0

These backend changes are already live in Supabase production. Do **not** run them manually again just to deploy the website.

- `20260904211327_vip_day_unlimited_watchlist_and_legacy_plan_hide`
  - VIP DAY (including Launch Free VIP) = full-market technical access + unlimited saved Watchlist while active.
  - FULL = full-market technical access + unlimited Watchlist.
  - When VIP/FULL ends, saved symbols are retained; symbols beyond the base-plan technical entitlement become locked instead of being deleted.
  - BASIC / PLUS / PRO remain resolvable for existing subscriptions but are hidden from new public catalog reads.
- `20260904213653_golden_board_signal_version_v1`
  - Existing Golden Board history is tagged `CCC_SIGNAL_V1`.
  - New Golden Board rows default to `CCC_SIGNAL_V1` until a future Signal V2 cutover changes the default.
- `20260904213703_golden_board_expose_signal_version`
  - `get_my_golden_board()` exposes `signal_version` per historical row.
- Same-Time VOL10 cutover is already live separately; the frontend release only changes terminology/help text.

The two Golden Board migration files are included in this release bundle so Git history can catch up with production. The larger VIP/Watchlist migration was already applied directly to production and is recorded by Supabase migration history; this bundle does not ask the operator to rerun it.
