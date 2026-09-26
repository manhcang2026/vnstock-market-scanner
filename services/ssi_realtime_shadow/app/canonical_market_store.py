"""Loss-tolerant, year-sharded canonical SSI market storage."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping

from .market_session import SessionType, classify_market_session


MARKET_SCHEMA_VERSION = "4"
MINUTE_FINALIZATION_GRACE_SECONDS = 3


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
    event_count INTEGER NOT NULL DEFAULT 0,
    first_price_at TEXT,
    last_price_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, trading_date, minute)
);
CREATE INDEX IF NOT EXISTS idx_minute_bars_date
    ON minute_bars(trading_date, symbol, minute);
CREATE INDEX IF NOT EXISTS idx_minute_bars_finalization
    ON minute_bars(is_finalized, trading_date, minute);

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
    last_price_at TEXT,
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
    provider_session TEXT,
    trading_status TEXT,
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


@dataclass(frozen=True, slots=True)
class RealtimeMarketEvent:
    symbol: str
    trading_date: str
    event_at: datetime
    minute: str
    exchange: str | None = None
    price: float | None = None
    total_volume: int | None = None
    provider_session: str | None = None
    ref_price: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    bid_price1: float | None = None
    bid_vol1: int | None = None
    ask_price1: float | None = None
    ask_vol1: int | None = None
    change: float | None = None
    ratio_change: float | None = None
    trading_status: str | None = None
    seed_volume_from_zero: bool = False


@dataclass(frozen=True, slots=True)
class RealtimeWriteResult:
    latest_quote_updated: bool
    late_event: bool
    partial_event: bool
    volume_regression: bool
    volume_delta: int
    effective_total_volume: int | None
    minute_was_finalized: bool


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
        self._lock = threading.RLock()

    def path_for_year(self, year: int) -> Path:
        if year in self.year_paths:
            return self.year_paths[year]
        if self.db_dir is None:
            raise ValueError(f"No canonical market path configured for {year}")
        return self.db_dir / f"ccc_market_{year}.db"

    def connection(self, year: int) -> sqlite3.Connection:
        year = int(year)
        with self._lock:
            existing = self._connections.get(year)
            if existing is not None:
                return existing
            path = self.path_for_year(year)
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(SCHEMA_SQL)
            self._migrate_realtime_schema(connection)
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

    @staticmethod
    def _migrate_realtime_schema(connection: sqlite3.Connection) -> None:
        migrations = {
            "minute_bars": (
                ("event_count", "event_count INTEGER NOT NULL DEFAULT 0"),
                ("first_price_at", "first_price_at TEXT"),
                ("last_price_at", "last_price_at TEXT"),
            ),
            "latest_quotes": (
                ("last_price_at", "last_price_at TEXT"),
                ("bid_price1", "bid_price1 REAL"),
                ("bid_vol1", "bid_vol1 INTEGER"),
                ("ask_price1", "ask_price1 REAL"),
                ("ask_vol1", "ask_vol1 INTEGER"),
                ("change", "change REAL"),
                ("ratio_change", "ratio_change REAL"),
                ("trading_status", "trading_status TEXT"),
            ),
        }
        for table, definitions in migrations.items():
            columns = {
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            for name, definition in definitions:
                if name not in columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    def close(self) -> None:
        with self._lock:
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

    @staticmethod
    def _event_iso(event_at: datetime, trading_date: str) -> str:
        if event_at.tzinfo is None:
            raise ValueError("realtime event_at must be timezone-aware")
        if event_at.date().isoformat() != trading_date:
            raise ValueError("realtime event_at does not match trading_date")
        return event_at.isoformat()

    @staticmethod
    def _quality_status(
        *,
        price: float | None,
        total_volume: int | None,
        volume_regression: bool,
        late_event: bool,
    ) -> str:
        if volume_regression:
            return "VOLUME_REGRESSION"
        if price is None and total_volume is None:
            return "PARTIAL"
        if price is None:
            return "MISSING_PRICE"
        if total_volume is None:
            return "MISSING_VOLUME"
        if late_event:
            return "LATE_CORRECTION"
        return "TRUSTED"

    @staticmethod
    def _minute_is_due(
        trading_date: str,
        minute: str,
        observed_at: datetime,
        grace_seconds: int,
    ) -> bool:
        minute_start = datetime.fromisoformat(f"{trading_date}T{minute}:00")
        if observed_at.tzinfo is not None:
            minute_start = minute_start.replace(tzinfo=observed_at.tzinfo)
        return observed_at >= minute_start + timedelta(
            minutes=1, seconds=grace_seconds
        )

    def finalize_due_minutes(
        self,
        observed_at: datetime,
        *,
        grace_seconds: int = MINUTE_FINALIZATION_GRACE_SECONDS,
    ) -> int:
        """Finalize persisted minutes that crossed the grace boundary.

        This is a lightweight shard sweep. It only updates existing rows and
        therefore never invents lunch/break minutes.
        """
        if grace_seconds < 0:
            raise ValueError("grace_seconds must not be negative")
        finalized = 0
        cutoff = observed_at - timedelta(minutes=1, seconds=grace_seconds)
        cutoff_date = cutoff.date().isoformat()
        cutoff_minute = cutoff.strftime("%H:%M")
        with self._lock:
            for connection in self._connections.values():
                try:
                    cursor = connection.execute(
                        """UPDATE minute_bars SET is_finalized=1
                           WHERE is_finalized=0
                             AND (trading_date < ?
                                  OR (trading_date = ? AND minute <= ?))""",
                        (cutoff_date, cutoff_date, cutoff_minute),
                    )
                    connection.commit()
                    if cursor.rowcount:
                        finalized += int(cursor.rowcount)
                except BaseException:
                    connection.rollback()
                    raise
        return finalized

    def write_realtime_event(
        self,
        event: RealtimeMarketEvent,
        *,
        observed_at: datetime | None = None,
        grace_seconds: int = MINUTE_FINALIZATION_GRACE_SECONDS,
    ) -> RealtimeWriteResult:
        """Atomically persist one normalized SSI event in its yearly shard."""
        symbol, trading_date, year = self._identity(event.symbol, event.trading_date)
        minute = str(event.minute or "").strip()
        datetime.strptime(minute, "%H:%M")
        event_iso = self._event_iso(event.event_at, trading_date)
        observed_at = observed_at or event.event_at
        if observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        price = float(event.price) if event.price is not None and event.price > 0 else None
        total_volume = (
            int(event.total_volume)
            if event.total_volume is not None and event.total_volume >= 0
            else None
        )
        provider_session = str(event.provider_session or "").strip().upper() or None
        now = utc_now()

        with self._lock:
            connection = self.connection(year)
            connection.execute("BEGIN IMMEDIATE")
            try:
                latest = connection.execute(
                    "SELECT * FROM latest_quotes WHERE symbol=?", (symbol,)
                ).fetchone()
                latest_iso = None
                if latest is not None and latest["trading_date"] == trading_date:
                    latest_time = latest["event_time"]
                    if latest_time:
                        latest_iso = f"{trading_date}T{latest_time}"
                comparable_event_iso = event_iso[:19]
                late_event = bool(latest_iso and comparable_event_iso < latest_iso)
                previous_total = (
                    int(latest["total_volume"])
                    if latest is not None
                    and latest["trading_date"] == trading_date
                    and latest["total_volume"] is not None
                    else None
                )
                effective_total = previous_total
                if total_volume is not None:
                    effective_total = (
                        total_volume
                        if effective_total is None
                        else max(effective_total, total_volume)
                    )
                volume_delta = 0
                if total_volume is not None and not late_event:
                    if previous_total is not None and total_volume >= previous_total:
                        volume_delta = total_volume - previous_total
                    elif previous_total is None and event.seed_volume_from_zero:
                        volume_delta = total_volume

                current = connection.execute(
                    """SELECT * FROM minute_bars
                       WHERE symbol=? AND trading_date=? AND minute=?""",
                    (symbol, trading_date, minute),
                ).fetchone()
                existing = dict(current) if current is not None else {}
                existing_provider_total = existing.get("provider_total_volume")
                minute_provider_total = existing_provider_total
                if total_volume is not None:
                    minute_provider_total = (
                        total_volume
                        if minute_provider_total is None
                        else max(int(minute_provider_total), total_volume)
                    )
                prior = connection.execute(
                    """SELECT provider_total_volume FROM minute_bars
                       WHERE symbol=? AND trading_date=? AND minute<?
                         AND provider_total_volume IS NOT NULL
                       ORDER BY minute DESC LIMIT 1""",
                    (symbol, trading_date, minute),
                ).fetchone()
                prior_total = int(prior[0]) if prior is not None else None
                volume_regression = bool(
                    total_volume is not None
                    and (
                        (
                            existing_provider_total is not None
                            and total_volume < int(existing_provider_total)
                        )
                        or (prior_total is not None and total_volume < prior_total)
                    )
                )
                minute_volume = existing.get("volume")
                if minute_provider_total is not None:
                    derived_volume = None
                    if prior_total is not None and minute_provider_total >= prior_total:
                        derived_volume = minute_provider_total - prior_total
                    elif event.seed_volume_from_zero:
                        derived_volume = minute_provider_total
                    if derived_volume is not None:
                        minute_volume = (
                            derived_volume
                            if minute_volume is None
                            else max(int(minute_volume), derived_volume)
                        )

                first_event_at = min(
                    value for value in (existing.get("first_event_at"), event_iso) if value
                )
                last_event_at = max(
                    value for value in (existing.get("last_event_at"), event_iso) if value
                )
                first_price_at = existing.get("first_price_at")
                last_price_at = existing.get("last_price_at")
                open_price = existing.get("open")
                high_price = existing.get("high")
                low_price = existing.get("low")
                close_price = existing.get("close")
                if price is not None:
                    if first_price_at is None or event_iso < first_price_at:
                        first_price_at = event_iso
                        open_price = price
                    if last_price_at is None or event_iso >= last_price_at:
                        last_price_at = event_iso
                        close_price = price
                    high_price = price if high_price is None else max(float(high_price), price)
                    low_price = price if low_price is None else min(float(low_price), price)

                minute_was_finalized = bool(existing.get("is_finalized", 0))
                is_finalized = minute_was_finalized or self._minute_is_due(
                    trading_date, minute, observed_at, grace_seconds
                )
                quality = self._quality_status(
                    price=(
                        close_price
                        if close_price is not None
                        else open_price or high_price or low_price
                    ),
                    total_volume=minute_provider_total,
                    volume_regression=volume_regression,
                    late_event=late_event or minute_was_finalized,
                )
                if existing.get("quality_status") == "VOLUME_REGRESSION":
                    quality = "VOLUME_REGRESSION"
                provider_time = max(
                    value
                    for value in (
                        existing.get("provider_time"),
                        event.event_at.strftime("%H:%M:%S"),
                    )
                    if value
                )
                minute_provider_session = provider_session
                if existing.get("last_event_at") and event_iso < existing["last_event_at"]:
                    minute_provider_session = existing.get("provider_session")
                connection.execute(
                    """INSERT INTO minute_bars(
                           symbol,trading_date,minute,exchange,open,high,low,close,
                           volume,value,provider_total_volume,provider_session,
                           provider_time,first_event_at,last_event_at,source,
                           quality_status,is_finalized,event_count,first_price_at,
                           last_price_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(symbol,trading_date,minute) DO UPDATE SET
                           exchange=excluded.exchange,open=excluded.open,
                           high=excluded.high,low=excluded.low,close=excluded.close,
                           volume=excluded.volume,
                           provider_total_volume=excluded.provider_total_volume,
                           provider_session=excluded.provider_session,
                           provider_time=excluded.provider_time,
                           first_event_at=excluded.first_event_at,
                           last_event_at=excluded.last_event_at,
                           source=excluded.source,quality_status=excluded.quality_status,
                           is_finalized=MAX(minute_bars.is_finalized,excluded.is_finalized),
                           event_count=excluded.event_count,
                           first_price_at=excluded.first_price_at,
                           last_price_at=excluded.last_price_at,
                           updated_at=excluded.updated_at""",
                    (
                        symbol, trading_date, minute,
                        event.exchange or existing.get("exchange"),
                        open_price, high_price, low_price, close_price,
                        minute_volume, existing.get("value"), minute_provider_total,
                        minute_provider_session or existing.get("provider_session"),
                        provider_time, first_event_at,
                        last_event_at, "SSI_STREAM", quality, int(is_finalized),
                        int(existing.get("event_count") or 0) + 1,
                        first_price_at, last_price_at, now,
                    ),
                )
                provider_total_changed = (
                    minute_provider_total is not None
                    and minute_provider_total != existing_provider_total
                )
                if late_event and provider_total_changed:
                    self._recalculate_next_minute_volume(
                        connection,
                        symbol=symbol,
                        trading_date=trading_date,
                        corrected_minute=minute,
                        corrected_total=int(minute_provider_total),
                    )

                exchange = str(event.exchange or "").strip().upper()
                exchange_session = (
                    classify_market_session(exchange, event.event_at)
                    if exchange in {"HOSE", "HNX", "UPCOM"}
                    else None
                )
                if (
                    provider_session
                    and provider_session != "ATO"
                    and exchange == "HOSE"
                ):
                    self._finalize_realtime_ato(
                        connection,
                        symbol=symbol,
                        trading_date=trading_date,
                        exchange=exchange,
                        transition_at=event.event_at,
                        updated_at=now,
                    )
                if (
                    provider_session == "ATO"
                    and exchange == "HOSE"
                    and exchange_session is not None
                    and exchange_session.session_type is SessionType.OPEN_AUCTION
                ):
                    self._upsert_realtime_auction(
                        connection,
                        event=event,
                        symbol=symbol,
                        trading_date=trading_date,
                        event_iso=event_iso,
                        price=price,
                        total_volume=total_volume,
                        prior_latest=latest,
                        quality_status=quality,
                        updated_at=now,
                    )
                elif provider_session == "ATC":
                    self._upsert_realtime_auction(
                        connection,
                        event=event,
                        symbol=symbol,
                        trading_date=trading_date,
                        event_iso=event_iso,
                        price=price,
                        total_volume=total_volume,
                        prior_latest=latest,
                        quality_status=quality,
                        updated_at=now,
                    )
                elif provider_session and provider_session != "ATO":
                    connection.execute(
                        """UPDATE auction_sessions SET finalized=1,updated_at=?
                           WHERE symbol=? AND trading_date=? AND auction_type='ATC'
                             AND finalized=0""",
                        (now, symbol, trading_date),
                    )

                latest_updated = self._upsert_realtime_latest(
                    connection,
                    event=event,
                    symbol=symbol,
                    trading_date=trading_date,
                    effective_total_volume=effective_total,
                    updated_at=now,
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

        return RealtimeWriteResult(
            latest_quote_updated=latest_updated,
            late_event=late_event,
            partial_event=price is None or total_volume is None,
            volume_regression=volume_regression,
            volume_delta=volume_delta,
            effective_total_volume=effective_total,
            minute_was_finalized=minute_was_finalized,
        )

    @staticmethod
    def _recalculate_next_minute_volume(
        connection: sqlite3.Connection,
        *,
        symbol: str,
        trading_date: str,
        corrected_minute: str,
        corrected_total: int,
    ) -> None:
        next_row = connection.execute(
            """SELECT minute,provider_total_volume FROM minute_bars
               WHERE symbol=? AND trading_date=? AND minute>?
                 AND provider_total_volume IS NOT NULL
               ORDER BY minute LIMIT 1""",
            (symbol, trading_date, corrected_minute),
        ).fetchone()
        if next_row is None:
            return
        next_total = int(next_row["provider_total_volume"])
        if next_total < corrected_total:
            return
        connection.execute(
            """UPDATE minute_bars SET volume=?
               WHERE symbol=? AND trading_date=? AND minute=?""",
            (
                next_total - corrected_total,
                symbol,
                trading_date,
                next_row["minute"],
            ),
        )

    @staticmethod
    def _upsert_realtime_latest(
        connection: sqlite3.Connection,
        *,
        event: RealtimeMarketEvent,
        symbol: str,
        trading_date: str,
        effective_total_volume: int | None,
        updated_at: str,
    ) -> bool:
        columns = (
            "symbol", "trading_date", "event_time", "last_price", "last_price_at",
            "total_volume",
            "ref_price", "open", "high", "low", "close", "bid_price1",
            "bid_vol1", "ask_price1", "ask_vol1", "change", "ratio_change",
            "exchange", "provider_session", "trading_status", "updated_at",
        )
        values = (
            symbol,
            trading_date,
            event.event_at.strftime("%H:%M:%S"),
            event.price if event.price is not None and event.price > 0 else None,
            (
                event.event_at.strftime("%H:%M:%S")
                if event.price is not None and event.price > 0
                else None
            ),
            effective_total_volume,
            event.ref_price,
            event.open,
            event.high,
            event.low,
            event.close,
            event.bid_price1,
            event.bid_vol1,
            event.ask_price1,
            event.ask_vol1,
            event.change,
            event.ratio_change,
            event.exchange,
            str(event.provider_session or "").strip().upper() or None,
            event.trading_status,
            updated_at,
        )
        merge_columns = columns[3:-1]
        assignments = ",".join(
            f"{column}=CASE "
            f"WHEN excluded.trading_date > latest_quotes.trading_date "
            f"THEN excluded.{column} "
            f"ELSE COALESCE(excluded.{column},latest_quotes.{column}) END"
            for column in merge_columns
        )
        cursor = connection.execute(
            f"""INSERT INTO latest_quotes({','.join(columns)})
                VALUES({','.join('?' for _ in columns)})
                ON CONFLICT(symbol) DO UPDATE SET
                    trading_date=excluded.trading_date,
                    event_time=excluded.event_time,
                    {assignments},
                    updated_at=excluded.updated_at
                WHERE excluded.trading_date > latest_quotes.trading_date
                   OR (excluded.trading_date = latest_quotes.trading_date
                       AND (latest_quotes.event_time IS NULL
                            OR excluded.event_time >= latest_quotes.event_time))""",
            values,
        )
        return bool(cursor.rowcount)

    @staticmethod
    def _finalize_realtime_ato(
        connection: sqlite3.Connection,
        *,
        symbol: str,
        trading_date: str,
        exchange: str,
        transition_at: datetime,
        updated_at: str,
    ) -> None:
        existing_row = connection.execute(
            """SELECT * FROM auction_sessions
               WHERE symbol=? AND trading_date=? AND auction_type='ATO'
                 AND exchange=? AND finalized=0""",
            (symbol, trading_date, exchange),
        ).fetchone()
        if existing_row is None:
            return
        existing = dict(existing_row)
        last_event_text = existing.get("last_event_at")
        if last_event_text is None:
            return
        try:
            last_event_at = datetime.fromisoformat(str(last_event_text))
        except ValueError:
            return
        evidence_session = classify_market_session(exchange, last_event_at)
        if (
            evidence_session.session_type is not SessionType.OPEN_AUCTION
            or evidence_session.session_end is None
            or transition_at < evidence_session.session_end
            or transition_at <= last_event_at
        ):
            return
        connection.execute(
            """UPDATE auction_sessions SET finalized=1,updated_at=?
               WHERE symbol=? AND trading_date=? AND auction_type='ATO'
                 AND exchange=? AND finalized=0""",
            (
                updated_at,
                symbol,
                trading_date,
                exchange,
            ),
        )

    @staticmethod
    def _upsert_realtime_auction(
        connection: sqlite3.Connection,
        *,
        event: RealtimeMarketEvent,
        symbol: str,
        trading_date: str,
        event_iso: str,
        price: float | None,
        total_volume: int | None,
        prior_latest: sqlite3.Row | None,
        quality_status: str,
        updated_at: str,
    ) -> None:
        auction_type = str(event.provider_session).strip().upper()
        existing_row = connection.execute(
            """SELECT * FROM auction_sessions
               WHERE symbol=? AND trading_date=? AND auction_type=?""",
            (symbol, trading_date, auction_type),
        ).fetchone()
        existing = dict(existing_row) if existing_row is not None else {}
        if auction_type == "ATO" and int(existing.get("finalized") or 0):
            return
        prior_total = (
            int(prior_latest["total_volume"])
            if prior_latest is not None
            and prior_latest["trading_date"] == trading_date
            and prior_latest["total_volume"] is not None
            else None
        )
        start_total = existing.get("start_total_volume")
        if not existing and prior_total is not None:
            start_total = prior_total
        elif (
            start_total is None
            and auction_type == "ATO"
            and event.seed_volume_from_zero
        ):
            start_total = 0
        end_total = existing.get("end_total_volume")
        if total_volume is not None:
            end_total = total_volume if end_total is None else max(int(end_total), total_volume)
        if auction_type == "ATO":
            auction_volume = (
                int(end_total) - int(start_total)
                if end_total is not None
                and start_total is not None
                and int(end_total) >= int(start_total)
                else None
            )
        else:
            auction_volume = (
                max(0, int(end_total) - int(start_total))
                if end_total is not None and start_total is not None
                else None
            )
        pre_auction_price = existing.get("pre_auction_price")
        if (
            auction_type == "ATC"
            and pre_auction_price is None
            and prior_latest is not None
            and str(prior_latest["provider_session"] or "").upper() == "LO"
            and prior_latest["last_price"] is not None
        ):
            pre_auction_price = float(prior_latest["last_price"])
        first_event = min(
            value for value in (existing.get("first_event_at"), event_iso) if value
        )
        last_event = max(
            value for value in (existing.get("last_event_at"), event_iso) if value
        )
        auction_price = existing.get("auction_price")
        if price is not None and (
            auction_type != "ATO"
            or existing.get("last_event_at") is None
            or event_iso >= str(existing["last_event_at"])
        ):
            auction_price = price
        if existing.get("quality_status") == "VOLUME_REGRESSION":
            quality_status = "VOLUME_REGRESSION"
        elif (
            auction_type == "ATO"
            and (auction_volume is None or auction_price is None)
        ):
            quality_status = "PARTIAL"
        connection.execute(
            """INSERT INTO auction_sessions(
                   symbol,trading_date,exchange,auction_type,provider_session,
                   pre_auction_price,auction_price,start_total_volume,
                   end_total_volume,auction_volume,event_count,first_event_at,
                   last_event_at,source,quality_status,finalized,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(symbol,trading_date,auction_type) DO UPDATE SET
                   exchange=COALESCE(excluded.exchange,auction_sessions.exchange),
                   provider_session=excluded.provider_session,
                   pre_auction_price=COALESCE(auction_sessions.pre_auction_price,
                                              excluded.pre_auction_price),
                   auction_price=COALESCE(excluded.auction_price,
                                          auction_sessions.auction_price),
                   start_total_volume=COALESCE(auction_sessions.start_total_volume,
                                               excluded.start_total_volume),
                   end_total_volume=COALESCE(excluded.end_total_volume,
                                             auction_sessions.end_total_volume),
                   auction_volume=excluded.auction_volume,
                   event_count=excluded.event_count,
                   first_event_at=excluded.first_event_at,
                   last_event_at=excluded.last_event_at,
                   source=excluded.source,quality_status=excluded.quality_status,
                   finalized=MAX(auction_sessions.finalized,excluded.finalized),
                   updated_at=excluded.updated_at""",
            (
                symbol,
                trading_date,
                event.exchange or existing.get("exchange"),
                auction_type,
                auction_type,
                pre_auction_price,
                auction_price,
                start_total,
                end_total,
                auction_volume,
                int(existing.get("event_count") or 0) + 1,
                first_event,
                last_event,
                "SSI_STREAM",
                quality_status,
                int(existing.get("finalized") or 0),
                updated_at,
            ),
        )

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
            with self._lock:
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
            with self._lock:
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
            with self._lock:
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
        with self._lock:
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
        with self._lock:
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
            with self._lock:
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
        with self._lock:
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
