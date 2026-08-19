from __future__ import annotations
import argparse, csv, json, re, sys, time, unicodedata
from datetime import date
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE="https://finance.vietstock.vn"
ENDPOINT_NORMS=f"{BASE}/data/GetListReportNorm_BCTT_ByStockCode"
ENDPOINT_REPORTS=f"{BASE}/data/BCTT_GetListReportData"
ENDPOINT_VALUES=f"{BASE}/data/GetReportDataDetailValue_BCTT_ByReportDataIds"
MAX_PERIODS=9; UNIT="1000000000"; TYPE_COMPARE="1"; REQUEST_DELAY=.60; TIMEOUT=45; MAX_ATTEMPTS=3
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36","Accept-Language":"vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"}
TERM_TO_PERIOD={2:"Q1",3:"Q2",4:"Q3",5:"Q4"}
COMMON={
"total_assets_bil_vnd":["Tổng cộng tài sản","Tổng tài sản"],
"equity_bil_vnd":["Vốn chủ sở hữu","Vốn và các quỹ","Tổng vốn chủ sở hữu"],
"eps_vnd":["Thu nhập trên mỗi cổ phần của 4 quý gần nhất (EPS)","EPS"],
"bvps_vnd":["Giá trị sổ sách của cổ phiếu (BVPS)","BVPS"],
"pe":["Chỉ số giá thị trường trên thu nhập (P/E)","P/E"],
"pb":["Chỉ số giá thị trường trên giá trị sổ sách (P/B)","P/B"],
"roea_pct":["Tỷ suất lợi nhuận trên vốn chủ sở hữu bình quân (ROEA)","ROEA","ROE"],
"roaa_pct":["Tỷ suất sinh lợi trên tổng tài sản bình quân (ROAA)","ROAA","ROA"],
}
NORMAL={"income_bil_vnd":["Doanh thu thuần về bán hàng và cung cấp dịch vụ","Doanh thu thuần"],"gross_profit_bil_vnd":["Lợi nhuận gộp về bán hàng và cung cấp dịch vụ","Lợi nhuận gộp"],"pbt_bil_vnd":["Tổng lợi nhuận kế toán trước thuế","Tổng lợi nhuận kế toán","Lợi nhuận trước thuế"],"net_profit_bil_vnd":["Lợi nhuận sau thuế thu nhập doanh nghiệp","Lợi nhuận sau thuế"],"parent_net_profit_bil_vnd":["Lợi nhuận sau thuế của cổ đông Công ty mẹ"],"liabilities_bil_vnd":["Nợ phải trả"],"gross_margin_pct":["Tỷ suất lợi nhuận gộp biên"],"net_margin_pct":["Tỷ suất sinh lợi trên doanh thu thuần"],"debt_assets_pct":["Tỷ số Nợ trên Tổng tài sản"],"debt_equity_pct":["Tỷ số Nợ vay trên Vốn chủ sở hữu"]}
BANK={"income_bil_vnd":["Thu nhập lãi thuần","Tổng thu nhập hoạt động","Thu nhập hoạt động"],"gross_profit_bil_vnd":["Tổng thu nhập hoạt động","Thu nhập hoạt động"],"pbt_bil_vnd":["Tổng lợi nhuận trước thuế","Lợi nhuận trước thuế"],"net_profit_bil_vnd":["Lợi nhuận sau thuế"],"parent_net_profit_bil_vnd":["Lợi nhuận sau thuế của cổ đông của Ngân hàng mẹ","Lợi nhuận sau thuế của cổ đông Ngân hàng mẹ","Lợi nhuận sau thuế của cổ đông công ty mẹ"],"liabilities_bil_vnd":["Nợ phải trả","Tổng nợ phải trả"]}
SEC={"income_bil_vnd":["Doanh thu thuần về hoạt động kinh doanh","Doanh thu hoạt động"],"gross_profit_bil_vnd":["Kết quả hoạt động kinh doanh","Lợi nhuận từ hoạt động kinh doanh"],"pbt_bil_vnd":["Lợi nhuận kế toán trước thuế","Tổng lợi nhuận kế toán trước thuế"],"net_profit_bil_vnd":["Lợi nhuận sau thuế TNDN","Lợi nhuận kế toán sau thuế"],"parent_net_profit_bil_vnd":["Lợi nhuận sau thuế của cổ đông Công ty mẹ","Lợi nhuận sau thuế thuộc về cổ đông công ty mẹ"],"liabilities_bil_vnd":["Nợ phải trả"]}
INS={"income_bil_vnd":["Doanh thu thuần hoạt động kinh doanh bảo hiểm","Doanh thu phí bảo hiểm","Doanh thu hoạt động kinh doanh bảo hiểm","Doanh thu thuần"],"gross_profit_bil_vnd":["Lợi nhuận gộp hoạt động kinh doanh bảo hiểm","Lợi nhuận gộp"],"pbt_bil_vnd":["Tổng lợi nhuận kế toán trước thuế","Tổng lợi nhuận kế toán","Lợi nhuận trước thuế"],"net_profit_bil_vnd":["Lợi nhuận sau thuế thu nhập doanh nghiệp","Lợi nhuận sau thuế"],"parent_net_profit_bil_vnd":["Lợi nhuận sau thuế của cổ đông công ty mẹ"],"liabilities_bil_vnd":["Nợ phải trả"]}

