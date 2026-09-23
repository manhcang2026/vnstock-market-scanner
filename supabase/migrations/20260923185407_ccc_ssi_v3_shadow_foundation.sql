create schema if not exists market;
create schema if not exists ops;

comment on schema market is 'CCC V3 SSI-only market data shadow schema. Portable PostgreSQL foundation.';
comment on schema ops is 'CCC V3 ingestion, data-gap, EOD finalization and reconciliation operations.';

create table market.trading_calendar (
    exchange text not null,
    trading_date date not null,
    is_trading_day boolean not null default true,
    provider_status text,
    source text not null default 'SSI',
    first_seen_at timestamptz not null default now(),
    finalized_at timestamptz,
    metadata jsonb not null default '{}'::jsonb,
    primary key (exchange, trading_date)
);

create table market.minute_bars_1m (
    symbol text not null,
    exchange text not null,
    trading_date date not null,
    minute_of_day time without time zone not null,
    minute_start timestamptz not null,
    open numeric(20,6) not null,
    high numeric(20,6) not null,
    low numeric(20,6) not null,
    close numeric(20,6) not null,
    volume bigint not null check (volume >= 0),
    turnover_value numeric(28,4),
    provider_total_volume bigint check (provider_total_volume is null or provider_total_volume >= 0),
    provider_time timestamptz,
    provider_session text,
    source text not null,
    quality_status text not null default 'UNVERIFIED',
    is_partial boolean not null default true,
    is_final boolean not null default false,
    source_meta jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (symbol, trading_date, minute_of_day),
    check (high >= low),
    check (open >= 0 and high >= 0 and low >= 0 and close >= 0)
);

create index minute_bars_1m_symbol_time_idx
    on market.minute_bars_1m (symbol, minute_start desc);
create index minute_bars_1m_date_exchange_idx
    on market.minute_bars_1m (trading_date, exchange);
create index minute_bars_1m_same_time_idx
    on market.minute_bars_1m (trading_date, minute_of_day);
create index minute_bars_1m_unfinalized_idx
    on market.minute_bars_1m (trading_date, symbol)
    where is_final = false;

create table market.daily_bars (
    symbol text not null,
    exchange text not null,
    trading_date date not null,
    open numeric(20,6) not null,
    high numeric(20,6) not null,
    low numeric(20,6) not null,
    close numeric(20,6) not null,
    volume bigint not null check (volume >= 0),
    turnover_value numeric(28,4),
    provider_time timestamptz,
    source text not null default 'SSI_DAILY_OHLC',
    quality_status text not null default 'UNVERIFIED',
    is_final boolean not null default false,
    source_meta jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (symbol, trading_date),
    check (high >= low),
    check (open >= 0 and high >= 0 and low >= 0 and close >= 0)
);

create index daily_bars_symbol_date_idx
    on market.daily_bars (symbol, trading_date desc);
create index daily_bars_date_exchange_idx
    on market.daily_bars (trading_date, exchange);

create table market.market_reference_prices (
    symbol text not null,
    exchange text not null,
    trading_date date not null,
    previous_close numeric(20,6),
    ref_price numeric(20,6) not null,
    ceiling_price numeric(20,6),
    floor_price numeric(20,6),
    reference_adjusted boolean not null default false,
    adjustment_factor numeric(20,10),
    adjustment_pct numeric(14,8),
    adjustment_class text not null default 'NONE',
    is_ex_right_date boolean,
    corporate_action_type text,
    signal_paused boolean not null default false,
    signal_pause_reason text,
    source text not null default 'SSI_MASTERDATA',
    quality_status text not null default 'UNVERIFIED',
    source_meta jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (symbol, trading_date),
    check (ref_price >= 0),
    check (previous_close is null or previous_close >= 0),
    check (ceiling_price is null or ceiling_price >= 0),
    check (floor_price is null or floor_price >= 0),
    check (adjustment_class in ('NONE','PRICE_ONLY','STRUCTURAL','UNKNOWN'))
);

create index market_reference_prices_date_adjusted_idx
    on market.market_reference_prices (trading_date, reference_adjusted);
create index market_reference_prices_paused_idx
    on market.market_reference_prices (trading_date, signal_paused)
    where signal_paused = true;

create table market.live_quotes (
    symbol text primary key,
    exchange text not null,
    trading_date date not null,
    last_price numeric(20,6),
    cumulative_volume bigint,
    provider_session text,
    event_time timestamptz,
    provider_time timestamptz,
    source text not null default 'SSI_FASTCONNECT',
    quality_status text not null default 'UNVERIFIED',
    source_meta jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    check (last_price is null or last_price >= 0),
    check (cumulative_volume is null or cumulative_volume >= 0)
);

create index live_quotes_date_exchange_idx
    on market.live_quotes (trading_date, exchange);
create index live_quotes_event_time_idx
    on market.live_quotes (event_time desc);

