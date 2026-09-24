from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

import backfill_daily_history as backfill
import compare_local_baseline as compare
import daily_baseline_history_shadow as shadow
import finalize_clean_history as finalize
from common import load_watchlist, now_vn


DEFAULT_SYMBOLS = "BCF,BRR,BTV,BTW,DNA,KTL,NQN,SEB,THN,VSN"
REPORT_JSON = Path("daily_history_reconcile_report.json")
REPORT_CSV = Path("daily_history_reconcile_report.csv")
CONFIRM_TOKEN = "RECONCILE"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_symbols(raw: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in raw.replace(";", ",").split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in seen:
            result.append(symbol)
            seen.add(symbol)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Targeted reconcile daily_history theo Daily Baseline production. "
            "Mac dinh DRY-RUN; fail-closed neu provider khong tai tao EXACT baseline."
        )
    )
    parser.add_argument(
        "--symbols",
        default=os.getenv("RECONCILE_SYMBOLS", DEFAULT_SYMBOLS),
        help="Danh sach ma can reconcile, phan tach bang dau phay.",
    )
    parser.add_argument(
        "--run-date",
        default=os.getenv("RECONCILE_RUN_DATE", "2026-08-27"),
        help="history_exclusive_date cua Daily Baseline can khoa (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        default=env_bool("RECONCILE_WRITE", False),
        help="Cho phep upsert target + delete extras + verify.",
    )
    parser.add_argument(
        "--confirm",
        default=os.getenv("RECONCILE_CONFIRM", ""),
        help=f"Write=true bat buoc nhap {CONFIRM_TOKEN}.",
    )
    return parser.parse_args()


def parse_run_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"RECONCILE_RUN_DATE khong hop le: {raw!r}") from exc


def load_existing_history(symbol: str) -> list[dict[str, Any]]:
    response = backfill.supabase_request(
        "GET",
        "daily_history",
        params={
            "select": "symbol,exchange,trading_date,close,volume,source,updated_at",
            "symbol": f"eq.{symbol}",
            "order": "trading_date.asc",
            "limit": "1000",
        },
    )
    rows = response.json()
    return rows if isinstance(rows, list) else []


