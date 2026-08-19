from __future__ import annotations

import argparse
import csv
import re
import time
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://finance.vietstock.vn"
DELAY = 0.70
TIMEOUT = 30
MAX_ATTEMPTS = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Giữ taxonomy tương thích pipeline 258 mã cũ.
GROUP_ORDER = {
    "Ngân hàng": 1,
    "Chứng khoán": 2,
    "Bảo hiểm": 3,
    "Bất động sản": 4,
    "Thép": 5,
    "Dầu khí": 6,
    "Điện": 7,
    "Bán lẻ": 8,
    "Công nghệ": 9,
    "Hóa chất": 10,
    "Phân bón": 11,
    "Thủy sản": 12,
    "Dệt may": 13,
    "Cảng & Logistics": 14,
    "Xây dựng": 15,
    "Vật liệu xây dựng": 16,
    "Hàng không": 17,
    "Thực phẩm & đồ uống": 18,
    "Dược & Y tế": 19,
    "Cao su": 20,
    "Nông nghiệp": 21,
    "Nước": 22,
    "Viễn thông": 23,
    "Gỗ & Giấy": 24,
    "Gỗ & Nội thất": 25,
    "Ô tô & Phụ tùng": 26,
    "Du lịch & Giải trí": 27,
    "Truyền thông": 28,
    "Thiết bị điện": 29,
    "Máy móc & Thiết bị": 30,
    "Bao bì": 31,
    "Kim loại & Khoáng sản": 32,
    "Thương mại & Phân phối": 33,
    "Dịch vụ công nghiệp": 34,
    "Dịch vụ tiêu dùng": 35,
    "Hàng tiêu dùng lâu bền": 36,
    "Đa ngành": 37,
    "Tài chính khác": 38,
    "Khác / cần duyệt": 99,
}

# Quy tắc cụ thể trước, rộng sau.
GROUP_RULES = [
    ("Ngân hàng", ["ngan hang", "banks", "credit institutions"]),
    ("Chứng khoán", ["chung khoan", "securities", "thi truong von", "capital markets"]),
    ("Bảo hiểm", ["bao hiem", "insurance"]),
    ("Bất động sản", ["bat dong san", "real estate"]),
    ("Thép", ["thep", "steel", "sat va thep"]),
    ("Dầu khí", ["dau khi", "oil & gas", "oil and gas", "petroleum", "gas distribution"]),
    ("Bán lẻ", ["ban le", "retail"]),
    ("Công nghệ", ["cong nghe thong tin", "phan mem", "information technology", "software"]),
    ("Phân bón", ["phan bon", "fertilizer"]),
    ("Thủy sản", ["thuy san", "hai san", "seafood", "aquaculture"]),
    ("Dệt may", ["det may", "textile", "apparel", "may mac"]),
    ("Cảng & Logistics", ["cang", "logistics", "van tai bien", "hang hai", "kho bai", "transportation infrastructure"]),
    ("Hàng không", ["hang khong", "airlines", "airport", "aviation"]),
    ("Vật liệu xây dựng", ["vat lieu xay dung", "xi mang", "cement", "gach", "construction materials"]),
    ("Xây dựng", ["ky thuat xay dung", "xay dung", "construction & engineering", "construction"]),
    ("Thực phẩm & đồ uống", ["thuc pham", "do uong", "food", "beverage", "bia", "sua"]),
    ("Dược & Y tế", ["duoc", "y te", "cham soc suc khoe", "health care", "pharmaceutical"]),
    ("Ô tô & Phụ tùng", ["o to", "phu tung", "automobile", "auto components"]),
    ("Cao su", ["cao su", "rubber"]),
    ("Nông nghiệp", ["nong nghiep", "chan nuoi", "agriculture", "farming"]),
    ("Nước", ["cap nuoc", "nuoc sach", "water utilities", "water"]),
    ("Viễn thông", ["vien thong", "telecommunication"]),
    ("Gỗ & Nội thất", ["noi that", "furnishings", "home furnishings"]),
    ("Gỗ & Giấy", ["go va giay", "go & giay", "giay", "paper", "forest products"]),
    ("Du lịch & Giải trí", ["du lich", "giai tri", "hotels", "resorts", "leisure"]),
    ("Truyền thông", ["truyen thong", "media", "publishing"]),
    ("Thiết bị điện", ["thiet bi dien", "electrical components", "electrical equipment"]),
    ("Máy móc & Thiết bị", ["may moc", "machinery", "industrial machinery"]),
    ("Bao bì", ["bao bi", "packaging"]),
    ("Kim loại & Khoáng sản", ["khai khoang", "luyen kim", "kim loai", "khoang san", "metals & mining", "mining"]),
    ("Thương mại & Phân phối", ["nha phan phoi", "phan phoi", "trading companies", "distributors"]),
    ("Dịch vụ công nghiệp", ["dich vu chuyen nghiep", "professional services", "commercial services"]),
    ("Dịch vụ tiêu dùng", ["dich vu tieu dung", "consumer services"]),
    ("Hàng tiêu dùng lâu bền", ["hang tieu dung lau ben", "consumer durables"]),
    ("Đa ngành", ["tap doan da nganh", "conglomerates", "multi-sector holdings"]),
    ("Tài chính khác", ["tin dung phi ngan hang", "consumer finance", "specialized finance"]),
    ("Hóa chất", ["hoa chat", "chemical"]),
    # Điện để sau "Thiết bị điện" để tránh bắt nhầm.
    ("Điện", ["dien luc", "san xuat dien", "power generation", "electric utilities", "independent power"]),
]

