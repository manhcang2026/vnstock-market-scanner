from __future__ import annotations
import argparse,csv,math
from pathlib import Path
META_COLS=["symbol","exchange","company_name","display_name","en_company_name","website_group","financial_model","website_group_order","metadata_status"]
FIN_Q_COLS=["symbol","website_group","financial_model","period","year","quarter","report_data_id","consolidated","audit_status","total_assets_bil_vnd","total_assets_bil_vnd_source","equity_bil_vnd","equity_bil_vnd_source","eps_vnd","eps_vnd_source","bvps_vnd","bvps_vnd_source","pe","pe_source","pb","pb_source","roea_pct","roea_pct_source","roaa_pct","roaa_pct_source","income_bil_vnd","income_bil_vnd_source","gross_profit_bil_vnd","gross_profit_bil_vnd_source","pbt_bil_vnd","pbt_bil_vnd_source","net_profit_bil_vnd","net_profit_bil_vnd_source","parent_net_profit_bil_vnd","parent_net_profit_bil_vnd_source","liabilities_bil_vnd","liabilities_bil_vnd_source","gross_margin_pct","gross_margin_pct_source","net_margin_pct","net_margin_pct_source","debt_assets_pct","debt_assets_pct_source","debt_equity_pct","debt_equity_pct_source","income_qoq_pct","income_yoy_pct","profit_qoq_pct","profit_yoy_pct","freshness_status","data_status","missing_core_fields"]
FIN_L_COLS=FIN_Q_COLS+["error_message","production_ready"]
NUMERIC={"website_group_order","year","report_data_id","total_assets_bil_vnd","equity_bil_vnd","eps_vnd","bvps_vnd","pe","pb","roea_pct","roaa_pct","income_bil_vnd","gross_profit_bil_vnd","pbt_bil_vnd","net_profit_bil_vnd","parent_net_profit_bil_vnd","liabilities_bil_vnd","gross_margin_pct","net_margin_pct","debt_assets_pct","debt_equity_pct","income_qoq_pct","income_yoy_pct","profit_qoq_pct","profit_yoy_pct"}
BOOLEAN={"consolidated"}
def read_csv(p):
    with open(p,newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))
def sv(c,v):
    if v is None:return "NULL"
    s=str(v).strip()
    if s=="" or s.lower() in {"nan","none","null"}:return "NULL"
    if c in BOOLEAN:return "TRUE" if s.lower() in {"true","1","yes"} else "FALSE"
    if c in NUMERIC:
        try:
            n=float(s)
            if not math.isfinite(n):return "NULL"
            if c in {"website_group_order","year","report_data_id"}:return str(int(n))
            return repr(n)
        except:return "NULL"
    return "'"+s.replace("'","''")+"'"
def insert_sql(table,cols,rows,conflict,chunk=500):
    if not rows:return f"-- Không có dữ liệu cho {table}\n"
    parts=["begin;","",f"-- UPSERT {len(rows)} rows vào {table}. KHÔNG DELETE/TRUNCATE."]
    for st in range(0,len(rows),chunk):
        batch=rows[st:st+chunk];allcols=cols+["updated_at"];parts.append(f"insert into public.{table} (\n  "+", ".join(allcols)+"\n) values")
        vals=[]
        for r in batch:vals.append("  ("+", ".join([sv(c,r.get(c)) for c in cols]+["now()"])+")")
        parts.append(",\n".join(vals));upd=[c for c in cols if c not in conflict]
        parts.append("\non conflict ("+", ".join(conflict)+") do update set\n  "+",\n  ".join(f"{c}=excluded.{c}" for c in upd)+",\n  updated_at=now();\n")
    parts+=["commit;",""];return "\n".join(parts)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--watchlist",default="config/watchlist.csv");ap.add_argument("--industry",default="tools/financial/output/industry_new_current_final.csv");ap.add_argument("--quarterly",default="tools/financial/output/production_current/financial_quarterly_production_current.csv");ap.add_argument("--latest",default="tools/financial/output/production_current/financial_latest_production_current.csv");ap.add_argument("--out-dir",default="tools/financial/output/sql_current");args=ap.parse_args()
    watch={(r.get("symbol") or "").upper():r for r in read_csv(Path(args.watchlist)) if (r.get("symbol") or "").strip()}
    industry=read_csv(Path(args.industry))
    bad=[r.get("symbol") for r in industry if (r.get("needs_review") or "").upper()=="YES" or (r.get("website_group") or "")=="Khác / cần duyệt"]
    if bad:raise RuntimeError("Còn mã chưa duyệt: "+", ".join(bad[:30]))
    metadata=[]
    for ir in industry:
        s=(ir.get("symbol") or "").upper();wr=watch.get(s,{})
        metadata.append({"symbol":s,"exchange":wr.get("exchange",ir.get("exchange","")),"company_name":wr.get("organ_name",ir.get("company_name","")),"display_name":ir.get("display_name") or wr.get("organ_name",""),"en_company_name":wr.get("en_organ_name",ir.get("en_company_name","")),"website_group":ir.get("website_group",""),"financial_model":ir.get("financial_model","NORMAL"),"website_group_order":ir.get("website_group_order","99"),"metadata_status":"COMPLETE"})
    quarterly=read_csv(Path(args.quarterly));latest=read_csv(Path(args.latest));out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"01_stock_metadata.sql").write_text(insert_sql("stock_metadata",META_COLS,metadata,["symbol"],300),encoding="utf-8")
    for i,st in enumerate(range(0,len(quarterly),1000),1):
        (out/f"02_financial_quarterly_part{i:02d}.sql").write_text(insert_sql("financial_quarterly",FIN_Q_COLS,quarterly[st:st+1000],["symbol","period"],250),encoding="utf-8")
    (out/"03_financial_latest.sql").write_text(insert_sql("financial_latest",FIN_L_COLS,latest,["symbol"],250),encoding="utf-8")
    verify="""-- CHỈ KIỂM TRA
with u as (select distinct symbol from public.stock_snapshot)
select count(*) universe_symbols,count(m.symbol) with_metadata,count(f.symbol) with_financial_latest,
count(*) filter(where m.symbol is null) missing_metadata,count(*) filter(where f.symbol is null) missing_financial
from u left join public.stock_metadata m using(symbol) left join public.financial_latest f using(symbol);
select data_status,production_ready,count(*) symbols from public.financial_latest
where symbol in (select symbol from public.stock_snapshot)
group by data_status,production_ready order by data_status,production_ready;
select u.symbol from (select distinct symbol from public.stock_snapshot) u left join public.stock_metadata m using(symbol) where m.symbol is null order by u.symbol;
select u.symbol from (select distinct symbol from public.stock_snapshot) u left join public.financial_latest f using(symbol) where f.symbol is null order by u.symbol;
"""
    (out/"99_verify_coverage.sql").write_text(verify,encoding="utf-8")
    print(f"SQL created: metadata {len(metadata)}, quarterly {len(quarterly)}, latest {len(latest)}")
if __name__=="__main__":main()
