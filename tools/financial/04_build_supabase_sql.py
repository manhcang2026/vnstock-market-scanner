from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

META_COLS = [
    "symbol", "exchange", "company_name", "display_name", "en_company_name",
    "website_group", "financial_model", "website_group_order", "metadata_status",
]

FIN_Q_COLS = [
    "symbol","website_group","financial_model","period","year","quarter",
    "report_data_id","consolidated","audit_status",
    "total_assets_bil_vnd","total_assets_bil_vnd_source",
    "equity_bil_vnd","equity_bil_vnd_source",
    "eps_vnd","eps_vnd_source","bvps_vnd","bvps_vnd_source",
    "pe","pe_source","pb","pb_source",
    "roea_pct","roea_pct_source","roaa_pct","roaa_pct_source",
    "income_bil_vnd","income_bil_vnd_source",
    "gross_profit_bil_vnd","gross_profit_bil_vnd_source",
    "pbt_bil_vnd","pbt_bil_vnd_source",
    "net_profit_bil_vnd","net_profit_bil_vnd_source",
    "parent_net_profit_bil_vnd","parent_net_profit_bil_vnd_source",
    "liabilities_bil_vnd","liabilities_bil_vnd_source",
    "gross_margin_pct","gross_margin_pct_source",
    "net_margin_pct","net_margin_pct_source",
    "debt_assets_pct","debt_assets_pct_source",
    "debt_equity_pct","debt_equity_pct_source",
    "income_qoq_pct","income_yoy_pct","profit_qoq_pct","profit_yoy_pct",
    "freshness_status","data_status","missing_core_fields",
]

FIN_L_COLS = FIN_Q_COLS + ["error_message", "production_ready"]

NUMERIC = {
    "website_group_order","year","report_data_id",
    "total_assets_bil_vnd","equity_bil_vnd","eps_vnd","bvps_vnd","pe","pb",
    "roea_pct","roaa_pct","income_bil_vnd","gross_profit_bil_vnd","pbt_bil_vnd",
    "net_profit_bil_vnd","parent_net_profit_bil_vnd","liabilities_bil_vnd",
    "gross_margin_pct","net_margin_pct","debt_assets_pct","debt_equity_pct",
    "income_qoq_pct","income_yoy_pct","profit_qoq_pct","profit_yoy_pct",
}
BOOLEAN = {"consolidated"}


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def sql_value(column, value):
    if value is None:
        return "NULL"
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return "NULL"
    if column in BOOLEAN:
        return "TRUE" if s.lower() in {"true", "1", "yes"} else "FALSE"
    if column in NUMERIC:
        try:
            n = float(s)
            if not math.isfinite(n):
                return "NULL"
            if column in {"website_group_order","year","report_data_id"}:
                return str(int(n))
            return repr(n)
        except Exception:
            return "NULL"
    return "'" + s.replace("'", "''") + "'"


