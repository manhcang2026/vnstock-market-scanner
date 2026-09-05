-- Optional rollback helper. Do not run unless you intentionally want
-- to restore the old full-day VOL10 behavior.

begin;

create or replace view public.latest_daily_baseline
with (security_invoker = true)
as
select distinct on (symbol)
    symbol,
    exchange,
    trading_date,
    previous_close,
    ma200,
    ma200_sessions,
    avg_volume_10,
    avg_volume_sessions,
    source,
    updated_at,
    data_status,
    ma10,
    ma10_sessions
from public.daily_baseline
order by symbol, trading_date desc, updated_at desc nulls last;

notify pgrst, 'reload schema';

commit;

do $$
declare
    v_jobid bigint;
begin
    select jobid into v_jobid
    from cron.job
    where jobname = 'refresh-same-time-volume-baseline-eod';

    if v_jobid is not null then
        perform cron.unschedule(v_jobid);
    end if;
end $$;