create table market.auction_sessions (
    symbol text not null,
    exchange text not null,
    trading_date date not null,
    auction_type text not null,
    provider_session text,
    reference_price numeric(20,6),
    pre_auction_price numeric(20,6),
    auction_price numeric(20,6),
    provider_total_volume_start bigint,
    provider_total_volume_end bigint,
    auction_volume bigint,
    auction_volume_share_pct numeric(14,8),
    price_impact_pct numeric(14,8),
    gap_pct numeric(14,8),
    baseline_sessions_used smallint,
    baseline_quality text,
    quality_status text not null default 'UNVERIFIED',
    event_count integer not null default 0,
    first_event_at timestamptz,
    last_event_at timestamptz,
    finalized boolean not null default false,
    source text not null default 'SSI_FASTCONNECT',
    source_meta jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (symbol, trading_date, auction_type),
    check (auction_type in ('ATO','ATC')),
    check (auction_volume is null or auction_volume >= 0),
    check (provider_total_volume_start is null or provider_total_volume_start >= 0),
    check (provider_total_volume_end is null or provider_total_volume_end >= 0),
    check (baseline_sessions_used is null or baseline_sessions_used between 0 and 10)
);

create index auction_sessions_date_type_idx
    on market.auction_sessions (trading_date, auction_type);
create index auction_sessions_symbol_date_idx
    on market.auction_sessions (symbol, trading_date desc);

create table ops.ingest_runs (
    id bigint generated always as identity primary key,
    run_type text not null,
    source text not null,
    trading_date date,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    status text not null default 'RUNNING',
    symbols_attempted integer not null default 0,
    symbols_succeeded integer not null default 0,
    symbols_failed integer not null default 0,
    rows_written bigint not null default 0,
    error_summary jsonb not null default '{}'::jsonb,
    metadata jsonb not null default '{}'::jsonb
);

create index ingest_runs_date_status_idx
    on ops.ingest_runs (trading_date desc, status);

create table ops.data_gaps (
    id bigint generated always as identity primary key,
    symbol text,
    exchange text,
    trading_date date not null,
    minute_of_day time without time zone,
    dataset text not null,
    gap_type text not null,
    status text not null default 'OPEN',
    retry_count integer not null default 0,
    first_detected_at timestamptz not null default now(),
    last_checked_at timestamptz,
    resolved_at timestamptz,
    details jsonb not null default '{}'::jsonb
);

create index data_gaps_open_idx
    on ops.data_gaps (trading_date, dataset, status);
create index data_gaps_symbol_idx
    on ops.data_gaps (symbol, trading_date desc);

create table ops.finalize_runs (
    id bigint generated always as identity primary key,
    trading_date date not null,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    status text not null default 'RUNNING',
    expected_symbols integer not null default 0,
    finalized_symbols integer not null default 0,
    failed_symbols integer not null default 0,
    intraday_rest_status text,
    daily_rest_status text,
    auction_status text,
    baseline_rebuilt boolean not null default false,
    details jsonb not null default '{}'::jsonb
);

create index finalize_runs_date_idx
    on ops.finalize_runs (trading_date desc, started_at desc);

create table ops.daily_reconciliation (
    symbol text not null,
    exchange text not null,
    trading_date date not null,
    minute_volume_sum bigint,
    daily_volume bigint,
    volume_difference bigint,
    volume_difference_pct numeric(14,8),
    reconciliation_status text not null default 'PENDING',
    intraday_final boolean not null default false,
    daily_final boolean not null default false,
    checked_at timestamptz not null default now(),
    details jsonb not null default '{}'::jsonb,
    primary key (symbol, trading_date)
);

create index daily_reconciliation_date_status_idx
    on ops.daily_reconciliation (trading_date, reconciliation_status);

create or replace function ops.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger minute_bars_1m_set_updated_at
before update on market.minute_bars_1m
for each row execute function ops.set_updated_at();

create trigger daily_bars_set_updated_at
before update on market.daily_bars
for each row execute function ops.set_updated_at();

create trigger market_reference_prices_set_updated_at
before update on market.market_reference_prices
for each row execute function ops.set_updated_at();

create trigger live_quotes_set_updated_at
before update on market.live_quotes
for each row execute function ops.set_updated_at();

create trigger auction_sessions_set_updated_at
before update on market.auction_sessions
for each row execute function ops.set_updated_at();

alter table market.trading_calendar enable row level security;
alter table market.minute_bars_1m enable row level security;
alter table market.daily_bars enable row level security;
alter table market.market_reference_prices enable row level security;
alter table market.live_quotes enable row level security;
alter table market.auction_sessions enable row level security;
alter table ops.ingest_runs enable row level security;
alter table ops.data_gaps enable row level security;
alter table ops.finalize_runs enable row level security;
alter table ops.daily_reconciliation enable row level security;

revoke all on schema market from public, anon, authenticated;
revoke all on schema ops from public, anon, authenticated;
revoke all on all tables in schema market from public, anon, authenticated;
revoke all on all tables in schema ops from public, anon, authenticated;
revoke all on all sequences in schema ops from public, anon, authenticated;

grant usage on schema market, ops to service_role;
grant select, insert, update, delete on all tables in schema market to service_role;
grant select, insert, update, delete on all tables in schema ops to service_role;
grant usage, select on all sequences in schema ops to service_role;

alter default privileges in schema market
    grant select, insert, update, delete on tables to service_role;
alter default privileges in schema ops
    grant select, insert, update, delete on tables to service_role;
alter default privileges in schema ops
    grant usage, select on sequences to service_role;
