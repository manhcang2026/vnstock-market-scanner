from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,12}$")
ALLOWED_RESOLUTIONS = {1, 5, 15, 30, 60}
FINALIZED_STATUSES = {"PASS", "REST_PASS"}
CANONICAL_HISTORY_SOURCES = {"SSI_REST", "SSI_STREAM_FINAL"}


@dataclass(frozen=True)
class ChartBar:
    trading_date: str
    minute: str
    symbol: str
    exchange: str | None
    open: float
    high: float
    low: float
    close: float
    volume: int
    quality_status: str
    data_source: str
    provider_time: str | None


@dataclass(frozen=True)
class ChartResult:
    symbol: str
    date_from: str
    date_to: str
    resolution: int
    bars: tuple[ChartBar, ...]
    invalid_ohlc_dropped: int
    source_counts: dict[str, int]


def is_valid_ohlc(
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int,
) -> bool:
    return (
        volume >= 0
        and high >= low
        and low <= open_price <= high
        and low <= close <= high
    )


def _validate_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not SYMBOL_RE.fullmatch(normalized):
        raise ValueError("invalid symbol")
    return normalized


def _validate_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc


def _connect_readonly(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def _fetch_rows(
    path: Path,
    *,
    symbol: str,
    date_from: str,
    date_to: str,
) -> list[sqlite3.Row]:
    conn = _connect_readonly(path)
    if conn is None:
        return []
    try:
        return conn.execute(
            """
            SELECT trading_date, minute, symbol, exchange,
                   open, high, low, close, volume,
                   quality_status, data_source, provider_time
            FROM minute_bars
            WHERE symbol = ?
              AND trading_date BETWEEN ? AND ?
            ORDER BY trading_date, minute
            """,
            (symbol, date_from, date_to),
        ).fetchall()
    finally:
        conn.close()


def _fetch_finalize_statuses(
    path: Path,
    *,
    date_from: str,
    date_to: str,
) -> dict[str, str]:
    """Return day-level finalize states when the metadata table exists."""
    conn = _connect_readonly(path)
    if conn is None:
        return {}
    try:
        exists = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name='daily_finalize_runs'
            """
        ).fetchone()
        if not exists:
            return {}
        return {
            str(row["trading_date"]): str(row["status"])
            for row in conn.execute(
                """
                SELECT trading_date, status
                FROM daily_finalize_runs
                WHERE trading_date BETWEEN ? AND ?
                """,
                (date_from, date_to),
            ).fetchall()
        }
    finally:
        conn.close()


def _canonical_history_dates(
    history_rows: Iterable[sqlite3.Row],
    finalize_statuses: dict[str, str],
) -> set[str]:
    """Choose dates where history wins at the whole-day level.

    PASS/REST_PASS is authoritative even when one symbol has no historical bars.
    Older SSI_REST/SSI_STREAM_FINAL history created before daily-finalize metadata
    existed is also canonical. Explicit BLOCKED/REST_BLOCKED metadata prevents
    legacy-source inference for that day.
    """
    canonical = {
        day
        for day, status in finalize_statuses.items()
        if status in FINALIZED_STATUSES
    }

    sources_by_day: dict[str, set[str]] = {}
    for row in history_rows:
        day = str(row["trading_date"])
        sources_by_day.setdefault(day, set()).add(str(row["data_source"]))

    for day, sources in sources_by_day.items():
        if day in finalize_statuses:
            continue
        if sources & CANONICAL_HISTORY_SOURCES:
            canonical.add(day)

    return canonical


def _row_to_bar(row: sqlite3.Row, *, invalid_override: bool = False) -> ChartBar:
    quality = "INVALID_OHLC" if invalid_override else str(row["quality_status"])
    return ChartBar(
        trading_date=str(row["trading_date"]),
        minute=str(row["minute"]),
        symbol=str(row["symbol"]),
        exchange=row["exchange"],
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=int(row["volume"]),
        quality_status=quality,
        data_source=str(row["data_source"]),
        provider_time=row["provider_time"],
    )


def _quality_rank(status: str) -> int:
    order = {
        "TRUSTED": 0,
        "LEGACY_UNVERIFIED": 1,
        "PARTIAL": 2,
        "UNKNOWN_MARKET": 3,
        "MISSING_TOTAL_VOLUME": 4,
        "VOLUME_REGRESSION": 5,
        "GAP": 6,
        "INVALID_OHLC": 7,
    }
    return order.get(status, 2)


def _aggregate(bars: Iterable[ChartBar], resolution: int) -> tuple[ChartBar, ...]:
    if resolution == 1:
        return tuple(bars)
    grouped: dict[tuple[str, int], list[ChartBar]] = {}
    for bar in bars:
        hour, minute = (int(part) for part in bar.minute.split(":", 1))
        absolute = hour * 60 + minute
        bucket = absolute - (absolute % resolution)
        grouped.setdefault((bar.trading_date, bucket), []).append(bar)

    out: list[ChartBar] = []
    for (trading_date, bucket), items in sorted(grouped.items()):
        items.sort(key=lambda item: item.minute)
        first = items[0]
        last = items[-1]
        worst = max(items, key=lambda item: _quality_rank(item.quality_status))
        hour, minute = divmod(bucket, 60)
        sources = {item.data_source for item in items}
        out.append(
            ChartBar(
                trading_date=trading_date,
                minute=f"{hour:02d}:{minute:02d}",
                symbol=first.symbol,
                exchange=first.exchange,
                open=first.open,
                high=max(item.high for item in items),
                low=min(item.low for item in items),
                close=last.close,
                volume=sum(item.volume for item in items),
                quality_status=worst.quality_status,
                data_source=next(iter(sources)) if len(sources) == 1 else "MIXED",
                provider_time=last.provider_time,
            )
        )
    return tuple(out)


class ChartDataStore:
    """Read a seamless chart series from historical + current realtime SQLite."""

    def __init__(self, history_path: Path, realtime_path: Path) -> None:
        self.history_path = Path(history_path)
        self.realtime_path = Path(realtime_path)

    def query(
        self,
        *,
        symbol: str,
        date_from: str,
        date_to: str,
        resolution: int = 1,
        include_invalid: bool = False,
    ) -> ChartResult:
        symbol = _validate_symbol(symbol)
        date_from = _validate_date(date_from)
        date_to = _validate_date(date_to)
        if date_from > date_to:
            raise ValueError("from must not be after to")
        if resolution not in ALLOWED_RESOLUTIONS:
            raise ValueError(
                f"resolution must be one of {sorted(ALLOWED_RESOLUTIONS)}"
            )

        history_rows = _fetch_rows(
            self.history_path,
            symbol=symbol,
            date_from=date_from,
            date_to=date_to,
        )
        realtime_rows = _fetch_rows(
            self.realtime_path,
            symbol=symbol,
            date_from=date_from,
            date_to=date_to,
        )
        finalize_statuses = _fetch_finalize_statuses(
            self.history_path,
            date_from=date_from,
            date_to=date_to,
        )
        canonical_dates = _canonical_history_dates(
            history_rows,
            finalize_statuses,
        )

        # History wins for an entire canonical day. Realtime may only fill a date
        # that has not been finalized/canonicalized yet (normally the current day).
        merged: dict[tuple[str, str], sqlite3.Row] = {
            (str(row["trading_date"]), str(row["minute"])): row
            for row in history_rows
        }
        for row in realtime_rows:
            day = str(row["trading_date"])
            if day in canonical_dates:
                continue
            merged.setdefault(
                (day, str(row["minute"])),
                row,
            )

        invalid_dropped = 0
        bars: list[ChartBar] = []
        source_counts: dict[str, int] = {}
        for key in sorted(merged):
            row = merged[key]
            valid = is_valid_ohlc(
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                int(row["volume"]),
            )
            if not valid and not include_invalid:
                invalid_dropped += 1
                continue
            bar = _row_to_bar(row, invalid_override=not valid)
            bars.append(bar)
            source_counts[bar.data_source] = source_counts.get(bar.data_source, 0) + 1

        aggregated = _aggregate(bars, resolution)
        return ChartResult(
            symbol=symbol,
            date_from=date_from,
            date_to=date_to,
            resolution=resolution,
            bars=aggregated,
            invalid_ohlc_dropped=invalid_dropped,
            source_counts=source_counts,
        )
