"""Disposable/rebuildable CCC calculation store."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .canonical_market_store import utc_now


ENGINE_SCHEMA_VERSION = "1"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS technical_baseline (
    symbol TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    previous_close REAL,
    ma10 REAL,
    ma10_sessions INTEGER NOT NULL,
    ma200 REAL,
    ma200_sessions INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(symbol, as_of_date)
);
CREATE TABLE IF NOT EXISTS volume_baseline_curve (
    symbol TEXT NOT NULL,
    minute TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    avg_cumulative_volume REAL,
    day_sessions_used INTEGER NOT NULL,
    avg_volume_15 REAL,
    rvol15_sessions_used INTEGER NOT NULL,
    avg_volume_30 REAL,
    rvol30_sessions_used INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(symbol, minute, as_of_date)
);
CREATE TABLE IF NOT EXISTS current_state (
    symbol TEXT PRIMARY KEY,
    exchange TEXT,
    trading_date TEXT,
    minute TEXT,
    last_price REAL,
    cumulative_volume INTEGER,
    day_rvol REAL,
    rvol15 REAL,
    rvol30 REAL,
    price5_pct REAL,
    price15_pct REAL,
    ma10 REAL,
    ma200 REAL,
    distance_ma10_pct REAL,
    distance_ma200_pct REAL,
    baseline_sessions_used INTEGER,
    quality_status TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class TechnicalBaseline:
    symbol: str
    as_of_date: str
    previous_close: float | None
    ma10: float | None
    ma10_sessions: int
    ma200: float | None
    ma200_sessions: int
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class VolumeBaselinePoint:
    symbol: str
    minute: str
    as_of_date: str
    avg_cumulative_volume: float | None
    day_sessions_used: int
    avg_volume_15: float | None
    rvol15_sessions_used: int
    avg_volume_30: float | None
    rvol30_sessions_used: int
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class CurrentState:
    symbol: str
    exchange: str | None
    trading_date: str | None
    minute: str | None
    last_price: float | None
    cumulative_volume: int | None
    day_rvol: float | None
    rvol15: float | None
    rvol30: float | None
    price5_pct: float | None
    price15_pct: float | None
    ma10: float | None
    ma200: float | None
    distance_ma10_pct: float | None
    distance_ma200_pct: float | None
    baseline_sessions_used: int
    quality_status: str
    reason_codes_json: str
    updated_at: str = ""


class CanonicalEngineStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(SCHEMA_SQL)
        self.connection.execute(
            """INSERT INTO schema_meta(key,value,updated_at) VALUES(?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
               updated_at=excluded.updated_at""",
            ("schema_version", ENGINE_SCHEMA_VERSION, utc_now()),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "CanonicalEngineStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def replace_as_of(
        self,
        *,
        as_of_date: str,
        technical: Iterable[TechnicalBaseline],
        volume: Iterable[VolumeBaselinePoint],
        current: Iterable[CurrentState],
    ) -> None:
        technical_rows = list(technical)
        volume_rows = list(volume)
        current_rows = list(current)
        with self.connection:
            self.connection.execute(
                "DELETE FROM technical_baseline WHERE as_of_date=?", (as_of_date,)
            )
            self.connection.execute(
                "DELETE FROM volume_baseline_curve WHERE as_of_date=?", (as_of_date,)
            )
            self.connection.execute("DELETE FROM current_state")
            self.connection.executemany(
                """INSERT INTO technical_baseline(
                       symbol,as_of_date,previous_close,ma10,ma10_sessions,
                       ma200,ma200_sessions,updated_at
                   ) VALUES(:symbol,:as_of_date,:previous_close,:ma10,:ma10_sessions,
                            :ma200,:ma200_sessions,:updated_at)""",
                [self._values(row) for row in technical_rows],
            )
            self.connection.executemany(
                """INSERT INTO volume_baseline_curve(
                       symbol,minute,as_of_date,avg_cumulative_volume,
                       day_sessions_used,avg_volume_15,rvol15_sessions_used,
                       avg_volume_30,rvol30_sessions_used,updated_at
                   ) VALUES(:symbol,:minute,:as_of_date,:avg_cumulative_volume,
                            :day_sessions_used,:avg_volume_15,:rvol15_sessions_used,
                            :avg_volume_30,:rvol30_sessions_used,:updated_at)""",
                [self._values(row) for row in volume_rows],
            )
            for row in current_rows:
                self._upsert_current(row)

    def begin_rebuild(self, as_of_date: str) -> None:
        """Clear disposable output before streaming one symbol at a time."""
        with self.connection:
            self.connection.execute(
                "DELETE FROM technical_baseline WHERE as_of_date=?", (as_of_date,)
            )
            self.connection.execute(
                "DELETE FROM volume_baseline_curve WHERE as_of_date=?", (as_of_date,)
            )
            self.connection.execute("DELETE FROM current_state")

    def write_symbol(
        self,
        *,
        technical: TechnicalBaseline | None,
        volume: Iterable[VolumeBaselinePoint],
        current: CurrentState,
    ) -> None:
        """Commit one symbol so rebuild memory is independent of universe size."""
        volume_rows = list(volume)
        with self.connection:
            if technical is not None:
                self.connection.execute(
                    """INSERT INTO technical_baseline(
                           symbol,as_of_date,previous_close,ma10,ma10_sessions,
                           ma200,ma200_sessions,updated_at
                       ) VALUES(:symbol,:as_of_date,:previous_close,:ma10,
                                :ma10_sessions,:ma200,:ma200_sessions,:updated_at)""",
                    self._values(technical),
                )
            self.connection.executemany(
                """INSERT INTO volume_baseline_curve(
                       symbol,minute,as_of_date,avg_cumulative_volume,
                       day_sessions_used,avg_volume_15,rvol15_sessions_used,
                       avg_volume_30,rvol30_sessions_used,updated_at
                   ) VALUES(:symbol,:minute,:as_of_date,:avg_cumulative_volume,
                            :day_sessions_used,:avg_volume_15,:rvol15_sessions_used,
                            :avg_volume_30,:rvol30_sessions_used,:updated_at)""",
                [self._values(row) for row in volume_rows],
            )
            self._upsert_current(current)

    def _upsert_current(self, row: CurrentState) -> None:
        values = self._values(row)
        self.connection.execute(
            """INSERT INTO current_state(
                   symbol,exchange,trading_date,minute,last_price,
                   cumulative_volume,day_rvol,rvol15,rvol30,price5_pct,
                   price15_pct,ma10,ma200,distance_ma10_pct,
                   distance_ma200_pct,baseline_sessions_used,quality_status,
                   reason_codes_json,updated_at
               ) VALUES(:symbol,:exchange,:trading_date,:minute,:last_price,
                   :cumulative_volume,:day_rvol,:rvol15,:rvol30,:price5_pct,
                   :price15_pct,:ma10,:ma200,:distance_ma10_pct,
                   :distance_ma200_pct,:baseline_sessions_used,:quality_status,
                   :reason_codes_json,:updated_at)
               ON CONFLICT(symbol) DO UPDATE SET
                   exchange=excluded.exchange,trading_date=excluded.trading_date,
                   minute=excluded.minute,last_price=excluded.last_price,
                   cumulative_volume=excluded.cumulative_volume,
                   day_rvol=excluded.day_rvol,rvol15=excluded.rvol15,
                   rvol30=excluded.rvol30,price5_pct=excluded.price5_pct,
                   price15_pct=excluded.price15_pct,ma10=excluded.ma10,
                   ma200=excluded.ma200,
                   distance_ma10_pct=excluded.distance_ma10_pct,
                   distance_ma200_pct=excluded.distance_ma200_pct,
                   baseline_sessions_used=excluded.baseline_sessions_used,
                   quality_status=excluded.quality_status,
                   reason_codes_json=excluded.reason_codes_json,
                   updated_at=excluded.updated_at""",
            values,
        )

    @staticmethod
    def _values(row: object) -> dict[str, object]:
        values = asdict(row)  # type: ignore[arg-type]
        if not values.get("updated_at"):
            values["updated_at"] = utc_now()
        return values
