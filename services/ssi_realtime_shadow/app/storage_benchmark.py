"""Reproducible local SQLite storage benchmark for CCC market-data schemas."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

from .market_storage_schema import (
    ensure_5m_archive_schema,
    ensure_market_storage_schema,
)
from .storage import SCHEMA


GIB = 1024**3
DEFAULT_ROWS = 100_000


@dataclass(frozen=True, slots=True)
class TableMeasurement:
    table: str
    rows: int
    page_size: int
    page_count: int
    empty_schema_bytes: int
    total_db_bytes: int
    incremental_bytes: int
    gross_bytes_per_row: float
    incremental_bytes_per_row: float
    wal_bytes: int


def _batched(rows: Iterable[Sequence[object]], size: int = 5_000) -> Iterator[list[Sequence[object]]]:
    batch: list[Sequence[object]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def _measure(connection: sqlite3.Connection) -> tuple[int, int, int]:
    connection.commit()
    connection.execute("VACUUM")
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    return page_size, page_count, page_size * page_count


def _symbols() -> tuple[str, ...]:
    return tuple(f"S{index:04d}" for index in range(800))


def _daily_rows(count: int) -> Iterator[Sequence[object]]:
    symbols = _symbols()
    start = date(2022, 1, 3)
    timestamp = "2026-09-18T16:00:00+07:00"
    for index in range(count):
        session = index // len(symbols)
        symbol = symbols[index % len(symbols)]
        trading_date = (start + timedelta(days=session)).isoformat()
        price = 10_000.0 + (index % 10_000)
        yield (
            symbol, trading_date, "HOSE", price, price + 200, price - 100,
            price + 50, 1_000_000 + index, price * (1_000_000 + index),
            "SSI_DAILY_OHLC", "TRUSTED", timestamp,
        )


def _minute_rows(count: int) -> Iterator[Sequence[object]]:
    symbols = _symbols()
    start = date(2026, 8, 31)
    for index in range(count):
        per_session = len(symbols) * 270
        session = index // per_session
        within = index % per_session
        minute_index = within // len(symbols)
        symbol = symbols[within % len(symbols)]
        total_minutes = 9 * 60 + minute_index
        minute = f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
        trading_date = (start + timedelta(days=session)).isoformat()
        price = 10_000.0 + (index % 10_000)
        yield (
            trading_date, minute, symbol, price, price + 100, price - 100,
            price + 50, 10_000 + index, 1_000_000 + index, 20, 0, "HOSE",
            "TRUSTED", 0, None, None, "SSI_STREAM", f"{minute}:30",
            f"{trading_date}T{minute}:30+07:00",
        )


def _archive_rows(count: int) -> Iterator[Sequence[object]]:
    symbols = _symbols()
    start = date(2024, 1, 2)
    timestamp = "2026-09-18T16:00:00+07:00"
    for index in range(count):
        per_session = len(symbols) * 54
        session = index // per_session
        within = index % per_session
        bar_index = within // len(symbols)
        symbol = symbols[within % len(symbols)]
        total_minutes = 9 * 60 + bar_index * 5
        bar_time = f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
        trading_date = (start + timedelta(days=session)).isoformat()
        price = 10_000.0 + (index % 10_000)
        yield (
            symbol, "HOSE", trading_date, bar_time, price, price + 100,
            price - 100, price + 50, 50_000 + index, price * (50_000 + index),
            "TRUSTED", "SSI_1M_AGG", timestamp,
        )


def _benchmark_one(
    path: Path,
    *,
    table: str,
    row_count: int,
    initialize: Callable[[sqlite3.Connection], None],
    insert_sql: str,
    rows: Iterable[Sequence[object]],
) -> TableMeasurement:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = OFF")
        initialize(connection)
        page_size, _, empty_bytes = _measure(connection)
        connection.execute("BEGIN")
        for batch in _batched(rows):
            connection.executemany(insert_sql, batch)
        connection.commit()
        page_size, page_count, total_bytes = _measure(connection)
        actual_rows = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        connection.close()
    if actual_rows != row_count:
        raise RuntimeError(f"{table}: inserted {actual_rows}/{row_count} rows")
    wal_path = Path(str(path) + "-wal")
    wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
    incremental = total_bytes - empty_bytes
    return TableMeasurement(
        table=table,
        rows=actual_rows,
        page_size=page_size,
        page_count=page_count,
        empty_schema_bytes=empty_bytes,
        total_db_bytes=total_bytes,
        incremental_bytes=incremental,
        gross_bytes_per_row=total_bytes / actual_rows,
        incremental_bytes_per_row=incremental / actual_rows,
        wal_bytes=wal_bytes,
    )


def run_benchmark(row_count: int = DEFAULT_ROWS) -> dict[str, object]:
    """Benchmark three real schemas in a temporary directory and project storage."""
    if row_count < 1:
        raise ValueError("row_count must be positive")
    with tempfile.TemporaryDirectory(prefix="ccc-storage-benchmark-") as raw_dir:
        root = Path(raw_dir)
        daily = _benchmark_one(
            root / "daily.db", table="daily_bars", row_count=row_count,
            initialize=lambda connection: ensure_market_storage_schema(
                connection, applied_at="2026-09-18T10:00:00+07:00"
            ),
            insert_sql="INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows=_daily_rows(row_count),
        )
        minute = _benchmark_one(
            root / "minute.db", table="minute_bars", row_count=row_count,
            initialize=lambda connection: connection.executescript(SCHEMA),
            insert_sql="INSERT INTO minute_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows=_minute_rows(row_count),
        )
        archive = _benchmark_one(
            root / "archive.db", table="bars_5m_archive", row_count=row_count,
            initialize=ensure_5m_archive_schema,
            insert_sql="INSERT INTO bars_5m_archive VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows=_archive_rows(row_count),
        )

    projections = {
        "minute_15_sessions": {
            "rows": 800 * 270 * 15,
            "gib": 800 * 270 * 15 * minute.incremental_bytes_per_row / GIB,
        },
        "archive_1_year": {
            "rows": 800 * 54 * 250,
            "gib": 800 * 54 * 250 * archive.incremental_bytes_per_row / GIB,
        },
        "archive_2_years": {
            "rows": 800 * 54 * 250 * 2,
            "gib": 800 * 54 * 250 * 2 * archive.incremental_bytes_per_row / GIB,
        },
        "daily_5_years": {
            "rows": 800 * 250 * 5,
            "gib": 800 * 250 * 5 * daily.incremental_bytes_per_row / GIB,
        },
        "daily_10_years": {
            "rows": 800 * 250 * 10,
            "gib": 800 * 250 * 10 * daily.incremental_bytes_per_row / GIB,
        },
    }
    used_gib = 5.2
    usable_gib = 45.0
    thresholds = {
        f"{percent}_percent": {
            "used_gib": usable_gib * percent / 100,
            "additional_headroom_gib": usable_gib * percent / 100 - used_gib,
        }
        for percent in (60, 70, 80)
    }
    return {
        "method": {
            "sample_rows_per_table": row_count,
            "journal_mode": "DELETE",
            "vacuumed": True,
            "bytes_per_row_basis": "incremental populated bytes minus empty real schema",
        },
        "measurements": {
            "daily": asdict(daily), "minute_1m": asdict(minute),
            "archive_5m": asdict(archive),
        },
        "projections": projections,
        "filesystem_thresholds": thresholds,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    args = parser.parse_args(argv)
    print(json.dumps(run_benchmark(args.rows), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
