from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import backfill_daily_history as backfill
import canonical_history_sync as phase_b


FULL_MA200_SESSIONS = 200
TARGET_SESSIONS = 250
CANONICAL_SOURCE = "KBS"
REPORT_JSON = Path("canonical_bulk_report.json")
REPORT_CSV = Path("canonical_bulk_report.csv")


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
    symbols: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def almost_equal(left: float, right: float, tolerance: float = 0.0001) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def local_canonical_check(
    existing_rows: list[dict[str, Any]],
    profile: dict[str, Any],
) -> tuple[bool, str]:
    """
    Fast-path de KHONG goi provider neu kho local da canonical ro rang.

    Chi fast-skip khi:
    - production baseline source hien tai la KBS;
    - co it nhat 250 rows <= baseline_date;
    - 250 rows gan nhat deu source=KBS;
    - latest date = baseline_date;
    - close, MA10, MA200, KLTB10 tinh tu local khop EXACT production baseline.

    Neu thieu bat ky dieu kien nao -> KHONG skip; provider KBS se duoc goi de audit.
    """
    if str(profile.get("source") or "").strip().upper() != CANONICAL_SOURCE:
        return False, "baseline_source_not_kbs"

    normalized = phase_b.normalize_rows(existing_rows)
    anchor: date = profile["trading_date"]

    eligible_dates = sorted(d for d in normalized if d <= anchor)
    if len(eligible_dates) < TARGET_SESSIONS:
        return False, f"local_rows_before_anchor={len(eligible_dates)}<250"

    selected_dates = eligible_dates[-TARGET_SESSIONS:]
    selected = [normalized[d] for d in selected_dates]

    if selected_dates[-1] != anchor:
        return False, f"latest={selected_dates[-1]} != baseline={anchor}"

    if any(row["source_norm"] != CANONICAL_SOURCE for row in selected):
        return False, "latest_250_not_all_kbs"

    closes = [float(row["close_num"]) for row in selected]
    volumes = [float(row["volume_num"]) for row in selected]

    local_close = closes[-1]
    local_ma10 = sum(closes[-10:]) / 10
    local_ma200 = sum(closes[-200:]) / 200
    local_avgvol10 = sum(volumes[-10:]) / 10

    checks = (
        almost_equal(local_close, profile["previous_close"]),
        almost_equal(local_ma10, profile["ma10"]),
        almost_equal(local_ma200, profile["ma200"]),
        almost_equal(local_avgvol10, profile["avg_volume_10"]),
    )
    if not all(checks):
        return (
            False,
            "local_metrics_not_exact "
            f"close={local_close:.4f}/{profile['previous_close']:.4f}, "
            f"ma10={local_ma10:.4f}/{profile['ma10']:.4f}, "
            f"ma200={local_ma200:.4f}/{profile['ma200']:.4f}, "
            f"avgvol10={local_avgvol10:.4f}/{profile['avg_volume_10']:.4f}",
        )

    return (
        True,
        f"LOCAL_EXACT 250 rows {selected_dates[0]}..{selected_dates[-1]} "
        f"source={CANONICAL_SOURCE}",
    )


def make_report(
    *,
    run_at,
    mode: str,
    write: bool,
    force_provider: bool,
    resume_after: str,
    max_symbols: int,
    total_watchlist: int,
    total_eligible: int,
    global_under_200: int,
    selected_symbols: list[str],
) -> dict[str, Any]:
    return {
        "phase": "B.1",
        "run_at": run_at.isoformat(),
        "mode": mode,
        "write": write,
        "force_provider": force_provider,
        "resume_after": resume_after,
        "max_symbols": max_symbols,
        "total_watchlist": total_watchlist,
        "total_eligible": total_eligible,
        "global_under_200": global_under_200,
        "selected_count": len(selected_symbols),
        "selected_first": selected_symbols[0] if selected_symbols else None,
        "selected_last": selected_symbols[-1] if selected_symbols else None,
        "last_processed_symbol": None,
        "counts": {
            "processed": 0,
            "local_canonical_skip": 0,
            "provider_checked": 0,
            "already_canonical": 0,
            "candidate_ready": 0,
            "written": 0,
            "skipped_under_200": 0,
            "errors": 0,
        },
        "results": [],
        "errors": [],
    }