def norm(t):
    t=unicodedata.normalize("NFD",str(t or ""))
    return "".join(c for c in t if unicodedata.category(c)!="Mn").lower().strip()
def read_csv(p):
    with open(p,newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))
def write_csv(p,rows):
    if not rows:return
    fields=[];seen=set()
    for r in rows:
        for k in r:
            if k not in seen:seen.add(k);fields.append(k)
    p.parent.mkdir(parents=True,exist_ok=True)
    with open(p,"w",newline="",encoding="utf-8-sig") as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def load_master(p):
    out={}
    for r in read_csv(p):
        s=(r.get("symbol") or "").strip().upper()
        if not s:continue
        if (r.get("needs_review") or "").strip().upper()=="YES":raise RuntimeError(f"{s} còn needs_review=YES")
        out[s]=r
    return out
def expected_period(today=None):
    t=today or date.today(); y,m=t.year,t.month
    if m<=2:return y-1,4
    if m<=5:return y,1
    if m<=8:return y,2
    return y,3
def qindex(y,q):return y*4+q
def get_token(s,symbol):
    ref=f"{BASE}/{symbol}/tai-chinh.htm?tab=BCTT"; r=s.get(ref,headers=HEADERS,timeout=TIMEOUT);r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser");el=soup.find("input",{"name":"__RequestVerificationToken"})
    if el and el.get("value"):return el["value"],ref
    m=re.search(r'name=["\']__RequestVerificationToken["\'][^>]*value=["\']([^"\']+)',r.text,re.I)
    if not m:raise RuntimeError("Không tìm thấy token")
    return m.group(1),ref
def post_json(s,url,payload,ref):
    h={**HEADERS,"Accept":"*/*","Content-Type":"application/x-www-form-urlencoded; charset=UTF-8","Referer":ref,"X-Requested-With":"XMLHttpRequest"};last=None
    for a in range(1,MAX_ATTEMPTS+1):
        try:
            r=s.post(url,data=payload,headers=h,timeout=TIMEOUT)
            if r.status_code==429 or r.status_code>=500:raise requests.HTTPError(f"HTTP {r.status_code}",response=r)
            r.raise_for_status();return r.json()
        except (requests.RequestException,ValueError) as e:
            last=e
            if a<MAX_ATTEMPTS:time.sleep(2*a)
    raise RuntimeError(str(last))
def extract_list(o):
    if isinstance(o,list):return o
    if isinstance(o,dict):
        for k in ("data","Data","result","Result","rows","Rows","items","Items"):
            if isinstance(o.get(k),list):return o[k]
    raise RuntimeError(f"Cấu trúc JSON lạ: {type(o).__name__}")
