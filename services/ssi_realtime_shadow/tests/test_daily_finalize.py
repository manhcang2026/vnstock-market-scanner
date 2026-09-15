from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.daily_finalize import finalize_day


SCHEMA = """
CREATE TABLE minute_bars (
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
    quality_status TEXT NOT NULL DEFAULT 'TRUSTED',
    has_gap INTEGER NOT NULL DEFAULT 0,
    gap_from TEXT,
    gap_to TEXT,
    data_source TEXT NOT NULL DEFAULT 'SSI_STREAM',
    provider_time TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trading_date, minute, symbol)
);
"""


def _make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.commit()
    con.close()


def _insert(
    path: Path,
    *,
    trading_date: str,
    minute: str,
    symbol: str,
    open_price: float = 10.0,
    high: float = 11.0,
    low: float = 9.0,
    close: float = 10.5,
    gap: int = 0,
) -> None:
    con = sqlite3.connect(path)
    con.execute(
        """
        INSERT INTO minute_bars (
            trading_date, minute, symbol, open, high, low, close, volume,
            last_total_volume, event_count, is_partial, exchange,
            quality_status, has_gap, gap_from, gap_to, data_source,
            provider_time, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 100, 100, 2, 0, 'HOSE',
                  'TRUSTED', ?, NULL, NULL, 'SSI_STREAM', ?, ?)
        """,
        (
            trading_date,
            minute,
            symbol,
            open_price,
            high,
            low,
            close,
            gap,
            minute + ":00",
            trading_date + "T15:30:00+07:00",
        ),
    )
    con.commit()
    con.close()


def test_finalize_promotes_and_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "shadow.db"
    history = tmp_path / "history.db"
    _make_db(source)
    _make_db(history)
    _insert(source, trading_date="2026-09-15", minute="09:00", symbol="HPG")
    _insert(source, trading_date="2026-09-15", minute="14:45", symbol="SSI")

    now = datetime(2026, 9, 15, 16, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    result = finalize_day(
        source_path=source,
        history_path=history,
        trading_date="2026-09-15",
        min_symbols=2,
        min_minutes=2,
        min_rows=2,
        min_last_minute="14:45",
        now=now,
    )
    assert result.status == "PASS"
    assert result.inserted_rows == 2

    again = finalize_day(
        source_path=source,
        history_path=history,
        trading_date="2026-09-15",
        min_symbols=2,
        min_minutes=2,
        min_rows=2,
        min_last_minute="14:45",
        now=now,
    )
    assert again.status == "PASS"
    assert again.inserted_rows == 0
    assert again.history_rows_after == 2

    con = sqlite3.connect(history)
    assert con.execute(
        "SELECT COUNT(*) FROM minute_bars WHERE data_source='SSI_STREAM_FINAL'"
    ).fetchone()[0] == 2
    assert con.execute(
        "SELECT status FROM daily_finalize_runs WHERE trading_date='2026-09-15'"
    ).fetchone()[0] == "PASS"
    con.close()


def test_finalize_blocks_invalid_ohlc(tmp_path: Path) -> None:
    source = tmp_path / "shadow.db"
    history = tmp_path / "history.db"
    _make_db(source)
    _make_db(history)
    _insert(
        source,
        trading_date="2026-09-15",
        minute="14:45",
        symbol="HPG",
        open_price=10.0,
        high=10.0,
        low=10.0,
        close=9.0,
    )

    result = finalize_day(
        source_path=source,
        history_path=history,
        trading_date="2026-09-15",
        min_symbols=1,
        min_minutes=1,
        min_rows=1,
        min_last_minute="14:45",
    )
    assert result.status == "BLOCKED"
    assert result.audit.invalid_ohlc_rows == 1
    assert "invalid_ohlc_rows=1" in result.reasons


def test_finalize_blocks_gap(tmp_path: Path) -> None:
    source = tmp_path / "shadow.db"
    history = tmp_path / "history.db"
    _make_db(source)
    _make_db(history)
    _insert(
        source,
        trading_date="2026-09-15",
        minute="14:45",
        symbol="HPG",
        gap=1,
    )

    result = finalize_day(
        source_path=source,
        history_path=history,
        trading_date="2026-09-15",
        min_symbols=1,
        min_minutes=1,
        min_rows=1,
        min_last_minute="14:45",
    )
    assert result.status == "BLOCKED"
    assert result.audit.gap_rows == 1
