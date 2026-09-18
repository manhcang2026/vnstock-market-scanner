from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from time import sleep
from typing import Any


SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.auction_bootstrap_audit import (  # noqa: E402
    INFERRED_BOUNDARY,
    audit_provider_session,
    compare_provider_rows,
    recommend_domain,
)


SYMBOLS = ("FPT", "HPG", "SSI", "VIC", "VCB", "VIX")
PROVIDERS = ("KBS", "VCI")
EVALUATION_DATE = date(2026, 9, 18)
PREFERRED_SESSIONS = 15
DEFAULT_FETCH_START = date(2026, 8, 14)
REQUEST_INTERVAL_SECONDS = 3.2  # guest vnstock tier is limited to 20 requests/minute

# vnstock 4.0.5 otherwise starts a background agent-onboarding writer on import.
# The audit is read-only apart from its explicit local output files.
os.environ.setdefault("VNSTOCK_DISABLE_AGENT_SETUP", "1")
os.environ.setdefault("VNSTOCK_DISABLE_GLOBAL_AGENT", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    return [_json_safe(row) for row in frame.to_dict("records")]


def _fetch(symbol: str, provider: str, start: str, end: str) -> tuple[list[dict], list[dict]]:
    from vnstock import Quote

    quote = Quote(symbol=symbol, source=provider, show_log=False)
    minute_kwargs = {"get_all": True} if provider == "KBS" else {}
    minute = quote.history(start=start, end=end, interval="1m", **minute_kwargs)
    sleep(REQUEST_INTERVAL_SECONDS)
    daily_kwargs = {"get_all": True} if provider == "KBS" else {}
    daily = quote.history(start=start, end=end, interval="1D", **daily_kwargs)
    return _records(minute), _records(daily)


def _date_of(row: dict[str, Any]) -> str:
    return str(row["time"])[:10]


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def _coverage(rows: list[dict[str, Any]], provider: str, domain: str) -> dict[str, Any]:
    selected = [row for row in rows if row["provider"] == provider]
    quality_key = "opening_inference_quality" if domain == "ATO" else "closing_inference_quality"
    usable = sum(row[quality_key] == INFERRED_BOUNDARY for row in selected)
    return {
        "provider_sessions_expected": len(selected),
        "provider_sessions_usable": usable,
        "coverage_pct": usable / len(selected) * 100 if selected else 0,
    }


def run(output_dir: Path, start: date, evaluation_date: date, sessions: int) -> dict[str, Any]:
    fetched: dict[tuple[str, str], tuple[list[dict], list[dict]]] = {}
    failures: list[dict[str, str]] = []
    for provider in PROVIDERS:
        for symbol in SYMBOLS:
            try:
                fetched[(provider, symbol)] = _fetch(
                    symbol, provider, start.isoformat(), (evaluation_date - timedelta(days=1)).isoformat()
                )
            except BaseException as exc:  # vnai rate limiting may raise SystemExit
                if isinstance(exc, KeyboardInterrupt):
                    raise
                failures.append(
                    {
                        "provider": provider,
                        "symbol": symbol,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            sleep(REQUEST_INTERVAL_SECONDS)

    observed_dates = sorted(
        {
            _date_of(row)
            for minute_rows, _ in fetched.values()
            for row in minute_rows
            if _date_of(row) < evaluation_date.isoformat()
        }
    )[-sessions:]

    audit_rows: list[dict[str, Any]] = []
    for provider in PROVIDERS:
        for symbol in SYMBOLS:
            pair = fetched.get((provider, symbol))
            if pair is None:
                continue
            minute_rows, daily_rows = pair
            daily_by_date = {_date_of(row): row for row in daily_rows}
            daily_dates = sorted(daily_by_date)
            for session_date in observed_dates:
                previous_dates = [item for item in daily_dates if item < session_date]
                audit_rows.append(
                    audit_provider_session(
                        provider=provider,
                        symbol=symbol,
                        trading_date=session_date,
                        minute_bars=[row for row in minute_rows if _date_of(row) == session_date],
                        daily_row=daily_by_date.get(session_date),
                        previous_daily_row=(
                            daily_by_date[previous_dates[-1]] if previous_dates else None
                        ),
                    )
                )

    by_key = {
        (row["provider"], row["symbol"], row["trading_date"]): row
        for row in audit_rows
    }
    comparisons = [
        compare_provider_rows(
            by_key.get(("KBS", symbol, session_date)),
            by_key.get(("VCI", symbol, session_date)),
            domain=domain,
        )
        for symbol in SYMBOLS
        for session_date in observed_dates
        for domain in ("ATO", "ATC")
    ]
    recommendation = {
        domain: recommend_domain(audit_rows, comparisons, domain=domain)
        for domain in ("ATO", "ATC")
    }
    summary = {
        "job": "BETA-04A",
        "evaluation_date": evaluation_date.isoformat(),
        "retrieval_start": start.isoformat(),
        "completed_session_rule": "strictly_before_evaluation_date",
        "symbols": list(SYMBOLS),
        "providers": list(PROVIDERS),
        "sessions_requested": sessions,
        "sessions_observed": observed_dates,
        "session_count": len(observed_dates),
        "provider_fetch_successes": [
            {"provider": provider, "symbol": symbol}
            for provider, symbol in sorted(fetched)
        ],
        "provider_fetch_failures": failures,
        "audit_row_count": len(audit_rows),
        "comparison_row_count": len(comparisons),
        "coverage": {
            domain: {
                provider: _coverage(audit_rows, provider, domain)
                for provider in PROVIDERS
            }
            for domain in ("ATO", "ATC")
        },
        "agreement": {
            domain: dict(
                Counter(
                    row["classification"]
                    for row in comparisons
                    if row["domain"] == domain
                )
            )
            for domain in ("ATO", "ATC")
        },
        "daily_reconciliation": {
            provider: {
                "rows": len(selected := [row for row in audit_rows if row["provider"] == provider]),
                "exact": sum(bool(row["reconciled_exactly"]) for row in selected),
                "missing_daily": sum(row["daily_volume"] is None for row in selected),
                "mismatch": sum(
                    row["daily_volume"] is not None and not row["reconciled_exactly"]
                    for row in selected
                ),
            }
            for provider in PROVIDERS
        },
        "recommendation": recommendation,
        "quality_guard": {
            "allowed_inferred_label": INFERRED_BOUNDARY,
            "proven_rows_emitted": sum(row["quality_tier"] == "PROVEN" for row in audit_rows),
        },
        "classification_note": (
            "STRONG requires exact timestamp, price and volume equality; WEAK requires "
            "equal timestamp and price with a volume difference. No product tolerance is applied."
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "auction_bootstrap_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(output_dir / "auction_bootstrap_audit_rows.csv", audit_rows)
    _write_csv(output_dir / "auction_bootstrap_provider_comparison.csv", comparisons)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only KBS/VCI auction bootstrap audit")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_FETCH_START)
    parser.add_argument("--evaluation-date", type=date.fromisoformat, default=EVALUATION_DATE)
    parser.add_argument("--sessions", type=int, default=PREFERRED_SESSIONS)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    summary = run(args.output_dir, args.start, args.evaluation_date, args.sessions)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
