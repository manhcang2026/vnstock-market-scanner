from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

import backfill_daily_history as backfill
import finalize_clean_history as finalizer


REBASE_PRICE_REL_TOLERANCE = 0.005
REBASE_VOLUME_REL_TOLERANCE = 0.02
REBASE_REPORT = Path("clean_history_rebase_report.json")

_ORIGINAL_GET_HISTORY = backfill.get_history
_REBASE_EVENTS: list[dict[str, Any]] = []


def parse_symbols(raw: str) -> set[str]:
    return {
        item.strip().upper()
        for item in raw.replace(";", ",").split(",")
        if item.strip()
    }


def relative_gap(left: float, right: float) -> float:
    denominator = max(abs(left), abs(right), 1.0)
    return abs(left - right) / denominator


def provider_consensus_detail(
    first_source: str,
    first_metrics: dict[str, Any],
    second_source: str,
    second_metrics: dict[str, Any],
) -> str:
    if first_metrics["trading_date"] != second_metrics["trading_date"]:
        raise RuntimeError(
            "REBASE provider date mismatch: "
            f"{first_source}={first_metrics['trading_date']} vs "
            f"{second_source}={second_metrics['trading_date']}"
        )

    checks = (
        ("previous_close", REBASE_PRICE_REL_TOLERANCE),
        ("ma10", REBASE_PRICE_REL_TOLERANCE),
        ("ma200", REBASE_PRICE_REL_TOLERANCE),
        ("avg_volume_10", REBASE_VOLUME_REL_TOLERANCE),
    )
    details: list[str] = []
    failures: list[str] = []

    for key, tolerance in checks:
        left = float(first_metrics[key])
        right = float(second_metrics[key])
        gap = relative_gap(left, right)
        details.append(
            f"{key}: {first_source}={left:.4f}, "
            f"{second_source}={right:.4f}, gap={gap:.4%}"
        )
        if gap > tolerance:
            failures.append(
                f"{key} gap={gap:.4%} > tolerance={tolerance:.2%}"
            )

    if failures:
        raise RuntimeError(
            "REBASE provider consensus FAIL: " + "; ".join(failures)
        )
    return "; ".join(details)


def fetch_rebase_candidate(
    *,
    symbol: str,
    source: str,
    run_date,
    profile: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_sessions = int(profile["ma200_sessions"])
    anchor_date = profile["trading_date"]
    history = backfill.fetch_source_history_adaptive(
        symbol=symbol,
        source=source,
        run_date=run_date,
        required_sessions=required_sessions,
        anchor_date=anchor_date,
    )
    if len(history) < required_sessions:
        raise RuntimeError(
            f"{source}: REBASE chi co {len(history)}/{required_sessions} phien"
        )

    metrics = backfill.calculate_compatibility_metrics(history, profile)
    if metrics["trading_date"] != anchor_date:
        raise RuntimeError(
            f"{source}: REBASE anchor mismatch "
            f"{metrics['trading_date']} != {anchor_date}"
        )
    return history, metrics


def get_rebase_history(
    *,
    symbol: str,
    run_date,
    profile: dict[str, Any],
    exact_error: str,
) -> tuple[pd.DataFrame, str]:
    preferred_source = str(profile["source"]).strip().upper()
    if preferred_source not in {backfill.PRIMARY_SOURCE, backfill.FALLBACK_SOURCE}:
        preferred_source = backfill.PRIMARY_SOURCE
    alternate_source = (
        backfill.FALLBACK_SOURCE
        if preferred_source == backfill.PRIMARY_SOURCE
        else backfill.PRIMARY_SOURCE
    )

    candidates: dict[str, tuple[pd.DataFrame, dict[str, Any]]] = {}
    provider_errors: list[str] = []
    for source in (preferred_source, alternate_source):
        try:
            candidates[source] = fetch_rebase_candidate(
                symbol=symbol,
                source=source,
                run_date=run_date,
                profile=profile,
            )
        except Exception as exc:
            provider_errors.append(f"{source}: {type(exc).__name__}: {exc}")

    if len(candidates) != 2:
        raise RuntimeError(
            "REBASE can 2 provider doc lap cung xac nhan; "
            + " | ".join(provider_errors or ["khong du 2 provider"])
        )

    preferred_history, preferred_metrics = candidates[preferred_source]
    _, alternate_metrics = candidates[alternate_source]
    consensus = provider_consensus_detail(
        preferred_source,
        preferred_metrics,
        alternate_source,
        alternate_metrics,
    )

    event = {
        "symbol": symbol,
        "mode": "REBASE_APPROVED_PROVIDER_CONSENSUS",
        "seed_source": preferred_source,
        "anchor_date": str(profile["trading_date"]),
        "production_source": str(profile.get("source") or ""),
        "exact_gate_error": exact_error,
        "provider_consensus": consensus,
        "preferred_metrics": preferred_metrics,
        "alternate_source": alternate_source,
        "alternate_metrics": alternate_metrics,
    }
    _REBASE_EVENTS.append(event)

    print(
        f"  -> REBASE APPROVED {symbol}: EXACT production khong con tai tao duoc; "
        f"2 provider dong thuan. seed={preferred_source}."
    )
    print(f"     consensus: {consensus}")
    return preferred_history, preferred_source


def install_rebase_gate() -> set[str]:
    approved = parse_symbols(os.getenv("FINALIZE_REBASE_SYMBOLS", ""))
    write = finalizer.env_bool("FINALIZE_WRITE", False)
    rebase_confirm = os.getenv("FINALIZE_REBASE_CONFIRM", "").strip().upper()

    if write and approved and rebase_confirm != "REBASE":
        raise RuntimeError(
            'write=true + FINALIZE_REBASE_SYMBOLS bat buoc '
            'FINALIZE_REBASE_CONFIRM="REBASE".'
        )

    def get_history_with_rebase(
        symbol: str,
        run_date,
        profile: dict[str, Any],
    ) -> tuple[pd.DataFrame, str]:
        try:
            return _ORIGINAL_GET_HISTORY(symbol, run_date, profile)
        except RuntimeError as exc:
            normalized = symbol.strip().upper()
            if normalized not in approved:
                raise
            print(
                f"  -> {normalized} nam trong FINALIZE_REBASE_SYMBOLS; "
                "kich hoat gate 2-provider consensus."
            )
            return get_rebase_history(
                symbol=normalized,
                run_date=run_date,
                profile=profile,
                exact_error=str(exc),
            )

    backfill.get_history = get_history_with_rebase
    return approved


def write_rebase_report() -> None:
    payload = {
        "requested_symbols": sorted(
            parse_symbols(os.getenv("FINALIZE_REBASE_SYMBOLS", ""))
        ),
        "rebase_count": len(_REBASE_EVENTS),
        "events": _REBASE_EVENTS,
        "safety": {
            "requires_two_providers": True,
            "price_metric_relative_tolerance": REBASE_PRICE_REL_TOLERANCE,
            "volume_metric_relative_tolerance": REBASE_VOLUME_REL_TOLERANCE,
            "write_requires_rebase_confirm": True,
        },
    }
    REBASE_REPORT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> None:
    approved = install_rebase_gate()
    atexit.register(write_rebase_report)
    print(
        "REBASE SAFETY GATE: "
        f"approved={','.join(sorted(approved)) if approved else '(none)'}; "
        "chi bypass EXACT khi 2 provider dong thuan trong tolerance; "
        "backfill_daily_history.py khong bi thay doi semantics."
    )
    finalizer.main()


if __name__ == "__main__":
    main()
