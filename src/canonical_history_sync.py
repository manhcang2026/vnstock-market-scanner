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
CANONICAL_SOURCE = "KBS"
VALUE_TOLERANCE = 0.0001
DEFAULT_SAMPLE = "TLP,VIT,CLC,VNC,MAC,PDN"
DELETE_BATCH_SIZE = 50


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


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


def normalize_rows(rows: list[dict[str, Any]]) -> dict[date, dict[str, Any]]:
    result: dict[date, dict[str, Any]] = {}
    for row in rows:
        try:
            trading_date = date.fromisoformat(str(row.get("trading_date") or ""))
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


def build_target_rows(
    *,
    symbol: str,
    exchange: str,
    history: pd.DataFrame,
    updated_at,
) -> list[dict[str, Any]]:
    return backfill.history_rows(
        symbol=symbol,
        exchange=exchange,
        history=history,
        source=CANONICAL_SOURCE,
        updated_at=updated_at,
    )


def compare_window(
    existing_rows: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    existing = normalize_rows(existing_rows)
    target = normalize_rows(target_rows)

    target_dates = sorted(target)
    if not target_dates:
        raise RuntimeError("Target canonical rong.")

    earliest = target_dates[0]
    latest = target_dates[-1]
    target_date_set = set(target_dates)

    existing_in_window = {
        d: row for d, row in existing.items() if earliest <= d <= latest
    }

    missing_dates = sorted(target_date_set - set(existing_in_window))
    extra_dates = sorted(set(existing_in_window) - target_date_set)

    value_diffs: list[dict[str, Any]] = []
    source_diffs: list[date] = []
    exact_values = 0

    for trading_date in sorted(target_date_set & set(existing_in_window)):
        current = existing_in_window[trading_date]
        expected = target[trading_date]
        close_diff = current["close_num"] - expected["close_num"]
        volume_diff = current["volume_num"] - expected["volume_num"]

        if (
            abs(close_diff) <= VALUE_TOLERANCE
            and abs(volume_diff) <= VALUE_TOLERANCE
        ):
            exact_values += 1
        else:
            value_diffs.append(
                {
                    "trading_date": trading_date,
                    "current_close": current["close_num"],
                    "target_close": expected["close_num"],
                    "current_volume": current["volume_num"],
                    "target_volume": expected["volume_num"],
                }
            )

        if current["source_norm"] != CANONICAL_SOURCE:
            source_diffs.append(trading_date)

    newer_preserved = sorted(d for d in existing if d > latest)
    older_preserved = sorted(d for d in existing if d < earliest)

    return {
        "earliest": earliest,
        "latest": latest,
        "target_rows": len(target_rows),
        "existing_total": len(existing_rows),
        "existing_window": len(existing_in_window),
        "exact_values": exact_values,
        "missing_dates": missing_dates,
        "extra_dates": extra_dates,
        "value_diffs": value_diffs,
        "source_diffs": source_diffs,
        "older_preserved": older_preserved,
        "newer_preserved": newer_preserved,
        "source_counts": Counter(
            str(row.get("source") or "").strip().upper() or "UNKNOWN"
            for row in existing_rows
        ),
    }


def fmt_dates(values: list[date], limit: int = 5) -> str:
    if not values:
        return "-"
    shown = ",".join(d.isoformat() for d in values[:limit])
    if len(values) > limit:
        shown += f",...(+{len(values) - limit})"
    return shown


def print_plan(symbol: str, comparison: dict[str, Any]) -> None:
    print(
        f"  -> PLAN {symbol}: target={comparison['target_rows']} | "
        f"window={comparison['earliest']}..{comparison['latest']} | "
        f"missing={len(comparison['missing_dates'])} | "
        f"value_diff={len(comparison['value_diffs'])} | "
        f"source_diff={len(comparison['source_diffs'])} | "
        f"delete_extra_in_window={len(comparison['extra_dates'])} | "
        f"older_preserved={len(comparison['older_preserved'])} | "
        f"newer_preserved={len(comparison['newer_preserved'])}"
    )
    print(
        "     EXISTING SOURCES: "
        + ", ".join(
            f"{name}={count}"
            for name, count in sorted(comparison["source_counts"].items())
        )
    )
    if comparison["missing_dates"]:
        print("     MISSING: " + fmt_dates(comparison["missing_dates"]))
    if comparison["extra_dates"]:
        print(
            "     DELETE ONLY INSIDE CANONICAL WINDOW: "
            + fmt_dates(comparison["extra_dates"])
        )
    if comparison["newer_preserved"]:
        print("     NEWER ROWS PRESERVED: " + fmt_dates(comparison["newer_preserved"]))


def delete_extra_dates(symbol: str, dates: list[date]) -> None:
    if not dates:
        return

    for offset in range(0, len(dates), DELETE_BATCH_SIZE):
        batch = dates[offset:offset + DELETE_BATCH_SIZE]
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


def verify_canonical_window(
    symbol: str,
    target_rows: list[dict[str, Any]],
) -> tuple[bool, str]:
    current_rows = load_existing_history(symbol)
    check = compare_window(current_rows, target_rows)

    problems: list[str] = []
    if check["missing_dates"]:
        problems.append(f"missing={len(check['missing_dates'])}")
    if check["extra_dates"]:
        problems.append(f"extra={len(check['extra_dates'])}")
    if check["value_diffs"]:
        problems.append(f"value_diff={len(check['value_diffs'])}")
    if check["source_diffs"]:
        problems.append(f"source_diff={len(check['source_diffs'])}")

    if problems:
        return False, ", ".join(problems)
    return True, (
        f"EXACT {check['target_rows']} rows "
        f"{check['earliest']}..{check['latest']} source={CANONICAL_SOURCE}"
    )


def fetch_kbs_exact_history(
    *,
    symbol: str,
    profile: dict[str, Any],
    run_date: date,
) -> pd.DataFrame:
    anchor_date = profile["trading_date"]

    history = backfill.fetch_source_history_adaptive(
        symbol=symbol,
        source=CANONICAL_SOURCE,
        run_date=run_date,
        required_sessions=FULL_MA200_SESSIONS,
        anchor_date=anchor_date,
    )

    if len(history) < FULL_MA200_SESSIONS:
        raise RuntimeError(
            f"KBS chi co {len(history)} phien; can >= {FULL_MA200_SESSIONS}."
        )

    exact, detail = backfill.compare_with_production(history, profile)
    if not exact:
        raise RuntimeError(
            "KBS khong EXACT voi Daily Baseline production: " + detail
        )

    return history


def main() -> None:
    write = env_bool("CANONICAL_WRITE", False)
    confirm = os.getenv("CANONICAL_CONFIRM", "").strip().upper()

    if write and confirm != "WRITE":
        raise RuntimeError(
            'CANONICAL_WRITE=true chi duoc phep khi CANONICAL_CONFIRM="WRITE".'
        )

    backfill.verify_vnstock_api_access()
    backfill.verify_supabase_config()

    run_at = backfill.now_vn()
    if backfill.in_market_protection_window(run_at):
        print(
            "SAFETY STOP: dang trong khung 08:20-15:10 ngay giao dich. "
            "Phase B khong goi VNStock va khong ghi Supabase."
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
        "Canonical Daily History Sync - PHASE B\n"
        f"run_at={run_at.isoformat()} | requested={len(requested_symbols)} | "
        f"canonical_source={CANONICAL_SOURCE} | target_buffer={TARGET_SESSIONS} | "
        f"write={write}\n"
        "RULE 1: chi xu ly ma Daily Baseline ma200_sessions >= 200.\n"
        "RULE 2: KBS phai tai tao EXACT Daily Baseline production.\n"
        "RULE 3: upsert canonical target truoc; chi xoa EXTRA date nam BEN TRONG "
        "cua so canonical sau do.\n"
        "RULE 4: row cu hon va row moi hon cua so canonical duoc GIU NGUYEN.\n"
        "RULE 5: khong dung VCI fallback trong Phase B."
    )

    candidate_ready = 0
    already_canonical = 0
    written = 0
    skipped_under_200 = 0
    errors: list[tuple[str, str]] = []

    for index, symbol in enumerate(requested_symbols, start=1):
        exchange = watchlist_map.get(symbol)
        profile = profiles.get(symbol)

        if exchange is None:
            message = "not in watchlist"
            errors.append((symbol, message))
            print(f"[{index}/{len(requested_symbols)}] {symbol} -> ERROR {message}")
            continue

        if profile is None:
            message = "no baseline profile"
            errors.append((symbol, message))
            print(f"[{index}/{len(requested_symbols)}] {symbol} -> ERROR {message}")
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
            f"baseline_date={profile['trading_date']} "
            f"baseline_source={profile['source']}"
        )

        try:
            history = fetch_kbs_exact_history(
                symbol=symbol,
                profile=profile,
                run_date=run_at.date(),
            )

            target_rows = build_target_rows(
                symbol=symbol,
                exchange=exchange,
                history=history,
                updated_at=run_at,
            )

            if len(target_rows) < FULL_MA200_SESSIONS:
                raise RuntimeError(
                    f"Target chi co {len(target_rows)} rows; khong du 200."
                )

            existing_rows = load_existing_history(symbol)
            comparison = compare_window(existing_rows, target_rows)
            print_plan(symbol, comparison)

            has_change = bool(
                comparison["missing_dates"]
                or comparison["extra_dates"]
                or comparison["value_diffs"]
                or comparison["source_diffs"]
            )

            if not has_change:
                already_canonical += 1
                print("  -> ALREADY_CANONICAL; khong can ghi.")
                continue

            candidate_ready += 1
            if not write:
                print("  -> DRY_RUN CANDIDATE_READY; khong ghi Supabase.")
                continue

            # SAFETY ORDER:
            # 1) upsert day du target KBS truoc, de neu delete fail thi khong tao gap.
            backfill.upsert_rows(
                "daily_history",
                target_rows,
                "symbol,trading_date",
            )

            # 2) verify target dates/value/source da canonical truoc khi xoa extra.
            after_upsert_rows = load_existing_history(symbol)
            after_upsert = compare_window(after_upsert_rows, target_rows)
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

            # 3) chi xoa extra date BEN TRONG cua so target.
            # Row cu hon / moi hon cua so target tuyet doi khong bi dong toi.
            delete_extra_dates(symbol, after_upsert["extra_dates"])

            # 4) final exact verify.
            exact, detail = verify_canonical_window(symbol, target_rows)
            if not exact:
                raise RuntimeError("FINAL VERIFY FAIL: " + detail)

            written += 1
            print(f"  -> WRITTEN + VERIFIED: {detail}")

        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            errors.append((symbol, message))
            print(f"  -> ERROR {message}")

    print(
        "\nCANONICAL PHASE B SUMMARY: "
        f"requested={len(requested_symbols)}, "
        f"candidate_ready={candidate_ready}, "
        f"already_canonical={already_canonical}, "
        f"written={written}, "
        f"skipped_under_200={skipped_under_200}, "
        f"errors={len(errors)}, "
        f"write={write}."
    )

    if errors:
        print("ERROR SYMBOLS:")
        for symbol, message in errors:
            print(f"  {symbol}: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
