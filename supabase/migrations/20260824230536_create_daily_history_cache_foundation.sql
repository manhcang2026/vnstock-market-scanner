create table if not exists public.daily_history (
    symbol text not null,
    exchange text not null,
    trading_date date not null,
    close numeric not null check (close > 0),
    volume numeric not null check (volume >= 0),
    source text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (symbol, trading_date)
);

create index if not exists daily_history_trading_date_idx
    on public.daily_history (trading_date desc);

create table if not exists public.daily_history_sync_state (
    symbol text primary key,
    exchange text not null,
    target_sessions smallint not null default 250 check (target_sessions > 0),
    sessions_loaded smallint not null default 0 check (sessions_loaded >= 0),
    oldest_trading_date date,
    latest_trading_date date,
    history_exclusive_date date,
    source text,
    status text not null default 'PENDING'
        check (status in ('PENDING', 'RUNNING', 'COMPLETE', 'ERROR')),
    last_error text,
    last_run_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz not null default now()
);

alter table public.daily_history enable row level security;
alter table public.daily_history_sync_state enable row level security;

revoke all on table public.daily_history from anon, authenticated;
revoke all on table public.daily_history_sync_state from anon, authenticated;

grant select, insert, update, delete on table public.daily_history to service_role;
grant select, insert, update, delete on table public.daily_history_sync_state to service_role;

comment on table public.daily_history is
    'Backend-only daily OHLC-lite cache for scanner calculations. Stores one completed trading session per symbol using close and volume.';
comment on table public.daily_history_sync_state is
    'Backend-only checkpoint/resume state for daily_history backfill and incremental sync.';
