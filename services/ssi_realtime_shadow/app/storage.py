from __future__ import annotations

import sqlite3
import threading
import time
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
"""


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
            self._conn.commit()

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
        with self._lock:
            row = self._conn.execute(
                "SELECT trading_date, total_volume FROM latest_quotes WHERE symbol = ?",
                (symbol,),
            ).fetchone()
            if not row or row["trading_date"] != trading_date or row["total_volume"] is None:
                return None
            return int(row["total_volume"])

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
        updated_at: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO minute_bars (
                    trading_date, minute, symbol, open, high, low, close,
                    volume, last_total_volume, event_count, is_partial, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(trading_date, minute, symbol) DO UPDATE SET
                    high = MAX(minute_bars.high, excluded.high),
                    low = MIN(minute_bars.low, excluded.low),
                    close = excluded.close,
                    volume = minute_bars.volume + excluded.volume,
                    last_total_volume = COALESCE(excluded.last_total_volume, minute_bars.last_total_volume),
                    event_count = minute_bars.event_count + 1,
                    is_partial = MAX(minute_bars.is_partial, excluded.is_partial),
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
