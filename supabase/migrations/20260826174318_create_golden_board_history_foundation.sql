create table if not exists public.golden_board_daily (
    trading_date date not null,
    symbol text not null,
    exchange text not null,

    first_hit_slot time without time zone not null,
    last_hit_slot time without time zone not null,
    hit_slots time without time zone[] not null default '{}'::time[],
    hit_count integer not null default 1,
    longest_streak_hits integer not null default 1,

    first_hit_at timestamptz not null,
    last_hit_at timestamptz not null,

    first_price numeric,
    first_price_change_pct numeric,
    first_daily_volume_pct numeric,
    first_ma200_distance_pct numeric,
    first_rvol30_pct numeric,
    first_rvol30_sessions integer,

    last_hit_price numeric,
    last_hit_price_change_pct numeric,
    last_hit_daily_volume_pct numeric,
    last_hit_ma200_distance_pct numeric,
    last_hit_rvol30_pct numeric,
    last_hit_rvol30_sessions integer,

    latest_observed_slot time without time zone,
    latest_observed_at timestamptz,
    latest_signal_count integer,
    latest_price numeric,
    latest_price_change_pct numeric,
    latest_rvol30_pct numeric,
    latest_rvol30_sessions integer,

    rvol30_sum numeric not null default 0,
    max_rvol30_pct numeric,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    primary key (trading_date, symbol),

    constraint golden_board_daily_symbol_check
      check (symbol ~ '^[A-Z0-9]{1,12}$'),
    constraint golden_board_daily_exchange_check
      check (exchange in ('HOSE','HNX','UPCOM')),
    constraint golden_board_daily_hit_count_check
      check (hit_count > 0),
    constraint golden_board_daily_streak_check
      check (longest_streak_hits > 0),
    constraint golden_board_daily_signal_count_check
      check (latest_signal_count is null or latest_signal_count between 0 and 4),
    constraint golden_board_daily_first_price_check
      check (first_price is null or first_price > 0),
    constraint golden_board_daily_last_hit_price_check
      check (last_hit_price is null or last_hit_price > 0),
    constraint golden_board_daily_latest_price_check
      check (latest_price is null or latest_price > 0)
);

create index if not exists golden_board_daily_date_first_hit_idx
  on public.golden_board_daily (trading_date desc, first_hit_slot asc);

create index if not exists golden_board_daily_symbol_date_idx
  on public.golden_board_daily (symbol, trading_date desc);

create or replace function public.ccc_golden_add_slot(
    p_slots time without time zone[],
    p_slot time without time zone
)
returns time without time zone[]
language sql
immutable
set search_path = ''
as $$
  select coalesce(array_agg(x order by x), '{}'::time[])
  from (
    select distinct x
    from unnest(coalesce(p_slots, '{}'::time[]) || array[p_slot]) as t(x)
    where x is not null
  ) s;
$$;

create or replace function public.ccc_golden_longest_streak(
    p_slots time without time zone[]
)
returns integer
language plpgsql
immutable
set search_path = ''
as $$
declare
  v_slots time without time zone[];
  v_i integer;
  v_current integer := 0;
  v_best integer := 0;
begin
  select coalesce(array_agg(x order by x), '{}'::time[])
  into v_slots
  from (
    select distinct x
    from unnest(coalesce(p_slots, '{}'::time[])) as t(x)
    where x is not null
  ) s;

  if cardinality(v_slots) = 0 then
    return 0;
  end if;

  v_current := 1;
  v_best := 1;

  for v_i in 2..cardinality(v_slots) loop
    if v_slots[v_i] - v_slots[v_i - 1] = interval '5 minutes' then
      v_current := v_current + 1;
      v_best := greatest(v_best, v_current);
    else
      v_current := 1;
    end if;
  end loop;

  return v_best;
end;
$$;

create or replace function public.capture_golden_board_from_stock_snapshot()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_is_4of4 boolean;
  v_existing public.golden_board_daily%rowtype;
  v_slots time without time zone[];
  v_is_new_slot boolean;
