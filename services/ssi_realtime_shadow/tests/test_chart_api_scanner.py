from __future__ import annotations

import http.client
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.access_control import (
    AuthenticationRequired,
    EntitlementServiceUnavailable,
    TechnicalAccessDecision,
    TechnicalAccessScope,
)
from app.canonical_engine_store import CanonicalEngineStore, CurrentState, SignalState
from app.canonical_market_store import CanonicalMarketStore
from app.canonical_state_reader import CanonicalStateReader
from app.chart_api import ChartAPIHandler, ChartHTTPServer
from app.market_session import VN_TZ
from app.state_contract import (
    PROTECTED_CCC_INTELLIGENCE_KEYS,
    PUBLIC_STOCK_DETAIL_KEYS,
    SCANNER_CCC_KEYS,
    SCANNER_PUBLIC_KEYS,
)


AT = datetime(2026, 9, 18, 10, 30, tzinfo=VN_TZ)
DAY = AT.date().isoformat()


def _current(symbol: str) -> CurrentState:
    return CurrentState(
        symbol=symbol,
        exchange="HOSE",
        trading_date=DAY,
        minute="10:29",
        last_price=100,
        cumulative_volume=1_000,
        day_rvol=1.25,
        rvol15=1.5,
        rvol30=2.5,
        price5_pct=0.5,
        price15_pct=1.0,
        ma10=98,
        ma200=90,
        distance_ma10_pct=2.04,
        distance_ma200_pct=11.11,
        baseline_sessions_used=10,
        day_rvol_sessions_used=10,
        rvol15_sessions_used=9,
        rvol30_sessions_used=8,
        quality_status="OK",
        reason_codes_json=json.dumps([f"CURRENT_{symbol}"]),
        updated_at=AT.isoformat(),
    )


def _signal(symbol: str, state: str, level: int) -> SignalState:
    return SignalState(
        symbol=symbol,
        exchange="HOSE",
        trading_date=DAY,
        minute="10:29",
        session_type="AM_CONTINUOUS",
        signal_state=state,
        signal_level=level,
        signal_direction="BULLISH" if level >= 2 else "NEUTRAL",
        reason_codes_json=json.dumps([f"REASON_{symbol}"]),
        signal_summary_vi=f"PROTECTED_{symbol}",
        metrics_trusted=1,
        baseline_sessions_used=10,
        engine_version="canonical-engine",
        config_version="canonical-config",
        updated_at=AT.isoformat(),
    )


def _make_canonical_dbs(market_dir: Path, engine_path: Path) -> None:
    with CanonicalEngineStore(engine_path) as engine:
        for symbol in ("AAA", "BBB", "DAN"):
            engine.upsert_current(_current(symbol))
        engine.upsert_signal(_signal("AAA", "FLOW_PRICE_CONFIRMED", 3))
        engine.upsert_signal(_signal("BBB", "WATCHING", 1))
    with CanonicalMarketStore(market_dir) as market:
        connection = market.connection(2026)
        for symbol, price, ratio in (("AAA", 101.0, 1.0), ("BBB", 99.0, -1.0)):
            connection.execute(
                """INSERT INTO latest_quotes(
                       symbol,trading_date,event_time,last_price,total_volume,
                       ref_price,change,ratio_change,exchange,provider_session,
                       trading_status,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    symbol, DAY, "10:30:00", price, 1_234, 100.0,
                    price - 100.0, ratio, "HOSE", "LO", "NORMAL", AT.isoformat(),
                ),
            )
        connection.commit()


def _insert_auction(
    market_dir: Path,
    *,
    symbol: str = "AAA",
    auction_type: str,
    provider_session: str,
    source: str,
    quality_status: str,
    auction_volume: int,
) -> None:
    path = market_dir / "ccc_market_2026.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """INSERT OR REPLACE INTO auction_sessions(
                   symbol,trading_date,exchange,auction_type,provider_session,
                   auction_volume,source,quality_status,finalized,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                symbol,
                DAY,
                "HOSE",
                auction_type,
                provider_session,
                auction_volume,
                source,
                quality_status,
                1,
                AT.isoformat(),
            ),
        )


