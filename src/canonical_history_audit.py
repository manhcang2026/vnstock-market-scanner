from __future__ import annotations

import os
import sys
from collections import Counter
from datetime import date
from typing import Any

import pandas as pd

import backfill_daily_history as backfill

TARGET_SESSIONS = 250
FULL_MA200_SESSIONS = 200
VALUE_TOLERANCE = 0.0001
DEFAULT_SAMPLE = "TLP,VIT,CLC,VNC,MAC,PDN"


def parse_symbols(raw: str) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


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


def normalize_existing_rows(rows: list[dict[str, Any]]) -> dict[date, dict[str, Any]]:
    result: dict[date, dict[str, Any]] = {}
    for row in rows:
        raw_date = str(row.get("trading_date") or "").strip()
        try:
            trading_date = date.fromisoformat(raw_date)
            close = float(row.get("close"))
            volume = float(row.get("volume"))
        except (TypeError, ValueError):
            continue
        result[trading_date] = {
            **row,
            "trading_date_obj": trading_date,
            "close_num": close,
            "volume_num": volume,
            "source_norm": str(row.get("source") or "").strip().upper(),
        }
    return result


def target_rows_from_history(
    symbol: str,
    exchange: str,
    history: pd.DataFrame,
    source: str,
    updated_at,
) -> list[dict[str, Any]]:
    return backfill.history_rows(
        symbol=symbol,
        exchange=exchange,
        history=history,
        source=source,
        updated_at=updated_at,
    )


def compare_existing_to_target(
    existing_rows: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
    canonical_source: str,
) -> dict[str, Any]:
    existing = normalize_existing_rows(existing_rows)

    target: dict[date, dict[str, Any]] = {}
    for row in target_rows:
        trading_date = date.fromisoformat(str(row["trading_date"]))
        target[trading_date] = {
            **row,
            "trading_date_obj": trading_date,
            "close_num": float(row["close"]),
            "volume_num": float(row["volume"]),
        }

    target_dates = set(target)
    existing_dates = set(existing)
    missing_dates = sorted(target_dates - existing_dates)
    extra_dates = sorted(existing_dates - target_dates)

    earliest_target = min(target_dates) if target_dates else None
    latest_target = max(target_dates) if target_dates else None

    harmless_old_extra = [
        d for d in extra_dates
        if earliest_target is not None and d < earliest_target
    ]
    window_extra = [
        d for d in extra_dates
        if earliest_target is None
        or latest_target is None
        or d >= earliest_target
    ]

    value_diffs: list[dict[str, Any]] = []
    source_mismatches: list[date] = []
    exact_rows = 0

    for trading_date in sorted(target_dates & existing_dates):
        current = existing[trading_date]
        expected = target[trading_date]
        close_diff = current["close_num"] - expected["close_num"]
        volume_diff = current["volume_num"] - expected["volume_num"]

        if (
            abs(close_diff) <= VALUE_TOLERANCE
            and abs(volume_diff) <= VALUE_TOLERANCE
        ):
            exact_rows += 1
        else:
            value_diffs.append(
                {
                    "trading_date": trading_date,
                    "current_close": current["close_num"],
                    "target_close": expected["close_num"],
                    "close_diff": close_diff,
                    "current_volume": current["volume_num"],
                    "target_volume": expected["volume_num"],
                    "volume_diff": volume_diff,
                }
            )

        if current["source_norm"] != canonical_source.upper():
            source_mismatches.append(trading_date)

    source_counts = Counter(
        str(row.get("source") or "").strip().upper() or "UNKNOWN"
        for row in existing_rows
    )

    return {
        "existing_rows": len(existing_rows),
        "target_rows": len(target_rows),
        "exact_rows": exact_rows,
        "missing_dates": missing_dates,
        "value_diffs": value_diffs,
        "source_mismatches": source_mismatches,
        "harmless_old_extra": harmless_old_extra,
        "window_extra": window_extra,
        "source_counts": source_counts,
    }


def fmt_dates(values: list[date], limit: int = 5) -> str:
    if not values:
        return "-"
    shown = ",".join(d.isoformat() for d in values[:limit])
    if len(values) > limit:
        shown += f",...(+{len(values) - limit})"
    return shown


def print_diff_examples(value_diffs: list[dict[str, Any]], limit: int = 3) -> None:
    for item in value_diffs[:limit]:
        print(
            "     DIFF "
            f"{item['trading_date']}: "
            f"close {item['current_close']:.4f}->{item['target_close']:.4f} "
            f"({item['close_diff']:+.4f}); "
            f"volume {item['current_volume']:.4f}->{item['target_volume']:.4f} "
            f"({item['volume_diff']:+.4f})"
        )