begin
  if new.trading_date is null or new.time_slot is null or new.symbol is null then
    return new;
  end if;

  v_is_4of4 :=
    coalesce(new.signal_count, 0) = 4
    and coalesce(new.signal_price_3pct, false)
    and coalesce(new.signal_daily_volume_200pct, false)
    and coalesce(new.signal_above_ma200, false)
    and coalesce(new.signal_rvol30_200pct, false);

  select *
  into v_existing
  from public.golden_board_daily
  where trading_date = new.trading_date
    and symbol = new.symbol;

  if not found then
    if not v_is_4of4 then
      return new;
    end if;

    insert into public.golden_board_daily (
      trading_date, symbol, exchange,
      first_hit_slot, last_hit_slot, hit_slots, hit_count, longest_streak_hits,
      first_hit_at, last_hit_at,
      first_price, first_price_change_pct, first_daily_volume_pct,
      first_ma200_distance_pct, first_rvol30_pct, first_rvol30_sessions,
      last_hit_price, last_hit_price_change_pct, last_hit_daily_volume_pct,
      last_hit_ma200_distance_pct, last_hit_rvol30_pct, last_hit_rvol30_sessions,
      latest_observed_slot, latest_observed_at, latest_signal_count,
      latest_price, latest_price_change_pct, latest_rvol30_pct, latest_rvol30_sessions,
      rvol30_sum, max_rvol30_pct, updated_at
    )
    values (
      new.trading_date, new.symbol, new.exchange,
      new.time_slot, new.time_slot, array[new.time_slot]::time[], 1, 1,
      coalesce(new.updated_at, now()), coalesce(new.updated_at, now()),
      new.current_price, new.price_change_pct, new.daily_volume_pct,
      new.ma200_distance_pct, new.rvol30_pct, new.rvol30_sessions,
      new.current_price, new.price_change_pct, new.daily_volume_pct,
      new.ma200_distance_pct, new.rvol30_pct, new.rvol30_sessions,
      new.time_slot, coalesce(new.updated_at, now()), coalesce(new.signal_count, 0),
      new.current_price, new.price_change_pct, new.rvol30_pct, new.rvol30_sessions,
      coalesce(new.rvol30_pct, 0), new.rvol30_pct, now()
    )
    on conflict (trading_date, symbol) do nothing;

    return new;
  end if;

  -- Ignore an older scanner row trying to overwrite the most recent observed state.
  if v_existing.latest_observed_slot is null
     or new.time_slot >= v_existing.latest_observed_slot then
    update public.golden_board_daily
    set
      exchange = new.exchange,
      latest_observed_slot = new.time_slot,
      latest_observed_at = coalesce(new.updated_at, now()),
      latest_signal_count = coalesce(new.signal_count, 0),
      latest_price = new.current_price,
      latest_price_change_pct = new.price_change_pct,
      latest_rvol30_pct = new.rvol30_pct,
      latest_rvol30_sessions = new.rvol30_sessions,
      updated_at = now()
    where trading_date = new.trading_date
      and symbol = new.symbol;
  end if;

  if not v_is_4of4 then
    return new;
  end if;

  v_is_new_slot := not (new.time_slot = any(v_existing.hit_slots));

  if not v_is_new_slot then
    return new;
  end if;

  v_slots := public.ccc_golden_add_slot(v_existing.hit_slots, new.time_slot);

  update public.golden_board_daily
  set
    exchange = new.exchange,
    hit_slots = v_slots,
    hit_count = cardinality(v_slots),
    longest_streak_hits = public.ccc_golden_longest_streak(v_slots),

    first_hit_slot = least(v_existing.first_hit_slot, new.time_slot),
    first_hit_at = case
      when new.time_slot < v_existing.first_hit_slot
        then coalesce(new.updated_at, now())
      else v_existing.first_hit_at
    end,
    first_price = case
      when new.time_slot < v_existing.first_hit_slot then new.current_price
      else v_existing.first_price
    end,
    first_price_change_pct = case
      when new.time_slot < v_existing.first_hit_slot then new.price_change_pct
      else v_existing.first_price_change_pct
    end,
    first_daily_volume_pct = case
      when new.time_slot < v_existing.first_hit_slot then new.daily_volume_pct
      else v_existing.first_daily_volume_pct
    end,
    first_ma200_distance_pct = case
      when new.time_slot < v_existing.first_hit_slot then new.ma200_distance_pct
      else v_existing.first_ma200_distance_pct
    end,
    first_rvol30_pct = case
      when new.time_slot < v_existing.first_hit_slot then new.rvol30_pct
      else v_existing.first_rvol30_pct
    end,
    first_rvol30_sessions = case
      when new.time_slot < v_existing.first_hit_slot then new.rvol30_sessions
      else v_existing.first_rvol30_sessions
    end,

    last_hit_slot = greatest(v_existing.last_hit_slot, new.time_slot),
    last_hit_at = case
      when new.time_slot > v_existing.last_hit_slot
        then coalesce(new.updated_at, now())
      else v_existing.last_hit_at
    end,
    last_hit_price = case
      when new.time_slot > v_existing.last_hit_slot then new.current_price
      else v_existing.last_hit_price
    end,
    last_hit_price_change_pct = case
      when new.time_slot > v_existing.last_hit_slot then new.price_change_pct
      else v_existing.last_hit_price_change_pct
    end,
    last_hit_daily_volume_pct = case
      when new.time_slot > v_existing.last_hit_slot then new.daily_volume_pct
      else v_existing.last_hit_daily_volume_pct
    end,
    last_hit_ma200_distance_pct = case
      when new.time_slot > v_existing.last_hit_slot then new.ma200_distance_pct
      else v_existing.last_hit_ma200_distance_pct
    end,
    last_hit_rvol30_pct = case
      when new.time_slot > v_existing.last_hit_slot then new.rvol30_pct
      else v_existing.last_hit_rvol30_pct
    end,
    last_hit_rvol30_sessions = case
      when new.time_slot > v_existing.last_hit_slot then new.rvol30_sessions
      else v_existing.last_hit_rvol30_sessions
    end,

    rvol30_sum = coalesce(v_existing.rvol30_sum, 0) + coalesce(new.rvol30_pct, 0),
    max_rvol30_pct = case
      when v_existing.max_rvol30_pct is null then new.rvol30_pct
      when new.rvol30_pct is null then v_existing.max_rvol30_pct
      else greatest(v_existing.max_rvol30_pct, new.rvol30_pct)
    end,
    updated_at = now()
  where trading_date = new.trading_date
    and symbol = new.symbol;

  return new;
