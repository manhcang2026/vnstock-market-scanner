"""Loss-tolerant, year-sharded canonical SSI market storage."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


MARKET_SCHEMA_VERSION = "2"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS minute_bars (
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    minute TEXT NOT NULL,
    exchange TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    value REAL,
    provider_total_volume INTEGER,
    provider_session TEXT,
    provider_time TEXT,
    first_event_at TEXT,
    last_event_at TEXT,
    source TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    is_finalized INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, trading_date, minute)
);
CREATE INDEX IF NOT EXISTS idx_minute_bars_date
    ON minute_bars(trading_date, symbol, minute);

CREATE TABLE IF NOT EXISTS daily_bars (
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    exchange TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    value REAL,
    source TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, trading_date)
);
CREATE INDEX IF NOT EXISTS idx_daily_bars_date
    ON daily_bars(trading_date, symbol);

CREATE TABLE IF NOT EXISTS latest_quotes (
    symbol TEXT PRIMARY KEY,
    trading_date TEXT NOT NULL,
    event_time TEXT,
    last_price REAL,
    total_volume INTEGER,
    ref_price REAL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    exchange TEXT,
    provider_session TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auction_sessions (
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    exchange TEXT,
    auction_type TEXT NOT NULL CHECK (auction_type IN ('ATO', 'ATC')),
    provider_session TEXT,
    pre_auction_price REAL,
    auction_price REAL,
    start_total_volume INTEGER,
    end_total_volume INTEGER,
    auction_volume INTEGER,
    event_count INTEGER NOT NULL DEFAULT 0,
    first_event_at TEXT,
    last_event_at TEXT,
    source TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    finalized INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, trading_date, auction_type)
);

CREATE TABLE IF NOT EXISTS data_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    trading_date TEXT NOT NULL,
    minute_from TEXT,
    minute_to TEXT,
    reason TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rest_fetch_status (
    mode TEXT NOT NULL,
    symbol TEXT NOT NULL,
    from_date TEXT NOT NULL,
    to_date TEXT NOT NULL,
    resolution INTEGER NOT NULL DEFAULT 0,
    year INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('COMPLETED', 'NO_DATA', 'FAILED')),
    attempts INTEGER NOT NULL DEFAULT 0,
    rows_received INTEGER NOT NULL DEFAULT 0,
    rows_written INTEGER NOT NULL DEFAULT 0,
    partial_rows INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (mode, symbol, from_date, to_date, resolution, year)
);

CREATE TABLE IF NOT EXISTS rest_session_status (
    mode TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    resolution INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('COMPLETED', 'NO_DATA', 'FAILED')),
    rows_received INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (mode, symbol, trading_date, resolution)
);
CREATE INDEX IF NOT EXISTS idx_rest_session_status_date
    ON rest_session_status(trading_date, mode, status, symbol);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_date(value: str | date) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value).strip()).isoformat()


@dataclass(frozen=True, slots=True)
class MinuteBar:
    symbol: str
    trading_date: str
    minute: str
    exchange: str | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    value: float | None = None
    provider_total_volume: int | None = None
    provider_session: str | None = None
    provider_time: str | None = None
    first_event_at: str | None = None
    last_event_at: str | None = None
    source: str = "SSI_REST"
    quality_status: str = "PARTIAL"
    is_finalized: int = 0
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class DailyBar:
    symbol: str
    trading_date: str
    exchange: str | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    value: float | None = None
    source: str = "SSI_REST"
    quality_status: str = "PARTIAL"
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class AuctionSession:
    symbol: str
    trading_date: str
    auction_type: str
    exchange: str | None = None
    provider_session: str | None = None
    pre_auction_price: float | None = None
    auction_price: float | None = None
    start_total_volume: int | None = None
    end_total_volume: int | None = None
    auction_volume: int | None = None
    event_count: int = 0
    first_event_at: str | None = None
    last_event_at: str | None = None
    source: str = "SSI_REALTIME_SALVAGE"
    quality_status: str = "PARTIAL"
    finalized: int = 0
    updated_at: str = ""


class CanonicalMarketStore:
    """Owns canonical market shards and routes each row by TradingDate year."""

    def __init__(
        self,
        db_dir: str | Path | None = None,
        *,
        year_paths: Mapping[int, str | Path] | None = None,
    ) -> None:
        if db_dir is None and not year_paths:
            raise ValueError("db_dir or year_paths is required")
        self.db_dir = Path(db_dir) if db_dir is not None else None
        self.year_paths = {
            int(year): Path(path) for year, path in (year_paths or {}).items()
        }
        self._connections: dict[int, sqlite3.Connection] = {}

    def path_for_year(self, year: int) -> Path:
        if year in self.year_paths:
            return self.year_paths[year]
        if self.db_dir is None:
            raise ValueError(f"No canonical market path configured for {year}")
        return self.db_dir / f"ccc_market_{year}.db"

    def connection(self, year: int) -> sqlite3.Connection:
        year = int(year)
        existing = self._connections.get(year)
        if existing is not None:
            return existing
        path = self.path_for_year(year)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(SCHEMA_SQL)
        now = utc_now()
        connection.execute(
            """INSERT INTO schema_meta(key, value, updated_at) VALUES(?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
               updated_at=excluded.updated_at""",
            ("schema_version", MARKET_SCHEMA_VERSION, now),
        )
        connection.commit()
        self._connections[year] = connection
        return connection

    def close(self) -> None:
        for connection in self._connections.values():
            connection.close()
        self._connections.clear()

    def __enter__(self) -> "CanonicalMarketStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _identity(symbol: str, trading_date: str) -> tuple[str, str, int]:
        canonical_symbol = str(symbol or "").strip().upper()
        if not canonical_symbol:
            raise ValueError("symbol is required")
        canonical = canonical_date(trading_date)
        return canonical_symbol, canonical, date.fromisoformat(canonical).year

    def upsert_minute_bars(self, rows: Iterable[MinuteBar]) -> int:
        written = 0
        grouped: dict[int, list[tuple[object, ...]]] = {}
        fields = tuple(MinuteBar.__dataclass_fields__)
        for row in rows:
            values = asdict(row)
            symbol, trading_date, year = self._identity(row.symbol, row.trading_date)
            minute = str(row.minute or "").strip()
            datetime.strptime(minute, "%H:%M")
            values.update(
                symbol=symbol,
                trading_date=trading_date,
                minute=minute,
                updated_at=row.updated_at or utc_now(),
            )
            grouped.setdefault(year, []).append(tuple(values[field] for field in fields))
        placeholders = ",".join("?" for _ in fields)
        updates = ",".join(
            f"{field}=COALESCE(excluded.{field}, minute_bars.{field})"
            for field in fields
            if field not in {"symbol", "trading_date", "minute"}
        )
        sql = (
            f"INSERT INTO minute_bars({','.join(fields)}) VALUES({placeholders}) "
            f"ON CONFLICT(symbol,trading_date,minute) DO UPDATE SET {updates}"
        )
        for year, values in grouped.items():
            connection = self.connection(year)
            connection.executemany(sql, values)
            connection.commit()
            written += len(values)
        return written

    def upsert_daily_bars(self, rows: Iterable[DailyBar]) -> int:
        written = 0
        grouped: dict[int, list[tuple[object, ...]]] = {}
        fields = tuple(DailyBar.__dataclass_fields__)
        for row in rows:
            values = asdict(row)
            symbol, trading_date, year = self._identity(row.symbol, row.trading_date)
            values.update(
                symbol=symbol,
                trading_date=trading_date,
                updated_at=row.updated_at or utc_now(),
            )
            grouped.setdefault(year, []).append(tuple(values[field] for field in fields))
        placeholders = ",".join("?" for _ in fields)
        updates = ",".join(
            f"{field}=COALESCE(excluded.{field}, daily_bars.{field})"
            for field in fields
            if field not in {"symbol", "trading_date"}
        )
        sql = (
            f"INSERT INTO daily_bars({','.join(fields)}) VALUES({placeholders}) "
            f"ON CONFLICT(symbol,trading_date) DO UPDATE SET {updates}"
        )
        for year, values in grouped.items():
            connection = self.connection(year)
            connection.executemany(sql, values)
            connection.commit()
            written += len(values)
        return written

    def upsert_auction_sessions(self, rows: Iterable[AuctionSession]) -> int:
        written = 0
        grouped: dict[int, list[tuple[object, ...]]] = {}
        fields = tuple(AuctionSession.__dataclass_fields__)
        for row in rows:
            values = asdict(row)
            symbol, trading_date, year = self._identity(row.symbol, row.trading_date)
            auction_type = str(row.auction_type or "").strip().upper()
            auction_type = {"OPEN_AUCTION": "ATO", "CLOSE_AUCTION": "ATC"}.get(
                auction_type, auction_type
            )
            if auction_type not in {"ATO", "ATC"}:
                raise ValueError(f"Unsupported auction_type: {row.auction_type!r}")
            values.update(
                symbol=symbol,
                trading_date=trading_date,
                auction_type=auction_type,
                updated_at=row.updated_at or utc_now(),
            )
            grouped.setdefault(year, []).append(tuple(values[field] for field in fields))
        placeholders = ",".join("?" for _ in fields)
        updates = ",".join(
            f"{field}=excluded.{field}"
            for field in fields
            if field not in {"symbol", "trading_date", "auction_type"}
        )
        sql = (
            f"INSERT INTO auction_sessions({','.join(fields)}) VALUES({placeholders}) "
            f"ON CONFLICT(symbol,trading_date,auction_type) DO UPDATE SET {updates}"
        )
        for year, values in grouped.items():
            connection = self.connection(year)
            connection.executemany(sql, values)
            connection.commit()
            written += len(values)
        return written

    def get_fetch_status(
        self,
        *,
        mode: str,
        symbol: str,
        from_date: str,
        to_date: str,
        resolution: int,
        year: int,
    ) -> sqlite3.Row | None:
        return self.connection(year).execute(
            """SELECT * FROM rest_fetch_status
               WHERE mode=? AND symbol=? AND from_date=? AND to_date=?
                 AND resolution=? AND year=?""",
            (mode, symbol, from_date, to_date, resolution, year),
        ).fetchone()

    def mark_fetch_status(
        self,
        *,
        mode: str,
        symbol: str,
        from_date: str,
        to_date: str,
        resolution: int,
        year: int,
        status: str,
        rows_received: int = 0,
        rows_written: int = 0,
        partial_rows: int = 0,
        last_error: str | None = None,
    ) -> None:
        canonical_status = status.strip().upper()
        if canonical_status not in {"COMPLETED", "NO_DATA", "FAILED"}:
            raise ValueError(f"Unsupported fetch status: {status!r}")
        connection = self.connection(year)
        connection.execute(
            """INSERT INTO rest_fetch_status(
                   mode,symbol,from_date,to_date,resolution,year,status,attempts,
                   rows_received,rows_written,partial_rows,last_error,updated_at
               ) VALUES(?,?,?,?,?,?,?,1,?,?,?,?,?)
               ON CONFLICT(mode,symbol,from_date,to_date,resolution,year)
               DO UPDATE SET status=excluded.status,
                   attempts=rest_fetch_status.attempts+1,
                   rows_received=excluded.rows_received,
                   rows_written=excluded.rows_written,
                   partial_rows=excluded.partial_rows,
                   last_error=excluded.last_error,
                   updated_at=excluded.updated_at""",
            (
                mode,
                symbol.strip().upper(),
                canonical_date(from_date),
                canonical_date(to_date),
                resolution,
                int(year),
                canonical_status,
                int(rows_received),
                int(rows_written),
                int(partial_rows),
                last_error,
                utc_now(),
            ),
        )
        connection.commit()

    def mark_rest_sessions_completed(
        self,
        *,
        mode: str,
        symbol: str,
        resolution: int,
        rows_by_date: Mapping[str, int],
    ) -> None:
        """Record positive per-session proof only for provider-observed dates."""
        canonical_symbol = str(symbol or "").strip().upper()
        if not canonical_symbol:
            raise ValueError("symbol is required")
        grouped: dict[int, list[tuple[object, ...]]] = {}
        timestamp = utc_now()
        for raw_date, row_count in rows_by_date.items():
            trading_date = canonical_date(raw_date)
            if int(row_count) <= 0:
                continue
            year = date.fromisoformat(trading_date).year
            grouped.setdefault(year, []).append(
                (
                    mode.strip().lower(),
                    canonical_symbol,
                    trading_date,
                    int(resolution),
                    "COMPLETED",
                    int(row_count),
                    timestamp,
                )
            )
        for year, rows in grouped.items():
            connection = self.connection(year)
            connection.executemany(
                """INSERT INTO rest_session_status(
                       mode,symbol,trading_date,resolution,status,rows_received,
                       updated_at
                   ) VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(mode,symbol,trading_date,resolution)
                   DO UPDATE SET status=excluded.status,
                       rows_received=excluded.rows_received,
                       updated_at=excluded.updated_at""",
                rows,
            )
            connection.commit()

    def record_data_gap(
        self,
        *,
        year: int,
        trading_date: str,
        reason: str,
        source: str,
        status: str,
        symbol: str | None = None,
        minute_from: str | None = None,
        minute_to: str | None = None,
        details: str | None = None,
    ) -> int:
        connection = self.connection(year)
        cursor = connection.execute(
            """INSERT INTO data_gaps(
                   symbol,trading_date,minute_from,minute_to,reason,source,
                   status,details,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                str(symbol).strip().upper() if symbol else None,
                canonical_date(trading_date),
                minute_from,
                minute_to,
                str(reason).strip(),
                str(source).strip(),
                str(status).strip().upper(),
                details,
                utc_now(),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
