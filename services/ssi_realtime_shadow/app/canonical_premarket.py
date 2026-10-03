"""Safety checks and post-rebuild validation for canonical premarket work."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping

from .canonical_config import CanonicalMetadataConfig
from .market_session import VN_TZ, market_day_feed_start
from .universe import load_exchange_map


PREMARKET_MIN_LEAD = timedelta(minutes=10)


def premarket_refusal_reason(
    *,
    market_db_dir: Path,
    day: date,
    now: datetime,
    exchange_map: Mapping[str, str],
) -> str | None:
    local = now.astimezone(VN_TZ) if now.tzinfo else now.replace(tzinfo=VN_TZ)
    if local.date() != day:
        return "DATE_MISMATCH"
    if local.weekday() >= 5:
        return "NON_WEEKDAY"
    market_db = market_db_dir / f"ccc_market_{day.year}.db"
    if market_db.exists():
        connection = sqlite3.connect(
            f"file:{market_db.resolve().as_posix()}?mode=ro", uri=True
        )
        try:
            has_evidence = connection.execute(
                "SELECT 1 FROM minute_bars WHERE trading_date=? LIMIT 1",
                (day.isoformat(),),
            ).fetchone()
        finally:
            connection.close()
        if has_evidence:
            return "TODAY_HAS_CANONICAL_LIVE_EVIDENCE"
    starts = [
        start
        for exchange in set(exchange_map.values())
        if (start := market_day_feed_start(local, exchange)) is not None
    ]
    if starts:
        earliest_start = min(starts)
        if local >= earliest_start:
            return "MARKET_DAY_ALREADY_STARTED"
        if local >= earliest_start - PREMARKET_MIN_LEAD:
            return "INSUFFICIENT_PREMARKET_LEAD"
    return None


def validate_rebuild(
    *, engine_db: Path, day: date, expected_symbols: int
) -> dict[str, int]:
    if expected_symbols <= 0:
        raise ValueError("expected_symbols must be positive")
    connection = sqlite3.connect(f"file:{engine_db.resolve().as_posix()}?mode=ro", uri=True)
    try:
        counts = {
            "technical_baseline": int(
                connection.execute(
                    "SELECT COUNT(*) FROM technical_baseline WHERE as_of_date=?",
                    (day.isoformat(),),
                ).fetchone()[0]
            ),
            "volume_baseline_curve": int(
                connection.execute(
                    """SELECT COUNT(DISTINCT symbol) FROM volume_baseline_curve
                       WHERE as_of_date=?""",
                    (day.isoformat(),),
                ).fetchone()[0]
            ),
            "current_state": int(
                connection.execute(
                    "SELECT COUNT(*) FROM current_state WHERE trading_date=?",
                    (day.isoformat(),),
                ).fetchone()[0]
            ),
        }
    finally:
        connection.close()
    mismatches = {
        name: count for name, count in counts.items() if count != expected_symbols
    }
    if mismatches:
        details = ",".join(f"{name}={count}" for name, count in mismatches.items())
        raise RuntimeError(
            f"PREMARKET_REBUILD_COUNT_MISMATCH expected={expected_symbols} {details}"
        )
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--date", required=True, type=date.fromisoformat)
    check.add_argument("--db-dir", required=True, type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--date", required=True, type=date.fromisoformat)
    validate.add_argument("--engine-db", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    metadata_config = CanonicalMetadataConfig.from_env()
    exchange_map = load_exchange_map(metadata_config)
    if not exchange_map:
        raise SystemExit("No symbols selected")
    if args.command == "check":
        reason = premarket_refusal_reason(
            market_db_dir=args.db_dir,
            day=args.date,
            now=datetime.now(VN_TZ),
            exchange_map=exchange_map,
        )
        if reason:
            print(f"REFUSED_ACTIVE_MARKET day={args.date.isoformat()} reason={reason}")
            return 3
        print(f"PREMARKET_SAFE day={args.date.isoformat()} symbols={len(exchange_map)}")
        return 0
    counts = validate_rebuild(
        engine_db=args.engine_db,
        day=args.date,
        expected_symbols=len(exchange_map),
    )
    print(
        f"PREMARKET_VALID day={args.date.isoformat()} symbols={len(exchange_map)} "
        + " ".join(f"{name}={count}" for name, count in counts.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