def get_norms(s,symbol,t,ref):return extract_list(post_json(s,ENDPOINT_NORMS,{"stockCode":symbol,"__RequestVerificationToken":t},ref))
def get_reports(s,symbol,t,ref):
    p={"StockCode":symbol,"UnitId":"-1","AuditedStatusId":"-1","Unit":UNIT,"IsNamDuongLich":"false","PeriodType":"QUY","SortTimeType":"Time_ASC","__RequestVerificationToken":t}
    return extract_list(post_json(s,ENDPOINT_REPORTS,p,ref))
def choose_recent_reports(reports,limit=9):
    ty,tq=expected_period(); maxidx=qindex(ty,tq); cand=[]
    for r in reports:
        if not isinstance(r,dict):continue
        try:y=int(r.get("YearPeriod") or 0);term=int(r.get("ReportTermID") or 0);rowno=int(r.get("RowNumber") or 0)
        except:continue
        if term not in TERM_TO_PERIOD:continue
        q=term-1
        if qindex(y,q)>maxidx:continue
        p=f"{y}{TERM_TO_PERIOD[term]}";iscon=norm(r.get("UnitedName"))=="hop nhat"
        cand.append({**r,"_year":y,"_term":term,"_row":rowno,"_period":p,"_consolidated":iscon})
    by={}
    for r in cand:by.setdefault(r["_period"],[]).append(r)
    periods=sorted(by,key=lambda p:(int(p[:4]),int(p[-1])),reverse=True);chosen=[]
    for p in periods:
        items=by[p];items.sort(key=lambda x:(1 if x["_consolidated"] else 0,x["_row"]),reverse=True);chosen.append(items[0])
        if len(chosen)>=limit:break
    return chosen
def get_values(s,symbol,chosen,t,ref,total):
    p=[("StockCode",symbol),("Unit",UNIT),("TypeCompare",TYPE_COMPARE)]
    for i,r in enumerate(chosen):
        p += [(f"listReportDataIds[{i}][Index]",str(i)),(f"listReportDataIds[{i}][ReportDataId]",str(r.get("ReportDataID",""))),(f"listReportDataIds[{i}][IsShowData]","true"),(f"listReportDataIds[{i}][RowNumber]",str(r.get("RowNumber",""))),(f"listReportDataIds[{i}][YearPeriod]",str(r.get("YearPeriod",""))),(f"listReportDataIds[{i}][TotalCount]",str(total)),(f"listReportDataIds[{i}][SortTimeType]","Time_ASC")]
    p.append(("__RequestVerificationToken",t));return extract_list(post_json(s,ENDPOINT_VALUES,p,ref))
def maps(norms,values):
    nm={int(x["ReportNormId"]):x for x in norms if isinstance(x,dict) and x.get("ReportNormId") is not None}
    vm={int(x["ReportNormId"]):x for x in values if isinstance(x,dict) and x.get("ReportNormId") is not None}
    return nm,vm
def vk(i):return f"Value{i+1}"
def find_metric(nm,vm,i,phrases):
    # Exact match always wins.
    for phrase in phrases:
        p=norm(phrase)
        for rid,n in nm.items():
            if norm(n.get("ReportNormName"))==p:
                v=vm.get(rid); val=v.get(vk(i)) if v else None
                if val is not None:return val,n.get("ReportNormName"),"EXACT",""
    # Contains allowed only when it resolves to exactly one norm candidate.
    candidates={}
    for phrase in phrases:
        p=norm(phrase)
        if not p:continue
        for rid,n in nm.items():
            name=norm(n.get("ReportNormName"))
            if p in name:
                v=vm.get(rid);val=v.get(vk(i)) if v else None
                if val is not None:candidates[rid]=(val,n.get("ReportNormName"))
    if len(candidates)==1:
        val,name=next(iter(candidates.values()));return val,name,"CONTAINS",""
    if len(candidates)>1:
        names=" || ".join(str(x[1]) for x in candidates.values())
        return None,None,"AMBIGUOUS",names
    return None,None,"MISSING",""
def pct(new,old):
    if new is None or old in (None,0):return None
    try:return (float(new)/float(old)-1)*100
    except:return None
