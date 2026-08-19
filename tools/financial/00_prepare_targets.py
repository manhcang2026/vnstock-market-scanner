from __future__ import annotations
import argparse, csv, hashlib, shutil
from pathlib import Path

WATCH_FIELDS = ["symbol", "exchange", "organ_name", "en_organ_name"]

def read_csv(path: Path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def write_csv(path: Path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

def symbols_from_file(path: Path):
    if not path.exists():
        return []
    rows = read_csv(path)
    return sorted({(r.get("symbol") or "").strip().upper() for r in rows if (r.get("symbol") or "").strip()})

def reset_downstream(work: Path):
    for p in [work/"industry_raw.csv", work/"industry_review.csv", work/"industry_final.csv", work/"industry_unresolved.csv"]:
        if p.exists(): p.unlink()
    for d in [work/"fundamental", work/"production", work/"sql"]:
        if d.exists(): shutil.rmtree(d)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", default="config/watchlist.csv")
    ap.add_argument("--symbols", default="tools/financial/input/symbols_to_add.csv")
    ap.add_argument("--work-dir", default="tools/financial/work")
    ap.add_argument("--all", action="store_true", help="Chạy toàn bộ watchlist thay vì danh sách input")
    args = ap.parse_args()

    watch_rows = read_csv(Path(args.watchlist))
    watch = {(r.get("symbol") or "").strip().upper(): r for r in watch_rows if (r.get("symbol") or "").strip()}
    if not watch:
        raise RuntimeError("Watchlist rỗng")

    wanted = sorted(watch) if args.all else symbols_from_file(Path(args.symbols))
    if not wanted:
        raise RuntimeError(
            "Chưa có mã cần xử lý. Điền ticker vào tools/financial/input/symbols_to_add.csv "
            "hoặc chạy với --all nếu thật sự muốn refresh toàn bộ."
        )

    missing = [s for s in wanted if s not in watch]
    if missing:
        raise RuntimeError("Các mã chưa có trong config/watchlist.csv: " + ", ".join(missing))

    rows=[]
    for s in wanted:
        r=watch[s]
        rows.append({
            "symbol": s,
            "exchange": r.get("exchange", ""),
            "organ_name": r.get("organ_name", ""),
            "en_organ_name": r.get("en_organ_name", ""),
        })

    work=Path(args.work_dir); work.mkdir(parents=True, exist_ok=True)
    digest=hashlib.sha256("\n".join(wanted).encode("utf-8")).hexdigest()
    hash_file=work/"targets.sha256"
    old_hash=hash_file.read_text(encoding="utf-8").strip() if hash_file.exists() else ""
    if old_hash and old_hash != digest:
        print("Danh sách target đã đổi -> dọn output cũ để tránh trộn dữ liệu.")
        reset_downstream(work)

    write_csv(work/"targets.csv", rows, WATCH_FIELDS)
    hash_file.write_text(digest, encoding="utf-8")
    print(f"Watchlist: {len(watch)} | targets: {len(rows)}")
    print("Targets:", (work/"targets.csv").resolve())

if __name__ == "__main__":
    main()