end;
$$;

drop trigger if exists zz_capture_golden_board_from_stock_snapshot
  on public.stock_snapshot;

create trigger zz_capture_golden_board_from_stock_snapshot
after insert or update on public.stock_snapshot
for each row
execute function public.capture_golden_board_from_stock_snapshot();

alter table public.golden_board_daily enable row level security;

revoke all on table public.golden_board_daily from anon, authenticated;
grant select, insert, update, delete on table public.golden_board_daily to service_role;

create or replace function public.get_public_golden_board(
  p_trading_date date default null
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_market_date date;
  v_target_date date;
  v_total integer := 0;
  v_rows jsonb := '[]'::jsonb;
  v_delay_minutes integer := 20;
begin
  select max(s.trading_date)
  into v_market_date
  from public.stock_snapshot s
  where s.trading_date is not null;

  select coalesce(
    p_trading_date,
    v_market_date,
    (select max(g.trading_date) from public.golden_board_daily g)
  )
  into v_target_date;

  if v_target_date is null then
    return jsonb_build_object(
      'trading_date', null,
      'market_total', 0,
      'teaser_delay_minutes', v_delay_minutes,
      'teaser_rows', '[]'::jsonb
    );
  end if;

  select count(*)::integer
  into v_total
  from public.golden_board_daily g
  where g.trading_date = v_target_date;

  select coalesce(jsonb_agg(q.row_json order by q.first_hit_at desc), '[]'::jsonb)
  into v_rows
  from (
    select
      g.first_hit_at,
      jsonb_build_object(
        'symbol', g.symbol,
        'display_name', coalesce(m.display_name, m.company_name, ''),
        'company_name', coalesce(m.company_name, ''),
        'exchange', g.exchange,
        'first_hit_slot', g.first_hit_slot
      ) as row_json
    from public.golden_board_daily g
    left join public.stock_metadata m on m.symbol = g.symbol
    where g.trading_date = v_target_date
      and (
        v_target_date < coalesce(v_market_date, v_target_date)
        or g.first_hit_at <= now() - make_interval(mins => v_delay_minutes)
      )
    order by g.first_hit_at desc
    limit 2
  ) q;

  return jsonb_build_object(
    'trading_date', v_target_date,
    'market_total', v_total,
    'teaser_delay_minutes', v_delay_minutes,
    'teaser_rows', v_rows
  );
end;
$$;

create or replace function public.get_my_golden_board(
  p_trading_date date default null
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := auth.uid();
  v_sub public.subscriptions%rowtype;
  v_plan public.plans%rowtype;
  v_vip_end timestamptz;
  v_effective_full boolean := false;
  v_market_date date;
  v_target_date date;
  v_market_total integer := 0;
  v_accessible_total integer := 0;
  v_rows jsonb := '[]'::jsonb;
  v_dates jsonb := '[]'::jsonb;
  v_week_start date;
  v_week_end date;
  v_week_rows jsonb := '[]'::jsonb;
begin
  if v_user_id is null then
    raise exception 'AUTH_REQUIRED';
  end if;

  v_sub := public.ccc_resolve_membership(v_user_id);
  if v_sub.id is null then
    raise exception 'NO_CURRENT_SUBSCRIPTION';
  end if;

  select *
  into v_plan
  from public.plans
  where id = v_sub.plan_id;

  v_vip_end := ccc_private.active_vip_day_end(v_user_id);
  v_effective_full :=
    coalesce(v_plan.full_market_access, false) or v_vip_end is not null;

  select max(s.trading_date)
  into v_market_date
  from public.stock_snapshot s
  where s.trading_date is not null;

  select coalesce(
    p_trading_date,
    v_market_date,
    (select max(g.trading_date) from public.golden_board_daily g)
  )
  into v_target_date;

  if v_target_date is null then
    return jsonb_build_object(
      'trading_date', null,
      'market_total', 0,
      'accessible_total', 0,
      'hidden_count', 0,
      'effective_full_market_access', v_effective_full,
      'rows', '[]'::jsonb,
      'available_dates', '[]'::jsonb,
      'week_summary', '[]'::jsonb
    );
  end if;

  select count(*)::integer
  into v_market_total
  from public.golden_board_daily g
  where g.trading_date = v_target_date;

  select count(*)::integer
  into v_accessible_total
  from public.golden_board_daily g
  where g.trading_date = v_target_date
    and (
      v_effective_full
      or exists (
        select 1
        from public.user_watchlist w
        where w.user_id = v_user_id
          and w.symbol = g.symbol
      )
    );

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'symbol', g.symbol,
        'display_name', coalesce(m.display_name, m.company_name, ''),
        'company_name', coalesce(m.company_name, ''),
        'exchange', g.exchange,
        'trading_date', g.trading_date,
        'first_hit_slot', g.first_hit_slot,
        'last_hit_slot', g.last_hit_slot,
        'hit_count', g.hit_count,
        'longest_streak_hits', g.longest_streak_hits,
        'first_price', g.first_price,
        'first_price_change_pct', g.first_price_change_pct,
        'first_daily_volume_pct', g.first_daily_volume_pct,
        'first_ma200_distance_pct', g.first_ma200_distance_pct,
        'first_rvol30_pct', g.first_rvol30_pct,
        'first_rvol30_sessions', g.first_rvol30_sessions,
        'last_hit_price', g.last_hit_price,
        'last_hit_price_change_pct', g.last_hit_price_change_pct,
        'last_hit_daily_volume_pct', g.last_hit_daily_volume_pct,
        'last_hit_ma200_distance_pct', g.last_hit_ma200_distance_pct,
        'last_hit_rvol30_pct', g.last_hit_rvol30_pct,
        'last_hit_rvol30_sessions', g.last_hit_rvol30_sessions,
        'latest_observed_slot', g.latest_observed_slot,
        'latest_signal_count', g.latest_signal_count,
        'latest_price', g.latest_price,
        'latest_price_change_pct', g.latest_price_change_pct,
        'latest_rvol30_pct', g.latest_rvol30_pct,
        'latest_rvol30_sessions', g.latest_rvol30_sessions,
        'still_4of4', coalesce(g.latest_signal_count, 0) = 4,
        'avg_rvol30_on_hits',
          case when g.hit_count > 0 then g.rvol30_sum / g.hit_count else null end,
        'max_rvol30_pct', g.max_rvol30_pct
      )
      order by g.first_hit_slot asc, g.symbol
    ),
    '[]'::jsonb
  )
  into v_rows
  from public.golden_board_daily g
  left join public.stock_metadata m on m.symbol = g.symbol
  where g.trading_date = v_target_date
    and (
      v_effective_full
      or exists (
        select 1
        from public.user_watchlist w
        where w.user_id = v_user_id
          and w.symbol = g.symbol
      )
    );

  select coalesce(jsonb_agg(d order by d desc), '[]'::jsonb)
  into v_dates
  from (
    select distinct g.trading_date as d
    from public.golden_board_daily g
    order by g.trading_date desc
    limit 60
  ) q;

  v_week_start := v_target_date - ((extract(isodow from v_target_date)::integer - 1));
  v_week_end := v_week_start + 4;

  select coalesce(
    jsonb_agg(q.row_json order by q.sessions_count desc, q.best_streak_hits desc, q.total_hits desc, q.avg_rvol30 desc nulls last, q.symbol),
    '[]'::jsonb
  )
  into v_week_rows
  from (
    select
      g.symbol,
      count(*)::integer as sessions_count,
      max(g.longest_streak_hits)::integer as best_streak_hits,
      sum(g.hit_count)::integer as total_hits,
      case
        when sum(g.hit_count) > 0 then sum(g.rvol30_sum) / sum(g.hit_count)
        else null
      end as avg_rvol30,
      jsonb_build_object(
        'symbol', g.symbol,
        'display_name', coalesce(max(m.display_name), max(m.company_name), ''),
        'company_name', coalesce(max(m.company_name), ''),
        'exchange', max(g.exchange),
        'sessions_count', count(*)::integer,
        'best_streak_hits', max(g.longest_streak_hits)::integer,
        'total_hits', sum(g.hit_count)::integer,
        'avg_rvol30',
          case
            when sum(g.hit_count) > 0 then sum(g.rvol30_sum) / sum(g.hit_count)
            else null
          end
      ) as row_json
    from public.golden_board_daily g
    left join public.stock_metadata m on m.symbol = g.symbol
    where g.trading_date between v_week_start and v_week_end
      and (
        v_effective_full
        or exists (
          select 1
          from public.user_watchlist w
          where w.user_id = v_user_id
            and w.symbol = g.symbol
        )
      )
    group by g.symbol
    order by
      count(*) desc,
      max(g.longest_streak_hits) desc,
      sum(g.hit_count) desc,
      case
        when sum(g.hit_count) > 0 then sum(g.rvol30_sum) / sum(g.hit_count)
        else null
      end desc nulls last,
      g.symbol
    limit 10
  ) q;

  return jsonb_build_object(
    'trading_date', v_target_date,
    'market_total', v_market_total,
    'accessible_total', v_accessible_total,
    'hidden_count', greatest(v_market_total - v_accessible_total, 0),
    'effective_full_market_access', v_effective_full,
    'vip_day_active', v_vip_end is not null,
    'vip_day_ends_at', v_vip_end,
    'base_plan_code', v_plan.plan_code,
    'rows', v_rows,
    'available_dates', v_dates,
    'week_start', v_week_start,
    'week_end', v_week_end,
    'week_summary', v_week_rows
  );