def main() -> None:
    # Phase A la audit tuyet doi read-only. Neu ai co gang bat write thi dung ngay.
    requested_write = os.getenv("CANONICAL_WRITE", "false").strip().lower()
    if requested_write in {"1", "true", "yes", "y", "on"}:
        raise RuntimeError(
            "Phase A canonical audit la DRY-RUN ONLY; CANONICAL_WRITE phai=false."
        )

    backfill.verify_vnstock_api_access()
    backfill.verify_supabase_config()

    run_at = backfill.now_vn()
    if backfill.in_market_protection_window(run_at):
        print(
            "SAFETY STOP: dang trong khung 08:20-15:10 ngay giao dich. "
            "Canonical audit khong goi VNStock de tranh quota voi Intraday."
        )
        return

    raw_symbols = os.getenv("CANONICAL_SYMBOLS", DEFAULT_SAMPLE).strip()
    requested_symbols = parse_symbols(raw_symbols or DEFAULT_SAMPLE)
    if not requested_symbols:
        raise RuntimeError("CANONICAL_SYMBOLS dang rong.")

    watchlist = backfill.load_watchlist()
    watchlist_map = {
        str(row.symbol).strip().upper(): str(row.exchange).strip().upper()
        for row in watchlist.itertuples(index=False)
    }
    profiles = backfill.load_baseline_profiles()

    print(
        "Canonical Daily History Audit - PHASE A (READ ONLY)\n"
        f"run_at={run_at.isoformat()} | requested={len(requested_symbols)} | "
        f"target_buffer={TARGET_SESSIONS} | full_ma200={FULL_MA200_SESSIONS}\n"
        "RULE: bo qua ma ma Daily Baseline co ma200_sessions < 200. "
        "Khong INSERT/UPDATE/DELETE Supabase."
    )

    audited = 0
    already_canonical = 0
    candidate_ready = 0
    skipped_under_200 = 0
    provider_errors = 0
    short_buffer = 0

    for index, symbol in enumerate(requested_symbols, start=1):
        exchange = watchlist_map.get(symbol)
        profile = profiles.get(symbol)

        if exchange is None:
            provider_errors += 1
            print(f"[{index}/{len(requested_symbols)}] {symbol} -> ERROR not in watchlist")
            continue

        if profile is None:
            provider_errors += 1
            print(f"[{index}/{len(requested_symbols)}] {symbol} -> ERROR no baseline profile")
            continue

        ma200_sessions = int(profile.get("ma200_sessions") or 0)
        if ma200_sessions < FULL_MA200_SESSIONS:
            skipped_under_200 += 1
            print(
                f"[{index}/{len(requested_symbols)}] {symbol} -> SKIP_UNDER_200 "
                f"baseline_ma200_sessions={ma200_sessions}"
            )
            continue

        print(
            f"[{index}/{len(requested_symbols)}] {symbol} ({exchange}) "
            f"baseline_date={profile['trading_date']} source={profile['source']}"
        )

        try:
            history, source = backfill.get_history(
                symbol=symbol,
                run_date=run_at.date(),
                profile=profile,
            )
            exact, detail = backfill.compare_with_production(history, profile)
            if not exact:
                raise RuntimeError(
                    "Provider history khong EXACT voi Daily Baseline: " + detail
                )

            target_rows = target_rows_from_history(
                symbol=symbol,
                exchange=exchange,
                history=history,
                source=source,
                updated_at=run_at,
            )
            existing_rows = load_existing_history(symbol)
            comparison = compare_existing_to_target(
                existing_rows=existing_rows,
                target_rows=target_rows,
                canonical_source=source,
            )

            audited += 1
            if len(target_rows) < TARGET_SESSIONS:
                short_buffer += 1

            has_value_issue = bool(
                comparison["missing_dates"]
                or comparison["value_diffs"]
                or comparison["window_extra"]
            )
            has_provenance_issue = bool(comparison["source_mismatches"])

            if not has_value_issue and not has_provenance_issue:
                already_canonical += 1
                status = "ALREADY_CANONICAL"
            else:
                candidate_ready += 1
                status = "CANDIDATE_READY"

            metrics = backfill.calculate_compatibility_metrics(history, profile)
            print(
                f"  -> {status} | provider={source} EXACT | "
                f"target={comparison['target_rows']} rows | "
                f"existing={comparison['existing_rows']} | "
                f"same_values={comparison['exact_rows']} | "
                f"missing={len(comparison['missing_dates'])} | "
                f"value_diff={len(comparison['value_diffs'])} | "
                f"source_diff={len(comparison['source_mismatches'])} | "
                f"window_extra={len(comparison['window_extra'])} | "
                f"old_extra={len(comparison['harmless_old_extra'])}"
            )
            print(
                "     METRICS EXACT: "
                f"close={metrics['previous_close']:.4f}, "
                f"ma10={metrics['ma10']:.4f}, "
                f"ma200={metrics['ma200']:.4f}, "
                f"avgvol10={metrics['avg_volume_10']:.4f}"
            )
            print(
                "     EXISTING SOURCES: "
                + ", ".join(
                    f"{name}={count}"
                    for name, count in sorted(comparison["source_counts"].items())
                )
            )

            if comparison["missing_dates"]:
                print(
                    "     MISSING TARGET DATES: "
                    + fmt_dates(comparison["missing_dates"])
                )
            if comparison["window_extra"]:
                print(
                    "     EXTRA DATES INSIDE CANONICAL WINDOW: "
                    + fmt_dates(comparison["window_extra"])
                )
            if comparison["source_mismatches"]:
                print(
                    "     NON-CANONICAL SOURCES IN TARGET WINDOW: "
                    + fmt_dates(comparison["source_mismatches"])
                )
            print_diff_examples(comparison["value_diffs"])

            if len(target_rows) < TARGET_SESSIONS:
                print(
                    f"     BUFFER_SHORT: provider chi co {len(target_rows)}/"
                    f"{TARGET_SESSIONS} rows, nhung van du 200 de doi chieu MA200."
                )

        except Exception as exc:
            provider_errors += 1
            print(f"  -> ERROR {type(exc).__name__}: {exc}")

    print(
        "\nCANONICAL AUDIT SUMMARY: "
        f"requested={len(requested_symbols)}, audited={audited}, "
        f"already_canonical={already_canonical}, "
        f"candidate_ready={candidate_ready}, "
        f"skipped_under_200={skipped_under_200}, "
        f"short_buffer={short_buffer}, provider_errors={provider_errors}, "
        "write=False."
    )

    if provider_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