class AccessProbe:
    def __init__(
        self, *, allowed=(), full_market=False, error=None, technical_allowed=None
    ):
        self.allowed = frozenset(allowed)
        self.full_market = full_market
        self.error = error
        self.technical_allowed = technical_allowed
        self.scope_calls = 0
        self.check_calls = 0

    def scope(self, *, token):
        self.scope_calls += 1
        assert token == "session-token"
        if self.error:
            raise self.error("ENTITLEMENT_UNAVAILABLE")
        return TechnicalAccessScope(
            effective_full_market_access=self.full_market,
            vip_day_active=False,
            allowed_symbols=self.allowed,
        )

    def check(self, *, token, symbol):
        self.check_calls += 1
        if self.technical_allowed is None:
            raise AssertionError("scanner must not make per-symbol entitlement checks")
        return TechnicalAccessDecision(
            symbol=symbol,
            technical_allowed=bool(self.technical_allowed),
            reason="TEST",
        )


def _traced_reader(
    market_dir: Path, engine_path: Path
) -> tuple[CanonicalStateReader, list[str]]:
    reader = CanonicalStateReader(market_dir=market_dir, engine_path=engine_path)
    statements: list[str] = []
    original = reader._connect_readonly

    def traced(path: Path) -> sqlite3.Connection:
        connection = original(path)
        connection.set_trace_callback(statements.append)
        return connection

    reader._connect_readonly = traced  # type: ignore[method-assign]
    return reader, statements


def _selects(statements: list[str]) -> list[str]:
    return [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]


def _assert_public_only_selects(statements: list[str]) -> None:
    selects = _selects(statements)
    combined = "\n".join(selects).lower()
    assert len(selects) == 2
    assert "from current_state" in combined
    assert "from latest_quotes" in combined
    assert "signal_state_current" not in combined
    assert "auction_sessions" not in combined
    for protected in (
        "day_rvol", "rvol15", "rvol30", "price5_pct", "price15_pct",
        "reason_codes_json", "signal_state", "auction_volume",
    ):
        assert protected not in combined


