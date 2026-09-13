from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS minute_bars (
    trading_date TEXT NOT NULL,
    minute TEXT NOT NULL,
    symbol TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL DEFAULT 0,
    last_total_volume INTEGER,
    event_count INTEGER NOT NULL DEFAULT 0,
    is_partial INTEGER NOT NULL DEFAULT 0,
    exchange TEXT,
    quality_status TEXT NOT NULL DEFAULT 'LEGACY_UNVERIFIED',
    has_gap INTEGER NOT NULL DEFAULT 0,
    gap_from TEXT,
    gap_to TEXT,
    data_source TEXT NOT NULL DEFAULT 'SSI_STREAM',
    provider_time TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trading_date, minute, symbol)
);
CREATE INDEX IF NOT EXISTS idx_minute_bars_symbol_date
    ON minute_bars(symbol, trading_date, minute);

CREATE TABLE IF NOT EXISTS latest_quotes (
    symbol TEXT PRIMARY KEY,
    trading_date TEXT,
    event_time TEXT,
    last_price REAL,
    total_volume INTEGER,
    ref_price REAL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    bid_price1 REAL,
    bid_vol1 INTEGER,
    ask_price1 REAL,
    ask_vol1 INTEGER,
    change REAL,
    ratio_change REAL,
    exchange TEXT,
    trading_session TEXT,
    trading_status TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collector_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_bootstrap_checkpoints (
    symbol TEXT NOT NULL,
    from_date TEXT NOT NULL,
    to_date TEXT NOT NULL,
    resolution INTEGER NOT NULL,
    status TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT NOT NULL,
    completed_at TEXT,
    error TEXT,
    PRIMARY KEY (symbol, from_date, to_date, resolution)
);
"""


@dataclass(frozen=True)
class LatestQuoteState:
    event_time: str | None
    total_volume: int | None
    exchange: str | None
    updated_at: str


@dataclass(frozen=True)
class HistoricalCheckpoint:
    symbol: str
    from_date: str
    to_date: str
    resolution: int
    status: str
    row_count: int
    attempt_count: int
    last_attempt_at: str
    completed_at: str | None
    error: str | None


_MINUTE_BAR_MIGRATIONS = (
    ("exchange", "exchange TEXT"),
    (
        "quality_status",
        "quality_status TEXT NOT NULL DEFAULT 'LEGACY_UNVERIFIED'",
    ),
    ("has_gap", "has_gap INTEGER NOT NULL DEFAULT 0"),
    ("gap_from", "gap_from TEXT"),
    ("gap_to", "gap_to TEXT"),
    ("data_source", "data_source TEXT NOT NULL DEFAULT 'SSI_STREAM'"),
    ("provider_time", "provider_time TEXT"),
)


class SQLiteStore:
    def __init__(
        self,
        path: Path,
        commit_every_events: int = 500,
        commit_every_seconds: int = 1,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._pending = 0
        self._last_commit = time.monotonic()
        self._commit_every_events = max(1, commit_every_events)
        self._commit_every_seconds = max(1, commit_every_seconds)
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.executescript(SCHEMA)
            self._migrate_schema()
            self._conn.commit()

    def _migrate_schema(self) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(minute_bars)").fetchall()
        }
        for name, definition in _MINUTE_BAR_MIGRATIONS:
            if name not in columns:
                self._conn.execute(f"ALTER TABLE minute_bars ADD COLUMN {definition}")
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_minute_bars_pending_gaps
                ON minute_bars(trading_date, symbol)
                WHERE has_gap = 1
            """
        )

    def _touch(self, count: int = 1) -> None:
        self._pending += count
        now = time.monotonic()
        if (
            self._pending >= self._commit_every_events
            or now - self._last_commit >= self._commit_every_seconds
        ):
            self._conn.commit()
            self._pending = 0
            self._last_commit = now

    def get_last_total(self, symbol: str, trading_date: str) -> int | None:
        state = self.get_latest_quote_state(symbol, trading_date)
        return state.total_volume if state else None

    def get_latest_quote_state(
        self, symbol: str, trading_date: str
    ) -> LatestQuoteState | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT trading_date, event_time, total_volume, exchange, updated_at
                FROM latest_quotes
                WHERE symbol = ?
                """,
                (symbol,),
            ).fetchone()
            if not row or row["trading_date"] != trading_date:
                return None
            total_volume = row["total_volume"]
            return LatestQuoteState(
                event_time=row["event_time"],
                total_volume=int(total_volume) if total_volume is not None else None,
                exchange=row["exchange"],
                updated_at=row["updated_at"],
            )

    def upsert_minute_bar(
        self,
        *,
        trading_date: str,
        minute: str,
        symbol: str,
        price: float,
        volume_delta: int,
        total_volume: int | None,
        is_partial: bool,
        exchange: str | None,
        quality_status: str,
        has_gap: bool,
        gap_from: str | None,
        gap_to: str | None,
        updated_at: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO minute_bars (
                    trading_date, minute, symbol, open, high, low, close,
                    volume, last_total_volume, event_count, is_partial, exchange,
                    quality_status, has_gap, gap_from, gap_to, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trading_date, minute, symbol) DO UPDATE SET
                    high = MAX(minute_bars.high, excluded.high),
                    low = MIN(minute_bars.low, excluded.low),
                    close = excluded.close,
                    volume = minute_bars.volume + excluded.volume,
                    last_total_volume = COALESCE(excluded.last_total_volume, minute_bars.last_total_volume),
                    event_count = minute_bars.event_count + 1,
                    is_partial = MAX(minute_bars.is_partial, excluded.is_partial),
                    exchange = COALESCE(excluded.exchange, minute_bars.exchange),
                    quality_status = CASE
                        WHEN minute_bars.quality_status = 'GAP'
                             OR excluded.quality_status = 'GAP' THEN 'GAP'
                        WHEN minute_bars.quality_status = 'VOLUME_REGRESSION'
                             OR excluded.quality_status = 'VOLUME_REGRESSION'
                            THEN 'VOLUME_REGRESSION'
                        WHEN minute_bars.quality_status = 'MISSING_TOTAL_VOLUME'
                             OR excluded.quality_status = 'MISSING_TOTAL_VOLUME'
                            THEN 'MISSING_TOTAL_VOLUME'
                        WHEN minute_bars.quality_status = 'PARTIAL'
                             OR excluded.quality_status = 'PARTIAL' THEN 'PARTIAL'
                        WHEN minute_bars.quality_status = 'UNKNOWN_MARKET'
                             OR excluded.quality_status = 'UNKNOWN_MARKET'
                            THEN 'UNKNOWN_MARKET'
                        WHEN minute_bars.quality_status = 'LEGACY_UNVERIFIED'
                            THEN 'LEGACY_UNVERIFIED'
                        ELSE excluded.quality_status
                    END,
                    has_gap = MAX(minute_bars.has_gap, excluded.has_gap),
                    gap_from = CASE
                        WHEN minute_bars.gap_from IS NULL THEN excluded.gap_from
                        WHEN excluded.gap_from IS NULL THEN minute_bars.gap_from
                        ELSE MIN(minute_bars.gap_from, excluded.gap_from)
                    END,
                    gap_to = CASE
                        WHEN minute_bars.gap_to IS NULL THEN excluded.gap_to
                        WHEN excluded.gap_to IS NULL THEN minute_bars.gap_to
                        ELSE MAX(minute_bars.gap_to, excluded.gap_to)
                    END,
                    updated_at = excluded.updated_at
                """,
                (
                    trading_date,
                    minute,
                    symbol,
                    price,
                    price,
                    price,
                    price,
                    max(0, int(volume_delta)),
                    total_volume,
                    1 if is_partial else 0,
                    exchange,
                    quality_status,
                    1 if has_gap else 0,
                    gap_from,
                    gap_to,
                    updated_at,
                ),
            )
            self._touch()

    def upsert_latest_quote(self, quote: dict[str, Any]) -> None:
        columns = [
            "symbol",
            "trading_date",
            "event_time",
            "last_price",
            "total_volume",
            "ref_price",
            "open",
            "high",
            "low",
            "close",
            "bid_price1",
            "bid_vol1",
            "ask_price1",
            "ask_vol1",
            "change",
            "ratio_change",
            "exchange",
            "trading_session",
            "trading_status",
            "updated_at",
        ]
        values = [quote.get(col) for col in columns]
        assignments = ", ".join(f"{col}=excluded.{col}" for col in columns[1:])
        with self._lock:
            self._conn.execute(
                f"""
                INSERT INTO latest_quotes ({', '.join(columns)})
                VALUES ({', '.join('?' for _ in columns)})
                ON CONFLICT(symbol) DO UPDATE SET {assignments}
                """,
                values,
            )
            self._touch()

    def insert_historical_bar(
        self,
        *,
        trading_date: str,
        minute: str,
        symbol: str,
        exchange: str,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: int,
        provider_time: str,
        updated_at: str,
    ) -> bool:
        """Insert one complete REST bar without mutating an existing canonical row."""
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO minute_bars (
                    trading_date, minute, symbol, open, high, low, close,
                    volume, last_total_volume, event_count, is_partial, exchange,
                    quality_status, has_gap, gap_from, gap_to, data_source,
                    provider_time, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, 0, ?,
                          'TRUSTED', 0, NULL, NULL, 'SSI_REST', ?, ?)
                """,
                (
                    trading_date,
                    minute,
                    symbol,
                    open_price,
                    high,
                    low,
                    close,
                    max(0, int(volume)),
                    exchange,
                    provider_time,
                    updated_at,
                ),
            )
            if cursor.rowcount:
                self._touch()
                return True
            return False

    def get_historical_checkpoint(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
        resolution: int,
    ) -> HistoricalCheckpoint | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT symbol, from_date, to_date, resolution, status, row_count,
                       attempt_count, last_attempt_at, completed_at, error
                FROM historical_bootstrap_checkpoints
                WHERE symbol = ? AND from_date = ? AND to_date = ?
                      AND resolution = ?
                """,
                (symbol, from_date, to_date, resolution),
            ).fetchone()
            return HistoricalCheckpoint(**dict(row)) if row else None

    def mark_historical_checkpoint_running(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
        resolution: int,
        attempted_at: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO historical_bootstrap_checkpoints (
                    symbol, from_date, to_date, resolution, status, row_count,
                    attempt_count, last_attempt_at, completed_at, error
                ) VALUES (?, ?, ?, ?, 'RUNNING', 0, 1, ?, NULL, NULL)
                ON CONFLICT(symbol, from_date, to_date, resolution) DO UPDATE SET
                    status = 'RUNNING',
                    attempt_count = historical_bootstrap_checkpoints.attempt_count + 1,
                    last_attempt_at = excluded.last_attempt_at,
                    completed_at = NULL,
                    error = NULL
                """,
                (symbol, from_date, to_date, resolution, attempted_at),
            )
            self._touch()

    def mark_historical_checkpoint_completed(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
        resolution: int,
        row_count: int,
        completed_at: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE historical_bootstrap_checkpoints
                SET status = 'COMPLETED', row_count = ?, completed_at = ?, error = NULL
                WHERE symbol = ? AND from_date = ? AND to_date = ?
                      AND resolution = ?
                """,
                (row_count, completed_at, symbol, from_date, to_date, resolution),
            )
            self._touch()

    def mark_historical_checkpoint_failed(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
        resolution: int,
        error: str,
        failed_at: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO historical_bootstrap_checkpoints (
                    symbol, from_date, to_date, resolution, status, row_count,
                    attempt_count, last_attempt_at, completed_at, error
                ) VALUES (?, ?, ?, ?, 'FAILED', 0, 1, ?, NULL, ?)
                ON CONFLICT(symbol, from_date, to_date, resolution) DO UPDATE SET
                    status = 'FAILED',
                    last_attempt_at = excluded.last_attempt_at,
                    completed_at = NULL,
                    error = excluded.error
                """,
                (
                    symbol,
                    from_date,
                    to_date,
                    resolution,
                    failed_at,
                    error[:1000],
                ),
            )
            self._touch()

    def set_meta(self, key: str, value: str, updated_at: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO collector_meta(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                (key, value, updated_at),
            )
            self._touch()

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()
            self._pending = 0
            self._last_commit = time.monotonic()

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()
