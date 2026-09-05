-- Production already applied on 2026-09-05.
-- Purpose: freeze historical Golden Board rows to the signal ruleset active when captured.

alter table public.golden_board_daily
  add column if not exists signal_version text;

update public.golden_board_daily
set signal_version = 'CCC_SIGNAL_V1'
where signal_version is null or btrim(signal_version) = '';

alter table public.golden_board_daily
  alter column signal_version set default 'CCC_SIGNAL_V1';

alter table public.golden_board_daily
  alter column signal_version set not null;

create index if not exists golden_board_daily_signal_version_idx
  on public.golden_board_daily(signal_version, trading_date desc);

comment on column public.golden_board_daily.signal_version is
  'Signal ruleset active when this Golden Board record was first captured. Historical rows remain tagged when later rulesets are introduced.';