def spec(model):
    return BANK if model=="BANK" else SEC if model=="SECURITIES" else INS if model=="INSURANCE" else NORMAL
def build_summary(symbol,meta,chosen,norms,values):
    model=(meta.get("financial_model") or "NORMAL").upper();nm,vm=maps(norms,values);rows=[]
    for i,r in enumerate(chosen):
        row={"symbol":symbol,"website_group":meta.get("website_group",""),"financial_model":model,"period":r["_period"],"year":r["_year"],"quarter":TERM_TO_PERIOD[r["_term"]],"report_data_id":r.get("ReportDataID"),"consolidated":r["_consolidated"],"audit_status":r.get("AuditStatusName")}
        warns=[]
        for field,phrases in {**COMMON,**spec(model)}.items():
            val,src,kind,detail=find_metric(nm,vm,i,phrases);row[field]=val;row[field+"_source"]=src
            if kind=="AMBIGUOUS":warns.append(f"{field}:AMBIGUOUS:{detail}")
        row["_metric_warnings"]=" | ".join(warns); rows.append(row)
    by={r["period"]:r for r in rows};qn={"Q1":1,"Q2":2,"Q3":3,"Q4":4}
    for row in rows:
        y=int(row["year"]);q=row["quarter"];n=qn[q];prev=by.get(f"{y-1}Q4" if n==1 else f"{y}Q{n-1}");yoy=by.get(f"{y-1}{q}")
        row["income_qoq_pct"]=pct(row.get("income_bil_vnd"),prev.get("income_bil_vnd") if prev else None)
        row["income_yoy_pct"]=pct(row.get("income_bil_vnd"),yoy.get("income_bil_vnd") if yoy else None)
        cur=row.get("parent_net_profit_bil_vnd") if row.get("parent_net_profit_bil_vnd") is not None else row.get("net_profit_bil_vnd")
        pv=(prev.get("parent_net_profit_bil_vnd") if prev else None)
        if pv is None and prev:pv=prev.get("net_profit_bil_vnd")
        yv=(yoy.get("parent_net_profit_bil_vnd") if yoy else None)
        if yv is None and yoy:yv=yoy.get("net_profit_bil_vnd")
        row["profit_qoq_pct"]=pct(cur,pv);row["profit_yoy_pct"]=pct(cur,yv)
    return rows
def load_completed(p):
    if not p.exists():return set()
    return {(r.get("symbol") or "").upper() for r in read_csv(p) if (r.get("status") or "").upper()=="OK"}
