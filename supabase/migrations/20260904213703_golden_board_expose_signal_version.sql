-- Production already applied on 2026-09-05.
-- Adds signal_version to authenticated Golden Board row payloads.

do $do$
declare
  v_def text;
  v_new text;
begin
  select pg_get_functiondef('public.get_my_golden_board(date)'::regprocedure) into v_def;
  v_new := v_def;
  if position($needle$'trading_date', g.trading_date,$needle$ in v_new) = 0 then
    raise exception 'GOLDEN_BOARD_RPC_PATCH_MARKER_NOT_FOUND';
  end if;
  v_new := replace(
    v_new,
    $needle$'trading_date', g.trading_date,$needle$,
    $replacement$'trading_date', g.trading_date,
        'signal_version', g.signal_version,$replacement$
  );
  execute v_new;
end;
$do$;
