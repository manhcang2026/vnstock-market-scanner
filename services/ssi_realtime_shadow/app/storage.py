from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .auction import AuctionSessionBucket
from .price_momentum import MinutePrice


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

CREATE TABLE IF NOT EXISTS auction_session_buckets (
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    exchange TEXT NOT NULL,
    auction_type TEXT NOT NULL CHECK (
        auction_type IN ('OPEN_AUCTION', 'CLOSE_AUCTION')
    ),
    provider_session TEXT NOT NULL,
    auction_price REAL,
    pre_auction_price REAL,
    auction_volume INTEGER NOT NULL CHECK (auction_volume >= 0),
    start_total_volume INTEGER NOT NULL CHECK (start_total_volume >= 0),
    end_total_volume INTEGER NOT NULL CHECK (end_total_volume >= 0),
    event_count INTEGER NOT NULL CHECK (event_count >= 0),
    out_of_order_events INTEGER NOT NULL CHECK (out_of_order_events >= 0),
    first_event_at TEXT,
    last_event_at TEXT,
    quality_status TEXT NOT NULL,
    finalized INTEGER NOT NULL CHECK (finalized IN (0, 1)),
    data_source TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, trading_date, auction_type)
);
CREATE INDEX IF NOT EXISTS idx_auction_session_buckets_date
    ON auction_session_buckets(trading_date, exchange, auction_type, symbol);
"""


@dataclass(frozen=True)
class LatestQuoteState:
    event_time: str | None
    total_volume: int | None
    exchange: str | None
    last_price: float | None
    trading_session: str | None
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
            self._conn.execute("PRAGMA busy_timeout=5000")
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
                SELECT trading_date, event_time, total_volume, exchange,
                       last_price, trading_session, updated_at
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
                last_price=(
                    float(row["last_price"])
                    if row["last_price"] is not None
                    else None
                ),
                trading_session=row["trading_session"],
                updated_at=row["updated_at"],
            )

    def get_auction_buckets(
        self, symbol: str, trading_date: str
    ) -> tuple[AuctionSessionBucket, ...]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT symbol, trading_date, exchange, auction_type,
                       provider_session, auction_price, pre_auction_price,
                       auction_volume, start_total_volume, end_total_volume,
                       event_count, out_of_order_events, first_event_at,
                       last_event_at, quality_status, finalized, data_source,
                       updated_at
                FROM auction_session_buckets
                WHERE symbol=? AND trading_date=?
                ORDER BY auction_type
                """,
                (str(symbol or "").strip().upper(), trading_date),
            ).fetchall()
            return tuple(
                AuctionSessionBucket(
                    symbol=str(row["symbol"]),
                    trading_date=str(row["trading_date"]),
                    exchange=str(row["exchange"]),
                    auction_type=str(row["auction_type"]),
                    provider_session=str(row["provider_session"]),
                    auction_price=(
                        float(row["auction_price"])
                        if row["auction_price"] is not None
                        else None
                    ),
                    pre_auction_price=(
                        float(row["pre_auction_price"])
                        if row["pre_auction_price"] is not None
                        else None
                    ),
                    auction_volume=int(row["auction_volume"]),
                    start_total_volume=int(row["start_total_volume"]),
                    end_total_volume=int(row["end_total_volume"]),
                    event_count=int(row["event_count"]),
                    out_of_order_events=int(row["out_of_order_events"]),
                    first_event_at=row["first_event_at"],
                    last_event_at=row["last_event_at"],
                    quality_status=str(row["quality_status"]),
                    finalized=bool(row["finalized"]),
                    data_source=str(row["data_source"]),
                    updated_at=str(row["updated_at"]),
                )
                for row in rows
            )

    def get_latest_quote(self, symbol: str, trading_date: str) -> dict[str, Any] | None:
        """Return the canonical full quote after collector normalization."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM latest_quotes WHERE symbol=? AND trading_date=?",
                (str(symbol or "").strip().upper(), trading_date),
            ).fetchone()
            return dict(row) if row is not None else None

    def get_minute_price(
        self, symbol: str, trading_date: str, minute: str
    ) -> MinutePrice | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT trading_date, minute, close, quality_status,
                       is_partial, has_gap
                FROM minute_bars
                WHERE symbol=? AND trading_date=? AND minute=?
                """,
                (str(symbol or "").strip().upper(), trading_date, minute),
            ).fetchone()
            if row is None:
                return None
            return MinutePrice(
                trading_date=str(row["trading_date"]),
                minute=str(row["minute"]),
                close=float(row["close"]),
                quality_status=str(row["quality_status"]),
                is_partial=bool(row["is_partial"]),
                has_gap=bool(row["has_gap"]),
            )

    def get_day_minute_prices(
        self, trading_date: str
    ) -> dict[str, list[MinutePrice]]:
        """Hydrate current-day price anchors without exposing the connection."""
        result: dict[str, list[MinutePrice]] = {}
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT symbol, trading_date, minute, close, quality_status,
                       is_partial, has_gap
                FROM minute_bars WHERE trading_date=?
                ORDER BY minute, symbol
                """,
                (trading_date,),
            ).fetchall()
        for row in rows:
            result.setdefault(str(row["symbol"]), []).append(
                MinutePrice(
                    trading_date=str(row["trading_date"]),
                    minute=str(row["minute"]),
                    close=float(row["close"]),
                    quality_status=str(row["quality_status"]),
                    is_partial=bool(row["is_partial"]),
                    has_gap=bool(row["has_gap"]),
                )
            )
        return result

    def get_volume_hydration_rows(self, trading_date: str) -> list[dict[str, Any]]:
        """Return canonical stored bars in deterministic chronological order."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT trading_date, minute, symbol, volume, last_total_volume,
                       exchange, quality_status, is_partial, has_gap, data_source
                FROM minute_bars WHERE trading_date=?
                ORDER BY minute, symbol
                """,
                (trading_date,),
            ).fetchall()
            return [dict(row) for row in rows]

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

    def upsert_auction_bucket(self, bucket: dict[str, Any]) -> None:
        columns = [
            "symbol",
            "trading_date",
            "exchange",
            "auction_type",
            "provider_session",
            "auction_price",
            "pre_auction_price",
            "auction_volume",
            "start_total_volume",
            "end_total_volume",
            "event_count",
            "out_of_order_events",
            "first_event_at",
            "last_event_at",
            "quality_status",
            "finalized",
            "data_source",
            "updated_at",
        ]
        values = [bucket.get(column) for column in columns]
        values[15] = 1 if values[15] else 0
        assignments = ", ".join(
            f"{column}=excluded.{column}" for column in columns[3:]
        )
        with self._lock:
            self._conn.execute(
                f"""
                INSERT INTO auction_session_buckets ({', '.join(columns)})
                VALUES ({', '.join('?' for _ in columns)})
                ON CONFLICT(symbol, trading_date, auction_type)
                DO UPDATE SET {assignments}
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
