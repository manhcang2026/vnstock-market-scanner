"""Small read-only adapter for canonical year-sharded market data."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

QUOTE_COLUMNS = (
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
)


class CanonicalMarketReader:
    """Read canonical market shards without creating or modifying them."""

    def __init__(self, market_dir: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        self.market_dir = Path(market_dir)
        self.busy_timeout_ms = max(0, int(busy_timeout_ms))

    def path_for_year(self, year: int) -> Path:
        return self.market_dir / f"ccc_market_{int(year)}.db"

    def _connect(self, year: int) -> sqlite3.Connection | None:
        path = self.path_for_year(year)
        if not path.is_file():
            return None
        connection = sqlite3.connect(
            f"file:{path.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=self.busy_timeout_ms / 1000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        return connection

    @staticmethod
    def _mapping(row: sqlite3.Row) -> dict[str, object]:
        return {key: row[key] for key in row.keys()}

    def minute_rows(
        self,
        *,
        symbol: str,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, object]]:
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
        rows: list[dict[str, object]] = []
        for year in range(start.year, end.year + 1):
            shard_from = max(start, date(year, 1, 1)).isoformat()
            shard_to = min(end, date(year, 12, 31)).isoformat()
            connection = self._connect(year)
            if connection is None:
                continue
            try:
                fetched = connection.execute(
                    """
                    SELECT trading_date, minute, symbol, exchange,
                           open, high, low, close, volume,
                           quality_status, source AS data_source,
                           provider_time, is_finalized
                    FROM minute_bars
                    WHERE symbol = ?
                      AND trading_date BETWEEN ? AND ?
                    ORDER BY trading_date, minute
                    """,
                    (symbol, shard_from, shard_to),
                ).fetchall()
                rows.extend(self._mapping(row) for row in fetched)
            finally:
                connection.close()
        rows.sort(key=lambda row: (str(row["trading_date"]), str(row["minute"])))
        return rows

    def candle_rows(
        self,
        *,
        symbol: str,
        trading_date: str,
        minute_from: str | None = None,
        minute_to: str | None = None,
    ) -> list[dict[str, object]]:
        day = date.fromisoformat(trading_date)
        connection = self._connect(day.year)
        if connection is None:
            return []
        try:
            where = "symbol = ? AND trading_date = ?"
            params: list[object] = [symbol, day.isoformat()]
            if minute_from is not None:
                where += " AND minute >= ?"
                params.append(minute_from)
            if minute_to is not None:
                where += " AND minute <= ?"
                params.append(minute_to)
            fetched = connection.execute(
                f"""
                SELECT minute, open, high, low, close, volume,
                       source AS data_source, provider_time
                FROM minute_bars
                WHERE {where}
                ORDER BY minute
                """,
                params,
            ).fetchall()
            return [self._mapping(row) for row in fetched]
        finally:
            connection.close()

    def latest_quote(
        self,
        symbol: str,
        *,
        as_of_year: int | None = None,
    ) -> dict[str, object] | None:
        current_year = int(as_of_year or datetime.now(VN_TZ).year)
        candidates: list[dict[str, object]] = []
        select_columns = (
            *QUOTE_COLUMNS[:17],
            "provider_session AS trading_session",
            *QUOTE_COLUMNS[18:],
        )
        for year in (current_year, current_year - 1):
            connection = self._connect(year)
            if connection is None:
                continue
            try:
                row = connection.execute(
                    f"SELECT {', '.join(select_columns)} "
                    "FROM latest_quotes WHERE symbol = ?",
                    (symbol,),
                ).fetchone()
                if row is not None:
                    candidates.append(self._mapping(row))
            finally:
                connection.close()
        if not candidates:
            return None
        newest = max(
            candidates,
            key=lambda row: (
                str(row.get("trading_date") or ""),
                str(row.get("event_time") or ""),
            ),
        )
        newest["source"] = "CANONICAL_MARKET"
        return newest
