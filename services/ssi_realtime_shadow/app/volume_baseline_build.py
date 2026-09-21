from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .volume_baseline import DEFAULT_MAX_SCAN_SESSIONS, build_volume_baseline


def _symbols(value: str) -> list[str]:
    symbols = [item.strip().upper() for item in value.split(",") if item.strip()]
    if not symbols:
        raise argparse.ArgumentTypeError("at least one symbol is required")
    return symbols


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
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--symbols", type=_symbols, help="Comma-separated symbols")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.lookback != 10:
        raise SystemExit("--lookback must be 10 for the approved policy")
    if args.max_scan_sessions < 1:
        raise SystemExit("--max-scan-sessions must be positive")
    try:
        if date.fromisoformat(args.as_of_date).isoformat() != args.as_of_date:
            raise ValueError
    except ValueError as exc:
        raise SystemExit("--as-of-date must be YYYY-MM-DD") from exc
    summary = build_volume_baseline(
        history_db=args.history_db,
        daily_db=args.daily_db,
        output_db=args.output_db,
        as_of_date=args.as_of_date,
        lookback=args.lookback,
        max_scan_sessions=args.max_scan_sessions,
        symbols=args.symbols,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
