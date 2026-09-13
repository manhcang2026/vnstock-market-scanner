from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from .market_session import (
    VN_TZ,
    SessionType,
    classify_market_session,
    normalize_exchange,
)


BASELINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS volume_baseline (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    minute TEXT NOT NULL,
    session_segment TEXT NOT NULL,
    historical_sessions INTEGER NOT NULL,
    avg_cumulative_volume REAL NOT NULL,
    avg_volume_15 REAL,
    avg_volume_30 REAL,
    avg_opening_volume REAL,
    PRIMARY KEY (symbol, minute)
);
CREATE INDEX IF NOT EXISTS idx_volume_baseline_exchange_minute
    ON volume_baseline(exchange, minute, symbol);

CREATE TABLE IF NOT EXISTS volume_baseline_coverage (
    symbol TEXT PRIMARY KEY,
    exchange TEXT,
    available_sessions INTEGER NOT NULL,
    baseline_sessions_used INTEGER NOT NULL,
    active_sessions_available INTEGER NOT NULL,
    active_sessions_used INTEGER NOT NULL,
    first_history_date TEXT,
    last_history_date TEXT
);

CREATE TABLE IF NOT EXISTS volume_baseline_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class VolumeGridPoint:
    minute: str
    session_segment: str
    is_continuous: bool
    is_opening: bool
    is_closing: bool
    rolling_15_ready: bool
    rolling_30_ready: bool


@dataclass(frozen=True)
class RawVolumeBar:
    trading_date: str
    minute: str
    exchange: str
    volume: int


@dataclass(frozen=True)
class BaselineRow:
    symbol: str
    exchange: str
    minute: str
    session_segment: str
    historical_sessions: int
    avg_cumulative_volume: float
    avg_volume_15: float | None
    avg_volume_30: float | None
    avg_opening_volume: float | None


@dataclass(frozen=True)
class CoverageRow:
    symbol: str
    exchange: str | None
    available_sessions: int
    baseline_sessions_used: int
    active_sessions_available: int
    active_sessions_used: int
    first_history_date: str | None
    last_history_date: str | None


@dataclass(frozen=True)
class BaselineBuildSummary:
    symbols: int
    symbols_without_history: int
    baseline_rows: int
    lookback: int


@dataclass
class _PointSamples:
    cumulative: list[int]
    rolling_15: list[int]
    rolling_30: list[int]
    opening: list[int]


_GRID_REFERENCE_DATE = date(2026, 9, 14)
_OPENING_BUCKETS = {"HOSE": "09:15"}
_CLOSING_BUCKETS = {"HOSE": "14:45", "HNX": "14:45"}
_COVERAGE_MIGRATIONS = (
    (
        "active_sessions_available",
        "active_sessions_available INTEGER NOT NULL DEFAULT 0",
    ),
    ("active_sessions_used", "active_sessions_used INTEGER NOT NULL DEFAULT 0"),
)


def volume_market_grid(exchange: str) -> tuple[VolumeGridPoint, ...]:
    """Build the valid historical volume grid from the shared session engine."""
    canonical = normalize_exchange(exchange)
    points: list[VolumeGridPoint] = []
    continuous_bar_counts = {
        SessionType.AM_CONTINUOUS.value: 0,
        SessionType.PM_CONTINUOUS.value: 0,
    }
    start = datetime.combine(_GRID_REFERENCE_DATE, datetime.min.time(), tzinfo=VN_TZ)
    moment = start.replace(hour=9)
    end = start.replace(hour=15)
    while moment <= end:
        minute = moment.strftime("%H:%M")
        session = classify_market_session(canonical, moment)
        if _OPENING_BUCKETS.get(canonical) == minute:
            points.append(
                VolumeGridPoint(
                    minute=minute,
                    session_segment="OPENING_BUCKET",
                    is_continuous=False,
                    is_opening=True,
                    is_closing=False,
                    rolling_15_ready=False,
                    rolling_30_ready=False,
                )
            )
        elif _CLOSING_BUCKETS.get(canonical) == minute:
            points.append(
                VolumeGridPoint(
                    minute=minute,
                    session_segment="CLOSE_BUCKET",
                    is_continuous=False,
                    is_opening=False,
                    is_closing=True,
                    rolling_15_ready=False,
                    rolling_30_ready=False,
                )
            )
        elif session.is_continuous:
            segment = session.session_type.value
            continuous_bar_counts[segment] += 1
            bar_count = continuous_bar_counts[segment]
            points.append(
                VolumeGridPoint(
                    minute=minute,
                    session_segment=segment,
                    is_continuous=True,
                    is_opening=False,
                    is_closing=False,
                    rolling_15_ready=bar_count >= 15,
                    rolling_30_ready=bar_count >= 30,
                )
            )
        moment += timedelta(minutes=1)
    return tuple(points)


