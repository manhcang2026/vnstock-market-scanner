"""Resumable SSI REST bootstrap into the clean year-sharded market store."""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

from .canonical_market_store import (
    CanonicalMarketStore,
    DailyBar,
    MinuteBar,
    utc_now,
)
from .market_session import normalize_exchange
from .normalization import parse_trading_date
from .settings import Settings
from .ssi_historical import SSIHistoricalClient, SSINoDataFound
from .universe import load_exchange_map


class RestFetcher(Protocol):
    def fetch_intraday_ohlc(
        self, symbol: str, from_date: date, to_date: date, resolution: int = 1
    ) -> list[dict[str, Any]]: ...

    def fetch_daily_ohlc(
        self, symbol: str, from_date: date, to_date: date
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class BootstrapSummary:
    requested: int
    completed: int
    no_data: int
    failed: int
    rows_received: int
    rows_written: int
    partial_rows: int
    elapsed_seconds: float


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _finite_float(value: Any, *, positive: bool = False) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or (positive and number <= 0):
        return None
    return number


def _nonnegative_int(value: Any) -> int | None:
    number = _finite_float(value)
    if number is None or number < 0 or not number.is_integer():
        return None
    return int(number)


def _exchange(row: Mapping[str, Any], hint: str | None) -> str | None:
    raw = _first(row, "Market", "market", "Exchange", "exchange")
    if raw is not None:
        try:
            return normalize_exchange(str(raw))
        except ValueError:
            pass
    if hint:
        try:
            return normalize_exchange(hint)
        except ValueError:
            pass
    return None


def _minute(value: Any) -> tuple[str, str] | None:
    if value is None:
        return None
    raw = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%H:%M:%S.%f", "%H%M%S"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.strftime("%H:%M"), raw
        except ValueError:
            continue
    return None


def _quality(
    open_price: float | None,
    high: float | None,
    low: float | None,
    close: float | None,
    volume: int | None,
) -> str:
    prices = (open_price, high, low, close)
    complete = all(value is not None for value in prices) and volume is not None
    consistent = complete and high >= max(open_price, close) and low <= min(
        open_price, close
    ) and high >= low
    return "TRUSTED" if consistent else "PARTIAL"


def normalize_minute_row(
    raw: Mapping[str, Any], *, symbol_hint: str, exchange_hint: str | None = None
) -> MinuteBar | None:
    symbol = str(_first(raw, "Symbol", "symbol") or symbol_hint).strip().upper()
    trading_date = parse_trading_date(
        _first(raw, "TradingDate", "tradingDate", "tradingdate", "trading_date")
    )
    parsed_minute = _minute(_first(raw, "Time", "time", "provider_time"))
    if not symbol or trading_date is None or parsed_minute is None:
        return None
    minute, provider_time = parsed_minute
    open_price = _finite_float(_first(raw, "Open", "open"), positive=True)
    high = _finite_float(_first(raw, "High", "high"), positive=True)
    low = _finite_float(_first(raw, "Low", "low"), positive=True)
    close = _finite_float(_first(raw, "Close", "close"), positive=True)
    volume = _nonnegative_int(_first(raw, "Volume", "volume"))
    return MinuteBar(
        symbol=symbol,
        trading_date=trading_date,
        minute=minute,
        exchange=_exchange(raw, exchange_hint),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        value=_finite_float(_first(raw, "Value", "value")),
        provider_total_volume=_nonnegative_int(
            _first(raw, "TotalVol", "TotalVolume", "totalVolume")
        ),
        provider_session=(
            str(_first(raw, "TradingSession", "tradingSession") or "").strip()
            or None
        ),
        provider_time=provider_time,
        source="SSI_REST",
        quality_status=_quality(open_price, high, low, close, volume),
        is_finalized=1,
        updated_at=utc_now(),
    )


def normalize_daily_row(
    raw: Mapping[str, Any], *, symbol_hint: str, exchange_hint: str | None = None
) -> DailyBar | None:
    symbol = str(_first(raw, "Symbol", "symbol") or symbol_hint).strip().upper()
    trading_date = parse_trading_date(
        _first(raw, "TradingDate", "tradingDate", "tradingdate", "trading_date")
    )
    if not symbol or trading_date is None:
        return None
    open_price = _finite_float(_first(raw, "Open", "open"), positive=True)
    high = _finite_float(_first(raw, "High", "high"), positive=True)
    low = _finite_float(_first(raw, "Low", "low"), positive=True)
    close = _finite_float(_first(raw, "Close", "close"), positive=True)
    volume = _nonnegative_int(_first(raw, "Volume", "volume"))
    return DailyBar(
        symbol=symbol,
        trading_date=trading_date,
        exchange=_exchange(raw, exchange_hint),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        value=_finite_float(_first(raw, "Value", "value")),
        source="SSI_REST",
        quality_status=_quality(open_price, high, low, close, volume),
        updated_at=utc_now(),
    )


def _year_ranges(start: date, end: date) -> list[tuple[int, date, date]]:
    ranges: list[tuple[int, date, date]] = []
    for year in range(start.year, end.year + 1):
        ranges.append(
            (
                year,
                max(start, date(year, 1, 1)),
                min(end, date(year, 12, 31)),
            )
        )
    return ranges


def run_bootstrap(
    *,
    mode: str,
    store: CanonicalMarketStore,
    client: RestFetcher,
    symbols: Iterable[str],
    exchange_map: Mapping[str, str],
    from_date: date,
    to_date: date,
    retry_failed: bool = False,
    verbose: bool = False,
    output: Callable[[str], None] = print,
    monotonic: Callable[[], float] = time.monotonic,
) -> BootstrapSummary:
    canonical_mode = mode.strip().lower()
    if canonical_mode not in {"minute", "daily"}:
        raise ValueError("mode must be minute or daily")
    if from_date > to_date:
        raise ValueError("from_date must not be after to_date")
    ordered_symbols = sorted({str(item).strip().upper() for item in symbols if item})
    tasks = [
        (symbol, year, start, end)
        for symbol in ordered_symbols
        for year, start, end in _year_ranges(from_date, to_date)
    ]
    started = monotonic()
    completed = no_data = failed = rows_received = rows_written = partial_rows = 0
    resolution = 1 if canonical_mode == "minute" else 0

    for index, (symbol, year, start, end) in enumerate(tasks, start=1):
        checkpoint = store.get_fetch_status(
            mode=canonical_mode,
            symbol=symbol,
            from_date=start.isoformat(),
            to_date=end.isoformat(),
            resolution=resolution,
            year=year,
        )
        if checkpoint is not None and checkpoint["status"] in {"COMPLETED", "NO_DATA"}:
            if checkpoint["status"] == "COMPLETED":
                completed += 1
            else:
                no_data += 1
            if verbose:
                output(f"[{index}/{len(tasks)}] {symbol} {year} skipped={checkpoint['status']}")
            continue
        if checkpoint is not None and checkpoint["status"] == "FAILED" and not retry_failed:
            failed += 1
            if verbose:
                output(f"[{index}/{len(tasks)}] {symbol} {year} skipped=FAILED")
            continue

        try:
            if canonical_mode == "minute":
                raw_rows = client.fetch_intraday_ohlc(symbol, start, end, resolution=1)
                normalized = [
                    row
                    for raw in raw_rows
                    if (
                        row := normalize_minute_row(
                            raw,
                            symbol_hint=symbol,
                            exchange_hint=exchange_map.get(symbol),
                        )
                    )
                    is not None
                    and row.symbol == symbol
                    and date.fromisoformat(row.trading_date).year == year
                ]
                unique = {
                    (row.symbol, row.trading_date, row.minute): row for row in normalized
                }
                canonical_rows = list(unique.values())
                written = store.upsert_minute_bars(canonical_rows)
                observed_dates: dict[str, int] = {}
                for row in canonical_rows:
                    observed_dates[row.trading_date] = (
                        observed_dates.get(row.trading_date, 0) + 1
                    )
                store.mark_rest_sessions_completed(
                    mode="minute",
                    symbol=symbol,
                    resolution=1,
                    rows_by_date=observed_dates,
                )
            else:
                raw_rows = client.fetch_daily_ohlc(symbol, start, end)
                normalized = [
                    row
                    for raw in raw_rows
                    if (
                        row := normalize_daily_row(
                            raw,
                            symbol_hint=symbol,
                            exchange_hint=exchange_map.get(symbol),
                        )
                    )
                    is not None
                    and row.symbol == symbol
                    and date.fromisoformat(row.trading_date).year == year
                ]
                unique = {(row.symbol, row.trading_date): row for row in normalized}
                canonical_rows = list(unique.values())
                written = store.upsert_daily_bars(canonical_rows)

            received = len(raw_rows)
            partial = sum(row.quality_status != "TRUSTED" for row in canonical_rows)
            if not raw_rows:
                raise ValueError(
                    "EMPTY_RESPONSE: provider did not explicitly report NO_DATA"
                )
            if not canonical_rows:
                raise ValueError("provider rows lacked canonical identity")
            store.mark_fetch_status(
                mode=canonical_mode,
                symbol=symbol,
                from_date=start.isoformat(),
                to_date=end.isoformat(),
                resolution=resolution,
                year=year,
                status="COMPLETED",
                rows_received=received,
                rows_written=written,
                partial_rows=partial,
            )
            completed += 1
            rows_received += received
            rows_written += written
            partial_rows += partial
            if verbose:
                output(
                    f"[{index}/{len(tasks)}] {symbol} {year} COMPLETED "
                    f"received={received} written={written} partial={partial}"
                )
        except SSINoDataFound as exc:
            store.mark_fetch_status(
                mode=canonical_mode,
                symbol=symbol,
                from_date=start.isoformat(),
                to_date=end.isoformat(),
                resolution=resolution,
                year=year,
                status="NO_DATA",
                last_error=f"PROVIDER_NO_DATA: {exc}",
            )
            store.record_data_gap(
                year=year,
                symbol=symbol,
                trading_date=start.isoformat(),
                reason="PROVIDER_NO_DATA",
                source="SSI_REST",
                status="OPEN",
                details=f"bounded_range={start.isoformat()}..{end.isoformat()}",
            )
            no_data += 1
        except Exception as exc:
            store.mark_fetch_status(
                mode=canonical_mode,
                symbol=symbol,
                from_date=start.isoformat(),
                to_date=end.isoformat(),
                resolution=resolution,
                year=year,
                status="FAILED",
                last_error=f"{type(exc).__name__}: {exc}",
            )
            failed += 1
            if verbose:
                output(f"[{index}/{len(tasks)}] {symbol} {year} FAILED {exc}")

    return BootstrapSummary(
        requested=len(tasks),
        completed=completed,
        no_data=no_data,
        failed=failed,
        rows_received=rows_received,
        rows_written=rows_written,
        partial_rows=partial_rows,
        elapsed_seconds=max(0.0, monotonic() - started),
    )


def _cli_date(value: str) -> date:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError("expected dd/mm/yyyy or yyyy-mm-dd")


def _symbols(value: str) -> set[str]:
    return {part.strip().upper() for part in value.split(",") if part.strip()}


def _universe_file(path: Path) -> set[str]:
    values: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        values.update(_symbols(line.split("#", 1)[0].replace(" ", ",")))
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("minute", "daily"), required=True)
    parser.add_argument("--from-date", type=_cli_date, required=True)
    parser.add_argument("--to-date", type=_cli_date, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--symbols", help="Comma-separated symbols")
    group.add_argument("--universe-file", type=Path)
    parser.add_argument("--db-dir", type=Path, default=Path("data"))
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--request-interval", type=float, default=1.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    exchange_map = load_exchange_map(settings)
    if args.symbols:
        symbols = _symbols(args.symbols)
    elif args.universe_file:
        symbols = _universe_file(args.universe_file)
    else:
        symbols = set(exchange_map)
    if not symbols:
        raise SystemExit("No symbols selected")
    client = SSIHistoricalClient(
        base_url=settings.ssi_url,
        consumer_id=settings.ssi_consumer_id,
        consumer_secret=settings.ssi_consumer_secret,
        auth_type=settings.ssi_auth_type,
        request_interval=args.request_interval,
    )
    with CanonicalMarketStore(args.db_dir) as store:
        summary = run_bootstrap(
            mode=args.mode,
            store=store,
            client=client,
            symbols=symbols,
            exchange_map=exchange_map,
            from_date=args.from_date,
            to_date=args.to_date,
            retry_failed=args.retry_failed,
            verbose=args.verbose,
        )
    print(
        "summary "
        f"requested={summary.requested} completed={summary.completed} "
        f"no_data={summary.no_data} failed={summary.failed} "
        f"rows_received={summary.rows_received} rows_written={summary.rows_written} "
        f"partial_rows={summary.partial_rows} "
        f"elapsed_seconds={summary.elapsed_seconds:.2f}"
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
