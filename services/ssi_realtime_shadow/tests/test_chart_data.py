from __future__ import annotations

import sqlite3
from pathlib import Path

from app.chart_data import ChartDataStore


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

CREATE TABLE daily_finalize_runs (
    trading_date TEXT PRIMARY KEY,
    status TEXT NOT NULL
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
    day: str,
    minute: str,
    symbol: str = "HPG",
    open_price: float = 10.0,
    high: float = 11.0,
    low: float = 9.0,
    close: float = 10.5,
    volume: int = 100,
    source: str = "SSI_REST",
) -> None:
    con = sqlite3.connect(path)
    con.execute(
        """
        INSERT INTO minute_bars (
            trading_date, minute, symbol, open, high, low, close, volume,
            exchange, quality_status, data_source, provider_time, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'HOSE', 'TRUSTED', ?, ?, ?)
        """,
        (
            day,
            minute,
            symbol,
            open_price,
            high,
            low,
            close,
            volume,
            source,
            minute + ":00",
            day + "T15:30:00+07:00",
        ),
    )
    con.commit()
    con.close()


def _finalize(path: Path, *, day: str, status: str) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "INSERT INTO daily_finalize_runs(trading_date, status) VALUES (?, ?)",
        (day, status),
    )
    con.commit()
    con.close()


def test_finalized_history_is_canonical_by_day_and_realtime_fills_new_day(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    realtime = tmp_path / "realtime.db"
    _make_db(history)
    _make_db(realtime)

    _insert(
        history,
        day="2026-09-14",
        minute="09:00",
        close=10.5,
        source="SSI_REST",
    )
    _insert(
        history,
        day="2026-09-15",
        minute="09:00",
        close=11.0,
        source="SSI_REST",
    )
    _finalize(history, day="2026-09-15", status="REST_PASS")

    # Conflicting + extra realtime bars on a finalized day must both be ignored.
    _insert(
        realtime,
        day="2026-09-15",
        minute="09:00",
        close=99.0,
        high=100.0,
        source="SSI_STREAM",
    )
    _insert(
        realtime,
        day="2026-09-15",
        minute="09:01",
        close=98.0,
        high=100.0,
        source="SSI_STREAM",
    )

    # Current/unfinalized day is still allowed to come from realtime.
    _insert(
        realtime,
        day="2026-09-16",
        minute="09:00",
        close=12.0,
        high=12.0,
        low=12.0,
        open_price=12.0,
        source="SSI_STREAM",
    )

    result = ChartDataStore(history, realtime).query(
        symbol="HPG",
        date_from="2026-09-14",
        date_to="2026-09-16",
    )

    assert len(result.bars) == 3
    assert result.bars[0].data_source == "SSI_REST"
    assert result.bars[1].close == 11.0
    assert result.bars[1].data_source == "SSI_REST"
    assert result.bars[2].close == 12.0
    assert result.bars[2].data_source == "SSI_STREAM"
    assert result.source_counts == {"SSI_REST": 2, "SSI_STREAM": 1}


def test_finalized_day_suppresses_realtime_even_when_symbol_has_no_history_bar(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    realtime = tmp_path / "realtime.db"
    _make_db(history)
    _make_db(realtime)

    _finalize(history, day="2026-09-15", status="REST_PASS")
    _insert(
        realtime,
        day="2026-09-15",
        minute="09:00",
        symbol="HPG",
        source="SSI_STREAM",
    )

    result = ChartDataStore(history, realtime).query(
        symbol="HPG",
        date_from="2026-09-15",
        date_to="2026-09-15",
    )

    assert result.bars == ()
    assert result.source_counts == {}


def test_legacy_rest_history_without_finalize_metadata_is_canonical(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    realtime = tmp_path / "realtime.db"
    _make_db(history)
    _make_db(realtime)

    _insert(
        history,
        day="2026-09-14",
        minute="09:00",
        source="SSI_REST",
    )
    _insert(
        realtime,
        day="2026-09-14",
        minute="09:01",
        source="SSI_STREAM",
    )

    result = ChartDataStore(history, realtime).query(
        symbol="HPG",
        date_from="2026-09-14",
        date_to="2026-09-14",
    )

    assert len(result.bars) == 1
    assert result.bars[0].minute == "09:00"
    assert result.bars[0].data_source == "SSI_REST"


def test_blocked_day_can_still_use_realtime_fill(tmp_path: Path) -> None:
    history = tmp_path / "history.db"
    realtime = tmp_path / "realtime.db"
    _make_db(history)
    _make_db(realtime)

    _insert(
        history,
        day="2026-09-15",
        minute="09:00",
        source="SSI_REST",
    )
    _finalize(history, day="2026-09-15", status="REST_BLOCKED")
    _insert(
        realtime,
        day="2026-09-15",
        minute="09:01",
        source="SSI_STREAM",
    )

    result = ChartDataStore(history, realtime).query(
        symbol="HPG",
        date_from="2026-09-15",
        date_to="2026-09-15",
    )

    assert len(result.bars) == 2
    assert result.source_counts == {"SSI_REST": 1, "SSI_STREAM": 1}


def test_invalid_ohlc_is_filtered_by_default(tmp_path: Path) -> None:
    history = tmp_path / "history.db"
    realtime = tmp_path / "realtime.db"
    _make_db(history)
    _make_db(realtime)

    _insert(
        history,
        day="2026-01-05",
        minute="09:00",
        open_price=10.0,
        high=10.0,
        low=10.0,
        close=9.0,
    )

    store = ChartDataStore(history, realtime)
    filtered = store.query(
        symbol="HPG",
        date_from="2026-01-05",
        date_to="2026-01-05",
    )
    assert filtered.bars == ()
    assert filtered.invalid_ohlc_dropped == 1

    included = store.query(
        symbol="HPG",
        date_from="2026-01-05",
        date_to="2026-01-05",
        include_invalid=True,
    )
    assert len(included.bars) == 1
    assert included.bars[0].quality_status == "INVALID_OHLC"


def test_five_minute_aggregation(tmp_path: Path) -> None:
    history = tmp_path / "history.db"
    realtime = tmp_path / "realtime.db"
    _make_db(history)
    _make_db(realtime)

    _insert(
        history,
        day="2026-01-05",
        minute="09:00",
        open_price=10,
        high=11,
        low=9,
        close=10,
        volume=100,
    )
    _insert(
        history,
        day="2026-01-05",
        minute="09:01",
        open_price=10,
        high=12,
        low=10,
        close=11,
        volume=200,
    )
    _insert(
        history,
        day="2026-01-05",
        minute="09:04",
        open_price=11,
        high=13,
        low=10,
        close=12,
        volume=300,
    )

    result = ChartDataStore(history, realtime).query(
        symbol="HPG",
        date_from="2026-01-05",
        date_to="2026-01-05",
        resolution=5,
    )

    assert len(result.bars) == 1
    bar = result.bars[0]
    assert bar.minute == "09:00"
    assert bar.open == 10
    assert bar.high == 13
    assert bar.low == 9
    assert bar.close == 12
    assert bar.volume == 600
