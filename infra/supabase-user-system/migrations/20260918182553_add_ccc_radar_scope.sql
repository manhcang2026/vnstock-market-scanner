create or replace function public.get_my_technical_scope()
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_profile_status text;
  v_sub public.subscriptions%rowtype;
  v_plan public.plans%rowtype;
  v_vip_end timestamptz;
  v_effective_full boolean := false;
  v_allowed_symbols text[] := array[]::text[];
begin
  if v_user_id is null then
    raise exception 'AUTH_REQUIRED';
  end if;

  select p.status into v_profile_status
  from public.profiles p
  where p.id = v_user_id;

  if coalesce(v_profile_status, '') <> 'ACTIVE' then
    return jsonb_build_object(
      'effective_full_market_access', false,
      'vip_day_active', false,
      'allowed_symbols', to_jsonb(v_allowed_symbols),
      'subscription_status', null,
      'plan_code', null,
      'reason', 'ACCOUNT_INACTIVE'
    );
  end if;

  v_sub := public.ccc_resolve_membership(v_user_id);
  if v_sub.id is null then
    return jsonb_build_object(
      'effective_full_market_access', false,
      'vip_day_active', false,
      'allowed_symbols', to_jsonb(v_allowed_symbols),
      'subscription_status', null,
      'plan_code', null,
      'reason', 'NO_SUBSCRIPTION'
    );
  end if;

  select * into v_plan
  from public.plans
  where id = v_sub.plan_id;

  if v_plan.id is null or v_sub.status = 'SUSPENDED' then
    return jsonb_build_object(
      'effective_full_market_access', false,
      'vip_day_active', false,
      'allowed_symbols', to_jsonb(v_allowed_symbols),
      'subscription_status', v_sub.status,
      'plan_code', v_plan.plan_code,
      'reason', case when v_plan.id is null then 'PLAN_NOT_FOUND' else 'SUBSCRIPTION_SUSPENDED' end
    );
  end if;

  v_vip_end := ccc_private.active_vip_day_end(v_user_id);
  v_effective_full := coalesce(v_plan.full_market_access, false) or v_vip_end is not null;

  if not v_effective_full then
    select coalesce(array_agg(upper(w.symbol) order by upper(w.symbol)), array[]::text[])
      into v_allowed_symbols
    from public.user_watchlist w
    where w.user_id = v_user_id
      and coalesce(w.base_active, false);
  end if;

  return jsonb_build_object(
    'effective_full_market_access', v_effective_full,
    'vip_day_active', v_vip_end is not null,
    'vip_day_ends_at', v_vip_end,
    'allowed_symbols', to_jsonb(v_allowed_symbols),
    'subscription_status', v_sub.status,
    'plan_code', v_plan.plan_code,
    'reason', case
      when coalesce(v_plan.full_market_access, false) then 'FULL_MARKET'
      when v_vip_end is not null then 'VIP_ACCESS'
      else 'WATCHLIST_SCOPE'
    end
  );
end;
$$;

revoke all on function public.get_my_technical_scope() from public;
revoke all on function public.get_my_technical_scope() from anon;
grant execute on function public.get_my_technical_scope() to authenticated;
