"""Idempotently import approved realtime auction summary salvage evidence."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any, Mapping

from .canonical_market_store import AuctionSession, CanonicalMarketStore, utc_now
from .normalization import parse_trading_date
from .value_parsing import finite_float, nonnegative_int


def _value(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(key).strip().casefold(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.casefold())
        if value is not None and str(value).strip() != "":
            return value
    return None


def normalize_salvage_row(row: Mapping[str, Any]) -> AuctionSession | None:
    symbol = str(_value(row, "symbol", "ticker") or "").strip().upper()
    trading_date = parse_trading_date(
        _value(row, "trading_date", "tradingdate", "date")
    )
    raw_type = str(
        _value(row, "auction_type", "session_type", "provider_session") or ""
    ).strip().upper()
    auction_type = {
        "OPEN_AUCTION": "ATO",
        "CLOSE_AUCTION": "ATC",
        "ATO": "ATO",
        "ATC": "ATC",
    }.get(raw_type)
    if not symbol or trading_date is None or auction_type is None:
        return None
    provider_session = str(
        _value(row, "provider_session", "trading_session") or auction_type
    ).strip().upper()
    auction_price = finite_float(
        _value(row, "auction_price", "price", "last_price"), positive=True
    )
    start_volume = nonnegative_int(
        _value(row, "start_total_volume", "start_volume")
    )
    end_volume = nonnegative_int(_value(row, "end_total_volume", "end_volume"))
    auction_volume = nonnegative_int(
        _value(row, "auction_volume", "volume", "volume_delta")
    )
    quality = str(_value(row, "quality_status", "quality") or "PARTIAL").strip().upper()
    return AuctionSession(
        symbol=symbol,
        trading_date=trading_date,
        exchange=(str(_value(row, "exchange", "market") or "").strip().upper() or None),
        auction_type=auction_type,
        provider_session=provider_session or None,
        pre_auction_price=finite_float(
            _value(row, "pre_auction_price", "last_continuous_price"), positive=True
        ),
        auction_price=auction_price,
        start_total_volume=start_volume,
        end_total_volume=end_volume,
        auction_volume=auction_volume,
        event_count=nonnegative_int(_value(row, "event_count")) or 0,
        first_event_at=(
            str(_value(row, "first_event_at") or "").strip() or None
        ),
        last_event_at=(str(_value(row, "last_event_at") or "").strip() or None),
        source=str(_value(row, "source") or "SSI_REALTIME_SALVAGE").strip(),
        quality_status=quality or "PARTIAL",
        finalized=1 if str(_value(row, "finalized") or "1").strip().casefold()
        in {"1", "true", "yes"} else 0,
        updated_at=utc_now(),
    )


def import_salvage(
    source_path: str | Path,
    *,
    store: CanonicalMarketStore,
    expected_rows: int | None = None,
    expected_atc_by_date: Mapping[str, int] | None = None,
) -> int:
    path = Path(source_path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    normalized = [item for row in rows if (item := normalize_salvage_row(row))]
    unique = {
        (row.symbol, row.trading_date, row.auction_type): row for row in normalized
    }
    if len(unique) != len(rows):
        raise ValueError(
            f"Salvage contains {len(rows)} rows but only {len(unique)} unique valid rows"
        )
    if expected_rows is not None and len(unique) != expected_rows:
        raise ValueError(
            f"Expected {expected_rows} salvage rows, found {len(unique)}"
        )
    if expected_atc_by_date is not None:
        actual = {
            trading_date: sum(
                row.trading_date == trading_date and row.auction_type == "ATC"
                for row in unique.values()
            )
            for trading_date in expected_atc_by_date
        }
        if actual != dict(expected_atc_by_date):
            raise ValueError(
                f"Unexpected ATC salvage distribution: expected "
                f"{dict(expected_atc_by_date)}, found {actual}"
            )
    return store.upsert_auction_sessions(unique.values())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/auction_evidence_salvage_20260924.tsv"),
    )
    parser.add_argument("--db-dir", type=Path, default=Path("data"))
    parser.add_argument("--expected-rows", type=int, default=1110)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with CanonicalMarketStore(args.db_dir) as store:
        written = import_salvage(
            args.source,
            store=store,
            expected_rows=args.expected_rows,
            expected_atc_by_date={"2026-09-22": 551, "2026-09-24": 559},
        )
    print(f"auction_salvage rows_written={written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
