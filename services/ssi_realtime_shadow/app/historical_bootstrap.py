from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Iterable, Protocol

from .market_session import VN_TZ
from .settings import Settings
from .ssi_historical import (
    SSIHistoricalClient,
    SSIHistoricalError,
    normalize_historical_record,
)
from .storage import SQLiteStore
from .universe import load_universe


LOG = logging.getLogger(__name__)
RESOLUTION = 1


class HistoricalFetcher(Protocol):
    def fetch_intraday_ohlc(
        self,
        symbol: str,
        from_date: date | str,
        to_date: date | str,
        resolution: int = 1,
    ) -> list[dict]: ...


@dataclass(frozen=True)
class BootstrapSummary:
    completed: int
    skipped: int
    failed: int
    valid_rows: int
    inserted_rows: int
    existing_rows: int
    rejected_rows: int


def _cli_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected dd/mm/yyyy") from exc


def _parse_symbols(value: str) -> set[str]:
    return {item.strip().upper() for item in value.split(",") if item.strip()}


def run_bootstrap(
    *,
    store: SQLiteStore,
    client: HistoricalFetcher,
    symbols: Iterable[str],
    from_date: date,
    to_date: date,
    output: Callable[[str], None] = print,
    now: Callable[[], datetime] = lambda: datetime.now(VN_TZ),
) -> BootstrapSummary:
    ordered_symbols = sorted({str(item).strip().upper() for item in symbols if item})
    from_key = from_date.isoformat()
    to_key = to_date.isoformat()
    completed = skipped = failed = valid_rows = inserted_rows = existing_rows = 0
    rejected_rows = 0

    for index, symbol in enumerate(ordered_symbols, start=1):
        prefix = f"[{index}/{len(ordered_symbols)}] {symbol}"
        checkpoint = store.get_historical_checkpoint(
            symbol, from_key, to_key, RESOLUTION
        )
        if checkpoint and checkpoint.status == "COMPLETED":
            skipped += 1
            output(f"{prefix} skipped=completed rows={checkpoint.row_count}")
            continue

        attempted_at = now().isoformat()
        store.mark_historical_checkpoint_running(
            symbol, from_key, to_key, RESOLUTION, attempted_at
        )
        store.commit()
        try:
            raw_rows = client.fetch_intraday_ohlc(
                symbol, from_date, to_date, resolution=RESOLUTION
            )
            normalized = []
            for raw_row in raw_rows:
                bar = normalize_historical_record(raw_row)
                if bar is not None and bar.symbol == symbol:
                    normalized.append(bar)
            raw_count = len(raw_rows)
            valid_count = len(normalized)
            rejected_count = raw_count - valid_count
            unique_bars = {
                (bar.symbol, bar.trading_date, bar.minute): bar for bar in normalized
            }
            bars = list(unique_bars.values())
            if raw_count > 0 and not bars:
                raise SSIHistoricalError(
                    "provider returned rows but none could be normalized "
                    f"(raw_count={raw_count}, valid_count=0, "
                    f"rejected_count={rejected_count})"
                )
            inserted = 0
            for bar in bars:
                if store.insert_historical_bar(
                    trading_date=bar.trading_date,
                    minute=bar.minute,
                    symbol=bar.symbol,
                    exchange=bar.exchange,
                    open_price=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    provider_time=bar.provider_time,
                    updated_at=now().isoformat(),
                ):
                    inserted += 1
            existing = len(bars) - inserted
            store.mark_historical_checkpoint_completed(
                symbol,
                from_key,
                to_key,
                RESOLUTION,
                len(bars),
                now().isoformat(),
            )
            store.commit()
            completed += 1
            valid_rows += len(bars)
            inserted_rows += inserted
            existing_rows += existing
            rejected_rows += rejected_count
            output(
                f"{prefix} completed raw_count={raw_count} "
                f"valid_count={valid_count} rejected_count={rejected_count} "
                f"rows={len(bars)} inserted={inserted} existing={existing}"
            )
        except Exception as exc:
            failed += 1
            message = f"{type(exc).__name__}: {exc}"
            store.mark_historical_checkpoint_failed(
                symbol,
                from_key,
                to_key,
                RESOLUTION,
                message,
                now().isoformat(),
            )
            store.commit()
            LOG.error("Historical bootstrap failed for %s: %s", symbol, message)
            output(f"{prefix} failed={message}")

    return BootstrapSummary(
        completed=completed,
        skipped=skipped,
        failed=failed,
        valid_rows=valid_rows,
        inserted_rows=inserted_rows,
        existing_rows=existing_rows,
        rejected_rows=rejected_rows,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap SSI historical 1-minute bars")
    parser.add_argument("--from-date", required=True, type=_cli_date, help="dd/mm/yyyy")
    parser.add_argument("--to-date", required=True, type=_cli_date, help="dd/mm/yyyy")
    parser.add_argument("--symbols", help="Comma-separated symbols, e.g. HPG,SSI,VIX")
    parser.add_argument("--limit-symbols", type=int, help="Process only the first N symbols")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.from_date > args.to_date:
        raise SystemExit("--from-date must not be after --to-date")
    if args.limit_symbols is not None and args.limit_symbols < 1:
        raise SystemExit("--limit-symbols must be positive")

    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    symbols = _parse_symbols(args.symbols) if args.symbols else load_universe(settings)
    ordered = sorted(symbols)
    if args.limit_symbols is not None:
        ordered = ordered[: args.limit_symbols]
    if not ordered:
        raise SystemExit("No symbols selected")

    store = SQLiteStore(
        settings.database_path,
        commit_every_events=settings.commit_every_events,
        commit_every_seconds=settings.commit_every_seconds,
    )
    try:
        client = SSIHistoricalClient(
            base_url=settings.ssi_url,
            consumer_id=settings.ssi_consumer_id,
            consumer_secret=settings.ssi_consumer_secret,
            auth_type=settings.ssi_auth_type,
        )
        summary = run_bootstrap(
            store=store,
            client=client,
            symbols=ordered,
            from_date=args.from_date,
            to_date=args.to_date,
        )
    finally:
        store.close()

    print(
        "summary "
        f"completed={summary.completed} skipped={summary.skipped} "
        f"failed={summary.failed} rows={summary.valid_rows} "
        f"inserted={summary.inserted_rows} existing={summary.existing_rows} "
        f"rejected={summary.rejected_rows}"
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
