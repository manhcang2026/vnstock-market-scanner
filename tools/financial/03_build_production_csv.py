from __future__ import annotations
import argparse,csv
from datetime import date
from pathlib import Path

ESSENTIAL={
"NORMAL":["income_bil_vnd","pbt_bil_vnd","net_profit_bil_vnd","total_assets_bil_vnd","equity_bil_vnd"],
"BANK":["income_bil_vnd","pbt_bil_vnd","net_profit_bil_vnd","total_assets_bil_vnd","equity_bil_vnd"],
"SECURITIES":["income_bil_vnd","pbt_bil_vnd","net_profit_bil_vnd","total_assets_bil_vnd","equity_bil_vnd"],
"INSURANCE":["income_bil_vnd","pbt_bil_vnd","net_profit_bil_vnd","total_assets_bil_vnd","equity_bil_vnd"],
}
QUALITY=["roea_pct","roaa_pct","eps_vnd","pb"]
def read_csv(p):
    with open(p,newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))
def write_csv(p,rows):
    if not rows:return
    fields=[];seen=set()
    for r in rows:
        for k in r:
            if k not in seen:seen.add(k);fields.append(k)
    with open(p,"w",newline="",encoding="utf-8-sig") as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def blank(v):return v is None or str(v).strip()==""
def expected(today=None):
    t=today or date.today();y,m=t.year,t.month
    if m<=2:return y-1,4
    if m<=5:return y,1
    if m<=8:return y,2
    return y,3
def qi(y,q):return y*4+q
def freshness(r,ty,tq):
    try:y=int(float(r.get("year") or 0));q=int(str(r.get("quarter") or "Q0").replace("Q",""))
    except:return "STALE"
    age=qi(ty,tq)-qi(y,q)
    if age<0:return "FUTURE_INVALID"
    if age==0:return "CURRENT"
    if age==1:return "LAGGING"
    return "STALE"
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--summary",default="tools/financial/work/fundamental/fundamental_summary.csv")
    ap.add_argument("--master",default="tools/financial/work/industry_final.csv")
    ap.add_argument("--errors",default="tools/financial/work/fundamental/errors.csv")
    ap.add_argument("--out-dir",default="tools/financial/work/production")
    args=ap.parse_args()

    source=Path(args.summary)
    master_path=Path(args.master)
    error_path=Path(args.errors)
    if not source.exists():raise FileNotFoundError(source)
    if not master_path.exists():raise FileNotFoundError(master_path)

    rows=read_csv(source)
    master_rows=read_csv(master_path)
    if not rows:raise RuntimeError("Summary rỗng")
    if not master_rows: raise RuntimeError("Master rỗng")

    master={}
    for r in master_rows:
        s=(r.get("symbol") or "").strip().upper()
        if not s:raise RuntimeError("Master có symbol rỗng")
        master[s]=r
    if len(master)!=len(master_rows):raise RuntimeError("Master có symbol trùng")

    errors={}
    if error_path.exists():
        for r in read_csv(error_path):
            s=(r.get("symbol") or "").strip().upper()
            if s:errors[s]=r

    ty,tq=expected(); enriched=[]
    for src in rows:
        r=dict(src);model=(r.get("financial_model") or "NORMAL").upper();essential=ESSENTIAL.get(model,ESSENTIAL["NORMAL"])
        miss=[f for f in essential if blank(r.get(f))];qmiss=[f for f in QUALITY if blank(r.get(f))]
        fr=freshness(r,ty,tq)
        if fr=="FUTURE_INVALID":continue
        warnings=(r.get("_metric_warnings") or "").strip()
        r["freshness_status"]=fr
        r["data_status"]="COMPLETE" if not miss and not warnings else "PARTIAL"
        r["missing_core_fields"]="|".join(miss + ([f"AMBIGUOUS_METRIC:{warnings}"] if warnings else []))
        r["_quality_missing"]="|".join(qmiss)
        enriched.append(r)

    bykey={}
    for r in enriched:bykey[(r.get("symbol","").upper(),r.get("period",""))]=r
    quarterly=list(bykey.values())

    def pkey(r):
        try:return int(float(r.get("year") or 0)),int(str(r.get("quarter","Q0")).replace("Q",""))
        except:return 0,0

    latest={}
    for r in quarterly:
        s=r.get("symbol","").upper()
        if s and (s not in latest or pkey(r)>pkey(latest[s])):latest[s]=r

    outlatest=[]
    for s in sorted(master):
        if s in latest:
            r=dict(latest[s]);r["error_message"]=""
            r["production_ready"]="YES" if r["freshness_status"]=="CURRENT" and r["data_status"]=="COMPLETE" else "REVIEW"
            outlatest.append(r)
            continue

        # Không để mã thiếu BCTC biến mất khỏi financial_latest.
        meta=master[s]
        err=errors.get(s,{})
        msg=(err.get("error") or "Không có dữ liệu BCTC quý hợp lệ trên Vietstock").strip()
        model=(meta.get("financial_model") or "NORMAL").upper()
        outlatest.append({
            "symbol":s,
            "website_group":meta.get("website_group",""),
            "financial_model":model,
            "period":"",
            "year":"",
            "quarter":"",
            "report_data_id":"",
            "consolidated":"",
            "audit_status":"",
            "freshness_status":"NO_DATA",
            "data_status":"NO_FINANCIAL_DATA",
            "missing_core_fields":"|".join(ESSENTIAL.get(model,ESSENTIAL["NORMAL"])),
            "error_message":msg,
            "production_ready":"NO",
        })

    target_count=len(master)
    if len(outlatest)!=target_count or len({r["symbol"] for r in outlatest})!=target_count:
        raise RuntimeError(f"Latest coverage phải {target_count}/{target_count}, hiện {len(outlatest)}")

    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    qf=out/"financial_quarterly.csv"
    lf=out/"financial_latest.csv"
    write_csv(qf,quarterly);write_csv(lf,outlatest)

    no_data=[r["symbol"] for r in outlatest if r["data_status"]=="NO_FINANCIAL_DATA"]
    partial=[r["symbol"] for r in outlatest if r["data_status"]=="PARTIAL"]
    stale=[r["symbol"] for r in outlatest if r.get("freshness_status")=="STALE"]
    current_ok=[r["symbol"] for r in outlatest if r.get("production_ready")=="YES"]

    print(f"Quarterly {len(quarterly)} | Latest {len(outlatest)}/{len(master)}")
    print(f"READY {len(current_ok)} | PARTIAL {len(partial)} | NO_DATA {len(no_data)} | STALE {len(stale)}")
    if no_data:print("NO_DATA:",", ".join(no_data))
    if partial:print("PARTIAL:",", ".join(partial))
    if stale:print("STALE:",", ".join(stale))

if __name__=="__main__":main()
