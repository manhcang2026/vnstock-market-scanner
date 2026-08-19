from __future__ import annotations
import argparse, csv, re, time, unicodedata
from difflib import SequenceMatcher
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE = "https://finance.vietstock.vn"
CLASSIFIER_VERSION = "v2_20260820"
DELAY = 0.70
TIMEOUT = 30
MAX_ATTEMPTS = 3
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}
GROUP_ORDER = {
    "Ngân hàng":1,"Chứng khoán":2,"Bảo hiểm":3,"Bất động sản":4,"Thép":5,"Dầu khí":6,"Điện":7,
    "Bán lẻ":8,"Công nghệ":9,"Hóa chất":10,"Phân bón":11,"Thủy sản":12,"Dệt may":13,
    "Cảng & Logistics":14,"Xây dựng":15,"Vật liệu xây dựng":16,"Hàng không":17,
    "Thực phẩm & đồ uống":18,"Dược & Y tế":19,"Cao su":20,"Nông nghiệp":21,"Nước":22,
    "Viễn thông":23,"Gỗ & Giấy":24,"Gỗ & Nội thất":25,"Ô tô & Phụ tùng":26,
    "Du lịch & Giải trí":27,"Truyền thông":28,"Thiết bị điện":29,"Máy móc & Thiết bị":30,
    "Bao bì":31,"Kim loại & Khoáng sản":32,"Thương mại & Phân phối":33,"Dịch vụ công nghiệp":34,
    "Dịch vụ tiêu dùng":35,"Hàng tiêu dùng lâu bền":36,"Đa ngành":37,"Tài chính khác":38,
    "Khác / cần duyệt":99,
}
GROUP_RULES = [
    ("Ngân hàng",["ngan hang","banks","credit institutions"]),
    ("Chứng khoán",["chung khoan","securities","thi truong von","capital markets"]),
    ("Bảo hiểm",["bao hiem","insurance"]),("Bất động sản",["bat dong san","real estate"]),
    ("Thép",["thep","steel","sat va thep"]),("Dầu khí",["dau khi","oil & gas","oil and gas","petroleum","gas distribution","gas sinh hoat","khi dot","khi thien nhien"]),
    ("Bán lẻ",["ban le","retail"]),("Công nghệ",["cong nghe thong tin","phan mem","information technology","software"]),
    ("Phân bón",["phan bon","fertilizer"]),("Thủy sản",["thuy san","hai san","seafood","aquaculture"]),
    ("Dệt may",["det may","textile","apparel","may mac"]),
    ("Cảng & Logistics",["cang","logistics","van tai bien","hang hai","kho bai","transportation infrastructure","ha tang giao thong","van tai mat dat","van tai duong bo"]),
    ("Hàng không",["hang khong","airlines","airport","aviation"]),
    ("Vật liệu xây dựng",["vat lieu xay dung","xi mang","cement","gach","construction materials"]),
    ("Xây dựng",["ky thuat xay dung","xay dung","construction & engineering","construction"]),
    ("Thực phẩm & đồ uống",["thuc pham","do uong","food","beverage","bia","sua"]),
    ("Dược & Y tế",["duoc","y te","cham soc suc khoe","health care","pharmaceutical"]),
    ("Ô tô & Phụ tùng",["o to","phu tung","automobile","auto components"]),("Cao su",["cao su","rubber"]),
    ("Nông nghiệp",["nong nghiep","chan nuoi","agriculture","farming"]),("Nước",["cap nuoc","nuoc sach","cap thoat nuoc","nuoc","water utilities","water"]),
    ("Viễn thông",["vien thong","telecommunication"]),("Gỗ & Nội thất",["noi that","furnishings","home furnishings"]),
    ("Gỗ & Giấy",["go va giay","go & giay","giay","paper","forest products"]),("Truyền thông",["truyen thong","media","publishing"]),
    ("Du lịch & Giải trí",["du lich","giai tri","hotels","resorts","leisure"]),("Thiết bị điện",["thiet bi dien","electrical components","electrical equipment"]),
    ("Máy móc & Thiết bị",["may moc","machinery","industrial machinery"]),("Bao bì",["bao bi","packaging"]),
    ("Kim loại & Khoáng sản",["khai khoang","luyen kim","kim loai","khoang san","metals & mining","mining"]),
    ("Thương mại & Phân phối",["nha phan phoi","phan phoi","thuong mai hang thiet yeu","trading companies","distributors"]),
    ("Dịch vụ công nghiệp",["dich vu chuyen nghiep","professional services","commercial services"]),
    ("Dịch vụ tiêu dùng",["dich vu tieu dung","consumer services"]),("Hàng tiêu dùng lâu bền",["hang tieu dung lau ben","consumer durables"]),
    ("Đa ngành",["tap doan da nganh","conglomerates","multi-sector holdings"]),
    ("Tài chính khác",["tin dung phi ngan hang","consumer finance","specialized finance"]),
    ("Hóa chất",["hoa chat","chemical"]),("Điện",["dien luc","san xuat dien","phat dien","thuy dien","nhiet dien","dien tai tao","dien","power generation","electric utilities","independent power"]),
]
FIELDS = [
    "classifier_version","symbol","exchange","company_name","display_name","en_company_name","vietstock_company_name","name_match_status",
    "watchlist_sector_l1","watchlist_sector_l2","watchlist_sector_l3","vietstock_sector_l1","vietstock_sector_l2","vietstock_sector_l3",
    "website_group","financial_model","website_group_order","matched_keyword","mapping_confidence","suggestion_source",
    "source_url","vietstock_financial_url","status","needs_review","review_reason",
]

