from __future__ import annotations

import sqlite3
import http.client
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.chart_api import (
    ChartAPIHandler,
    ChartHTTPServer,
    _fetch_latest_quote,
    _normalize_symbol,
)


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


def test_chart_endpoint_is_public_and_returns_market_bars_only(tmp_path: Path) -> None:
    @dataclass
    class Bar:
        trading_date: str
        minute: str
        open: float
        high: float
        low: float
        close: float
        volume: int

    class FakeStore:
        realtime_path = tmp_path / "unused.db"

        def query(self, **_kwargs):
            return SimpleNamespace(
                symbol="HPG",
                date_from="2026-09-18",
                date_to="2026-09-18",
                resolution=5,
                invalid_ohlc_dropped=0,
                source_counts={"SSI_STREAM": 1},
                bars=[Bar("2026-09-18", "10:00", 20, 21, 19, 20.5, 1000)],
            )

    class AccessMustNotRun:
        def check(self, **_kwargs):
            raise AssertionError("public chart must not call entitlement")

    server = ChartHTTPServer(
        ("127.0.0.1", 0),
        ChartAPIHandler,
        FakeStore(),
        AccessMustNotRun(),
        tmp_path / "state.db",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        connection.request(
            "GET",
            "/v1/chart/HPG?from=2026-09-18&to=2026-09-18&resolution=5",
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["bars"][0]["close"] == 20.5
        serialized = json.dumps(payload)
        assert "day_rvol" not in serialized
        assert "signal_state" not in serialized
        assert "reason_codes" not in serialized
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
