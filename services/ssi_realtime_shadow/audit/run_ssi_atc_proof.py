from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.ssi_atc_proof import (  # noqa: E402
    CONFIRMED_INFERRED_BOUNDARY,
    UNCONFIRMED_BOUNDARY,
    UNAVAILABLE,
    exact10_coverage,
    prove_ssi_atc_boundary,
)
from app.volume_baseline import load_candidate_market_sessions  # noqa: E402


SYMBOLS = ("FPT", "HPG", "SSI", "VIC", "VCB", "VIX")
SESSIONS = (
    "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28",
    "2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08",
    "2026-09-09", "2026-09-10", "2026-09-11", "2026-09-14",
    "2026-09-15", "2026-09-16", "2026-09-17",
)
AS_OF_DATE = "2026-09-18"
EXPECTED_ARCHIVE_SHA256 = "a2a7b17b5f27d567276f48391fe2193e5b83b382cd79f27ed5f15be2de60b710"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_witnesses(path: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    witnesses: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _read_csv(path):
        provider = row["provider"].upper()
        if provider in {"KBS", "VCI"} and row.get("closing_inference_quality") == "INFERRED_BOUNDARY":
            witnesses[(provider, row["symbol"], row["trading_date"])] = row
    return witnesses


def _csv_value(value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_dates_from_local(
    minute_rows: list[dict[str, str]], daily_rows: list[dict[str, str]]
) -> list[str]:
    history = sqlite3.connect(":memory:")
    daily = sqlite3.connect(":memory:")
    history.execute("CREATE TABLE minute_bars (trading_date TEXT, data_source TEXT, exchange TEXT)")
    daily.execute("CREATE TABLE daily_bars (trading_date TEXT, source TEXT, quality_status TEXT)")
    history.executemany(
        "INSERT INTO minute_bars VALUES (?, ?, ?)",
        {(row["trading_date"], row["source"], row["exchange"]) for row in minute_rows},
    )
    daily.executemany(
        "INSERT INTO daily_bars VALUES (?, ?, ?)",
        {(row["trading_date"], row["source"], row["quality_status"]) for row in daily_rows},
    )
    return load_candidate_market_sessions(history, daily, as_of_date=AS_OF_DATE, lookback=10)


def _stream_settlement_check(
    stream_rows: list[dict[str, str]], rest_rows: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rest = {
        (row["symbol"], row["trading_date"]): row
        for row in rest_rows
        if row["minute"] == "14:45" and row["trading_date"] in {"2026-09-16", "2026-09-17"}
    }
    comparisons: list[dict[str, Any]] = []
    for row in stream_rows:
        if row["minute"] != "14:45":
            continue
        key = (row["symbol"], row["trading_date"])
        witness = rest.get(key)
        price_match = bool(witness) and float(row["close"]) == float(witness["close"])
        volume_match = bool(witness) and int(row["volume"]) == int(witness["volume"])
        comparisons.append(
            {
                "symbol": row["symbol"],
                "trading_date": row["trading_date"],
                "stream_close": float(row["close"]),
                "stream_volume": int(row["volume"]),
                "stream_quality_status": row["quality_status"],
                "stream_is_partial": int(row["is_partial"]),
                "rest_close": float(witness["close"]) if witness else None,
                "rest_volume": int(witness["volume"]) if witness else None,
                "price_match": price_match,
                "volume_match": volume_match,
                "settled_match": price_match and volume_match,
            }
        )
    return comparisons, {
        "rows": len(comparisons),
        "exact_price_volume_matches": sum(row["settled_match"] for row in comparisons),
        "differences": sum(not row["settled_match"] for row in comparisons),
    }


def run(output_dir: Path, input_dir: Path) -> dict[str, Any]:
    required = {
        "minute": input_dir / "ssi_1m_beta04b_complete.csv",
        "daily": input_dir / "ssi_daily_beta04b.csv",
        "reconciliation": input_dir / "ssi_beta04b_reconciliation.csv",
        "stream": input_dir / "ssi_stream_20260916_20260917.csv",
        "old_rest": input_dir / "ssi_rest_1m_beta04b.csv",
        "gap_rest": input_dir / "ssi_rest_gap_20260916_20260917.csv",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing BETA-04B local input: " + ", ".join(missing))

    witnesses = _read_witnesses(output_dir / "auction_bootstrap_audit_rows.csv")
    minute_rows = _read_csv(required["minute"])
    daily_rows = _read_csv(required["daily"])
    reconciliation_rows = _read_csv(required["reconciliation"])
    stream_rows = _read_csv(required["stream"])
    old_rest_rows = _read_csv(required["old_rest"])
    gap_rest_rows = _read_csv(required["gap_rest"])

    expected_keys = {(symbol, session) for symbol in SYMBOLS for session in SESSIONS}
    minute_by_key: dict[tuple[str, str], list[dict[str, str]]] = {}
    invalid_minute_keys: set[tuple[str, str]] = set()
    for row in minute_rows:
        key = (row["symbol"], row["trading_date"])
        minute_by_key.setdefault(key, []).append(row)
        if row["source"] != "SSI_REST" or row["quality_status"] != "TRUSTED":
            invalid_minute_keys.add(key)
    daily_by_key = {(row["symbol"], row["trading_date"]): row for row in daily_rows}

    proof_rows: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        for session in SESSIONS:
            key = (symbol, session)
            daily = daily_by_key.get(key)
            result = prove_ssi_atc_boundary(
                symbol=symbol,
                trading_date=session,
                ssi_bars=minute_by_key.get(key, []),
                ssi_daily_volume=int(daily["volume"]) if daily else None,
                kbs_witness=witnesses.get(("KBS", symbol, session)),
                vci_witness=witnesses.get(("VCI", symbol, session)),
            )
            if key in invalid_minute_keys or (
                daily is not None
                and (daily["source"] != "SSI_DAILY_OHLC" or daily["quality_status"] != "TRUSTED")
            ):
                result["failure_reasons"].append("SSI_INPUT_NOT_CANONICAL_TRUSTED")
                result["classification"] = UNCONFIRMED_BOUNDARY
                result["quality"] = UNCONFIRMED_BOUNDARY
                result["proof"] = None
            proof_rows.append(result)

    exact_dates = _candidate_dates_from_local(minute_rows, daily_rows)
    coverage = exact10_coverage(symbols=SYMBOLS, candidate_dates=exact_dates, proof_rows=proof_rows)
    stream_comparisons, stream_summary = _stream_settlement_check(stream_rows, minute_rows)
    confirmed = sum(row["classification"] == CONFIRMED_INFERRED_BOUNDARY for row in proof_rows)
    rejected = sum(row["classification"] == UNCONFIRMED_BOUNDARY for row in proof_rows)
    unavailable = sum(row["classification"] == UNAVAILABLE for row in proof_rows)
    cross_match_keys = (
        "minute_match_kbs", "minute_match_vci", "price_match_kbs",
        "price_match_vci", "volume_match_kbs", "volume_match_vci",
    )
    exact_cross_provider = sum(all(row.get(key) for key in cross_match_keys) for row in proof_rows)
    cross_mismatch = sum(not all(row.get(key) for key in cross_match_keys) for row in proof_rows)
    daily_exact = sum(bool(row.get("ssi_daily_reconciled_exactly")) for row in proof_rows)
    daily_mismatch = sum(not bool(row.get("ssi_daily_reconciled_exactly")) for row in proof_rows)

    archive = input_dir / "ccc_beta04b_dataset_20260918.tar.gz"
    archive_hash = _sha256(archive) if archive.is_file() else None
    extraction_reconciliation_exact = sum(row.get("exact") == "True" for row in reconciliation_rows)
    fpt = next(row for row in proof_rows if row["symbol"] == "FPT" and row["trading_date"] == "2026-09-17")
    vix_stream = next(
        row for row in stream_comparisons
        if row["symbol"] == "VIX" and row["trading_date"] == "2026-09-16"
    )
    decision = (
        "ALLOW_TEMP_INFERRED_BOOTSTRAP"
        if confirmed == len(expected_keys)
        and daily_exact == len(expected_keys)
        and exact_cross_provider == len(expected_keys)
        and len(exact_dates) == 10
        and all(row["temporary_baseline_usable"] for row in coverage)
        else "DIAGNOSTIC_ONLY"
    )
    summary = {
        "job": "BETA-04B",
        "audit_status": "COMPLETED_LOCAL_DATASET",
        "as_of_date": AS_OF_DATE,
        "symbols": list(SYMBOLS),
        "sessions": list(SESSIONS),
        "scope_rows": len(expected_keys),
        "rows_attempted": len(proof_rows),
        "rows_confirmed": confirmed,
        "rows_rejected": rejected,
        "rows_unavailable": unavailable,
        "three_provider_exact_matches": exact_cross_provider,
        "three_provider_mismatches": cross_mismatch,
        "ssi_daily_reconciliation_exact": daily_exact,
        "ssi_daily_reconciliation_mismatch": daily_mismatch,
        "exact_previous_10_dates": exact_dates,
        "exact_previous_10_coverage": coverage,
        "input_verification": {
            "combined_minute_rows": len(minute_rows),
            "old_rest_rows": len(old_rest_rows),
            "gap_rest_rows": len(gap_rest_rows),
            "minute_symbol_sessions": len(minute_by_key),
            "missing_symbol_sessions": len(expected_keys.difference(minute_by_key)),
            "duplicate_minute_keys": len(minute_rows) - len({(row["symbol"], row["trading_date"], row["minute"]) for row in minute_rows}),
            "minute_source_counts": dict(Counter(row["source"] for row in minute_rows)),
            "minute_quality_counts": dict(Counter(row["quality_status"] for row in minute_rows)),
            "daily_rows": len(daily_rows),
            "extraction_reconciliation_rows": len(reconciliation_rows),
            "extraction_reconciliation_exact": extraction_reconciliation_exact,
            "archive_present": archive.is_file(),
            "archive_sha256": archive_hash,
            "archive_sha256_matches_expected": archive_hash == EXPECTED_ARCHIVE_SHA256 if archive_hash else False,
        },
        "ssi_rest_stream_settlement": stream_summary,
        "vix_2026_09_16_event_vs_settled": vix_stream,
        "fpt_2026_09_17": fpt,
        "historical_proven_rows": sum(row.get("quality") == "PROVEN" for row in proof_rows),
        "final_decision": decision,
        "blocker": None if decision == "ALLOW_TEMP_INFERRED_BOOTSTRAP" else "One or more locked proof criteria failed.",
    }
    _write_csv(output_dir / "ssi_atc_proof_rows.csv", proof_rows)
    _write_csv(output_dir / "ssi_atc_exact10_coverage.csv", coverage)
    (output_dir / "ssi_atc_proof_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-only SSI historical ATC proof")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--input-dir", type=Path, default=Path(__file__).resolve().parent / "beta04b_input")
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir, args.input_dir), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
