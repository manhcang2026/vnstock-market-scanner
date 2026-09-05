from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import backfill_daily_history as backfill
from common import load_watchlist


LOOKBACK_DAYS = 500
TOLERANCE = 0.0001
REPORT_JSON = Path("baseline_compare_report.json")
REPORT_CSV = Path("baseline_compare_report.csv")


def parse_symbols(raw: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in raw.replace(";", ",").split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def load_history(symbol: str) -> list[dict[str, Any]]:
    response = backfill.supabase_request(
        "GET",
        "daily_history",
        params={
            "select": "symbol,exchange,trading_date,close,volume,source",
            "symbol": f"eq.{symbol}",
            "order": "trading_date.asc",
            "limit": "1000",
        },
    )
    return response.json()


def load_production() -> dict[str, dict[str, Any]]:
    response = backfill.supabase_request(
        "GET",
        "latest_daily_baseline",
        params={
            "select": (
                "symbol,exchange,trading_date,previous_close,"
                "ma10,ma10_sessions,ma200,ma200_sessions,"
                "avg_volume_10,avg_volume_sessions,source,"
                "updated_at,data_status"
            ),
            "order": "symbol.asc",
            "limit": "1000",
        },
    )
    result: dict[str, dict[str, Any]] = {}
    for row in response.json():
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol:
            result[symbol] = row
    return result


def calculate_local(symbol: str, rows: list[dict[str, Any]], run_date: date) -> dict[str, Any]:
    start = run_date - timedelta(days=LOOKBACK_DAYS)
    prepared: list[tuple[date, float, float]] = []
    for row in rows:
        try:
            d = date.fromisoformat(str(row["trading_date"]))
            close = float(row["close"])
            volume = float(row["volume"])
        except (KeyError, TypeError, ValueError):
            continue
        if start <= d < run_date and close > 0 and volume >= 0:
            prepared.append((d, close, volume))

    prepared.sort(key=lambda item: item[0])
    if not prepared:
        raise RuntimeError(f"{symbol}: no local rows in 500d window")

    count = len(prepared)
    m10n = min(count, 10)
    m200n = min(count, 200)
    v10n = min(count, 10)
    latest = prepared[-1]

    closes = [item[1] for item in prepared]
    volumes = [item[2] for item in prepared]

    return {
        "trading_date": latest[0].isoformat(),
        "previous_close": round(latest[1], 4),
        "ma10": round(sum(closes[-m10n:]) / m10n, 4),
        "ma10_sessions": m10n,
        "ma200": round(sum(closes[-m200n:]) / m200n, 4),
        "ma200_sessions": m200n,
        "avg_volume_10": round(sum(volumes[-v10n:]) / v10n, 4),
        "avg_volume_sessions": v10n,
        "local_window_sessions": count,
    }


def value_equal(left: Any, right: Any) -> bool:
    try:
        return abs(float(left) - float(right)) <= TOLERANCE
    except (TypeError, ValueError):
        return False


def write_report(report: dict[str, Any]) -> None:
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    rows = report["results"]
    if not rows:
        REPORT_CSV.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with REPORT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    raw_date = os.getenv("COMPARE_RUN_DATE", "").strip()
    if not raw_date:
        raise RuntimeError("COMPARE_RUN_DATE bat buoc.")
    run_date = date.fromisoformat(raw_date)

    backfill.verify_supabase_config()

    watchlist = load_watchlist()
    all_symbols = sorted(
        str(row.symbol).strip().upper()
        for row in watchlist.itertuples(index=False)
    )
    explicit = parse_symbols(os.getenv("COMPARE_SYMBOLS", "").strip())
    symbols = explicit or all_symbols
    production = load_production()

    report: dict[str, Any] = {
        "compare_run_date": run_date.isoformat(),
        "selected": len(symbols),
        "production_rows": len(production),
        "counts": {
            "exact": 0,
            "mismatch": 0,
            "missing_production": 0,
            "local_error": 0,
            "production_not_ok": 0,
        },
        "results": [],
    }

    compare_fields = (
        "trading_date",
        "previous_close",
        "ma10",
        "ma10_sessions",
        "ma200",
        "ma200_sessions",
        "avg_volume_10",
        "avg_volume_sessions",
    )

    for index, symbol in enumerate(symbols, start=1):
        row: dict[str, Any] = {
            "symbol": symbol,
            "status": "",
            "production_source": "",
            "production_data_status": "",
            "diff_fields": "",
            "error": "",
        }
        prod = production.get(symbol)
        if prod is None:
            row["status"] = "MISSING_PRODUCTION"
            report["counts"]["missing_production"] += 1
            report["results"].append(row)
            print(f"[{index}/{len(symbols)}] {symbol} -> MISSING_PRODUCTION")
            continue

        row["production_source"] = prod.get("source")
        row["production_data_status"] = prod.get("data_status")
        if str(prod.get("data_status") or "").upper() != "OK":
            report["counts"]["production_not_ok"] += 1

        try:
            local = calculate_local(symbol, load_history(symbol), run_date)
            diffs: list[str] = []
            for field in compare_fields:
                lv = local.get(field)
                pv = prod.get(field)
                if field == "trading_date":
                    equal = str(lv) == str(pv)
                elif field.endswith("_sessions"):
                    equal = int(lv) == int(pv)
                else:
                    equal = value_equal(lv, pv)

                row[f"local_{field}"] = lv
                row[f"prod_{field}"] = pv
                if not equal:
                    diffs.append(field)

            if diffs:
                row["status"] = "MISMATCH"
                row["diff_fields"] = ",".join(diffs)
                report["counts"]["mismatch"] += 1
                print(
                    f"[{index}/{len(symbols)}] {symbol} -> MISMATCH "
                    + ",".join(diffs)
                )
            else:
                row["status"] = "EXACT"
                report["counts"]["exact"] += 1
                print(f"[{index}/{len(symbols)}] {symbol} -> EXACT")

        except Exception as exc:
            row["status"] = "LOCAL_ERROR"
            row["error"] = f"{type(exc).__name__}: {exc}"
            report["counts"]["local_error"] += 1
            print(f"[{index}/{len(symbols)}] {symbol} -> {row['error']}")

        report["results"].append(row)
        write_report(report)

    print(
        "\nCOMPARE SUMMARY: "
        + ", ".join(f"{k}={v}" for k, v in report["counts"].items())
    )

    # Green only when every selected symbol matches production exactly and
    # production itself reports OK for every symbol.
    if (
        report["counts"]["mismatch"]
        or report["counts"]["missing_production"]
        or report["counts"]["local_error"]
        or report["counts"]["production_not_ok"]
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
