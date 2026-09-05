-- Applied to production on 2026-09-05.
-- get_my_golden_board calls ccc_resolve_membership(), which may SELECT ... FOR UPDATE
-- and update subscription state. Therefore the wrapper cannot be STABLE/read-only.
alter function public.get_my_golden_board(date) volatile;

comment on function public.get_my_golden_board(date) is
  'Membership-aware Golden Board history. VOLATILE because membership resolution may lock or update subscription state; full-market/VIP sees all and scoped members see active watchlist rows.';