def append_checkpoint(p,s):
    exists=p.exists();p.parent.mkdir(parents=True,exist_ok=True)
    with open(p,"a",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=["symbol","status"])
        if not exists:w.writeheader()
        w.writerow({"symbol":s,"status":"OK"})
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--master",default="tools/financial/output/industry_new_current_final.csv")
    ap.add_argument("--out-dir",default="tools/financial/output/fundamental_current")
    ap.add_argument("--force-model",choices=["BANK","SECURITIES","INSURANCE","NORMAL"],default=None,help="Chạy lại riêng một financial_model dù đã checkpoint")
    args=ap.parse_args()
    mp=Path(args.master)
    if not mp.exists():raise FileNotFoundError(f"Không thấy {mp}; phải duyệt STEP 1 trước.")
    master=load_master(mp); symbols=sorted(master)
    if len(symbols)!=543:raise RuntimeError(f"Master phải 543 mã, hiện {len(symbols)}")
    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    summary_csv=out/"fundamental_summary_current.csv";long_csv=out/"metrics_long_current.csv";raw_json=out/"raw_current.json";error_csv=out/"errors_current.csv";checkpoint_csv=out/"checkpoint_success_current.csv";latest_csv=out/"financial_latest_raw_current.csv"
    completed=load_completed(checkpoint_csv);allsum=read_csv(summary_csv) if summary_csv.exists() else [];alllong=read_csv(long_csv) if long_csv.exists() else [];errors=read_csv(error_csv) if error_csv.exists() else []
    raw={}
    if raw_json.exists():
        try:raw=json.loads(raw_json.read_text(encoding="utf-8"))
        except:raw={}
    if args.force_model:
        pending=[s for s in symbols if (master[s].get("financial_model") or "NORMAL").upper()==args.force_model]
        print(f"FORCE MODEL {args.force_model}: chạy lại {len(pending)} mã, bỏ qua checkpoint cho nhóm này.")
    else:
        pending=[s for s in symbols if s not in completed]
    print(f"=== VIETSTOCK FUNDAMENTAL CURRENT ===\nMaster {len(symbols)} | done {len(completed)} | pending {len(pending)}")
    for idx,symbol in enumerate(pending,1):
        meta=master[symbol];print(f"[{idx}/{len(pending)}] {symbol} | {meta.get('website_group')} | {meta.get('financial_model')}")
        s=requests.Session()
        try:
            token,ref=get_token(s,symbol);norms=get_norms(s,symbol,token,ref);time.sleep(REQUEST_DELAY)
            reports=get_reports(s,symbol,token,ref);chosen=choose_recent_reports(reports,MAX_PERIODS)
            if not chosen:raise RuntimeError("Không có kỳ báo cáo hợp lệ sau khi chặn kỳ tương lai")
            time.sleep(REQUEST_DELAY);values=get_values(s,symbol,chosen,token,ref,len(reports));summary=build_summary(symbol,meta,chosen,norms,values)
            if not summary:raise RuntimeError("Summary rỗng")
            allsum=[r for r in allsum if str(r.get("symbol","")).upper()!=symbol];alllong=[r for r in alllong if str(r.get("symbol","")).upper()!=symbol];errors=[r for r in errors if str(r.get("symbol","")).upper()!=symbol];allsum.extend(summary)
            nm,_=maps(norms,values)
            for item in values:
                if not isinstance(item,dict):continue
                rid=item.get("ReportNormId");n={}
                if rid is not None:
                    try:n=nm.get(int(rid),{})
                    except:n={}
                for i,r in enumerate(chosen):
                    alllong.append({"symbol":symbol,"website_group":meta.get("website_group"),"financial_model":meta.get("financial_model"),"period":r["_period"],"report_data_id":r.get("ReportDataID"),"report_norm_id":rid,"report_type_code":item.get("ReportTypeCode") or n.get("ReportTypeCode"),"report_type_name":n.get("ReportTypeName"),"metric_name":n.get("ReportNormName"),"unit":n.get("Unit"),"value":item.get(vk(i))})
            raw[symbol]={"meta":meta,"periods":chosen,"norms":norms,"values":values};append_checkpoint(checkpoint_csv,symbol)
            print("  OK",summary[0].get("period"),"warnings:",summary[0].get("_metric_warnings","") or "none")
        except Exception as exc:
            print("  ERROR",exc);errors=[r for r in errors if str(r.get("symbol","")).upper()!=symbol];errors.append({"symbol":symbol,"website_group":meta.get("website_group"),"financial_model":meta.get("financial_model"),"error":str(exc)});raw[symbol]={"meta":meta,"error":str(exc)}
        write_csv(summary_csv,allsum);write_csv(long_csv,alllong)
        if errors:write_csv(error_csv,errors)
        raw_json.write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding="utf-8");time.sleep(REQUEST_DELAY)
    latest=[];seen=set()
    def key(r):
        try:return str(r.get("symbol","")),int(float(r.get("year") or 0)),int(str(r.get("quarter","Q0")).replace("Q","") or 0)
        except:return str(r.get("symbol","")),0,0
    for r in sorted(allsum,key=key,reverse=True):
        sym=str(r.get("symbol","")).upper()
        if sym and sym not in seen:seen.add(sym);latest.append(r)
    write_csv(latest_csv,latest)
    print(f"STEP 2 XONG | latest {len(latest)}/{len(symbols)} | errors {len(errors)}")
if __name__=="__main__":
    try:main()
    except KeyboardInterrupt:sys.exit("\nĐã dừng. Chạy lại sẽ resume.")