def strip_accents(text):
    text = unicodedata.normalize("NFD", str(text or ""))
    text = "".join(c for c in text if unicodedata.category(c)!="Mn")
    # NFD không tách ký tự đ/Đ, phải đổi thủ công.
    text = text.replace("đ", "d").replace("Đ", "D")
    return text.lower().strip()

def canonical_company(text):
    x = strip_accents(text)
    x = re.sub(r"\b(cong ty co phan|ctcp|tong cong ty|ngan hang tmcp|tap doan|jsc|joint stock company|corporation|corp)\b"," ",x)
    x = re.sub(r"[^a-z0-9]+"," ",x)
    return re.sub(r"\s+"," ",x).strip()

def company_match(a,b):
    ca, cb = canonical_company(a), canonical_company(b)
    if not ca or not cb: return "NO_VIETSTOCK_NAME"
    if ca in cb or cb in ca: return "MATCH"
    return "MATCH" if SequenceMatcher(None,ca,cb).ratio() >= 0.72 else "MISMATCH_REVIEW"

def read_csv(path):
    with open(path,newline="",encoding="utf-8-sig") as f: return list(csv.DictReader(f))

def write_csv(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def extract_industry(html):
    soup=BeautifulSoup(html,"html.parser")
    for node in soup.find_all(string=re.compile(r"Ngành\s*:",re.I)):
        parent=node.parent
        for container in (parent, parent.parent if parent else None):
            if not container: continue
            names=[]
            for a in container.find_all("a"):
                t=re.sub(r"\s+"," ",a.get_text(" ",strip=True)).strip()
                if t and len(t)<=80 and t not in names: names.append(t)
            if names: return names[:3]
    text=soup.get_text(" ",strip=True)
    m=re.search(r"Ngành:\s+(.{1,250}?)(?:\s+\d{1,3}(?:,\d{3}){1,3}|\s+Xem nhiều|\s+HOSE|\s+HNX|\s+UPCOM)",text,re.I)
    return [m.group(1).strip()] if m else []

def extract_company_name(html, symbol):
    soup=BeautifulSoup(html,"html.parser")
    for sel in ["h1",".company-name",".title-company",".stock-profile-name"]:
        el=soup.select_one(sel)
        if el:
            t=re.sub(r"\s+"," ",el.get_text(" ",strip=True)).strip()
            if t and symbol.upper() not in t.upper() and 3 < len(t) < 180: return t
    title=(soup.title.get_text(" ",strip=True) if soup.title else "")
    title=re.sub(r"\s*[-|]\s*Vietstock.*$","",title,flags=re.I).strip()
    title=re.sub(rf"^\s*{re.escape(symbol)}\s*[-:|]\s*","",title,flags=re.I).strip()
    return title if 3 < len(title) < 180 else ""

def classify_group(levels):
    # Ưu tiên ngành chi tiết nhất (L3 -> L2 -> L1), tránh việc
    # "Truyền thông và giải trí" bị bắt nhầm bởi từ "giải trí".
    normalized = [strip_accents(x) for x in levels if str(x or "").strip()]
    for level in reversed(normalized):
        for group, kws in GROUP_RULES:
            for kw in kws:
                if strip_accents(kw) in level:
                    return group, kw
    return "Khác / cần duyệt",""

def financial_model(group):
    return {"Ngân hàng":"BANK","Chứng khoán":"SECURITIES","Bảo hiểm":"INSURANCE"}.get(group,"NORMAL")

def fetch_html(session,url):
    last=None
    for attempt in range(1,MAX_ATTEMPTS+1):
        try:
            r=session.get(url,headers=HEADERS,timeout=TIMEOUT)
            if r.status_code==429 or r.status_code>=500: raise requests.HTTPError(f"HTTP {r.status_code}",response=r)
            r.raise_for_status(); return r.text
        except requests.RequestException as exc:
            last=exc
            if attempt<MAX_ATTEMPTS: time.sleep(2*attempt)
    raise RuntimeError(str(last))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--watchlist",default="config/watchlist.csv")
    ap.add_argument("--existing",default="tools/financial/data/existing_symbols_current.csv")
    ap.add_argument("--out",default="tools/financial/output/industry_new_current_raw.csv")
    ap.add_argument("--review",default="tools/financial/output/industry_review_current.csv")
    args=ap.parse_args()
    watch=read_csv(Path(args.watchlist))
    by={(r.get("symbol") or "").strip().upper():r for r in watch if (r.get("symbol") or "").strip()}
    existing={(r.get("symbol") or "").strip().upper() for r in read_csv(Path(args.existing))}
    targets=sorted(set(by)-existing)
    print(f"Universe {len(by)} | existing {len(existing & set(by))} | targets {len(targets)}")
    if len(by)!=800 or len(targets)!=543: raise RuntimeError("Universe/target count không đúng 800/543")

    outp=Path(args.out); previous={}
    if outp.exists():
        old_rows = read_csv(outp)
        versions = {str(r.get("classifier_version") or "").strip() for r in old_rows}
        if versions == {CLASSIFIER_VERSION}:
            for r in old_rows:
                s=(r.get("symbol") or "").upper()
                if s: previous[s]=r
        else:
            print(f"Classifier đổi sang {CLASSIFIER_VERSION}: rebuild toàn bộ {len(targets)} mã.")
    done={s for s,r in previous.items() if str(r.get("status","")).startswith(("OK","NO_INDUSTRY"))}
    result=dict(previous); session=requests.Session()
    pending=[s for s in targets if s not in done]

    for idx,symbol in enumerate(pending,1):
        wr=by[symbol]; url=f"{BASE}/{symbol}/ho-so-doanh-nghiep.htm"
        fin_url=f"{BASE}/{symbol}/tai-chinh.htm?tab=BCTT"
        watch_levels=[wr.get("sector1_vn",""),wr.get("sector2_vn",""),wr.get("sector3_vn","")]
        watch_group,watch_kw=classify_group(watch_levels)
        print(f"[{idx}/{len(pending)}] {symbol} ... ",end="",flush=True)
        reasons=[]
        try:
            html=fetch_html(session,url)
            levels=extract_industry(html)
            vs_name=extract_company_name(html,symbol)
            nmatch=company_match(wr.get("organ_name",""),vs_name)
            if nmatch=="MISMATCH_REVIEW": reasons.append("Tên VNStock khác Vietstock")
            vs_group,vs_kw=classify_group(levels)
            if vs_group!="Khác / cần duyệt":
                group,kw,conf,src,review=vs_group,vs_kw,"VIETSTOCK_RULE","VIETSTOCK","NO"
            elif watch_group!="Khác / cần duyệt":
                group,kw,conf,src,review=watch_group,watch_kw,"WATCHLIST_FALLBACK","WATCHLIST","YES"
                reasons.append("Phân ngành dùng fallback watchlist")
            else:
                group,kw,conf,src,review="Khác / cần duyệt","","REVIEW","","YES"
                reasons.append("Chưa map được ngành")
            combined=strip_accents(" | ".join(levels+watch_levels))
            if "ngan hang" in combined: group="Ngân hàng"
            elif "thi truong von" in combined or "chung khoan" in combined: group="Chứng khoán"
            elif "bao hiem" in combined: group="Bảo hiểm"
            if nmatch=="MISMATCH_REVIEW": review="YES"
            if not levels:
                review="YES"; reasons.append("Vietstock không trả ngành")
            row={
                "classifier_version":CLASSIFIER_VERSION,"symbol":symbol,"exchange":wr.get("exchange",""),"company_name":wr.get("organ_name",""),
                "display_name":wr.get("organ_name",""),"en_company_name":wr.get("en_organ_name",""),
                "vietstock_company_name":vs_name,"name_match_status":nmatch,
                "watchlist_sector_l1":watch_levels[0],"watchlist_sector_l2":watch_levels[1],"watchlist_sector_l3":watch_levels[2],
                "vietstock_sector_l1":levels[0] if len(levels)>0 else "","vietstock_sector_l2":levels[1] if len(levels)>1 else "",
                "vietstock_sector_l3":levels[2] if len(levels)>2 else "","website_group":group,
                "financial_model":financial_model(group),"website_group_order":GROUP_ORDER.get(group,99),
                "matched_keyword":kw,"mapping_confidence":conf,"suggestion_source":src,"source_url":url,
                "vietstock_financial_url":fin_url,"status":"OK" if levels else "NO_INDUSTRY","needs_review":review,
                "review_reason":" | ".join(dict.fromkeys(reasons)),
            }
            print(f"{group} | name={nmatch}")
        except Exception as exc:
            row={
                "classifier_version":CLASSIFIER_VERSION,"symbol":symbol,"exchange":wr.get("exchange",""),"company_name":wr.get("organ_name",""),
                "display_name":wr.get("organ_name",""),"en_company_name":wr.get("en_organ_name",""),
                "vietstock_company_name":"","name_match_status":"ERROR","website_group":watch_group,
                "financial_model":financial_model(watch_group),"website_group_order":GROUP_ORDER.get(watch_group,99),
                "matched_keyword":watch_kw,"mapping_confidence":"ERROR_RETRY","suggestion_source":"WATCHLIST" if watch_group!="Khác / cần duyệt" else "",
                "source_url":url,"vietstock_financial_url":fin_url,"status":f"ERROR: {exc}","needs_review":"YES","review_reason":"Lỗi gọi Vietstock",
            }
            print("ERROR",exc)
        result[symbol]=row
        ordered=[result[s] for s in targets if s in result]
        write_csv(outp,ordered)
        write_csv(Path(args.review),[r for r in ordered if r.get("needs_review")=="YES" or str(r.get("status","")).startswith("ERROR")])
        time.sleep(DELAY)

    ordered=[result[s] for s in targets if s in result]
    review=[r for r in ordered if r.get("needs_review")=="YES" or str(r.get("status","")).startswith("ERROR")]
    print(f"\nSTEP 1 XONG: {len(ordered)}/{len(targets)} | cần review {len(review)}")
    print("Raw:",outp.resolve()); print("Review:",Path(args.review).resolve())

if __name__=="__main__": main()
