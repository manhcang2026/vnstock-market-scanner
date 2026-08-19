-- CHỈ KIỂM TRA
with u as (select distinct symbol from public.stock_snapshot)
select count(*) universe_symbols,count(m.symbol) with_metadata,count(f.symbol) with_financial_latest,
count(*) filter(where m.symbol is null) missing_metadata,count(*) filter(where f.symbol is null) missing_financial
from u left join public.stock_metadata m using(symbol) left join public.financial_latest f using(symbol);
select data_status,production_ready,count(*) symbols from public.financial_latest
where symbol in (select symbol from public.stock_snapshot)
group by data_status,production_ready order by data_status,production_ready;
select u.symbol from (select distinct symbol from public.stock_snapshot) u left join public.stock_metadata m using(symbol) where m.symbol is null order by u.symbol;
select u.symbol from (select distinct symbol from public.stock_snapshot) u left join public.financial_latest f using(symbol) where f.symbol is null order by u.symbol;