FIELDS = [
    "symbol",
    "exchange",
    "company_name",
    "display_name",
    "en_company_name",
    "watchlist_sector_l1",
    "watchlist_sector_l2",
    "watchlist_sector_l3",
    "vietstock_sector_l1",
    "vietstock_sector_l2",
    "vietstock_sector_l3",
    "website_group",
    "financial_model",
    "website_group_order",
    "matched_keyword",
    "mapping_confidence",
    "suggestion_source",
    "source_url",
    "status",
    "needs_review",
]


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text or ""))
    return "".join(
        c for c in text if unicodedata.category(c) != "Mn"
    ).lower().strip()


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def extract_industry(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    for text_node in soup.find_all(string=re.compile(r"Ngành\s*:", re.I)):
        parent = text_node.parent
        if not parent:
            continue

        for container in (parent, parent.parent):
            if not container:
                continue
            anchors = container.find_all("a")
            names = [
                re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
                for a in anchors
                if a.get_text(strip=True)
            ]
            names = [x for x in names if x and len(x) <= 80]
            unique = []
            seen = set()
            for x in names:
                if x not in seen:
                    seen.add(x)
                    unique.append(x)
            if unique:
                return unique[:3]

    text = soup.get_text(" ", strip=True)
    m = re.search(
        r"Ngành:\s+(.{1,250}?)(?:\s+\d{1,3}(?:,\d{3}){1,3}"
        r"|\s+Xem nhiều|\s+HOSE|\s+HNX|\s+UPCOM)",
        text,
        re.I,
    )
    return [m.group(1).strip()] if m else []


def classify_group(levels: list[str]) -> tuple[str, str]:
    haystack = strip_accents(" | ".join(levels))
    for group, keywords in GROUP_RULES:
        for kw in keywords:
            if strip_accents(kw) in haystack:
                return group, kw
    return "Khác / cần duyệt", ""


def financial_model(group: str) -> str:
    if group == "Ngân hàng":
        return "BANK"
    if group == "Chứng khoán":
        return "SECURITIES"
    if group == "Bảo hiểm":
        return "INSURANCE"
    return "NORMAL"


def fetch_html(session: requests.Session, url: str) -> str:
    last = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            last = exc
            if attempt >= MAX_ATTEMPTS:
                break
            wait = 2 * attempt
            print(f" retry sau {wait}s", end="", flush=True)
            time.sleep(wait)
    raise RuntimeError(str(last))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", default="config/watchlist.csv")
    ap.add_argument(
        "--existing",
        default="tools/financial/data/existing_symbols_258.csv",
    )
    ap.add_argument(
        "--out",
        default="tools/financial/output/industry_new_542_raw.csv",
    )
    ap.add_argument(
        "--review",
        default="tools/financial/output/industry_review_542.csv",
    )
    args = ap.parse_args()

    watchlist_path = Path(args.watchlist)
    if not watchlist_path.exists():
        fallback = Path("tools/financial/data/watchlist_800_snapshot.csv")
        if fallback.exists():
            watchlist_path = fallback
        else:
            raise FileNotFoundError("Không thấy config/watchlist.csv")

    watch_rows = read_csv(watchlist_path)
    by_symbol = {
        (r.get("symbol") or "").strip().upper(): r
        for r in watch_rows
        if (r.get("symbol") or "").strip()
    }

    existing = {
        (r.get("symbol") or "").strip().upper()
        for r in read_csv(Path(args.existing))
        if (r.get("symbol") or "").strip()
    }
    targets = sorted(set(by_symbol) - existing)

    print(f"Universe hiện tại : {len(by_symbol)} mã")
    print(f"Đã có metadata    : {len(existing & set(by_symbol))} mã")
    print(f"Cần phân loại mới : {len(targets)} mã\n")

    out_path = Path(args.out)
    previous = {}
    if out_path.exists():
        for r in read_csv(out_path):
            sym = (r.get("symbol") or "").strip().upper()
            if sym:
                previous[sym] = r

    # Chỉ coi OK/NO_INDUSTRY là đã gọi Vietstock xong.
    # ERROR sẽ tự retry khi chạy lại.
    done = {
        s for s, r in previous.items()
        if str(r.get("status", "")).startswith(("OK", "NO_INDUSTRY"))
    }

    result = dict(previous)
    session = requests.Session()

    pending = [s for s in targets if s not in done]
    print(f"Resume: đã xử lý {len(done)}/{len(targets)}, còn {len(pending)}.\n")

    for idx, symbol in enumerate(pending, 1):
        wr = by_symbol[symbol]
        url = f"{BASE}/{symbol}/ho-so-doanh-nghiep.htm"
        print(f"[{idx}/{len(pending)}] {symbol}", end=" ... ", flush=True)

        watch_levels = [
            wr.get("sector1_vn", ""),
            wr.get("sector2_vn", ""),
            wr.get("sector3_vn", ""),
        ]
        watch_group, watch_kw = classify_group(watch_levels)

        try:
            html = fetch_html(session, url)
            levels = extract_industry(html)
            vs_group, vs_kw = classify_group(levels)

            # Vietstock là nguồn chính. Nếu không map được, dùng watchlist
            # làm fallback nhưng bắt buộc needs_review=YES.
            if vs_group != "Khác / cần duyệt":
                group = vs_group
                kw = vs_kw
                confidence = "VIETSTOCK_RULE"
                suggestion_source = "VIETSTOCK"
                needs_review = "NO"
            elif watch_group != "Khác / cần duyệt":
                group = watch_group
                kw = watch_kw
                confidence = "WATCHLIST_FALLBACK"
                suggestion_source = "WATCHLIST"
                needs_review = "YES"
            else:
                group = "Khác / cần duyệt"
                kw = ""
                confidence = "REVIEW"
                suggestion_source = ""
                needs_review = "YES"

            # Bảo vệ 3 mô hình tài chính đặc thù bằng cả 2 nguồn.
            combined = strip_accents(" | ".join(levels + watch_levels))
            if "ngan hang" in combined:
                group = "Ngân hàng"
            elif "thi truong von" in combined or "chung khoan" in combined:
                group = "Chứng khoán"
            elif "bao hiem" in combined:
                group = "Bảo hiểm"

            row = {
                "symbol": symbol,
                "exchange": wr.get("exchange", ""),
                "company_name": wr.get("organ_name", ""),
                "display_name": wr.get("short_name", "") or wr.get("organ_name", ""),
                "en_company_name": wr.get("en_organ_name", ""),
                "watchlist_sector_l1": wr.get("sector1_vn", ""),
                "watchlist_sector_l2": wr.get("sector2_vn", ""),
                "watchlist_sector_l3": wr.get("sector3_vn", ""),
                "vietstock_sector_l1": levels[0] if len(levels) > 0 else "",
                "vietstock_sector_l2": levels[1] if len(levels) > 1 else "",
                "vietstock_sector_l3": levels[2] if len(levels) > 2 else "",
                "website_group": group,
                "financial_model": financial_model(group),
                "website_group_order": GROUP_ORDER.get(group, 99),
                "matched_keyword": kw,
                "mapping_confidence": confidence,
                "suggestion_source": suggestion_source,
                "source_url": url,
                "status": "OK" if levels else "NO_INDUSTRY",
                "needs_review": needs_review if levels else "YES",
            }
            print(
                f"{row['vietstock_sector_l1']} > "
                f"{row['vietstock_sector_l2']} > "
                f"{row['vietstock_sector_l3']} => {group}"
            )
        except Exception as exc:
            row = {
                "symbol": symbol,
                "exchange": wr.get("exchange", ""),
                "company_name": wr.get("organ_name", ""),
                "display_name": wr.get("short_name", "") or wr.get("organ_name", ""),
                "en_company_name": wr.get("en_organ_name", ""),
                "watchlist_sector_l1": wr.get("sector1_vn", ""),
                "watchlist_sector_l2": wr.get("sector2_vn", ""),
                "watchlist_sector_l3": wr.get("sector3_vn", ""),
                "vietstock_sector_l1": "",
                "vietstock_sector_l2": "",
                "vietstock_sector_l3": "",
                "website_group": watch_group,
                "financial_model": financial_model(watch_group),
                "website_group_order": GROUP_ORDER.get(watch_group, 99),
                "matched_keyword": watch_kw,
                "mapping_confidence": "ERROR_RETRY",
                "suggestion_source": "WATCHLIST" if watch_group != "Khác / cần duyệt" else "",
                "source_url": url,
                "status": f"ERROR: {exc}",
                "needs_review": "YES",
            }
            print("LỖI:", exc)

        result[symbol] = row
        ordered = [result[s] for s in targets if s in result]
        write_csv(out_path, ordered)
        review_rows = [
            r for r in ordered
            if r.get("needs_review") == "YES"
            or str(r.get("status", "")).startswith("ERROR")
        ]
        write_csv(Path(args.review), review_rows)
        time.sleep(DELAY)

    ordered = [result[s] for s in targets if s in result]
    review_rows = [
        r for r in ordered
        if r.get("needs_review") == "YES"
        or str(r.get("status", "")).startswith("ERROR")
    ]

    print("\n==============================")
    print("STEP 1 XONG")
    print("Raw   :", out_path.resolve())
    print("Review:", Path(args.review).resolve())
    print(f"Đã có : {len(ordered)}/{len(targets)} mã")
    print(f"Cần xem lại: {len(review_rows)} mã")
    print("Gửi 2 file output này cho ChatGPT để duyệt trước STEP 2.")


if __name__ == "__main__":
    main()
