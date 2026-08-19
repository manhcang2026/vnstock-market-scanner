from __future__ import annotations
import argparse, csv, sys
from pathlib import Path

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

def read_csv(path: Path):
    with open(path,newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))

def write_csv(path: Path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)

def model_for(group):
    return {"Ngân hàng":"BANK","Chứng khoán":"SECURITIES","Bảo hiểm":"INSURANCE"}.get(group,"NORMAL")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw",default="tools/financial/work/industry_raw.csv")
    ap.add_argument("--overrides",default="tools/financial/config/industry_overrides.csv")
    ap.add_argument("--final",default="tools/financial/work/industry_final.csv")
    ap.add_argument("--unresolved",default="tools/financial/work/industry_unresolved.csv")
    args=ap.parse_args()

    raw=read_csv(Path(args.raw))
    if not raw: raise RuntimeError("industry_raw.csv rỗng")
    symbols=[(r.get("symbol") or "").strip().upper() for r in raw]
    if len(symbols)!=len(set(symbols)): raise RuntimeError("industry_raw.csv có symbol trùng")

    overrides={}
    op=Path(args.overrides)
    if op.exists():
        for r in read_csv(op):
            s=(r.get("symbol") or "").strip().upper()
            if s: overrides[s]=r

    unresolved=[]
    for r in raw:
        s=(r.get("symbol") or "").strip().upper()
        needs=(r.get("needs_review") or "").strip().upper()=="YES" or (r.get("website_group") or "").strip()=="Khác / cần duyệt"
        if not needs: continue
        ov=overrides.get(s)
        if not ov:
            unresolved.append(r); continue
        group=(ov.get("website_group") or "").strip()
        if group not in GROUP_ORDER or group=="Khác / cần duyệt":
            unresolved.append(r); continue
        r["website_group"]=group
        r["financial_model"]=(ov.get("financial_model") or model_for(group)).strip().upper()
        r["website_group_order"]=str(GROUP_ORDER[group])
        r["matched_keyword"]="MANUAL_OVERRIDE"
        r["mapping_confidence"]="MANUAL_REVIEW"
        r["suggestion_source"]="MANUAL_OVERRIDE"
        r["needs_review"]="NO"
        reason=(ov.get("review_reason") or "Đã duyệt thủ công").strip()
        r["review_reason"]="Đã duyệt: "+reason

    fields=list(raw[0].keys())
    write_csv(Path(args.final),raw,fields)
    write_csv(Path(args.unresolved),unresolved,fields)
    if unresolved:
        print(f"CÒN {len(unresolved)} MÃ CẦN DUYỆT:", ", ".join(r.get('symbol','') for r in unresolved))
        print("Gửi tools/financial/work/industry_unresolved.csv cho ChatGPT; sau đó bổ sung tools/financial/config/industry_overrides.csv và chạy lại.")
        sys.exit(2)
    print(f"FINAL INDUSTRY OK: {len(raw)} mã | unresolved 0")
    print("Final:", Path(args.final).resolve())

if __name__=="__main__":main()
