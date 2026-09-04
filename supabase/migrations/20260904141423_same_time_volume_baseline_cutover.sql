create table if not exists public.intraday_volume_baseline_10 (
    symbol text not null,
    exchange text not null,
    time_slot time without time zone not null,
    avg_volume_accumulated_10 numeric,
    historical_sessions smallint not null default 0,
    latest_trading_date date,
    lookback_days smallint not null default 35,
    updated_at timestamp with time zone not null default now(),
    constraint intraday_volume_baseline_10_pkey primary key (symbol, time_slot),
    constraint intraday_volume_baseline_10_exchange_check check (exchange = any (array['HOSE'::text,'HNX'::text,'UPCOM'::text])),
    constraint intraday_volume_baseline_10_sessions_check check (historical_sessions >= 0 and historical_sessions <= 10),
    constraint intraday_volume_baseline_10_lookback_check check (lookback_days > 0)
);

alter table public.intraday_volume_baseline_10 enable row level security;
revoke all on table public.intraday_volume_baseline_10 from public, anon, authenticated;
grant select, insert, update, delete on table public.intraday_volume_baseline_10 to service_role;

create or replace function public.refresh_intraday_volume_baseline_10(p_as_of_date date default current_date)
returns jsonb
language plpgsql
set search_path to ''
as $function$
declare
    v_rows integer := 0;
    v_max_date date;
begin
    if p_as_of_date is null then
        p_as_of_date := current_date;
    end if;

    delete from public.intraday_volume_baseline_10 where symbol is not null;

    with valid_rows as materialized (
        select symbol, exchange, trading_date, time_slot, volume_accumulated
        from public.intraday_snapshots
        where trading_date >= (p_as_of_date - 35)
          and trading_date < p_as_of_date
          and time_slot between time '09:00:00' and time '15:00:00'
          and volume_accumulated is not null
          and coalesce(data_status, 'OK') = 'OK'
    ), ranked as (
        select symbol, exchange, trading_date, time_slot, volume_accumulated,
               row_number() over (partition by symbol, time_slot order by trading_date desc) as rn
        from valid_rows
    ), aggregated as (
        select symbol,
               max(exchange) as exchange,
               time_slot,
               avg(volume_accumulated) as avg_volume_accumulated_10,
               count(*)::smallint as historical_sessions,
               max(trading_date) as latest_trading_date
        from ranked
        where rn <= 10
        group by symbol, time_slot
    )
    insert into public.intraday_volume_baseline_10 (
        symbol, exchange, time_slot, avg_volume_accumulated_10,
        historical_sessions, latest_trading_date, lookback_days, updated_at
    )
    select symbol, exchange, time_slot, avg_volume_accumulated_10,
           historical_sessions, latest_trading_date, 35, now()
    from aggregated;

    get diagnostics v_rows = row_count;
    select max(latest_trading_date) into v_max_date from public.intraday_volume_baseline_10;

    return jsonb_build_object(
        'ok', true,
        'rows', v_rows,
        'latest_trading_date', v_max_date,
        'as_of_date', p_as_of_date
    );
end;
$function$;

revoke all on function public.refresh_intraday_volume_baseline_10(date) from public, anon, authenticated;
grant execute on function public.refresh_intraday_volume_baseline_10(date) to service_role;

create or replace view public.latest_daily_baseline
with (security_invoker = true)
as
with latest as (
    select distinct on (symbol)
        symbol, exchange, trading_date, previous_close,
        ma200, ma200_sessions,
        avg_volume_10 as full_day_avg_volume_10,
        avg_volume_sessions as full_day_avg_volume_sessions,
        source, updated_at, data_status, ma10, ma10_sessions
    from public.daily_baseline
    order by symbol, trading_date desc, updated_at desc nulls last
), clock as (
    select (timezone('Asia/Ho_Chi_Minh', now()))::time as local_time
), slot as (
    select local_time,
           ((local_time between time '09:00:00' and time '11:34:59')
             or (local_time between time '13:00:00' and time '15:04:59')) as in_market_window,
           case
             when local_time > time '11:30:00' and local_time <= time '11:34:59' then time '11:30:00'
             when local_time > time '15:00:00' and local_time <= time '15:04:59' then time '15:00:00'
             else make_time(
                 extract(hour from local_time)::int,
                 (floor(extract(minute from local_time) / 5) * 5)::int,
                 0
             )
           end as current_slot
    from clock
)
select l.symbol, l.exchange, l.trading_date, l.previous_close,
       l.ma200, l.ma200_sessions,
       case when s.in_market_window then v.avg_volume_accumulated_10
            else l.full_day_avg_volume_10 end::numeric as avg_volume_10,
       case when s.in_market_window then v.historical_sessions::integer
            else l.full_day_avg_volume_sessions end::integer as avg_volume_sessions,
       l.source, l.updated_at, l.data_status, l.ma10, l.ma10_sessions
from latest l
cross join slot s
left join public.intraday_volume_baseline_10 v
  on v.symbol = l.symbol
 and v.time_slot = s.current_slot;

comment on view public.latest_daily_baseline is
'Production latest baseline. During market hours avg_volume_10/avg_volume_sessions are same-time cumulative-volume baseline (max 10 prior sessions); outside market hours they retain full-day daily-baseline semantics.';

create extension if not exists pg_cron;

do $do$
begin
    if not exists (
        select 1 from cron.job
        where jobname = 'refresh-same-time-volume-baseline-eod'
    ) then
        perform cron.schedule(
            'refresh-same-time-volume-baseline-eod',
            '10 9 * * 1-5',
            $cron$select public.refresh_intraday_volume_baseline_10((timezone('Asia/Ho_Chi_Minh', now())::date + 1));$cron$
        );
    end if;
end
$do$;

notify pgrst, 'reload schema';
