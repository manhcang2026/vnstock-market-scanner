from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from .volume_baseline import DEFAULT_MAX_SCAN_SESSIONS, build_volume_baseline


def _symbols(value: str) -> list[str]:
    symbols = [item.strip().upper() for item in value.split(",") if item.strip()]
    if not symbols:
        raise argparse.ArgumentTypeError("at least one symbol is required")
    return symbols


def next_trading_session(market_db: Path, completed_date: str) -> str:
    """Resolve the next session from trading_calendar, with weekday fallback.

    A populated calendar is authoritative.  If it has no future session, fail
    closed instead of silently guessing beyond its known horizon.
    """
    completed = date.fromisoformat(completed_date)
    connection = sqlite3.connect(f"{market_db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        has_calendar = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='trading_calendar'"
        ).fetchone()
        if has_calendar:
            count = int(
                connection.execute("SELECT COUNT(*) FROM trading_calendar").fetchone()[0]
            )
            if count:
                row = connection.execute(
                    """
                    SELECT MIN(trading_date) FROM trading_calendar
                    WHERE is_trading_day=1 AND trading_date>?
                    """,
                    (completed_date,),
                ).fetchone()
                if row is None or row[0] is None:
                    raise ValueError(
                        "trading_calendar has no proven next session after "
                        f"{completed_date}"
                    )
                return str(row[0])
    finally:
        connection.close()
    candidate = completed + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic CCC V2 volume baselines from SSI history"
    )
    parser.add_argument("--history-db", required=True, type=Path)
    parser.add_argument("--daily-db", required=True, type=Path)
    parser.add_argument("--output-db", required=True, type=Path)
    parser.add_argument("--lookback", type=int, default=10)
    parser.add_argument(
        "--max-scan-sessions",
        type=int,
        default=DEFAULT_MAX_SCAN_SESSIONS,
        help="Maximum candidate market sessions scanned per symbol",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--as-of-date")
    target.add_argument("--next-session-after")
    parser.add_argument("--symbols", type=_symbols, help="Comma-separated symbols")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.lookback != 10:
        raise SystemExit("--lookback must be 10 for the approved policy")
    if args.max_scan_sessions < 1:
        raise SystemExit("--max-scan-sessions must be positive")
    as_of_date = args.as_of_date
    if args.next_session_after:
        try:
            as_of_date = next_trading_session(args.daily_db, args.next_session_after)
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise SystemExit(f"cannot resolve next trading session: {exc}") from exc
    try:
        if date.fromisoformat(as_of_date).isoformat() != as_of_date:
            raise ValueError
    except ValueError as exc:
        raise SystemExit("--as-of-date must be YYYY-MM-DD") from exc
    summary = build_volume_baseline(
        history_db=args.history_db,
        daily_db=args.daily_db,
        output_db=args.output_db,
        as_of_date=as_of_date,
        lookback=args.lookback,
        max_scan_sessions=args.max_scan_sessions,
        symbols=args.symbols,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