def insert_sql(table, columns, rows, conflict_cols, chunk=500):
    if not rows:
        return f"-- Không có dữ liệu cho {table}\n"

    parts = [
        "begin;",
        "",
        f"-- UPSERT {len(rows)} rows vào {table}. KHÔNG DELETE / TRUNCATE.",
    ]
    for start in range(0, len(rows), chunk):
        batch = rows[start:start + chunk]
        all_cols = columns + ["updated_at"]
        parts.append(
            f"insert into public.{table} (\n  "
            + ", ".join(all_cols)
            + "\n) values"
        )
        vals = []
        for r in batch:
            row_vals = [sql_value(c, r.get(c)) for c in columns] + ["now()"]
            vals.append("  (" + ", ".join(row_vals) + ")")
        parts.append(",\n".join(vals))
        update_cols = [
            c for c in columns if c not in conflict_cols
        ]
        parts.append(
            "\non conflict (" + ", ".join(conflict_cols) + ") do update set\n  "
            + ",\n  ".join(f"{c}=excluded.{c}" for c in update_cols)
            + ",\n  updated_at=now();\n"
        )
    parts += ["commit;", ""]
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--watchlist",
        default="config/watchlist.csv",
    )
    ap.add_argument(
        "--industry",
        default="tools/financial/output/industry_new_542_final.csv",
    )
    ap.add_argument(
        "--quarterly",
        default="tools/financial/output/production_542/financial_quarterly_production_542.csv",
    )
    ap.add_argument(
        "--latest",
        default="tools/financial/output/production_542/financial_latest_production_542.csv",
    )
    ap.add_argument(
        "--out-dir",
        default="tools/financial/output/sql_542",
    )
    args = ap.parse_args()

    watch_path = Path(args.watchlist)
    if not watch_path.exists():
        watch_path = Path("tools/financial/data/watchlist_800_snapshot.csv")

    watch = {
        (r.get("symbol") or "").upper(): r
        for r in read_csv(watch_path)
        if (r.get("symbol") or "").strip()
    }
    industry_rows = read_csv(Path(args.industry))

    bad = [
        r.get("symbol")
        for r in industry_rows
        if (r.get("needs_review") or "").upper() == "YES"
        or (r.get("website_group") or "") == "Khác / cần duyệt"
    ]
    if bad:
        raise RuntimeError(
            "Còn mã chưa duyệt trong industry master: "
            + ", ".join(bad[:30])
            + (" ..." if len(bad) > 30 else "")
        )

    metadata = []
    for ir in industry_rows:
        sym = (ir.get("symbol") or "").upper()
        wr = watch.get(sym, {})
        metadata.append({
            "symbol": sym,
            "exchange": wr.get("exchange", ir.get("exchange", "")),
            "company_name": wr.get("organ_name", ir.get("company_name", "")),
            "display_name": wr.get("short_name", ir.get("display_name", "")),
            "en_company_name": wr.get("en_organ_name", ir.get("en_company_name", "")),
            "website_group": ir.get("website_group", ""),
            "financial_model": ir.get("financial_model", "NORMAL"),
            "website_group_order": ir.get("website_group_order", "99"),
            "metadata_status": "COMPLETE",
        })

    quarterly = read_csv(Path(args.quarterly))
    latest = read_csv(Path(args.latest))

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    (out / "01_stock_metadata_542.sql").write_text(
        insert_sql("stock_metadata", META_COLS, metadata, ["symbol"], 300)
        + "\nselect count(*) as stock_metadata_rows, "
          "count(distinct symbol) as stock_metadata_symbols "
          "from public.stock_metadata;\n",
        encoding="utf-8",
    )

    # Split quarterly SQL into parts <= 1000 rows for easier SQL Editor use.
    part_size = 1000
    q_files = []
    for i, start in enumerate(range(0, len(quarterly), part_size), 1):
        part_rows = quarterly[start:start + part_size]
        p = out / f"02_financial_quarterly_part{i:02d}.sql"
        p.write_text(
            insert_sql(
                "financial_quarterly",
                FIN_Q_COLS,
                part_rows,
                ["symbol", "period"],
                250,
            ),
            encoding="utf-8",
        )
        q_files.append(p.name)

    (out / "03_financial_latest_542.sql").write_text(
        insert_sql("financial_latest", FIN_L_COLS, latest, ["symbol"], 250),
        encoding="utf-8",
    )

    verify = r"""
-- CHỈ KIỂM TRA, KHÔNG GHI DỮ LIỆU.
with u as (
  select distinct symbol from public.stock_snapshot
)
select
  count(*) as universe_symbols,
  count(m.symbol) as with_metadata,
  count(f.symbol) as with_financial_latest,
  count(*) filter (where m.symbol is null) as missing_metadata,
  count(*) filter (where f.symbol is null) as missing_financial
from u
left join public.stock_metadata m using(symbol)
left join public.financial_latest f using(symbol);

select
  data_status,
  production_ready,
  count(*) as symbols
from public.financial_latest
group by data_status, production_ready
order by data_status, production_ready;

select u.symbol
from (select distinct symbol from public.stock_snapshot) u
left join public.stock_metadata m using(symbol)
where m.symbol is null
order by u.symbol;

select u.symbol
from (select distinct symbol from public.stock_snapshot) u
left join public.financial_latest f using(symbol)
where f.symbol is null
order by u.symbol;
"""
    (out / "99_verify_coverage.sql").write_text(verify.strip() + "\n", encoding="utf-8")

    print("SQL đã tạo:")
    print(" - 01_stock_metadata_542.sql")
    for x in q_files:
        print(" -", x)
    print(" - 03_financial_latest_542.sql")
    print(" - 99_verify_coverage.sql")
    print("\nKhông có DELETE/TRUNCATE. Tất cả dùng UPSERT.")


if __name__ == "__main__":
    main()