def _average(values: Sequence[int]) -> float | None:
    return sum(values) / len(values) if values else None


def build_symbol_volume_baseline(
    symbol: str,
    raw_bars: Iterable[RawVolumeBar],
    *,
    lookback: int,
    trading_calendar: Sequence[str],
) -> tuple[CoverageRow, list[BaselineRow]]:
    if lookback < 1:
        raise ValueError("lookback must be positive")

    bars = list(raw_bars)
    exchanges = {normalize_exchange(bar.exchange) for bar in bars}
    if len(exchanges) > 1:
        raise ValueError(f"Conflicting exchanges in history for {symbol}: {exchanges}")
    exchange = next(iter(exchanges), None)
    if exchange is None:
        return (
            CoverageRow(
                symbol=symbol,
                exchange=None,
                available_sessions=0,
                baseline_sessions_used=0,
                active_sessions_available=0,
                active_sessions_used=0,
                first_history_date=None,
                last_history_date=None,
            ),
            [],
        )

    grid = volume_market_grid(exchange)
    valid_minutes = {point.minute for point in grid}
    active_dates = sorted({bar.trading_date for bar in bars})
    by_date: dict[str, dict[str, int]] = {}
    for bar in bars:
        if bar.minute not in valid_minutes:
            continue
        if bar.volume < 0:
            raise ValueError(f"Negative historical volume for {symbol}")
        by_date.setdefault(bar.trading_date, {})[bar.minute] = bar.volume

    if not active_dates:
        return (
            CoverageRow(
                symbol=symbol,
                exchange=exchange,
                available_sessions=0,
                baseline_sessions_used=0,
                active_sessions_available=0,
                active_sessions_used=0,
                first_history_date=None,
                last_history_date=None,
            ),
            [],
        )
    first_observed_date = active_dates[0]
    eligible_dates = [
        trading_date
        for trading_date in trading_calendar
        if trading_date >= first_observed_date
    ]
    selected_dates = eligible_dates[-lookback:]
    active_date_set = set(active_dates)
    coverage = CoverageRow(
        symbol=symbol,
        exchange=exchange,
        available_sessions=len(eligible_dates),
        baseline_sessions_used=len(selected_dates),
        active_sessions_available=sum(
            trading_date in active_date_set for trading_date in eligible_dates
        ),
        active_sessions_used=sum(
            trading_date in active_date_set for trading_date in selected_dates
        ),
        first_history_date=first_observed_date,
        last_history_date=active_dates[-1],
    )
    if not selected_dates:
        return coverage, []

    samples = {
        point.minute: _PointSamples([], [], [], [])
        for point in grid
    }
    for trading_date in selected_dates:
        day = by_date.get(trading_date, {})
        cumulative = 0
        segment_volumes: dict[str, list[int]] = {
            SessionType.AM_CONTINUOUS.value: [],
            SessionType.PM_CONTINUOUS.value: [],
        }
        for point in grid:
            if point.is_continuous:
                volume = day.get(point.minute, 0)
                cumulative += volume
                segment = segment_volumes[point.session_segment]
                segment.append(volume)
                point_samples = samples[point.minute]
                point_samples.cumulative.append(cumulative)
                if point.rolling_15_ready:
                    point_samples.rolling_15.append(sum(segment[-15:]))
                if point.rolling_30_ready:
                    point_samples.rolling_30.append(sum(segment[-30:]))
            else:
                volume = day.get(point.minute, 0)
                cumulative += volume
                point_samples = samples[point.minute]
                point_samples.cumulative.append(cumulative)
                if point.is_opening:
                    point_samples.opening.append(volume)

    baseline_rows: list[BaselineRow] = []
    for point in grid:
        point_samples = samples[point.minute]
        average_cumulative = _average(point_samples.cumulative)
        if average_cumulative is None:
            continue
        baseline_rows.append(
            BaselineRow(
                symbol=symbol,
                exchange=exchange,
                minute=point.minute,
                session_segment=point.session_segment,
                historical_sessions=len(point_samples.cumulative),
                avg_cumulative_volume=average_cumulative,
                avg_volume_15=_average(point_samples.rolling_15),
                avg_volume_30=_average(point_samples.rolling_30),
                avg_opening_volume=_average(point_samples.opening),
            )
        )
    return coverage, baseline_rows


def _open_history_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"History database does not exist: {path}")
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _load_trading_calendar(connection: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            """
            SELECT DISTINCT trading_date
            FROM minute_bars
            WHERE quality_status = 'TRUSTED'
              AND data_source = 'SSI_REST'
            ORDER BY trading_date
            """
        )
    ]


