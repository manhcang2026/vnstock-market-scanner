from __future__ import annotations

import argparse
import logging
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Iterable, Mapping, Protocol

from .market_session import VN_TZ
from .settings import Settings
from .ssi_historical import (
    SSIHistoricalClient,
    SSIHistoricalError,
    SSINoDataFound,
    normalize_historical_record,
)
from .storage import HistoricalBarWrite, SQLiteStore
from .universe import load_exchange_map


LOG = logging.getLogger(__name__)
RESOLUTION = 1
DEFAULT_REQUEST_INTERVAL = 1.0
DEFAULT_MAX_RETRIES = 5
DEFAULT_INITIAL_RETRY_DELAY = 2.0
DEFAULT_MAX_RETRY_DELAY = 120.0
DEFAULT_RETRY_JITTER_RATIO = 0.25


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
    requested: int
    skipped_completed: int
    completed: int
    no_data: int
    failed: int
    retry_count: int
    valid_rows: int
    inserted_rows: int
    existing_rows: int
    rejected_rows: int
    elapsed_seconds: float

    @property
    def skipped(self) -> int:
        """Backward-compatible alias for callers predating the safer summary."""
        return self.skipped_completed


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
    exchange_map: Mapping[str, str],
    from_date: date,
    to_date: date,
    resolution: int = RESOLUTION,
    output: Callable[[str], None] = print,
    now: Callable[[], datetime] = lambda: datetime.now(VN_TZ),
    monotonic: Callable[[], float] = time_module.monotonic,
    verbose: bool = False,
) -> BootstrapSummary:
    if from_date > to_date:
        raise ValueError("from_date must not be after to_date")
    if resolution != RESOLUTION:
        raise ValueError("The canonical historical loader supports resolution=1 only")
    ordered_symbols = sorted({str(item).strip().upper() for item in symbols if item})
    from_key = from_date.isoformat()
    to_key = to_date.isoformat()
    started_at = monotonic()
    retry_count_before = int(getattr(client, "retry_count", 0))
    completed = skipped_completed = no_data = failed = 0
    valid_rows = inserted_rows = existing_rows = 0
    rejected_rows = 0

    for index, symbol in enumerate(ordered_symbols, start=1):
        prefix = f"[{index}/{len(ordered_symbols)}] {symbol}"
        checkpoint = store.get_historical_checkpoint(
            symbol, from_key, to_key, resolution
        )
        if checkpoint and checkpoint.status == "COMPLETED":
            skipped_completed += 1
            if verbose:
                output(
                    f"{prefix} skipped=completed rows={checkpoint.row_count}"
                )
            continue
        if checkpoint and checkpoint.status == "NO_DATA":
            no_data += 1
            if verbose:
                output(f"{prefix} no_data=known")
            continue

        attempted_at = now().isoformat()
        store.mark_historical_checkpoint_running(
            symbol, from_key, to_key, resolution, attempted_at
        )
        store.commit()
        try:
            exchange_hint = exchange_map.get(symbol)
            if exchange_hint is None:
                raise SSIHistoricalError(
                    f"missing trusted exchange metadata for {symbol}"
                )
            raw_rows = client.fetch_intraday_ohlc(
                symbol, from_date, to_date, resolution=resolution
            )
            normalized = []
            for raw_row in raw_rows:
                bar = normalize_historical_record(
                    raw_row, exchange_hint=exchange_hint
                )
                if bar is not None and bar.symbol == symbol:
                    normalized.append(bar)
            raw_count = len(raw_rows)
            if raw_count == 0:
                raise SSIHistoricalError(
                    "EMPTY_RESPONSE: SSI returned a successful response "
                    "without rows or explicit NoDataFound"
                )
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
            batch_updated_at = now().isoformat()
            writes = [
                HistoricalBarWrite(
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
                    updated_at=batch_updated_at,
                )
                for bar in bars
            ]
            inserted, existing = store.complete_historical_batch(
                symbol=symbol,
                from_date=from_key,
                to_date=to_key,
                resolution=resolution,
                bars=writes,
                completed_at=now().isoformat(),
            )
            completed += 1
            valid_rows += len(bars)
            inserted_rows += inserted
            existing_rows += existing
            rejected_rows += rejected_count
            if verbose:
                output(
                    f"{prefix} completed raw_count={raw_count} "
                    f"valid_count={valid_count} rejected_count={rejected_count} "
                    f"rows={len(bars)} inserted={inserted} existing={existing}"
                )
        except SSINoDataFound as exc:
            no_data += 1
            store.mark_historical_checkpoint_no_data(
                symbol,
                from_key,
                to_key,
                resolution,
                now().isoformat(),
                str(exc),
            )
            store.commit()
            if verbose:
                output(f"{prefix} no_data={exc}")
        except Exception as exc:
            failed += 1
            message = f"{type(exc).__name__}: {exc}"
            store.mark_historical_checkpoint_failed(
                symbol,
                from_key,
                to_key,
                resolution,
                message,
                now().isoformat(),
            )
            store.commit()
            LOG.debug("Historical bootstrap failed for %s: %s", symbol, message)
            if verbose:
                output(f"{prefix} failed={message}")

    retry_count_after = int(getattr(client, "retry_count", retry_count_before))
    return BootstrapSummary(
        requested=len(ordered_symbols),
        skipped_completed=skipped_completed,
        completed=completed,
        no_data=no_data,
        failed=failed,
        retry_count=max(0, retry_count_after - retry_count_before),
        valid_rows=valid_rows,
        inserted_rows=inserted_rows,
        existing_rows=existing_rows,
        rejected_rows=rejected_rows,
        elapsed_seconds=max(0.0, monotonic() - started_at),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap SSI historical 1-minute bars")
    parser.add_argument("--from-date", required=True, type=_cli_date, help="dd/mm/yyyy")
    parser.add_argument("--to-date", required=True, type=_cli_date, help="dd/mm/yyyy")
    parser.add_argument(
        "--symbols",
        required=True,
        help="Required comma-separated bounded symbol subset, e.g. HPG,SSI,VIX",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        choices=[RESOLUTION],
        default=RESOLUTION,
        help="SSI intraday resolution (canonical loader currently supports 1 only)",
    )
    parser.add_argument("--limit-symbols", type=int, help="Process only the first N symbols")
    parser.add_argument(
        "--request-interval",
        type=float,
        default=DEFAULT_REQUEST_INTERVAL,
        help="Minimum pacing delay between SSI REST attempts in seconds",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Retries after the initial SSI REST attempt",
    )
    parser.add_argument(
        "--initial-retry-delay",
        type=float,
        default=DEFAULT_INITIAL_RETRY_DELAY,
        help="Initial exponential retry cooldown in seconds",
    )
    parser.add_argument(
        "--max-retry-delay",
        type=float,
        default=DEFAULT_MAX_RETRY_DELAY,
        help="Maximum retry cooldown in seconds",
    )
    parser.add_argument(
        "--retry-jitter-ratio",
        type=float,
        default=DEFAULT_RETRY_JITTER_RATIO,
        help="Positive jitter fraction applied to retry cooldowns",
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-symbol progress")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.from_date > args.to_date:
        raise SystemExit("--from-date must not be after --to-date")
    if args.limit_symbols is not None and args.limit_symbols < 1:
        raise SystemExit("--limit-symbols must be positive")
    if args.request_interval < 0:
        raise SystemExit("--request-interval must not be negative")
    if args.max_retries < 0:
        raise SystemExit("--max-retries must not be negative")
    if args.initial_retry_delay <= 0 or args.max_retry_delay <= 0:
        raise SystemExit("retry delays must be positive")
    if args.initial_retry_delay > args.max_retry_delay:
        raise SystemExit("--initial-retry-delay must not exceed --max-retry-delay")
    if args.retry_jitter_ratio < 0:
        raise SystemExit("--retry-jitter-ratio must not be negative")

    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    symbols = _parse_symbols(args.symbols)
    exchange_map = load_exchange_map(settings)
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
            request_interval=args.request_interval,
            max_attempts=args.max_retries + 1,
            initial_retry_delay=args.initial_retry_delay,
            max_retry_delay=args.max_retry_delay,
            retry_jitter_ratio=args.retry_jitter_ratio,
        )
        summary = run_bootstrap(
            store=store,
            client=client,
            symbols=ordered,
            exchange_map=exchange_map,
            from_date=args.from_date,
            to_date=args.to_date,
            resolution=args.resolution,
            verbose=args.verbose,
        )
    finally:
        store.close()

    print(
        "summary "
        f"requested={summary.requested} "
        f"skipped_completed={summary.skipped_completed} "
        f"completed={summary.completed} no_data={summary.no_data} "
        f"failed={summary.failed} retry_count={summary.retry_count} "
        f"rows={summary.valid_rows} "
        f"inserted={summary.inserted_rows} existing={summary.existing_rows} "
        f"rejected={summary.rejected_rows} "
        f"elapsed_seconds={summary.elapsed_seconds:.2f}"
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
