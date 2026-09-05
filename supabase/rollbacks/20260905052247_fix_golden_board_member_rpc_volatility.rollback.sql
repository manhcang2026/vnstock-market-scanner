-- Emergency rollback only. Reverting to STABLE will reintroduce the read-only
-- transaction failure while ccc_resolve_membership() uses SELECT FOR UPDATE.
alter function public.get_my_golden_board(date) stable;