def _migrate_baseline_schema(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(volume_baseline_coverage)"
        ).fetchall()
    }
    for name, definition in _COVERAGE_MIGRATIONS:
        if name not in columns:
            connection.execute(
                f"ALTER TABLE volume_baseline_coverage ADD COLUMN {definition}"
            )


def _source_symbols(
    connection: sqlite3.Connection, requested: Iterable[str] | None
) -> list[str]:
    if requested is not None:
        return sorted(
            {str(symbol).strip().upper() for symbol in requested if str(symbol).strip()}
        )
    symbols = {
        str(row[0]).strip().upper()
        for row in connection.execute(
            "SELECT DISTINCT symbol FROM minute_bars WHERE symbol IS NOT NULL"
        )
        if str(row[0]).strip()
    }
    if _table_exists(connection, "historical_bootstrap_checkpoints"):
        symbols.update(
            str(row[0]).strip().upper()
            for row in connection.execute(
                "SELECT DISTINCT symbol FROM historical_bootstrap_checkpoints "
                "WHERE symbol IS NOT NULL"
            )
            if str(row[0]).strip()
        )
    return sorted(symbols)


def _load_raw_bars(
    connection: sqlite3.Connection, symbol: str
) -> list[RawVolumeBar]:
    rows = connection.execute(
        """
        SELECT trading_date, minute, exchange, volume
        FROM minute_bars
        WHERE symbol = ?
          AND quality_status = 'TRUSTED'
          AND data_source = 'SSI_REST'
          AND is_partial = 0
          AND has_gap = 0
        ORDER BY trading_date, minute
        """,
        (symbol,),
    )
    return [
        RawVolumeBar(
            trading_date=str(row["trading_date"]),
            minute=str(row["minute"]),
            exchange=str(row["exchange"] or ""),
            volume=int(row["volume"]),
        )
        for row in rows
    ]


def build_volume_baseline(
    *,
    history_db: Path,
    output_db: Path,
    lookback: int = 10,
    symbols: Iterable[str] | None = None,
) -> BaselineBuildSummary:
    """Rebuild deterministic volume-derived tables without mutating raw history."""
    if lookback < 1:
        raise ValueError("lookback must be positive")
    if history_db.resolve() == output_db.resolve():
        raise ValueError("output_db must be different from history_db")

    history = _open_history_readonly(history_db)
    output_db.parent.mkdir(parents=True, exist_ok=True)
    output = sqlite3.connect(output_db)
    try:
        selected_symbols = _source_symbols(history, symbols)
        trading_calendar = _load_trading_calendar(history)
        output.executescript(BASELINE_SCHEMA)
        output.row_factory = sqlite3.Row
        _migrate_baseline_schema(output)
        output.execute("BEGIN IMMEDIATE")
        output.execute("DELETE FROM volume_baseline")
        output.execute("DELETE FROM volume_baseline_coverage")
        output.execute("DELETE FROM volume_baseline_metadata")
        output.executemany(
            "INSERT INTO volume_baseline_metadata(key, value) VALUES (?, ?)",
            (("schema_version", "2"), ("lookback", str(lookback))),
        )

        baseline_row_count = 0
        symbols_without_history = 0
        for symbol in selected_symbols:
            coverage, rows = build_symbol_volume_baseline(
                symbol,
                _load_raw_bars(history, symbol),
                lookback=lookback,
                trading_calendar=trading_calendar,
            )
            output.execute(
                """
                INSERT INTO volume_baseline_coverage (
                    symbol, exchange, available_sessions, baseline_sessions_used,
                    active_sessions_available, active_sessions_used,
                    first_history_date, last_history_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    coverage.symbol,
                    coverage.exchange,
                    coverage.available_sessions,
                    coverage.baseline_sessions_used,
                    coverage.active_sessions_available,
                    coverage.active_sessions_used,
                    coverage.first_history_date,
                    coverage.last_history_date,
                ),
            )
            if coverage.available_sessions == 0:
                symbols_without_history += 1
            output.executemany(
                """
                INSERT INTO volume_baseline (
                    symbol, exchange, minute, session_segment,
                    historical_sessions, avg_cumulative_volume,
                    avg_volume_15, avg_volume_30, avg_opening_volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.symbol,
                        row.exchange,
                        row.minute,
                        row.session_segment,
                        row.historical_sessions,
                        row.avg_cumulative_volume,
                        row.avg_volume_15,
                        row.avg_volume_30,
                        row.avg_opening_volume,
                    )
                    for row in rows
                ],
            )
            baseline_row_count += len(rows)
        output.commit()
        return BaselineBuildSummary(
            symbols=len(selected_symbols),
            symbols_without_history=symbols_without_history,
            baseline_rows=baseline_row_count,
            lookback=lookback,
        )
    except Exception:
        output.rollback()
        raise
    finally:
        output.close()
        history.close()
