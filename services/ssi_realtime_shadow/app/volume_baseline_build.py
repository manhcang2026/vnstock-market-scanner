from __future__ import annotations

import argparse
from pathlib import Path

from .volume_baseline import build_volume_baseline


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
    parser.add_argument("--output-db", required=True, type=Path)
    parser.add_argument("--lookback", type=int, default=10)
    parser.add_argument("--symbols", type=_symbols, help="Comma-separated symbols")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.lookback < 1:
        raise SystemExit("--lookback must be positive")
    summary = build_volume_baseline(
        history_db=args.history_db,
        output_db=args.output_db,
        lookback=args.lookback,
        symbols=args.symbols,
    )
    print(
        f"baseline symbols={summary.symbols} rows={summary.baseline_rows} "
        f"without_history={summary.symbols_without_history} "
        f"lookback={summary.lookback}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