def write_checkpoint(report: dict[str, Any]) -> None:
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    fields = [
        "symbol",
        "status",
        "baseline_date",
        "baseline_source",
        "local_check",
        "provider_checked",
        "target_rows",
        "missing",
        "value_diff",
        "source_diff",
        "delete_extra",
        "written",
        "error",
    ]
    with REPORT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report["results"]:
            writer.writerow({key: row.get(key, "") for key in fields})


def append_result(
    report: dict[str, Any],
    row: dict[str, Any],
) -> None:
    report["results"].append(row)
    report["counts"]["processed"] += 1
    report["last_processed_symbol"] = row.get("symbol")
    write_checkpoint(report)


def select_symbols(
    *,
    raw_symbols: str,
    watchlist_symbols: list[str],
    profiles: dict[str, dict[str, Any]],
    resume_after: str,
    max_symbols: int,
) -> tuple[str, list[str], int, int]:
    """
    Return (mode, selected, total_eligible, global_under_200).

    Bulk mode (symbols rong) dung alphabetical order de resume_after on dinh.
    Explicit mode giu thu tu user nhap.
    """
    explicit = parse_symbols(raw_symbols)
    if explicit:
        selected = explicit
        if max_symbols > 0:
            selected = selected[:max_symbols]
        return "explicit", selected, 0, 0

    eligible: list[str] = []
    under_200 = 0
    for symbol in sorted(watchlist_symbols):
        profile = profiles.get(symbol)
        if profile is None:
            continue
        if int(profile.get("ma200_sessions") or 0) < FULL_MA200_SESSIONS:
            under_200 += 1
            continue
        eligible.append(symbol)

    total_eligible = len(eligible)

    if resume_after:
        resume_after = resume_after.upper()
        if resume_after not in eligible:
            raise RuntimeError(
                f"CANONICAL_RESUME_AFTER={resume_after} khong nam trong danh sach "
                "eligible bulk. Lay last_processed_symbol tu report truoc."
            )
        index = eligible.index(resume_after)
        eligible = eligible[index + 1 :]

    if max_symbols > 0:
        eligible = eligible[:max_symbols]

    return "bulk", eligible, total_eligible, under_200


