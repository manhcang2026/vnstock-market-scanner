from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.chart_api import _fetch_latest_quote, _normalize_symbol


SCHEMA = """
CREATE TABLE latest_quotes (
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
"""


def _make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute(
        """
        INSERT INTO latest_quotes (
            symbol, trading_date, event_time, last_price, total_volume,
            ref_price, open, high, low, close,
            bid_price1, bid_vol1, ask_price1, ask_vol1,
            change, ratio_change, exchange, trading_session, trading_status,
            updated_at
        ) VALUES (
            'HPG', '2026-09-16', '10:15:30', 21500, 12345678,
            21000, 21100, 21600, 20900, 21500,
            21450, 1000, 21550, 1200,
            500, 2.38, 'HOSE', 'CONTINUOUS', 'OPEN',
            '2026-09-16T10:15:30+07:00'
        )
        """
    )
    con.commit()
    con.close()


def test_fetch_latest_quote(tmp_path: Path) -> None:
    db = tmp_path / "realtime.db"
    _make_db(db)

    quote = _fetch_latest_quote(db, "hpg")

    assert quote is not None
    assert quote["symbol"] == "HPG"
    assert quote["last_price"] == 21500
    assert quote["total_volume"] == 12345678
    assert quote["ratio_change"] == 2.38
    assert quote["source"] == "SSI_STREAM"


def test_quote_not_found(tmp_path: Path) -> None:
    db = tmp_path / "realtime.db"
    _make_db(db)
    assert _fetch_latest_quote(db, "SSI") is None


@pytest.mark.parametrize("symbol", ["", "HPG/../../x", "A", "HPG?x=1"])
def test_invalid_symbol(symbol: str) -> None:
    with pytest.raises(ValueError):
        _normalize_symbol(symbol)
