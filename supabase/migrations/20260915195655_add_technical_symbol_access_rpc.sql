create or replace function public.get_my_technical_access(p_symbol text)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_symbol text := upper(btrim(coalesce(p_symbol, '')));
  v_profile_status text;
  v_sub public.subscriptions%rowtype;
  v_plan public.plans%rowtype;
  v_vip_end timestamptz;
  v_effective_full boolean := false;
  v_base_active boolean := false;
  v_allowed boolean := false;
  v_reason text := 'OUTSIDE_ENTITLEMENT';
begin
  if v_user_id is null then
    raise exception 'AUTH_REQUIRED';
  end if;

  if v_symbol !~ '^[A-Z0-9]{2,12}$' then
    raise exception 'INVALID_SYMBOL';
  end if;

  if not exists (
    select 1 from public.stock_metadata m where m.symbol = v_symbol
  ) then
    return jsonb_build_object(
      'symbol', v_symbol,
      'technical_allowed', false,
      'reason', 'UNKNOWN_SYMBOL'
    );
  end if;

  select p.status into v_profile_status
  from public.profiles p
  where p.id = v_user_id;

  if coalesce(v_profile_status, '') <> 'ACTIVE' then
    return jsonb_build_object(
      'symbol', v_symbol,
      'technical_allowed', false,
      'reason', 'ACCOUNT_INACTIVE'
    );
  end if;

  v_sub := public.ccc_resolve_membership(v_user_id);
  if v_sub.id is null then
    return jsonb_build_object(
      'symbol', v_symbol,
      'technical_allowed', false,
      'reason', 'NO_SUBSCRIPTION'
    );
  end if;

  select * into v_plan
  from public.plans
  where id = v_sub.plan_id;

  if v_plan.id is null then
    return jsonb_build_object(
      'symbol', v_symbol,
      'technical_allowed', false,
      'reason', 'PLAN_NOT_FOUND'
    );
  end if;

  if v_sub.status = 'SUSPENDED' then
    return jsonb_build_object(
      'symbol', v_symbol,
      'technical_allowed', false,
      'reason', 'SUBSCRIPTION_SUSPENDED',
      'subscription_status', v_sub.status,
      'plan_code', v_plan.plan_code,
      'effective_full_market_access', false,
      'vip_day_active', false
    );
  end if;

  v_vip_end := ccc_private.active_vip_day_end(v_user_id);
  v_effective_full := coalesce(v_plan.full_market_access, false) or v_vip_end is not null;

  if not v_effective_full then
    select coalesce(w.base_active, false)
      into v_base_active
    from public.user_watchlist w
    where w.user_id = v_user_id
      and w.symbol = v_symbol;
    v_base_active := coalesce(v_base_active, false);
  end if;

  v_allowed := v_effective_full or v_base_active;

  if v_allowed then
    if coalesce(v_plan.full_market_access, false) then
      v_reason := 'FULL_MARKET';
    elsif v_vip_end is not null then
      v_reason := 'VIP_ACCESS';
    else
      v_reason := 'WATCHLIST_ENTITLED';
    end if;
  else
    v_reason := 'OUTSIDE_ENTITLEMENT';
  end if;

  return jsonb_build_object(
    'symbol', v_symbol,
    'technical_allowed', v_allowed,
    'reason', v_reason,
    'subscription_status', v_sub.status,
    'plan_code', v_plan.plan_code,
    'effective_full_market_access', v_effective_full,
    'vip_day_active', v_vip_end is not null,
    'vip_day_ends_at', v_vip_end
  );
end;
$$;

revoke all on function public.get_my_technical_access(text) from public;
revoke all on function public.get_my_technical_access(text) from anon;
grant execute on function public.get_my_technical_access(text) to authenticated;