end;
$$;

revoke all on function public.ccc_golden_add_slot(time without time zone[], time without time zone) from public, anon, authenticated;
revoke all on function public.ccc_golden_longest_streak(time without time zone[]) from public, anon, authenticated;
revoke all on function public.capture_golden_board_from_stock_snapshot() from public, anon, authenticated;

revoke all on function public.get_public_golden_board(date) from public;
grant execute on function public.get_public_golden_board(date) to anon, authenticated;

revoke all on function public.get_my_golden_board(date) from public;
grant execute on function public.get_my_golden_board(date) to authenticated;

comment on table public.golden_board_daily is
  'CCC Golden Board history. One row per symbol/trading day after the backend first records all four CCC technical signals.';

comment on column public.golden_board_daily.first_rvol30_sessions is
  'RVOL30 session-count metadata at first 4/4 recording. It is never used to block Golden Board admission.';

comment on column public.golden_board_daily.latest_signal_count is
  'Most recent scanner signal_count observed later in the same trading day, including after a symbol falls below 4/4.';

comment on function public.get_public_golden_board(date) is
  'Guest teaser: full daily count plus at most two real symbols delayed by 20 minutes on the active trading day.';

comment on function public.get_my_golden_board(date) is
  'Membership-aware Golden Board history. Full-market/VIP sees all; other members see rows inside their personal watchlist scope.';
