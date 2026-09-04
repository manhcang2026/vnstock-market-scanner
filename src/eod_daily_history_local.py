from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import backfill_daily_history as backfill
import eod_daily_history_from_intraday as legacy_eod
import market_session_guard
from common import load_watchlist, now_vn

REPORT_JSON = Path("daily_history_eod_local_report.json")


def resolve_trading_date() -> date:
    raw = os.getenv("EOD_TRADING_DATE", "").strip()
    if raw:
        return date.fromisoformat(raw)
    return now_vn().date()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def set_github_output(name: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT", "").strip()
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def write_report(report: dict[str, Any]) -> None:
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> None:
    trading_date = resolve_trading_date()
    write = env_bool("EOD_WRITE", default=False)
    run_at = now_vn()

    decision = market_session_guard.session_decision(trading_date)
    set_github_output(
        "trading_day",
        "true" if decision.trading_day else "false",
    )

    report: dict[str, Any] = {
        "run_at": run_at.isoformat(),
        "trading_date": trading_date.isoformat(),
        "write": write,
        "session_decision": decision.reason,
        "counts": {
            "exists": 0,
            "intraday_eod": 0,
            "provider_fallback": 0,
            "no_bar": 0,
            "candidates": 0,
            "written": 0,
            "errors": 0,
        },
        "results": [],
    }

    # Holiday/weekend guard MUST happen before any provider verification/call.
    if not decision.trading_day:
        report["skipped"] = decision.reason
        write_report(report)
        print(
            f"EOD LOCAL SKIP: {trading_date} is not an approved trading day; "
            f"reason={decision.reason}; provider_fallback=0."
        )
        return

    if not legacy_eod.session_is_completed(trading_date):
        raise RuntimeError(
            f"SAFETY STOP: session {trading_date} is not completed (safe after 15:10 VN)."
        )

    backfill.verify_supabase_config()

    watchlist = load_watchlist()
    exchanges = {
        str(row.symbol).strip().upper(): str(row.exchange).strip().upper()
        for row in watchlist.itertuples(index=False)
    }
    symbols = sorted(exchanges)

    existing = legacy_eod.load_existing_symbols(trading_date)
    snapshots = legacy_eod.load_final_snapshots(trading_date)
    profiles = backfill.load_baseline_profiles()

    candidates: list[dict[str, Any]] = []
    provider_access_verified = False

    for index, symbol in enumerate(symbols, start=1):
        result: dict[str, Any] = {
            "symbol": symbol,
            "status": "",
            "source": "",
            "detail": "",
        }

        try:
            if symbol in existing:
                report["counts"]["exists"] += 1
                result["status"] = "EXISTS"
                report["results"].append(result)
                print(f"[{index}/{len(symbols)}] {symbol} -> EXISTS")
                continue

            snapshot = snapshots.get(symbol)
            row = legacy_eod.intraday_eod_row(
                symbol=symbol,
                exchange=exchanges[symbol],
                snapshot=snapshot,
                trading_date=trading_date,
                updated_at=run_at,
            )

            if row is not None:
                report["counts"]["intraday_eod"] += 1
                result["status"] = "CANDIDATE"
                result["source"] = "INTRADAY_EOD"
                result["detail"] = (
                    f"slot={snapshot.get('time_slot') if snapshot else None}, "
                    f"close={row['close']}, volume={row['volume']}"
                )
            else:
                # Ambiguous/missing/zero-volume final snapshot:
                # ask provider ONLY for this symbol. This avoids the old 800-symbol
                # nightly history scan while preserving official zero-volume bars.
                if not provider_access_verified:
                    backfill.verify_vnstock_api_access()
                    provider_access_verified = True

                profile = profiles.get(symbol) or {}
                preferred_source = str(
                    profile.get("source") or backfill.PRIMARY_SOURCE
                )
                row, detail = legacy_eod.fetch_provider_eod_row(
                    symbol=symbol,
                    exchange=exchanges[symbol],
                    preferred_source=preferred_source,
                    trading_date=trading_date,
                    updated_at=run_at,
                )
                report["counts"]["provider_fallback"] += 1
                result["detail"] = detail

                if row is None:
                    report["counts"]["no_bar"] += 1
                    result["status"] = "NO_BAR"
                    print(
                        f"[{index}/{len(symbols)}] {symbol} -> "
                        f"PROVIDER_FALLBACK NO_BAR"
                    )
                    report["results"].append(result)
                    continue

                result["status"] = "CANDIDATE"
                result["source"] = str(row["source"])

            report["counts"]["candidates"] += 1
            candidates.append(row)
            print(
                f"[{index}/{len(symbols)}] {symbol} -> CANDIDATE "
                f"source={result['source']}"
            )

            if write and len(candidates) >= legacy_eod.WRITE_BATCH_SIZE:
                legacy_eod.insert_ignore_duplicates(candidates)
                report["counts"]["written"] += len(candidates)
                existing.update(str(item["symbol"]) for item in candidates)
                candidates.clear()

        except Exception as exc:
            report["counts"]["errors"] += 1
            result["status"] = "ERROR"
            result["detail"] = f"{type(exc).__name__}: {exc}"
            print(
                f"[{index}/{len(symbols)}] {symbol} -> ERROR: "
                f"{result['detail']}"
            )

        report["results"].append(result)
        write_report(report)

    if write and candidates:
        legacy_eod.insert_ignore_duplicates(candidates)
        report["counts"]["written"] += len(candidates)
        existing.update(str(item["symbol"]) for item in candidates)
        candidates.clear()

    if write:
        stored = legacy_eod.load_existing_symbols(trading_date)
        expected = {
            str(row["symbol"])
            for row in report["results"]
            if row.get("status") == "CANDIDATE"
        }
        missing_after_write = sorted(expected - stored)
        if missing_after_write:
            report["counts"]["errors"] += len(missing_after_write)
            report["write_verify_missing"] = missing_after_write
            write_report(report)
            raise RuntimeError(
                "WRITE VERIFY ERROR: missing after insert: "
                + ", ".join(missing_after_write[:30])
            )

    write_report(report)
    counts = report["counts"]
    print(
        "EOD LOCAL-FIRST SUMMARY: "
        + ", ".join(f"{key}={value}" for key, value in counts.items())
    )
    print(
        "RULE: provider fallback is used only for symbols whose final intraday "
        "snapshot cannot establish an official EOD bar."
    )

    if counts["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