@contextmanager
def _server(
    market_dir: Path,
    engine_path: Path,
    access: AccessProbe,
    state_reader: CanonicalStateReader | None = None,
):
    server = ChartHTTPServer(
        ("127.0.0.1", 0), ChartAPIHandler,
        SimpleNamespace(realtime_path=market_dir / "unused.db"),
        access,
        market_dir,
        engine_path,
        state_reader,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(server, path="/v1/scanner", authorization=None):
    connection = http.client.HTTPConnection(*server.server_address, timeout=5)
    headers = {"Authorization": authorization} if authorization is not None else {}
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_anonymous_scanner_has_only_public_fields_and_null_ccc(tmp_path: Path) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    access = AccessProbe()
    reader, statements = _traced_reader(market_dir, engine_path)
    with _server(market_dir, engine_path, access, reader) as server:
        status, payload = _get(server)

    assert status == 200
    assert payload["contract_version"] == "ccc-scanner-v1"
    assert payload["technical_scope"] == "ANONYMOUS"
    assert payload["count"] == 3
    assert [row["symbol"] for row in payload["rows"]] == ["AAA", "BBB", "DAN"]
    assert all(tuple(row) == SCANNER_PUBLIC_KEYS + ("ccc",) for row in payload["rows"])
    assert all(row["ccc"] is None for row in payload["rows"])
    assert payload["rows"][0]["last_price"] == 101.0
    assert payload["rows"][0]["change_pct"] == 1.0
    assert payload["rows"][0]["total_volume"] == 1_234
    assert payload["rows"][2]["last_price"] is None
    assert payload["rows"][2]["total_volume"] is None
    serialized = json.dumps(payload)
    assert "PROTECTED_AAA" not in serialized
    assert "PROTECTED_BBB" not in serialized
    assert all(key not in payload["rows"][0] for key in SCANNER_CCC_KEYS)
    assert access.scope_calls == 0 and access.check_calls == 0
    _assert_public_only_selects(statements)


def test_watchlist_scope_enriches_only_allowed_symbol_once(tmp_path: Path) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    with sqlite3.connect(engine_path) as connection:
        connection.execute(
            "UPDATE signal_state_current SET reason_codes_json = ? WHERE symbol = ?",
            (json.dumps([123]), "BBB"),
        )
    access = AccessProbe(allowed={"AAA"})
    reader, statements = _traced_reader(market_dir, engine_path)
    with _server(market_dir, engine_path, access, reader) as server:
        status, payload = _get(server, authorization="Bearer session-token")

    assert status == 200
    assert payload["technical_scope"] == "WATCHLIST"
    first, second, dan = payload["rows"]
    assert first["ccc"] is not None
    assert tuple(first["ccc"]) == SCANNER_CCC_KEYS
    assert first["ccc"]["reason_codes"] == ["REASON_AAA"]
    assert type(first["ccc"]["metrics_trusted"]) is bool
    assert first["ccc"]["metrics_trusted"] is True
    assert second["ccc"] is None
    assert dan["ccc"] is None
    assert "PROTECTED_BBB" not in json.dumps(payload)
    assert "REASON_BBB" not in json.dumps(payload)
    assert access.scope_calls == 1 and access.check_calls == 0
    selects = _selects(statements)
    assert len(selects) == 5
    protected_selects = [
        sql for sql in selects
        if "signal_state_current" in sql or "auction_sessions" in sql
        or ("from current_state" in sql.lower() and "day_rvol" in sql.lower())
    ]
    assert len(protected_selects) == 3
    assert all("'AAA'" in sql and "'BBB'" not in sql for sql in protected_selects)


def test_full_market_enriches_all_rows(tmp_path: Path) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    access = AccessProbe(full_market=True)
    reader, statements = _traced_reader(market_dir, engine_path)
    with _server(market_dir, engine_path, access, reader) as server:
        status, payload = _get(server, authorization="Bearer session-token")
    assert status == 200
    assert payload["technical_scope"] == "FULL_MARKET"
    assert [row["ccc"]["signal_summary_vi"] for row in payload["rows"]] == [
        "PROTECTED_AAA", "PROTECTED_BBB", None,
    ]
    assert payload["rows"][2]["ccc"]["metrics_trusted"] is False
    assert access.scope_calls == 1 and access.check_calls == 0
    assert len(_selects(statements)) == 5


@pytest.mark.parametrize("error", [AuthenticationRequired, EntitlementServiceUnavailable])
def test_invalid_or_unavailable_scope_keeps_public_rows(tmp_path: Path, error) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    access = AccessProbe(error=error)
    reader, statements = _traced_reader(market_dir, engine_path)
    with _server(market_dir, engine_path, access, reader) as server:
        status, payload = _get(server, authorization="Bearer session-token")
    assert status == 200
    assert payload["technical_scope"] == "UNAVAILABLE"
    assert payload["count"] == 3
    assert all(row["ccc"] is None for row in payload["rows"])
    assert "PROTECTED_AAA" not in json.dumps(payload)
    assert access.scope_calls == 1 and access.check_calls == 0
    _assert_public_only_selects(statements)


def test_malformed_authorization_is_public_unavailable(tmp_path: Path) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    access = AccessProbe()
    reader, statements = _traced_reader(market_dir, engine_path)
    with _server(market_dir, engine_path, access, reader) as server:
        status, payload = _get(server, authorization="Basic bad-token")
    assert status == 200
    assert payload["technical_scope"] == "UNAVAILABLE"
    assert all(row["ccc"] is None for row in payload["rows"])
    assert access.scope_calls == 0
    _assert_public_only_selects(statements)


def test_scanner_uses_fixed_set_based_queries_without_symbol_n_plus_one(
    tmp_path: Path,
) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    reader, statements = _traced_reader(market_dir, engine_path)
    payload = reader.scanner_projection(full_market=True)

    selects = _selects(statements)
    assert payload["count"] == 3
    assert len([sql for sql in selects if "FROM current_state" in sql]) == 2
    assert len([sql for sql in selects if "FROM signal_state_current" in sql]) == 1
    assert len([sql for sql in selects if "FROM latest_quotes" in sql]) == 1
    assert len([sql for sql in selects if "FROM auction_sessions" in sql]) == 1
    assert len(selects) == 5


def test_existing_health_and_public_detail_routes_remain_available(tmp_path: Path) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    access = AccessProbe()
    reader, statements = _traced_reader(market_dir, engine_path)
    with _server(market_dir, engine_path, access, reader) as server:
        health_status, health = _get(server, "/health")
        detail_status, detail = _get(server, "/v1/stock-detail/AAA")
    assert health_status == 200 and health["service"] == "ccc-chart-api"
    assert detail_status == 200 and detail["symbol"] == "AAA"
    assert detail["last_price"] == 101.0
    assert detail["ref_price"] == 100.0
    assert detail["change_pct"] == 1.0
    assert detail["event_at"] == "2026-09-18T10:30:00+07:00"
    assert tuple(detail) == PUBLIC_STOCK_DETAIL_KEYS
    assert "day_rvol" not in detail
    assert "signal_state" not in detail
    assert access.scope_calls == 0 and access.check_calls == 0
    _assert_public_only_selects(statements)


def test_public_detail_distinguishes_bad_url_from_reader_value_error(
    tmp_path: Path,
) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    reader = CanonicalStateReader(market_dir=market_dir, engine_path=engine_path)

    def broken_reader(symbol: str) -> dict | None:
        raise ValueError(f"corrupt canonical row for {symbol}")

    reader.public_stock_detail = broken_reader  # type: ignore[method-assign]
    with _server(market_dir, engine_path, AccessProbe(), reader) as server:
        bad_status, bad = _get(server, "/v1/stock-detail/A")
        failed_status, failed = _get(server, "/v1/stock-detail/AAA")

    assert bad_status == 400 and bad["error"] == "INVALID_REQUEST"
    assert failed_status == 503 and failed["error"] == "STATE_UNAVAILABLE"


def test_ccc_route_keeps_auth_and_uses_canonical_signal_fields(tmp_path: Path) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    access = AccessProbe(technical_allowed=True)
    with _server(market_dir, engine_path, access) as server:
        denied_status, denied = _get(server, "/v1/ccc/AAA")
        status, payload = _get(
            server, "/v1/ccc/AAA", authorization="Bearer session-token"
        )

    assert denied_status == 401 and denied["error"] == "AUTH_REQUIRED"
    assert status == 200
    assert tuple(payload) == PROTECTED_CCC_INTELLIGENCE_KEYS
    assert payload["day_rvol"] == 1.25
    assert payload["reason_codes"] == ["REASON_AAA"]
    assert payload["signal_state"] == "FLOW_PRICE_CONFIRMED"
    assert payload["signal_summary_vi"] == "PROTECTED_AAA"
    assert payload["engine_version"] == "canonical-engine"
    assert payload["config_version"] == "canonical-config"
    assert payload["metrics_trusted"] is True
    assert access.check_calls == 1


def test_dan_like_missing_quote_and_signal_is_preserved_honestly(tmp_path: Path) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    access = AccessProbe(technical_allowed=True)
    with _server(market_dir, engine_path, access) as server:
        detail_status, detail = _get(server, "/v1/stock-detail/DAN")
        ccc_status, ccc = _get(
            server, "/v1/ccc/DAN", authorization="Bearer session-token"
        )

    assert detail_status == 200 and ccc_status == 200
    assert detail["symbol"] == "DAN"
    assert detail["last_price"] is None
    assert detail["total_volume"] is None
    assert detail["event_at"] is None
    assert ccc["day_rvol"] == 1.25
    assert ccc["signal_state"] is None
    assert ccc["engine_version"] is None
    assert ccc["metrics_trusted"] is False
    assert ccc["reason_codes"] == ["CURRENT_DAN"]


def test_finalized_partial_ato_zero_remains_unavailable(tmp_path: Path) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    _insert_auction(
        market_dir,
        auction_type="ATO",
        provider_session="ATO",
        source="SSI_STREAM",
        quality_status="PARTIAL",
        auction_volume=0,
    )
    reader = CanonicalStateReader(market_dir=market_dir, engine_path=engine_path)

    ccc = reader.ccc_intelligence("AAA")
    scanner = reader.scanner_projection(full_market=True)

    assert ccc is not None and ccc["ato_volume"] is None
    aaa = next(row for row in scanner["rows"] if row["symbol"] == "AAA")
    assert aaa["ccc"]["ato_volume"] is None


@pytest.mark.parametrize(
    "quality_status",
    ["DEGRADED", "MISSING_PRICE", "LATE_CORRECTION", "VOLUME_REGRESSION"],
)
def test_non_trusted_atc_quality_is_not_exposed(
    tmp_path: Path, quality_status: str
) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    _insert_auction(
        market_dir,
        auction_type="ATC",
        provider_session="ATC",
        source="SSI_STREAM",
        quality_status=quality_status,
        auction_volume=777,
    )
    reader = CanonicalStateReader(market_dir=market_dir, engine_path=engine_path)

    ccc = reader.ccc_intelligence("AAA")

    assert ccc is not None and ccc["atc_volume"] is None


def test_trusted_matching_ssi_stream_auction_volumes_are_exposed(
    tmp_path: Path,
) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    _insert_auction(
        market_dir,
        auction_type="ATO",
        provider_session="ATO",
        source="SSI_STREAM",
        quality_status="TRUSTED",
        auction_volume=123,
    )
    _insert_auction(
        market_dir,
        auction_type="ATC",
        provider_session="ATC",
        source="SSI_STREAM",
        quality_status="TRUSTED",
        auction_volume=456,
    )
    reader = CanonicalStateReader(market_dir=market_dir, engine_path=engine_path)

    ccc = reader.ccc_intelligence("AAA")

    assert ccc is not None
    assert ccc["ato_volume"] == 123
    assert ccc["atc_volume"] == 456
    assert ccc["ato_avg_volume_10"] is None
    assert ccc["ato_rvol"] is None
    assert ccc["atc_avg_volume_10"] is None
    assert ccc["atc_rvol"] is None
    assert ccc["atc_price_impact_pct"] is None


@pytest.mark.parametrize(
    ("provider_session", "source"),
    [("ATC", "SSI_STREAM"), ("ATO", "REST_IMPORT")],
)
def test_wrong_auction_identity_or_source_is_not_exposed(
    tmp_path: Path, provider_session: str, source: str
) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    _insert_auction(
        market_dir,
        auction_type="ATO",
        provider_session=provider_session,
        source=source,
        quality_status="TRUSTED",
        auction_volume=999,
    )
    reader = CanonicalStateReader(market_dir=market_dir, engine_path=engine_path)

    ccc = reader.ccc_intelligence("AAA")

    assert ccc is not None and ccc["ato_volume"] is None


def test_radar_uses_canonical_signals_and_hides_unauthorized_identities(
    tmp_path: Path,
) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    anonymous_access = AccessProbe()
    with _server(market_dir, engine_path, anonymous_access) as server:
        status, anonymous = _get(server, "/v1/radar")
    assert status == 200 and anonymous["identity_scope"] == "ANONYMOUS"
    watching = next(
        group for group in anonymous["groups"] if group["state"] == "WATCHING"
    )
    confirmed = next(
        group
        for group in anonymous["groups"]
        if group["state"] == "FLOW_PRICE_CONFIRMED"
    )
    assert watching["total"] == 1 and watching["items"] == []
    assert confirmed["total"] == 1 and confirmed["hidden"] == 1

    watchlist_access = AccessProbe(allowed={"AAA"})
    with _server(market_dir, engine_path, watchlist_access) as server:
        _, watchlist = _get(
            server, "/v1/radar", authorization="Bearer session-token"
        )
    confirmed = next(
        group
        for group in watchlist["groups"]
        if group["state"] == "FLOW_PRICE_CONFIRMED"
    )
    assert watchlist["identity_scope"] == "WATCHLIST"
    assert [item["symbol"] for item in confirmed["items"]] == ["AAA"]
    assert watchlist_access.scope_calls == 1

    full_access = AccessProbe(full_market=True)
    with _server(market_dir, engine_path, full_access) as server:
        _, full = _get(server, "/v1/radar", authorization="Bearer session-token")
    watching = next(
        group for group in full["groups"] if group["state"] == "WATCHING"
    )
    confirmed = next(
        group
        for group in full["groups"]
        if group["state"] == "FLOW_PRICE_CONFIRMED"
    )
    assert full["identity_scope"] == "FULL_MARKET"
    assert [item["symbol"] for item in watching["items"]] == ["BBB"]
    assert [item["symbol"] for item in confirmed["items"]] == ["AAA"]


def test_state_routes_ignore_conflicting_legacy_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    legacy_path = tmp_path / "ccc_market_v2.db"
    with sqlite3.connect(legacy_path) as legacy:
        legacy.execute(
            "CREATE TABLE stock_state_current(symbol TEXT PRIMARY KEY,last_price REAL)"
        )
        legacy.execute(
            "INSERT INTO stock_state_current VALUES('AAA',999999)"
        )
    monkeypatch.setenv("MARKET_V2_DATABASE_PATH", str(legacy_path))

    access = AccessProbe(full_market=True, technical_allowed=True)
    reader, statements = _traced_reader(market_dir, engine_path)
    with _server(market_dir, engine_path, access, reader) as server:
        detail_status, detail = _get(server, "/v1/stock-detail/AAA")
        scanner_status, scanner = _get(server, "/v1/scanner")
        ccc_status, ccc = _get(
            server, "/v1/ccc/AAA", authorization="Bearer session-token"
        )
        radar_status, radar = _get(
            server, "/v1/radar", authorization="Bearer session-token"
        )

    assert (detail_status, ccc_status, radar_status, scanner_status) == (200, 200, 200, 200)
    assert detail["last_price"] == 101.0
    assert ccc["signal_state"] == "FLOW_PRICE_CONFIRMED"
    assert any(
        item["symbol"] == "AAA"
        for group in radar["groups"]
        for item in group["items"]
    )
    assert scanner["rows"][0]["last_price"] == 101.0
    assert statements
    assert all("stock_state_current" not in sql.lower() for sql in statements)


def test_latest_engine_snapshot_date_selects_market_shard_not_wall_clock(
    tmp_path: Path,
) -> None:
    market_dir = tmp_path / "market"
    engine_path = tmp_path / "engine.db"
    _make_canonical_dbs(market_dir, engine_path)
    reader = CanonicalStateReader(market_dir=market_dir, engine_path=engine_path)

    payload = reader.public_stock_detail("AAA")

    assert payload is not None
    assert payload["trading_date"] == DAY
    assert payload["last_price"] == 101.0


def test_missing_canonical_engine_fails_without_legacy_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_path = tmp_path / "ccc_market_v2.db"
    with sqlite3.connect(legacy_path) as legacy:
        legacy.execute(
            "CREATE TABLE stock_state_current(symbol TEXT PRIMARY KEY,last_price REAL)"
        )
        legacy.execute("INSERT INTO stock_state_current VALUES('AAA',999999)")
    monkeypatch.setenv("MARKET_V2_DATABASE_PATH", str(legacy_path))
    market_dir = tmp_path / "market"

    with _server(market_dir, tmp_path / "missing-engine.db", AccessProbe()) as server:
        status, payload = _get(server, "/v1/stock-detail/AAA")

    assert status == 503
    assert payload["error"] == "STATE_UNAVAILABLE"
