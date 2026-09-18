"""Pure completed-session moving averages over canonical ``daily_bars``."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from .normalization import parse_trading_date


TRUSTED_QUALITY = "TRUSTED"


class DailyMAError(ValueError):
    """Raised when the supplied canonical history is internally inconsistent."""


@dataclass(frozen=True, slots=True)
class DailyClose:
    trading_date: str
    close: float
    quality_status: str


@dataclass(frozen=True, slots=True)
class MAResult:
    symbol: str
    as_of_date: str
    ma10: float | None
    ma200: float | None
    ma10_sessions: int
    ma200_sessions: int
    latest_completed_session: str | None
    ma10_reason: str | None
    ma200_reason: str | None


def _is_trusted(row: DailyClose) -> bool:
    return (
        row.quality_status == TRUSTED_QUALITY
        and math.isfinite(row.close)
        and row.close > 0
    )


def _canonical_date(value: date | str, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_trading_date(value)
    if parsed is None:
        raise ValueError(f"{field_name} must be a valid trading date")
    return date.fromisoformat(parsed)


def _window(
    rows: tuple[DailyClose, ...], target: int
) -> tuple[float | None, int, str | None]:
    recent = rows[-target:]
    trusted = sum(_is_trusted(row) for row in recent)
    if len(recent) < target:
        return None, trusted, f"INSUFFICIENT_SESSIONS:{len(recent)}/{target}"
    if trusted < target:
        return None, trusted, f"UNTRUSTED_REQUIRED_WINDOW:{trusted}/{target}"
    return math.fsum(row.close for row in recent) / target, target, None


def calculate_moving_averages(
    *,
    symbol: str,
    as_of_date: date | str,
    bars: Iterable[DailyClose],
) -> MAResult:
    """Calculate exact MA10/MA200 using only rows strictly before ``as_of_date``.

    The latest N canonical rows define each required window. A degraded or invalid
    row inside that window blocks the MA; older rows are never pulled in to hide it.
    """
    canonical_symbol = str(symbol or "").strip().upper()
    if not canonical_symbol:
        raise ValueError("symbol is required")
    cutoff = _canonical_date(as_of_date, "as_of_date")

    unique: dict[str, DailyClose] = {}
    for raw in bars:
        parsed = parse_trading_date(raw.trading_date)
        if parsed is None:
            raise DailyMAError(f"Invalid daily-bar date: {raw.trading_date!r}")
        if date.fromisoformat(parsed) >= cutoff:
            continue
        row = DailyClose(
            trading_date=parsed,
            close=float(raw.close),
            quality_status=str(raw.quality_status or "").strip().upper(),
        )
        existing = unique.get(parsed)
        if existing is not None and existing != row:
            raise DailyMAError(f"Conflicting daily closes for {parsed}")
        unique[parsed] = row

    eligible = tuple(unique[key] for key in sorted(unique))
    ma10, sessions10, reason10 = _window(eligible, 10)
    ma200, sessions200, reason200 = _window(eligible, 200)
    latest_trusted = next(
        (row.trading_date for row in reversed(eligible) if _is_trusted(row)),
        None,
    )
    return MAResult(
        symbol=canonical_symbol,
        as_of_date=cutoff.isoformat(),
        ma10=ma10,
        ma200=ma200,
        ma10_sessions=sessions10,
        ma200_sessions=sessions200,
        latest_completed_session=latest_trusted,
        ma10_reason=reason10,
        ma200_reason=reason200,
    )


def calculate_moving_averages_from_db(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    as_of_date: date | str,
) -> MAResult:
    """Read canonical daily history and invoke the pure MA calculator."""
    canonical_symbol = str(symbol or "").strip().upper()
    cutoff = _canonical_date(as_of_date, "as_of_date")
    rows = connection.execute(
        """
        SELECT trading_date, close, quality_status
        FROM daily_bars
        WHERE symbol = ? AND trading_date < ?
        ORDER BY trading_date
        """,
        (canonical_symbol, cutoff.isoformat()),
    ).fetchall()
    return calculate_moving_averages(
        symbol=canonical_symbol,
        as_of_date=cutoff,
        bars=(DailyClose(str(row[0]), float(row[1]), str(row[2])) for row in rows),
    )
