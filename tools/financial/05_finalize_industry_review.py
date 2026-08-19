from __future__ import annotations
import csv
from pathlib import Path

RAW = Path("tools/financial/output/industry_new_current_raw.csv")
OUT = Path("tools/financial/output/industry_new_current_final.csv")
EXPECTED_ROWS = 543
EXPECTED_VERSION = "v2_20260820"

GROUP_ORDER = {
    "Ngân hàng": 1, "Chứng khoán": 2, "Bảo hiểm": 3, "Bất động sản": 4,
    "Thép": 5, "Dầu khí": 6, "Điện": 7, "Bán lẻ": 8, "Công nghệ": 9,
    "Hóa chất": 10, "Phân bón": 11, "Thủy sản": 12, "Dệt may": 13,
    "Cảng & Logistics": 14, "Xây dựng": 15, "Vật liệu xây dựng": 16,
    "Hàng không": 17, "Thực phẩm & đồ uống": 18, "Dược & Y tế": 19,
    "Cao su": 20, "Nông nghiệp": 21, "Nước": 22, "Viễn thông": 23,
    "Gỗ & Giấy": 24, "Gỗ & Nội thất": 25, "Ô tô & Phụ tùng": 26,
    "Du lịch & Giải trí": 27, "Truyền thông": 28, "Thiết bị điện": 29,
    "Máy móc & Thiết bị": 30, "Bao bì": 31, "Kim loại & Khoáng sản": 32,
    "Thương mại & Phân phối": 33, "Dịch vụ công nghiệp": 34,
    "Dịch vụ tiêu dùng": 35, "Hàng tiêu dùng lâu bền": 36,
    "Đa ngành": 37, "Tài chính khác": 38, "Khác / cần duyệt": 99,
}

# 18 mã còn review sau classifier v2.
MANUAL = {
    "GGG": ("Ô tô & Phụ tùng", "Vietstock: Xe và linh kiện > Xe"),
    "HEP": ("Dịch vụ công nghiệp", "Môi trường và công trình đô thị"),
    "ILB": ("Cảng & Logistics", "ICD Tân Cảng - Long Bình"),
    "KTL": ("Ô tô & Phụ tùng", "Vietstock: Xe và linh kiện > Linh kiện xe"),
    "LIX": ("Hóa chất", "Bột giặt / sản phẩm chăm sóc gia đình"),
    "NET": ("Hóa chất", "Bột giặt / sản phẩm chăm sóc gia đình"),
    "PEG": ("Dầu khí", "Thiết bị và dịch vụ năng lượng"),
    "POS": ("Dầu khí", "PTSC - vận hành/xây lắp dầu khí"),
    "PSB": ("Dầu khí", "PTSC - cảng kỹ thuật dầu khí"),
    "PV2": ("Tài chính khác", "Vietstock: Dịch vụ tài chính"),
    "PVB": ("Dầu khí", "Bọc ống dầu khí"),
    "PVD": ("Dầu khí", "Khoan và dịch vụ khoan dầu khí"),
    "PVY": ("Dầu khí", "Chế tạo giàn khoan dầu khí"),
    "SRC": ("Ô tô & Phụ tùng", "Vietstock: Xe và linh kiện > Linh kiện xe"),
    "SZE": ("Dịch vụ công nghiệp", "Dịch vụ môi trường"),
    "TLG": ("Hàng tiêu dùng lâu bền", "Văn phòng phẩm / sản phẩm tiêu dùng"),
    "TMT": ("Ô tô & Phụ tùng", "Vietstock: Xe và linh kiện > Xe"),
    "VEF": ("Dịch vụ công nghiệp", "Hội chợ triển lãm / dịch vụ thương mại"),
}

STALE_57 = set("""AMD ART AVF BT6 CLG DAG DPS DTE FLC GTT HAI HLA HVG IBC ITA KLF KPF KSH NHP NTB PPI PQN PSG PSH PVA PXC RDP SJF SSN TBH TGG TNA TOP TTB BCG BII CMP ING KTC NS2 TCK VCW VOC CCT LGC ARM BCR HTP IDP LTG SHG SLD TNV TTE UXC VFC VTX""".split())
NEW_57 = set("""MVN DMX HTT HU3 VE3 FOC TNS CMN PXM AAM LBE TSB TXM JOS HEP MFS PSL PTV QNP SDK LM8 EFI INN KTL CDR BTW LDP DTI HPP VTK ALV HAS TS3 TGP YBM TA9 PBP VIM SIV DC2 VLS C32 SLS DHA NSC DNM PGN TCW TCT ULG NSH SKH RCL LHC GIC TDB L35""".split())

def read_csv(path: Path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def write_csv(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def main():
    if not RAW.exists():
        raise FileNotFoundError(RAW)
    rows = read_csv(RAW)
    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(f"Raw phải {EXPECTED_ROWS} mã, hiện {len(rows)}")

    symbols = {(r.get("symbol") or "").strip().upper() for r in rows}
    if len(symbols) != EXPECTED_ROWS:
        raise RuntimeError("Raw có symbol trùng/rỗng")

    versions = {(r.get("classifier_version") or "").strip() for r in rows}
    if versions != {EXPECTED_VERSION}:
        raise RuntimeError(f"Classifier version sai: {versions}")

    old = sorted(STALE_57 & symbols)
    if old:
        raise RuntimeError("Còn mã stale: " + ", ".join(old))
    missing_new = sorted(NEW_57 - symbols)
    if missing_new:
        raise RuntimeError("Thiếu mã final mới: " + ", ".join(missing_new))

    review_before = [
        (r.get("symbol") or "").strip().upper()
        for r in rows
        if (r.get("needs_review") or "").strip().upper() == "YES"
    ]
    unexpected = sorted(set(review_before) - set(MANUAL))
    missing_manual = sorted(set(MANUAL) - set(review_before))
    if unexpected:
        raise RuntimeError("Có review ngoài danh sách 18 mã đã duyệt: " + ", ".join(unexpected))
    if missing_manual:
        raise RuntimeError("Thiếu review dự kiến: " + ", ".join(missing_manual))

    for r in rows:
        s = (r.get("symbol") or "").strip().upper()
        if s not in MANUAL:
            continue
        group, reason = MANUAL[s]
        r["website_group"] = group
        r["financial_model"] = "NORMAL"
        r["website_group_order"] = str(GROUP_ORDER[group])
        r["matched_keyword"] = "MANUAL_REVIEW"
        r["mapping_confidence"] = "MANUAL_REVIEW"
        r["suggestion_source"] = "VIETSTOCK+MANUAL"
        r["needs_review"] = "NO"
        r["review_reason"] = "Đã duyệt: " + reason

    remaining = [
        (r.get("symbol") or "").strip().upper()
        for r in rows
        if (r.get("needs_review") or "").strip().upper() == "YES"
        or (r.get("website_group") or "").strip() == "Khác / cần duyệt"
    ]
    if remaining:
        raise RuntimeError("Vẫn còn mã cần review: " + ", ".join(remaining))

    fields = list(rows[0].keys())
    write_csv(OUT, rows, fields)

    print("=== FINAL INDUSTRY MASTER OK ===")
    print("Rows:", len(rows))
    print("Classifier:", EXPECTED_VERSION)
    print("Manual review resolved:", len(MANUAL))
    print("Stale 57 present:", len(STALE_57 & symbols))
    print("Final new 57 present:", len(NEW_57 & symbols))
    print("Needs review remaining:", len(remaining))
    print("Output:", OUT.resolve())

if __name__ == "__main__":
    main()
