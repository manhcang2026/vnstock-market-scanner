from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, datetime, timedelta, time
from pathlib import Path
from typing import Any

import pandas as pd

import backfill_daily_history as backfill
from common import load_watchlist


TARGET_SESSIONS = 250
LEGACY_LOOKBACK_DAYS = 500
MIN_EOD_TIME_SLOT = "15:00:00"
MARKET_CLOSE_SAFE_AFTER = time(15, 10)
VALUE_TOLERANCE = 0.0001
DELETE_BATCH_SIZE = 50

REPORT_JSON = Path("clean_history_report.json")
REPORT_CSV = Path("clean_history_report.csv")
SHADOW_LEGACY_JSON = Path("shadow_baseline_legacy.json")
SHADOW_LEGACY_CSV = Path("shadow_baseline_legacy.csv")
SHADOW_FULL_JSON = Path("shadow_baseline_full.json")
SHADOW_FULL_CSV = Path("shadow_baseline_full.csv")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_nonnegative_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} phai la so nguyen >=0; hien tai={raw!r}") from exc
    if value < 0:
        raise RuntimeError(f"{name} phai >=0; hien tai={value}")
    return value


def parse_symbols(raw: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in raw.replace(";", ",").split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def session_is_completed(trading_date: date) -> bool:
    current = backfill.now_vn()
    if trading_date < current.date():
        return True
    if trading_date > current.date():
        return False
    if current.weekday() >= 5:
        return False
    return current.time().replace(tzinfo=None) >= MARKET_CLOSE_SAFE_AFTER


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


def normalize_rows(rows: list[dict[str, Any]]) -> dict[date, dict[str, Any]]:
    result: dict[date, dict[str, Any]] = {}
    for row in rows:
        try:
            d = date.fromisoformat(str(row.get("trading_date") or ""))
            close = float(row.get("close"))
            volume = float(row.get("volume"))
        except (TypeError, ValueError):
            continue
        result[d] = {
            **row,
            "date_obj": d,
            "close_num": close,
            "volume_num": volume,
            "source_norm": str(row.get("source") or "").strip().upper(),
        }
    return result


def compare_exact_set(
    existing_rows: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    existing = normalize_rows(existing_rows)
    target = normalize_rows(target_rows)
    existing_dates = set(existing)
    target_dates = set(target)

    missing = sorted(target_dates - existing_dates)
    extras = sorted(existing_dates - target_dates)
    value_diffs: list[date] = []
    source_diffs: list[date] = []

    for d in sorted(target_dates & existing_dates):
        current = existing[d]
        expected = target[d]
        if (
            abs(current["close_num"] - expected["close_num"]) > VALUE_TOLERANCE
            or abs(current["volume_num"] - expected["volume_num"]) > VALUE_TOLERANCE
        ):
            value_diffs.append(d)
        if current["source_norm"] != expected["source_norm"]:
            source_diffs.append(d)

    return {
        "missing": missing,
        "extras": extras,
        "value_diffs": value_diffs,
        "source_diffs": source_diffs,
        "existing_count": len(existing),
        "target_count": len(target),
    }


def delete_dates(symbol: str, dates: list[date]) -> None:
    for offset in range(0, len(dates), DELETE_BATCH_SIZE):
        batch = dates[offset : offset + DELETE_BATCH_SIZE]
        values = ",".join(d.isoformat() for d in batch)
        backfill.supabase_request(
            "DELETE",
            "daily_history",
            params={
                "symbol": f"eq.{symbol}",
                "trading_date": f"in.({values})",
            },
            prefer="return=minimal",
        )


def verify_exact_clean_base(symbol: str, target_rows: list[dict[str, Any]]) -> None:
    check = compare_exact_set(load_existing_history(symbol), target_rows)
    problems: list[str] = []
    if check["missing"]:
        problems.append(f"missing={len(check['missing'])}")
    if check["extras"]:
        problems.append(f"extras={len(check['extras'])}")
    if check["value_diffs"]:
        problems.append(f"value_diff={len(check['value_diffs'])}")
    if check["source_diffs"]:
        problems.append(f"source_diff={len(check['source_diffs'])}")
    if problems:
        raise RuntimeError("Clean-base verify fail: " + ", ".join(problems))


def load_final_snapshots(trading_date: date) -> dict[str, dict[str, Any]]:
    """
    Current scanner has one >=15:00 row/symbol. Query up to 1000 rows and
    dedupe latest slot per symbol. Zero/invalid rows are intentionally kept
    so they can trigger provider EOD fallback.
    """
    response = backfill.supabase_request(
        "GET",
        "intraday_snapshots",
        params={
            "select": (
                "symbol,exchange,trading_date,time_slot,current_price,"
                "volume_accumulated,data_status,updated_at"
            ),
            "trading_date": f"eq.{trading_date.isoformat()}",
            "time_slot": f"gte.{MIN_EOD_TIME_SLOT}",
            "data_status": "eq.OK",
            "order": "symbol.asc,time_slot.desc",
            "limit": "1000",
        },
    )
    result: dict[str, dict[str, Any]] = {}
    for row in response.json():
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol and symbol not in result:
            result[symbol] = row
    return result


def intraday_eod_row(
    *,
    symbol: str,
    exchange: str,
    snapshot: dict[str, Any] | None,
    trading_date: date,
    updated_at: datetime,
) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    try:
        price = round(float(snapshot.get("current_price")), 4)
        volume = round(float(snapshot.get("volume_accumulated")), 4)
    except (TypeError, ValueError):
        return None

    # price=0/volume=0 rows are "no usable EOD bar", not a daily bar.
    if price <= 0 or volume <= 0:
        return None

    return {
        "symbol": symbol,
        "exchange": exchange,
        "trading_date": trading_date.isoformat(),
        "close": price,
        "volume": volume,
        "source": "INTRADAY_EOD",
        "updated_at": updated_at.isoformat(),
    }


def fetch_provider_eod_row(
    *,
    symbol: str,
    exchange: str,
    preferred_source: str,
    trading_date: date,
    updated_at: datetime,
) -> tuple[dict[str, Any] | None, str]:
    """
    Used only when final intraday snapshot is not usable.

    At least one provider must answer successfully before NO_BAR is accepted.
    This avoids treating provider/network failure as "symbol did not trade".
    """
    run_date = trading_date + timedelta(days=1)
    start = (trading_date - timedelta(days=10)).isoformat()
    end = run_date.isoformat()
    alternate = (
        backfill.FALLBACK_SOURCE
        if preferred_source == backfill.PRIMARY_SOURCE
        else backfill.PRIMARY_SOURCE
    )

    successful_provider_response = False
    notes: list[str] = []

    for source in (preferred_source, alternate):
        try:
            history = backfill.fetch_source_history(
                symbol=symbol,
                source=source,
                start=start,
                end=end,
                run_date=run_date,
            )
            successful_provider_response = True
            match = history[history["time"].dt.date == trading_date]
            if match.empty:
                notes.append(f"{source}: no {trading_date} bar")
                continue

            bar = match.iloc[-1]
            price = round(float(bar["close"]), 4)
            volume = round(float(bar["volume"]), 4)
            if price <= 0 or volume < 0:
                notes.append(f"{source}: invalid bar")
                continue

            return (
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "trading_date": trading_date.isoformat(),
                    "close": price,
                    "volume": volume,
                    "source": source,
                    "updated_at": updated_at.isoformat(),
                },
                f"{source}_EOD",
            )
        except Exception as exc:
            notes.append(f"{source}: {type(exc).__name__}: {exc}")

    if successful_provider_response:
        return None, "NO_BAR | " + " | ".join(notes)

    raise RuntimeError(
        "EOD provider unavailable; khong duoc tu suy dien NO_BAR. "
        + " | ".join(notes)
    )


def upsert_one(row: dict[str, Any]) -> None:
    backfill.upsert_rows(
        "daily_history",
        [row],
        "symbol,trading_date",
        batch_size=1,
    )


def rows_to_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = normalize_rows(rows)
    return [normalized[d] for d in sorted(normalized)]


def calculate_shadow(
    *,
    symbol: str,
    exchange: str,
    rows: list[dict[str, Any]],
    run_date: date,
    legacy_window: bool,
    eod_input_source: str,
) -> dict[str, Any]:
    series = [
        row for row in rows_to_series(rows)
        if row["date_obj"] < run_date
    ]
    if legacy_window:
        start = run_date - timedelta(days=LEGACY_LOOKBACK_DAYS)
        series = [row for row in series if row["date_obj"] >= start]

    if not series:
        raise RuntimeError(f"{symbol}: shadow khong co history truoc {run_date}")

    session_count = len(series)
    ma200_sessions = min(session_count, 200)
    ma10_sessions = min(session_count, 10)
    avgvol_sessions = min(session_count, 10)
    latest = series[-1]

    closes = [row["close_num"] for row in series]
    volumes = [row["volume_num"] for row in series]

    return {
        "symbol": symbol,
        "exchange": exchange,
        "shadow_for_date": run_date.isoformat(),
        "trading_date": latest["date_obj"].isoformat(),
        "previous_close": round(float(latest["close_num"]), 4),
        "ma200": round(
            sum(closes[-ma200_sessions:]) / ma200_sessions, 4
        ),
        "ma200_sessions": ma200_sessions,
        "avg_volume_10": round(
            sum(volumes[-avgvol_sessions:]) / avgvol_sessions, 4
        ),
        "avg_volume_sessions": avgvol_sessions,
        "source": "LOCAL_DAILY_HISTORY",
        "data_status": "OK",
        "ma10": round(
            sum(closes[-ma10_sessions:]) / ma10_sessions, 4
        ),
        "ma10_sessions": ma10_sessions,
        "history_sessions_in_calc": session_count,
        "eod_input_source": eod_input_source,
    }


def write_json_csv(path_json: Path, path_csv: Path, rows: list[dict[str, Any]]) -> None:
    path_json.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    if not rows:
        path_csv.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_report(report: dict[str, Any]) -> None:
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    rows = report["results"]
    write_json_csv(Path("/tmp/_unused.json"), REPORT_CSV, rows)
    Path("/tmp/_unused.json").unlink(missing_ok=True)


def select_symbols(
    raw: str,
    watchlist_symbols: list[str],
    resume_after: str,
    max_symbols: int,
) -> list[str]:
    explicit = parse_symbols(raw)
    if explicit:
        selected = explicit
    else:
        selected = sorted(watchlist_symbols)
        if resume_after:
            resume = resume_after.upper()
            if resume not in selected:
                raise RuntimeError(
                    f"resume_after={resume} khong nam trong watchlist."
                )
            selected = selected[selected.index(resume) + 1 :]
    if max_symbols > 0:
        selected = selected[:max_symbols]
    return selected


def main() -> None:
    write = env_bool("FINALIZE_WRITE", False)
    confirm = os.getenv("FINALIZE_CONFIRM", "").strip().upper()
    if write and confirm != "FINALIZE":
        raise RuntimeError('write=true bat buoc FINALIZE_CONFIRM="FINALIZE".')

    eod_raw = os.getenv("FINALIZE_EOD_DATE", "").strip()
    if not eod_raw:
        raise RuntimeError("FINALIZE_EOD_DATE bat buoc.")
    try:
        eod_date = date.fromisoformat(eod_raw)
    except ValueError as exc:
        raise RuntimeError(f"EOD date khong hop le: {eod_raw!r}") from exc

    if not session_is_completed(eod_date):
        raise RuntimeError(f"SAFETY STOP: phien {eod_date} chua ket thuc.")

    max_symbols = env_nonnegative_int("FINALIZE_MAX_SYMBOLS", 0)
    resume_after = os.getenv("FINALIZE_RESUME_AFTER", "").strip().upper()
    raw_symbols = os.getenv("FINALIZE_SYMBOLS", "").strip()

    backfill.verify_vnstock_api_access()
    backfill.verify_supabase_config()

    run_at = backfill.now_vn()
    if backfill.in_market_protection_window(run_at):
        raise RuntimeError(
            "SAFETY STOP: 08:20-15:10 ngay giao dich; khong finalize."
        )

    watchlist = load_watchlist()
    exchanges = {
        str(row.symbol).strip().upper(): str(row.exchange).strip().upper()
        for row in watchlist.itertuples(index=False)
    }
    profiles = backfill.load_baseline_profiles()
    selected = select_symbols(
        raw_symbols,
        list(exchanges),
        resume_after,
        max_symbols,
    )
    snapshots = load_final_snapshots(eod_date)
    shadow_run_date = eod_date + timedelta(days=1)

    report: dict[str, Any] = {
        "run_at": run_at.isoformat(),
        "write": write,
        "eod_date": eod_date.isoformat(),
        "shadow_run_date": shadow_run_date.isoformat(),
        "selected_count": len(selected),
        "resume_after": resume_after or None,
        "counts": {
            "processed": 0,
            "clean_ready": 0,
            "clean_written": 0,
            "intraday_eod": 0,
            "provider_eod": 0,
            "no_eod_bar": 0,
            "shadow_rows": 0,
            "errors": 0,
        },
        "last_processed_symbol": None,
        "results": [],
        "errors": [],
    }
    shadow_legacy: list[dict[str, Any]] = []
    shadow_full: list[dict[str, Any]] = []

    print(
        "CCC CLEAN DAILY HISTORY FINALIZER\n"
        f"selected={len(selected)} | write={write} | eod_date={eod_date} | "
        f"shadow_for={shadow_run_date} | snapshots>=15:00={len(snapshots)}\n"
        "PLAN: provider-validated clean base (toi da 250 phien) -> "
        "xoa moi extra row khong thuoc clean base -> append EOD -> shadow.\n"
        "EOD: intraday chi hop le khi price>0 va volume>0; neu khong, "
        "goi provider fallback de xac nhan co/no daily bar.\n"
        "Shadow LEGACY dung 500 calendar days de doi chieu Daily Baseline cu.\n"
        "Shadow FULL dung full clean store de danh gia kien truc moi."
    )

    for index, symbol in enumerate(selected, start=1):
        exchange = exchanges.get(symbol)
        profile = profiles.get(symbol)
        result: dict[str, Any] = {
            "symbol": symbol,
            "status": "",
            "baseline_date": str(profile["trading_date"]) if profile else "",
            "baseline_source": str(profile.get("source") or "") if profile else "",
            "seed_source": "",
            "seed_rows": "",
            "existing_rows": "",
            "missing_before": "",
            "value_diff_before": "",
            "source_diff_before": "",
            "extras_to_delete": "",
            "eod_source": "",
            "eod_close": "",
            "eod_volume": "",
            "legacy_trading_date": "",
            "legacy_ma200_sessions": "",
            "full_ma200_sessions": "",
            "error": "",
        }

        print(f"[{index}/{len(selected)}] {symbol}")
        try:
            if not exchange:
                raise RuntimeError("not in watchlist")
            if profile is None:
                raise RuntimeError("no valid production baseline profile")

            # Use production source first; fallback is accepted only if it
            # reproduces production EXACT (backfill.get_history contract).
            history, seed_source = backfill.get_history(
                symbol=symbol,
                run_date=run_at.date(),
                profile=profile,
            )
            target_rows = backfill.history_rows(
                symbol=symbol,
                exchange=exchange,
                history=history,
                source=seed_source,
                updated_at=run_at,
            )
            required = int(profile["ma200_sessions"])
            if len(target_rows) < required:
                raise RuntimeError(
                    f"clean seed {len(target_rows)} < required {required}"
                )

            existing = load_existing_history(symbol)
            before = compare_exact_set(existing, target_rows)
            result.update({
                "seed_source": seed_source,
                "seed_rows": len(target_rows),
                "existing_rows": len(existing),
                "missing_before": len(before["missing"]),
                "value_diff_before": len(before["value_diffs"]),
                "source_diff_before": len(before["source_diffs"]),
                "extras_to_delete": len(before["extras"]),
            })
            report["counts"]["clean_ready"] += 1

            print(
                f"  CLEAN PLAN source={seed_source} target={len(target_rows)} "
                f"missing={len(before['missing'])} "
                f"value_diff={len(before['value_diffs'])} "
                f"source_diff={len(before['source_diffs'])} "
                f"delete_extras={len(before['extras'])}"
            )

            if write:
                # Safe order: target first, verify target completeness, then
                # remove every unvalidated extra date. If delete fails, clean
                # target remains present; only extras remain.
                backfill.upsert_rows(
                    "daily_history",
                    target_rows,
                    "symbol,trading_date",
                )
                after_upsert = compare_exact_set(
                    load_existing_history(symbol),
                    target_rows,
                )
                if (
                    after_upsert["missing"]
                    or after_upsert["value_diffs"]
                    or after_upsert["source_diffs"]
                ):
                    raise RuntimeError(
                        "post-upsert target verify fail; KHONG delete extras"
                    )

                delete_dates(symbol, after_upsert["extras"])
                verify_exact_clean_base(symbol, target_rows)
                report["counts"]["clean_written"] += 1
                print("  -> CLEAN BASE WRITTEN + EXACT")

            snapshot = snapshots.get(symbol)
            eod_row = intraday_eod_row(
                symbol=symbol,
                exchange=exchange,
                snapshot=snapshot,
                trading_date=eod_date,
                updated_at=run_at,
            )

            if eod_row is not None:
                eod_source = "INTRADAY_EOD"
                report["counts"]["intraday_eod"] += 1
            else:
                eod_row, eod_source = fetch_provider_eod_row(
                    symbol=symbol,
                    exchange=exchange,
                    preferred_source=str(profile["source"]),
                    trading_date=eod_date,
                    updated_at=run_at,
                )
                if eod_row is None:
                    report["counts"]["no_eod_bar"] += 1
                else:
                    report["counts"]["provider_eod"] += 1

            result["eod_source"] = eod_source
            if eod_row is not None:
                result["eod_close"] = eod_row["close"]
                result["eod_volume"] = eod_row["volume"]
                if write:
                    upsert_one(eod_row)
                    check = load_existing_history(symbol)
                    current = normalize_rows(check).get(eod_date)
                    if current is None:
                        raise RuntimeError("EOD write verify missing")
                    if (
                        abs(current["close_num"] - float(eod_row["close"])) > VALUE_TOLERANCE
                        or abs(current["volume_num"] - float(eod_row["volume"])) > VALUE_TOLERANCE
                        or current["source_norm"] != str(eod_row["source"]).upper()
                    ):
                        raise RuntimeError("EOD write verify value/source mismatch")
                    print(
                        f"  -> EOD {eod_source} WRITTEN "
                        f"close={eod_row['close']} volume={eod_row['volume']}"
                    )
                else:
                    print(
                        f"  -> EOD {eod_source} CANDIDATE "
                        f"close={eod_row['close']} volume={eod_row['volume']}"
                    )
            else:
                print(f"  -> EOD {eod_source}; khong append daily bar.")

            prospective = list(target_rows)
            if eod_row is not None:
                prospective.append(eod_row)

            legacy = calculate_shadow(
                symbol=symbol,
                exchange=exchange,
                rows=prospective,
                run_date=shadow_run_date,
                legacy_window=True,
                eod_input_source=eod_source,
            )
            full = calculate_shadow(
                symbol=symbol,
                exchange=exchange,
                rows=prospective,
                run_date=shadow_run_date,
                legacy_window=False,
                eod_input_source=eod_source,
            )
            shadow_legacy.append(legacy)
            shadow_full.append(full)
            report["counts"]["shadow_rows"] += 1
            result["legacy_trading_date"] = legacy["trading_date"]
            result["legacy_ma200_sessions"] = legacy["ma200_sessions"]
            result["full_ma200_sessions"] = full["ma200_sessions"]
            result["status"] = "WRITTEN_VERIFIED" if write else "DRY_RUN_READY"

            print(
                f"  -> SHADOW legacy: date={legacy['trading_date']} "
                f"MA10={legacy['ma10']} MA200={legacy['ma200']} "
                f"KLTB10={legacy['avg_volume_10']} "
                f"sessions200={legacy['ma200_sessions']}"
            )

        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            result["status"] = "ERROR"
            result["error"] = message
            report["counts"]["errors"] += 1
            report["errors"].append({"symbol": symbol, "error": message})
            print(f"  -> ERROR {message}")

        report["results"].append(result)
        report["counts"]["processed"] += 1
        report["last_processed_symbol"] = symbol
        write_report(report)
        write_json_csv(
            SHADOW_LEGACY_JSON, SHADOW_LEGACY_CSV,
            sorted(shadow_legacy, key=lambda row: row["symbol"]),
        )
        write_json_csv(
            SHADOW_FULL_JSON, SHADOW_FULL_CSV,
            sorted(shadow_full, key=lambda row: row["symbol"]),
        )

    print(
        "\nFINAL SUMMARY: "
        + ", ".join(f"{k}={v}" for k, v in report["counts"].items())
        + f", last_processed={report['last_processed_symbol']}, write={write}."
    )

    if report["errors"]:
        print("ERROR SYMBOLS:")
        for item in report["errors"]:
            print(f"  {item['symbol']}: {item['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
