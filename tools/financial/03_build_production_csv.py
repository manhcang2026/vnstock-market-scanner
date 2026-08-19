from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

CORE_FIELDS = [
    "income_bil_vnd",
    "pbt_bil_vnd",
    "net_profit_bil_vnd",
    "total_assets_bil_vnd",
    "equity_bil_vnd",
    "roea_pct",
    "roaa_pct",
    "eps_vnd",
    "pb",
]


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    if not rows:
        return
    fields = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                fields.append(k)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def blank(v):
    return v is None or str(v).strip() == ""


def expected_latest_period(today=None):
    today = today or date.today()
    y, m = today.year, today.month
    if m <= 2:
        return y - 1, 4
    if m <= 5:
        return y, 1
    if m <= 8:
        return y, 2
    if m <= 11:
        return y, 3
    return y, 3


def quarter_index(year, q):
    return year * 4 + q


def freshness(row, target_y, target_q):
    try:
        y = int(float(row.get("year") or 0))
        q = int(str(row.get("quarter") or "Q0").replace("Q", ""))
    except Exception:
        return "STALE"
    age = quarter_index(target_y, target_q) - quarter_index(y, q)
    if age <= 0:
        return "CURRENT"
    if age == 1:
        return "LAGGING"
    return "STALE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--summary",
        default="tools/financial/output/fundamental_542/fundamental_summary_542.csv",
    )
    ap.add_argument(
        "--out-dir",
        default="tools/financial/output/production_542",
    )
    args = ap.parse_args()

    source = Path(args.summary)
    if not source.exists():
        raise FileNotFoundError(source)

    rows = read_csv(source)
    if not rows:
        raise RuntimeError("Summary rỗng")

    target_y, target_q = expected_latest_period()
    print(f"Kỳ kỳ vọng hiện tại: {target_y}Q{target_q}")

    enriched = []
    for src in rows:
        r = dict(src)
        missing = [f for f in CORE_FIELDS if blank(r.get(f))]
        r["freshness_status"] = freshness(r, target_y, target_q)
        r["data_status"] = "COMPLETE" if not missing else "PARTIAL"
        r["missing_core_fields"] = "|".join(missing) if missing else ""
        enriched.append(r)

    # dedupe symbol + period
    by_key = {}
    for r in enriched:
        by_key[(r.get("symbol", "").upper(), r.get("period", ""))] = r
    quarterly = list(by_key.values())

    def pkey(r):
        try:
            return (
                int(float(r.get("year") or 0)),
                int(str(r.get("quarter") or "Q0").replace("Q", "")),
            )
        except Exception:
            return (0, 0)

    latest_map = {}
    for r in quarterly:
        sym = r.get("symbol", "").upper()
        if not sym:
            continue
        if sym not in latest_map or pkey(r) > pkey(latest_map[sym]):
            latest_map[sym] = r

    latest = []
    for sym in sorted(latest_map):
        r = dict(latest_map[sym])
        r["error_message"] = ""
        r["production_ready"] = (
            "YES" if r.get("freshness_status") == "CURRENT" else "REVIEW"
        )
        latest.append(r)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    qfile = out / "financial_quarterly_production_542.csv"
    lfile = out / "financial_latest_production_542.csv"
    write_csv(qfile, quarterly)
    write_csv(lfile, latest)

    print("Quarterly:", qfile.resolve(), len(quarterly), "rows")
    print("Latest   :", lfile.resolve(), len(latest), "symbols")
    print("COMPLETE :", sum(r["data_status"] == "COMPLETE" for r in latest))
    print("PARTIAL  :", sum(r["data_status"] == "PARTIAL" for r in latest))
    print("READY YES:", sum(r["production_ready"] == "YES" for r in latest))
    print("REVIEW   :", sum(r["production_ready"] == "REVIEW" for r in latest))


if __name__ == "__main__":
    main()
