from __future__ import annotations

import http.client
import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.canonical_market_store import CanonicalMarketStore
from app.canonical_market_reader import CanonicalMarketReader
from app.chart_api import (
    ChartAPIHandler,
    ChartHTTPServer,
    _fetch_latest_quote,
    _normalize_symbol,
)
from app.chart_data import ChartDataStore


def _seed_quote(
    market_dir: Path,
    *,
    year: int,
    symbol: str = "HPG",
    trading_date: str | None = None,
    event_time: str | None = "10:15:30",
    last_price: float = 20050,
    total_volume: int = 35378700,
    provider_session: str | None = "CONTINUOUS",
    ref_price: float | None = 19800,
    bid_price1: float | None = 20000,
) -> None:
    with CanonicalMarketStore(market_dir) as store:
        connection = store.connection(year)
        connection.execute(
            """
            INSERT INTO latest_quotes(
                symbol,trading_date,event_time,last_price,last_price_at,total_volume,
                ref_price,open,high,low,close,bid_price1,bid_vol1,ask_price1,
                ask_vol1,change,ratio_change,exchange,provider_session,
                trading_status,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                symbol, trading_date or f"{year}-10-02", event_time, last_price,
                event_time, total_volume, ref_price, 19900, 20200, 19750,
                last_price, bid_price1, 1000 if bid_price1 is not None else None,
                20100 if bid_price1 is not None else None,
                1200 if bid_price1 is not None else None,
                last_price - ref_price if ref_price is not None else None,
                1.26 if ref_price is not None else None, "HOSE", provider_session,
                "OPEN" if provider_session is not None else None,
                f"{year}-10-02T10:15:30+07:00",
            ),
        )
        connection.commit()


def _seed_old_schema_quote(
    market_dir: Path,
    *,
    year: int,
    symbol: str = "HPG",
    trading_date: str | None = None,
    last_price: float = 19800,
    provider_session: str | None = "CONTINUOUS",
) -> None:
    connection = sqlite3.connect(market_dir / f"ccc_market_{year}.db")
    try:
        connection.execute(
            """
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
                exchange TEXT,
                provider_session TEXT,
                updated_at TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO latest_quotes(
                symbol,trading_date,event_time,last_price,total_volume,ref_price,
                open,high,low,close,exchange,provider_session,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                symbol, trading_date or f"{year}-12-31", "14:45:00", last_price,
                123456, 19700, 19750, 19900, 19600, last_price, "HOSE",
                provider_session, f"{year}-12-31T14:45:00+07:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_fetch_latest_canonical_quote_maps_all_public_fields(tmp_path: Path) -> None:
    _seed_quote(tmp_path, year=2026)
    quote = _fetch_latest_quote(tmp_path, "hpg", as_of_year=2026)
    assert quote is not None
    assert quote["symbol"] == "HPG"
    assert quote["last_price"] == 20050
    assert quote["total_volume"] == 35378700
    assert quote["trading_session"] == "CONTINUOUS"
    assert quote["source"] == "CANONICAL_MARKET"
    assert "provider_session" not in quote


def test_canonical_eod_values_and_nullable_provider_fields_are_unchanged(
    tmp_path: Path,
) -> None:
    _seed_quote(
        tmp_path, year=2026, event_time=None, last_price=20050,
        total_volume=35378700, provider_session=None, ref_price=None,
        bid_price1=None,
    )
    quote = _fetch_latest_quote(tmp_path, "HPG", as_of_year=2026)
    assert quote is not None
    assert quote["last_price"] == 20050
    assert quote["total_volume"] == 35378700
    assert quote["event_time"] is None
    assert quote["ref_price"] is None
    assert quote["bid_price1"] is None
    assert quote["trading_session"] is None


def test_previous_year_quote_is_last_known_fallback(tmp_path: Path) -> None:
    _seed_quote(
        tmp_path, year=2025, trading_date="2025-12-31", event_time="14:45:00"
    )
    quote = _fetch_latest_quote(tmp_path, "HPG", as_of_year=2026)
    assert quote is not None and quote["trading_date"] == "2025-12-31"
    assert not (tmp_path / "ccc_market_2026.db").exists()


def test_current_year_quote_returns_before_old_previous_schema_is_queried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_quote(tmp_path, year=2026, last_price=20100)
    _seed_old_schema_quote(tmp_path, year=2025)
    reader = CanonicalMarketReader(tmp_path)
    attempted_years: list[int] = []
    original_connect = reader._connect

    def tracked_connect(year: int):
        attempted_years.append(year)
        return original_connect(year)

    monkeypatch.setattr(reader, "_connect", tracked_connect)
    quote = reader.latest_quote("HPG", as_of_year=2026)

    assert quote is not None
    assert (quote["trading_date"], quote["last_price"]) == ("2026-10-02", 20100)
    assert attempted_years == [2026]


def test_old_previous_schema_projects_missing_optional_fields_as_none(
    tmp_path: Path,
) -> None:
    _seed_quote(tmp_path, year=2026, symbol="SSI")
    _seed_old_schema_quote(tmp_path, year=2025, provider_session="CLOSE")

    quote = _fetch_latest_quote(tmp_path, "HPG", as_of_year=2026)

    assert quote is not None
    assert quote["trading_date"] == "2025-12-31"
    assert quote["trading_session"] == "CLOSE"
    for field in (
        "bid_price1", "bid_vol1", "ask_price1", "ask_vol1", "change",
        "ratio_change", "trading_status",
    ):
        assert quote[field] is None


def test_missing_current_shard_falls_back_to_old_previous_schema(
    tmp_path: Path,
) -> None:
    _seed_old_schema_quote(tmp_path, year=2025)

    quote = _fetch_latest_quote(tmp_path, "HPG", as_of_year=2026)

    assert quote is not None
    assert quote["last_price"] == 19800
    assert quote["source"] == "CANONICAL_MARKET"
    assert not (tmp_path / "ccc_market_2026.db").exists()


def test_current_and_previous_year_choose_newest_quote(tmp_path: Path) -> None:
    _seed_quote(tmp_path, year=2025, trading_date="2025-12-31")
    _seed_quote(tmp_path, year=2026, trading_date="2026-01-02", last_price=20100)
    quote = _fetch_latest_quote(tmp_path, "HPG", as_of_year=2026)
    assert quote is not None
    assert (quote["trading_date"], quote["last_price"]) == ("2026-01-02", 20100)


def test_quote_does_not_scan_arbitrary_old_shard(tmp_path: Path) -> None:
    _seed_quote(tmp_path, year=2024, trading_date="2024-12-31")
    assert _fetch_latest_quote(tmp_path, "HPG", as_of_year=2026) is None


def test_quote_not_found_and_invalid_symbol(tmp_path: Path) -> None:
    _seed_quote(tmp_path, year=2026)
    assert _fetch_latest_quote(tmp_path, "SSI", as_of_year=2026) is None
    for symbol in ("", "HPG/../../x", "A", "HPG?x=1"):
        with pytest.raises(ValueError):
            _normalize_symbol(symbol)


def test_missing_quote_keeps_existing_http_404(tmp_path: Path) -> None:
    server = ChartHTTPServer(
        ("127.0.0.1", 0), ChartAPIHandler, ChartDataStore(tmp_path),
        SimpleNamespace(), tmp_path, tmp_path / "engine.db",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        connection.request("GET", "/v1/quote/HPG")
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 404
        assert payload == {"error": "QUOTE_NOT_FOUND", "symbol": "HPG"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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
        market_dir = tmp_path

        def query(self, **_kwargs):
            return SimpleNamespace(
                symbol="HPG", date_from="2026-09-18", date_to="2026-09-18",
                resolution=5, invalid_ohlc_dropped=0,
                source_counts={"SSI_REST": 1},
                bars=[Bar("2026-09-18", "10:00", 20, 21, 19, 20.5, 1000)],
            )

    class AccessMustNotRun:
        def check(self, **_kwargs):
            raise AssertionError("public chart must not call entitlement")

    server = ChartHTTPServer(
        ("127.0.0.1", 0), ChartAPIHandler, FakeStore(), AccessMustNotRun(),
        tmp_path, tmp_path / "engine.db",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        connection.request(
            "GET", "/v1/chart/HPG?from=2026-09-18&to=2026-09-18&resolution=5"
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