def main() -> None:
    write = env_bool("CANONICAL_WRITE", False)
    force_provider = env_bool("CANONICAL_FORCE_PROVIDER", False)
    raw_symbols = os.getenv("CANONICAL_SYMBOLS", "").strip()
    confirm = os.getenv("CANONICAL_CONFIRM", "").strip().upper()
    resume_after = os.getenv("CANONICAL_RESUME_AFTER", "").strip().upper()
    max_symbols = env_nonnegative_int("CANONICAL_MAX_SYMBOLS", 100)

    # Two-key confirmation:
    # - explicit list -> WRITE
    # - blank symbols = bulk -> WRITE-BULK
    if write:
        expected = "WRITE" if raw_symbols else "WRITE-BULK"
        if confirm != expected:
            raise RuntimeError(
                f"write=true can confirm={expected!r}; hien tai={confirm!r}."
            )

    backfill.verify_vnstock_api_access()
    backfill.verify_supabase_config()

    run_at = backfill.now_vn()
    if backfill.in_market_protection_window(run_at):
        print(
            "SAFETY STOP: dang trong khung 08:20-15:10 ngay giao dich. "
            "Phase B.1 khong goi VNStock va khong ghi Supabase."
        )
        return

    watchlist = backfill.load_watchlist()
    watchlist_map = {
        str(row.symbol).strip().upper(): str(row.exchange).strip().upper()
        for row in watchlist.itertuples(index=False)
    }
    watchlist_symbols = sorted(watchlist_map)
    profiles = backfill.load_baseline_profiles()

    mode, selected_symbols, total_eligible, global_under_200 = select_symbols(
        raw_symbols=raw_symbols,
        watchlist_symbols=watchlist_symbols,
        profiles=profiles,
        resume_after=resume_after,
        max_symbols=max_symbols,
    )

    report = make_report(
        run_at=run_at,
        mode=mode,
        write=write,
        force_provider=force_provider,
        resume_after=resume_after,
        max_symbols=max_symbols,
        total_watchlist=len(watchlist_symbols),
        total_eligible=total_eligible,
        global_under_200=global_under_200,
        selected_symbols=selected_symbols,
    )
    write_checkpoint(report)

    print(
        "Canonical Daily History Bulk-Safe - PHASE B.1\n"
        f"run_at={run_at.isoformat()} | mode={mode} | "
        f"selected={len(selected_symbols)} | write={write} | "
        f"force_provider={force_provider} | resume_after={resume_after or '-'} | "
        f"max_symbols={max_symbols}\n"
        f"watchlist={len(watchlist_symbols)} | "
        f"eligible_bulk={total_eligible if mode == 'bulk' else 'n/a'} | "
        f"under_200_global={global_under_200 if mode == 'bulk' else 'n/a'}\n"
        "RULE: <200 phien khong bi canonicalize.\n"
        "RULE: local canonical EXACT duoc skip provider neu force_provider=false.\n"
        "RULE: provider path chi dung KBS va phai EXACT Daily Baseline.\n"
        "RULE: write bulk can confirm WRITE-BULK."
    )

    if not selected_symbols:
        print("Khong con symbol nao trong chunk nay.")
        return

    for index, symbol in enumerate(selected_symbols, start=1):
        exchange = watchlist_map.get(symbol)
        profile = profiles.get(symbol)
        base_result = {
            "symbol": symbol,
            "status": "",
            "baseline_date": str(profile["trading_date"]) if profile else "",
            "baseline_source": str(profile.get("source") or "") if profile else "",
            "local_check": "",
            "provider_checked": False,
            "target_rows": "",
            "missing": "",
            "value_diff": "",
            "source_diff": "",
            "delete_extra": "",
            "written": False,
            "error": "",
        }

        print(f"[{index}/{len(selected_symbols)}] {symbol}")

        if exchange is None:
            message = "not in watchlist"
            base_result["status"] = "ERROR"
            base_result["error"] = message
            report["counts"]["errors"] += 1
            report["errors"].append({"symbol": symbol, "error": message})
            append_result(report, base_result)
            print(f"  -> ERROR {message}")
            continue

        if profile is None:
            message = "no baseline profile"
            base_result["status"] = "ERROR"
            base_result["error"] = message
            report["counts"]["errors"] += 1
            report["errors"].append({"symbol": symbol, "error": message})
            append_result(report, base_result)
            print(f"  -> ERROR {message}")
            continue

        ma200_sessions = int(profile.get("ma200_sessions") or 0)
        if ma200_sessions < FULL_MA200_SESSIONS:
            base_result["status"] = "SKIP_UNDER_200"
            base_result["local_check"] = f"ma200_sessions={ma200_sessions}"
            report["counts"]["skipped_under_200"] += 1
            append_result(report, base_result)
            print(f"  -> SKIP_UNDER_200 ma200_sessions={ma200_sessions}")
            continue

        try:
            existing_rows = phase_b.load_existing_history(symbol)
            is_local, local_detail = local_canonical_check(existing_rows, profile)
            base_result["local_check"] = local_detail

            if is_local and not force_provider:
                base_result["status"] = "LOCAL_CANONICAL_SKIP"
                base_result["target_rows"] = TARGET_SESSIONS
                report["counts"]["local_canonical_skip"] += 1
                append_result(report, base_result)
                print(f"  -> {local_detail}; SKIP provider.")
                continue

            history = phase_b.fetch_kbs_exact_history(
                symbol=symbol,
                profile=profile,
                run_date=run_at.date(),
            )
            report["counts"]["provider_checked"] += 1
            base_result["provider_checked"] = True

            target_rows = phase_b.build_target_rows(
                symbol=symbol,
                exchange=exchange,
                history=history,
                updated_at=run_at,
            )
            if len(target_rows) < FULL_MA200_SESSIONS:
                raise RuntimeError(
                    f"KBS target chi co {len(target_rows)} rows; khong du 200."
                )

            comparison = phase_b.compare_window(existing_rows, target_rows)
            base_result["target_rows"] = comparison["target_rows"]
            base_result["missing"] = len(comparison["missing_dates"])
            base_result["value_diff"] = len(comparison["value_diffs"])
            base_result["source_diff"] = len(comparison["source_diffs"])
            base_result["delete_extra"] = len(comparison["extra_dates"])

            has_change = bool(
                comparison["missing_dates"]
                or comparison["extra_dates"]
                or comparison["value_diffs"]
                or comparison["source_diffs"]
            )

            if not has_change:
                base_result["status"] = "ALREADY_CANONICAL"
                report["counts"]["already_canonical"] += 1
                append_result(report, base_result)
                print("  -> ALREADY_CANONICAL after provider check.")
                continue

            report["counts"]["candidate_ready"] += 1
            phase_b.print_plan(symbol, comparison)

            if not write:
                base_result["status"] = "CANDIDATE_READY"
                append_result(report, base_result)
                print("  -> DRY_RUN CANDIDATE_READY; khong ghi.")
                continue

            # Same safety order da pass test Phase B:
            # 1) upsert target KBS; 2) verify; 3) delete extra trong window; 4) verify.
            backfill.upsert_rows(
                "daily_history",
                target_rows,
                "symbol,trading_date",
            )

            after_upsert_rows = phase_b.load_existing_history(symbol)
            after_upsert = phase_b.compare_window(after_upsert_rows, target_rows)
            if (
                after_upsert["missing_dates"]
                or after_upsert["value_diffs"]
                or after_upsert["source_diffs"]
            ):
                raise RuntimeError(
                    "Post-upsert verify fail: "
                    f"missing={len(after_upsert['missing_dates'])}, "
                    f"value_diff={len(after_upsert['value_diffs'])}, "
                    f"source_diff={len(after_upsert['source_diffs'])}. "
                    "KHONG xoa extra dates."
                )

            phase_b.delete_extra_dates(symbol, after_upsert["extra_dates"])

            exact, detail = phase_b.verify_canonical_window(symbol, target_rows)
            if not exact:
                raise RuntimeError("FINAL VERIFY FAIL: " + detail)

            base_result["status"] = "WRITTEN_VERIFIED"
            base_result["written"] = True
            report["counts"]["written"] += 1
            append_result(report, base_result)
            print(f"  -> WRITTEN + VERIFIED: {detail}")

        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            base_result["status"] = "ERROR"
            base_result["error"] = message
            report["counts"]["errors"] += 1
            report["errors"].append({"symbol": symbol, "error": message})
            append_result(report, base_result)
            print(f"  -> ERROR {message}")

    print(
        "\nCANONICAL PHASE B.1 SUMMARY: "
        + ", ".join(f"{key}={value}" for key, value in report["counts"].items())
        + f", last_processed={report['last_processed_symbol']}, write={write}."
    )
    print(
        f"REPORT: {REPORT_JSON} + {REPORT_CSV}. "
        "Neu can resume bulk, nhap last_processed_symbol vao resume_after."
    )

    if report["errors"]:
        print("ERROR SYMBOLS:")
        for item in report["errors"]:
            print(f"  {item['symbol']}: {item['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
