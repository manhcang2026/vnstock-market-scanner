"""Canonical SSI DailyOhlc normalization and local bootstrap primitives."""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Protocol

from .market_session import VN_TZ, normalize_exchange
from .market_storage_schema import canonical_timestamp
from .normalization import parse_trading_date


LOG = logging.getLogger(__name__)
DAILY_SOURCE = "SSI_DAILY_OHLC"
TRUSTED_QUALITY = "TRUSTED"


class DailyHistoryError(RuntimeError):
    """Raised when canonical daily history cannot be safely persisted."""


class DailyHistoryConflict(DailyHistoryError):
    """Raised when the same canonical symbol/session has conflicting values."""


class _DailyRowError(ValueError):
    pass


class DailyFetcher(Protocol):
    def fetch_daily_ohlc(
        self,
        symbol: str,
        from_date: date | str,
        to_date: date | str,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class DailyBar:
    symbol: str
    trading_date: str
    exchange: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    value: float | None
    source: str = DAILY_SOURCE
    quality_status: str = TRUSTED_QUALITY


@dataclass(frozen=True, slots=True)
class DailyBootstrapResult:
    symbol: str
    from_date: str
    to_date: str
    status: str
    raw_rows: int
    valid_rows: int
    rejected_rows: int
    inserted_rows: int
    existing_rows: int


def _first(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = mapping.get(name)
        if value is not None:
            return value
    return None


def _canonical_date(value: date | str, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_trading_date(value)
    if parsed is None:
        raise ValueError(f"{field_name} must be a valid trading date")
    return date.fromisoformat(parsed)


def _daily_bar_from_record(
    record: Mapping[str, Any],
    *,
    exchange_hint: str | None,
    as_of_date: date | None,
) -> DailyBar:
    symbol = str(_first(record, "Symbol", "symbol") or "").strip().upper()
    if not symbol:
        raise _DailyRowError("missing symbol")

    trading_date_text = parse_trading_date(
        _first(record, "TradingDate", "tradingDate", "tradingdate", "trading_date")
    )
    if trading_date_text is None:
        raise _DailyRowError("invalid trading date")
    trading_day = date.fromisoformat(trading_date_text)
    if as_of_date is not None and trading_day >= as_of_date:
        raise _DailyRowError("session is not completed before as_of_date")

    raw_exchange = str(
        _first(record, "Market", "market", "Exchange", "exchange") or ""
    ).strip()
    trusted_exchange: str | None = None
    if exchange_hint is not None:
        try:
            trusted_exchange = normalize_exchange(exchange_hint)
        except ValueError as exc:
            raise _DailyRowError("invalid trusted exchange") from exc
    if raw_exchange:
        try:
            exchange = normalize_exchange(raw_exchange)
        except ValueError as exc:
            raise _DailyRowError("invalid provider exchange") from exc
        if trusted_exchange is not None and exchange != trusted_exchange:
            raise _DailyRowError("provider exchange conflicts with trusted exchange")
    elif trusted_exchange is not None:
        exchange = trusted_exchange
    else:
        raise _DailyRowError("missing exchange")

    raw_prices = (
        _first(record, "Open", "open"),
        _first(record, "High", "high"),
        _first(record, "Low", "low"),
        _first(record, "Close", "close"),
    )
    if any(isinstance(item, bool) for item in raw_prices):
        raise _DailyRowError("invalid boolean OHLC")
    try:
        open_price, high, low, close = (float(item) for item in raw_prices)
    except (TypeError, ValueError) as exc:
        raise _DailyRowError("invalid OHLC") from exc
    if not all(math.isfinite(item) and item > 0 for item in (open_price, high, low, close)):
        raise _DailyRowError("non-finite or non-positive OHLC")
    if high < low or not low <= open_price <= high or not low <= close <= high:
        raise _DailyRowError("invalid OHLC envelope")

    raw_volume_value = _first(record, "Volume", "volume")
    if isinstance(raw_volume_value, bool):
        raise _DailyRowError("invalid volume")
    try:
        raw_volume = float(raw_volume_value)
    except (TypeError, ValueError) as exc:
        raise _DailyRowError("invalid volume") from exc
    if not math.isfinite(raw_volume) or raw_volume < 0 or not raw_volume.is_integer():
        raise _DailyRowError("volume must be a nonnegative integer share count")

    raw_value = _first(record, "Value", "value")
    traded_value: float | None
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        traded_value = None
    else:
        if isinstance(raw_value, bool):
            raise _DailyRowError("invalid value")
        try:
            traded_value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise _DailyRowError("invalid value") from exc
        if not math.isfinite(traded_value) or traded_value < 0:
            raise _DailyRowError("value must be nonnegative or null")

    return DailyBar(
        symbol=symbol,
        trading_date=trading_date_text,
        exchange=exchange,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=int(raw_volume),
        value=traded_value,
    )


def normalize_daily_ohlc_record(
    record: Mapping[str, Any],
    *,
    exchange_hint: str | None = None,
    as_of_date: date | str | None = None,
) -> DailyBar | None:
    """Normalize one official SSI DailyOhlc row without unit conversion."""
    cutoff = (
        _canonical_date(as_of_date, "as_of_date")
        if as_of_date is not None
        else None
    )
    try:
        return _daily_bar_from_record(
            record,
            exchange_hint=exchange_hint,
            as_of_date=cutoff,
        )
    except _DailyRowError as exc:
        LOG.warning("Rejected SSI DailyOhlc row: %s", exc)
        return None


def normalize_daily_ohlc_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    expected_symbol: str,
    exchange_hint: str,
    as_of_date: date | str,
) -> tuple[tuple[DailyBar, ...], int]:
    """Normalize and deterministically deduplicate rows for one requested symbol."""
    symbol = str(expected_symbol or "").strip().upper()
    if not symbol:
        raise ValueError("expected_symbol is required")
    cutoff = _canonical_date(as_of_date, "as_of_date")
    unique: dict[tuple[str, str], DailyBar] = {}
    rejected = 0
    for record in rows:
        try:
            bar = _daily_bar_from_record(
                record,
                exchange_hint=exchange_hint,
                as_of_date=cutoff,
            )
        except _DailyRowError as exc:
            LOG.warning("Rejected SSI DailyOhlc row for %s: %s", symbol, exc)
            rejected += 1
            continue
        if bar.symbol != symbol:
            LOG.warning(
                "Rejected SSI DailyOhlc row: requested %s but received %s",
                symbol,
                bar.symbol,
            )
            rejected += 1
            continue
        key = (bar.symbol, bar.trading_date)
        existing = unique.get(key)
        if existing is None:
            unique[key] = bar
        elif existing != bar:
            raise DailyHistoryConflict(
                f"Conflicting normalized daily rows for {bar.symbol}/{bar.trading_date}"
            )
    return tuple(unique[key] for key in sorted(unique)), rejected


def persist_daily_bars(
    connection: sqlite3.Connection,
    bars: Iterable[DailyBar],
    *,
    finalized_at: str | datetime,
) -> tuple[int, int]:
    """Atomically insert canonical rows; identical reruns are no-ops."""
    if connection.in_transaction:
        raise RuntimeError("persist_daily_bars requires no active transaction")
    timestamp = canonical_timestamp(finalized_at)
    inserted = existing_count = 0
    connection.execute("BEGIN IMMEDIATE")
    try:
        for bar in bars:
            existing = connection.execute(
                """
                SELECT symbol, trading_date, exchange, open, high, low, close,
                       volume, value, source, quality_status
                FROM daily_bars
                WHERE symbol = ? AND trading_date = ?
                """,
                (bar.symbol, bar.trading_date),
            ).fetchone()
            canonical = (
                bar.symbol,
                bar.trading_date,
                bar.exchange,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.value,
                bar.source,
                bar.quality_status,
            )
            if existing is not None:
                if tuple(existing) != canonical:
                    raise DailyHistoryConflict(
                        "Existing canonical daily bar conflicts with SSI row for "
                        f"{bar.symbol}/{bar.trading_date}"
                    )
                existing_count += 1
                continue
            connection.execute(
                """
                INSERT INTO daily_bars (
                    symbol, trading_date, exchange, open, high, low, close,
                    volume, value, source, quality_status, finalized_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                canonical + (timestamp,),
            )
            inserted += 1
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return inserted, existing_count


def bootstrap_daily_history(
    *,
    connection: sqlite3.Connection,
    client: DailyFetcher,
    symbol: str,
    exchange: str,
    from_date: date | str,
    to_date: date | str,
    as_of_date: date | str,
    now: datetime | None = None,
) -> DailyBootstrapResult:
    """Fetch, validate, and atomically persist one symbol's completed daily rows."""
    canonical_symbol = str(symbol or "").strip().upper()
    if not canonical_symbol:
        raise ValueError("symbol is required")
    start = _canonical_date(from_date, "from_date")
    end = _canonical_date(to_date, "to_date")
    cutoff = _canonical_date(as_of_date, "as_of_date")
    if start > end:
        raise ValueError("from_date must not be after to_date")
    if end >= cutoff:
        raise ValueError("to_date must be strictly before as_of_date")
    trusted_exchange = normalize_exchange(exchange)

    raw_rows = client.fetch_daily_ohlc(canonical_symbol, start, end)
    bars, rejected = normalize_daily_ohlc_rows(
        raw_rows,
        expected_symbol=canonical_symbol,
        exchange_hint=trusted_exchange,
        as_of_date=cutoff,
    )
    inserted, existing = persist_daily_bars(
        connection,
        bars,
        finalized_at=now or datetime.now(VN_TZ),
    )
    status = "COMPLETE" if rejected == 0 else "PARTIAL_REJECTED"
    return DailyBootstrapResult(
        symbol=canonical_symbol,
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        status=status,
        raw_rows=len(raw_rows),
        valid_rows=len(bars),
        rejected_rows=rejected,
        inserted_rows=inserted,
        existing_rows=existing,
    )