def validate_production_snapshot(
    *,
    run_date: date,
    symbols: list[str],
    production: dict[str, dict[str, Any]],
    production_run: dict[str, Any],
) -> None:
    missing = [symbol for symbol in symbols if symbol not in production]
    if missing:
        raise RuntimeError(
            "RECONCILE SAFETY STOP: thieu production baseline: "
            + ", ".join(missing)
        )

    bad_status = [
        symbol
        for symbol in symbols
        if str(production[symbol].get("data_status") or "").upper() != "OK"
    ]
    if bad_status:
        raise RuntimeError(
            "RECONCILE SAFETY STOP: production data_status != OK: "
            + ", ".join(bad_status)
        )

    future = [
        symbol
        for symbol in symbols
        if date.fromisoformat(str(production[symbol]["trading_date"])) >= run_date
    ]
    if future:
        raise RuntimeError(
            "RECONCILE SAFETY STOP: production co trading_date >= run_date: "
            + ", ".join(future)
        )

    # Guard against accidentally reconciling to a newer Daily Baseline run.
    try:
        started = datetime.fromisoformat(str(production_run["started_at"]).replace("Z", "+00:00"))
        finished = datetime.fromisoformat(str(production_run["finished_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("RECONCILE SAFETY STOP: scan_runs timestamp khong hop le") from exc

    lower = started - timedelta(minutes=5)
    upper = finished + timedelta(minutes=5)
    wrong_generation: list[str] = []
    for symbol in symbols:
        raw = str(production[symbol].get("updated_at") or "")
        try:
            updated = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            wrong_generation.append(symbol)
            continue
        if not (lower <= updated <= upper):
            wrong_generation.append(symbol)

    if wrong_generation:
        raise RuntimeError(
            "RECONCILE SAFETY STOP: latest_daily_baseline khong thuoc run da khoa: "
            + ", ".join(wrong_generation)
        )


def target_rows_from_provider(
    *,
    symbol: str,
    exchange: str,
    run_date: date,
    profile: dict[str, Any],
    updated_at: datetime,
) -> tuple[list[dict[str, Any]], str, str]:
    history, source = backfill.get_history(symbol, run_date, profile)
    exact, detail = backfill.compare_with_production(history, profile)
    if not exact:
        raise RuntimeError(
            "Provider target mat EXACT gate sau fetch: " + detail
        )

    rows = backfill.history_rows(
        symbol=symbol,
        exchange=exchange,
        history=history,
        source=source,
        updated_at=updated_at,
    )
    if not rows:
        raise RuntimeError("Provider target rong")

    latest = date.fromisoformat(rows[-1]["trading_date"])
    if latest != profile["trading_date"]:
        raise RuntimeError(
            f"Target latest={latest} != production={profile['trading_date']}"
        )

    return rows, source, detail


def verify_target_present(
    symbol: str,
    target_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    check = finalize.compare_exact_set(load_existing_history(symbol), target_rows)
    problems: list[str] = []
    if check["missing"]:
        problems.append(f"missing={len(check['missing'])}")
    if check["value_diffs"]:
        problems.append(f"value_diff={len(check['value_diffs'])}")
    if check["source_diffs"]:
        problems.append(f"source_diff={len(check['source_diffs'])}")
    if problems:
        raise RuntimeError(
            "Target upsert verify fail truoc DELETE: " + ", ".join(problems)
        )
    return check


def verify_stored_matches_production(
    symbol: str,
    profile: dict[str, Any],
) -> str:
    rows = load_existing_history(symbol)
    if not rows:
        raise RuntimeError("Stored history rong sau reconcile")

    df = pd.DataFrame(
        {
            "time": [row.get("trading_date") for row in rows],
            "close": [row.get("close") for row in rows],
            "volume": [row.get("volume") for row in rows],
        }
    )
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = (
        df.dropna(subset=["time", "close", "volume"])
        .sort_values("time")
        .drop_duplicates("time", keep="last")
        .reset_index(drop=True)
    )
    df = df[df["time"].dt.date <= profile["trading_date"]].reset_index(drop=True)

    exact, detail = backfill.compare_with_production(df, profile)
    if not exact:
        raise RuntimeError("Stored production verify fail: " + detail)
    return detail


def write_report(report: dict[str, Any]) -> None:
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    rows = report.get("results") or []
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
    args = parse_args()
    run_date = parse_run_date(args.run_date)
    symbols = parse_symbols(args.symbols)
    if not symbols:
        raise RuntimeError("RECONCILE_SYMBOLS khong duoc de trong")

    run_at = now_vn()
    if backfill.in_market_protection_window(run_at):
        raise RuntimeError(
            "SAFETY STOP 08:20-15:10: reconcile co goi provider; "
            "khong tranh quota voi intraday."
        )

    if args.write and args.confirm.strip().upper() != CONFIRM_TOKEN:
        raise RuntimeError(
            f"WRITE SAFETY STOP: write=true bat buoc confirm={CONFIRM_TOKEN}."
        )

    backfill.verify_supabase_config()
    backfill.verify_vnstock_api_access()

    watchlist = load_watchlist()
    exchanges = {
        str(row.symbol).strip().upper(): str(row.exchange).strip().upper()
        for row in watchlist.itertuples(index=False)
    }
    unknown = [symbol for symbol in symbols if symbol not in exchanges]
    if unknown:
        raise RuntimeError(
            "Symbol khong nam trong scanner universe: " + ", ".join(unknown)
        )

    production_run = shadow.ensure_matching_production_success(
        run_date, len(watchlist)
    )
    production = compare.load_production()
    validate_production_snapshot(
        run_date=run_date,
        symbols=symbols,
        production=production,
        production_run=production_run,
    )
    profiles = backfill.load_baseline_profiles()

    report: dict[str, Any] = {
        "run_at": run_at.isoformat(),
        "run_date": run_date.isoformat(),
        "write": args.write,
        "confirm_required": CONFIRM_TOKEN,
        "production_run_id": production_run.get("run_id"),
        "selected": len(symbols),
        "counts": {
            "planned": 0,
            "no_change": 0,
            "written_verified": 0,
            "errors": 0,
        },
        "results": [],
    }

    print(
        "Daily History Targeted Reconcile\n"
        f"run_date={run_date} | symbols={len(symbols)} | write={args.write}\n"
        f"production_run_id={production_run.get('run_id')}\n"
        "RULE: provider phai tai tao EXACT production; dry-run mac dinh; "
        "write khong bat neu chua confirm RECONCILE."
    )

    for index, symbol in enumerate(symbols, start=1):
        result: dict[str, Any] = {
            "symbol": symbol,
            "status": "",
            "production_source": production[symbol].get("source"),
            "production_trading_date": production[symbol].get("trading_date"),
            "target_source": "",
            "existing_count": 0,
            "target_count": 0,
            "missing": 0,
            "extras": 0,
            "value_diffs": 0,
            "source_diffs": 0,
            "error": "",
        }
        try:
            profile = profiles.get(symbol)
            if profile is None:
                raise RuntimeError("Khong tao duoc production profile hop le")

            existing_rows = load_existing_history(symbol)
            target_rows, source, _ = target_rows_from_provider(
                symbol=symbol,
                exchange=exchanges[symbol],
                run_date=run_date,
                profile=profile,
                updated_at=run_at,
            )
            plan = finalize.compare_exact_set(existing_rows, target_rows)

            result.update(
                {
                    "target_source": source,
                    "existing_count": plan["existing_count"],
                    "target_count": plan["target_count"],
                    "missing": len(plan["missing"]),
                    "extras": len(plan["extras"]),
                    "value_diffs": len(plan["value_diffs"]),
                    "source_diffs": len(plan["source_diffs"]),
                }
            )

            changed = any(
                result[key]
                for key in ("missing", "extras", "value_diffs", "source_diffs")
            )
            if not changed:
                report["counts"]["no_change"] += 1
                result["status"] = "NO_CHANGE"
                print(f"[{index}/{len(symbols)}] {symbol} -> NO_CHANGE")
                report["results"].append(result)
                write_report(report)
                continue

            report["counts"]["planned"] += 1
            result["status"] = "DRY_RUN_PLAN"
            print(
                f"[{index}/{len(symbols)}] {symbol} -> PLAN "
                f"source={source}, target={result['target_count']}, "
                f"missing={result['missing']}, extras={result['extras']}, "
                f"value_diff={result['value_diffs']}, "
                f"source_diff={result['source_diffs']}"
            )

            if args.write:
                # 1) Upsert full target first. Nothing is deleted until every
                # target row is present with exact values/source.
                backfill.upsert_rows(
                    "daily_history",
                    target_rows,
                    "symbol,trading_date",
                    batch_size=backfill.SUPABASE_WRITE_BATCH_SIZE,
                )
                after_upsert = verify_target_present(symbol, target_rows)

                # 2) Only after target verify, remove dates outside canonical
                # target set for this symbol.
                extras = list(after_upsert["extras"])
                if extras:
                    finalize.delete_dates(symbol, extras)

                # 3) Exact-set verify + production compatibility verify.
                finalize.verify_exact_clean_base(symbol, target_rows)
                verify_stored_matches_production(symbol, profile)

                report["counts"]["written_verified"] += 1
                result["status"] = "WRITTEN_VERIFIED"
                print(
                    f"[{index}/{len(symbols)}] {symbol} -> WRITTEN_VERIFIED"
                )

        except Exception as exc:
            report["counts"]["errors"] += 1
            result["status"] = "ERROR"
            result["error"] = f"{type(exc).__name__}: {exc}"
            print(
                f"[{index}/{len(symbols)}] {symbol} -> ERROR: "
                f"{result['error']}"
            )

        report["results"].append(result)
        write_report(report)

    write_report(report)
    print(
        "RECONCILE SUMMARY: "
        + ", ".join(f"{key}={value}" for key, value in report["counts"].items())
    )

    if report["counts"]["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
