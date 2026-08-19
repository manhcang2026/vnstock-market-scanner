from __future__ import annotations
import argparse, csv
from pathlib import Path

def read_csv(path: Path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["symbol","exchange","organ_name","en_organ_name"])
        w.writeheader(); w.writerows(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", default="config/watchlist.csv")
    ap.add_argument("--existing", default="tools/financial/data/existing_symbols_current.csv")
    ap.add_argument("--out", default="tools/financial/data/missing_symbols_current.csv")
    ap.add_argument("--expected-universe", type=int, default=800)
    ap.add_argument("--expected-existing", type=int, default=257)
    args = ap.parse_args()

    watch = read_csv(Path(args.watchlist))
    by = {(r.get("symbol") or "").strip().upper(): r for r in watch if (r.get("symbol") or "").strip()}
    existing = {(r.get("symbol") or "").strip().upper() for r in read_csv(Path(args.existing)) if (r.get("symbol") or "").strip()}

    if len(by) != args.expected_universe:
        raise RuntimeError(f"Universe phải {args.expected_universe}, hiện {len(by)}")
    overlap = existing & set(by)
    if len(overlap) != args.expected_existing:
        raise RuntimeError(f"Existing overlap phải {args.expected_existing}, hiện {len(overlap)}")

    targets = sorted(set(by) - overlap)
    expected_missing = args.expected_universe - args.expected_existing
    if len(targets) != expected_missing:
        raise RuntimeError(f"Missing phải {expected_missing}, hiện {len(targets)}")

    rows = []
    for s in targets:
        r = by[s]
        rows.append({
            "symbol": s,
            "exchange": r.get("exchange",""),
            "organ_name": r.get("organ_name",""),
            "en_organ_name": r.get("en_organ_name",""),
        })
    write_csv(Path(args.out), rows)
    print(f"Universe: {len(by)} | existing: {len(overlap)} | missing: {len(targets)}")
    print("Targets:", Path(args.out).resolve())

if __name__ == "__main__":
    main()
