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
    TechnicalAccessScope,
)
from app.chart_api import ChartAPIHandler, ChartHTTPServer
from app.daily_ma import MAResult
from app.market_session import VN_TZ, classify_market_session
from app.market_storage_schema import ensure_market_storage_schema
from app.price_momentum import PriceMomentum
from app.state_contract import SCANNER_CCC_KEYS, SCANNER_PUBLIC_KEYS, build_scanner_projection
from app.stock_state_current import LatestQuote, project_stock_state, upsert_stock_state_current


AT = datetime(2026, 9, 18, 10, 30, tzinfo=VN_TZ)


def _make_state_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    ensure_market_storage_schema(connection, applied_at=AT)
    for symbol in ("BBB", "AAA"):
        row = project_stock_state(
            quote=LatestQuote(
                symbol=symbol, exchange="HOSE", trading_date="2026-09-18",
                event_at=AT, updated_at=AT.isoformat(), last_price=100,
            ),
            session=classify_market_session("HOSE", AT),
            volume=None,
            moving_averages=MAResult(
                symbol=symbol, as_of_date="2026-09-18", ma10=None, ma200=None,
                ma10_sessions=0, ma200_sessions=0, latest_completed_session=None,
                ma10_reason="INSUFFICIENT_SESSIONS:0/10",
                ma200_reason="INSUFFICIENT_SESSIONS:0/200",
            ),
            price_momentum=PriceMomentum(None, None),
        )
        row.update(
            day_rvol=1.25, rvol30=2.5,
            reason_codes_json=json.dumps([f"REASON_{symbol}"]),
            signal_summary_vi=f"PROTECTED_{symbol}",
            metrics_trusted=1,
        )
        upsert_stock_state_current(connection, row)
    connection.commit()
    connection.close()


class AccessProbe:
    def __init__(self, *, allowed=(), full_market=False, error=None):
        self.allowed = frozenset(allowed)
        self.full_market = full_market
        self.error = error
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

    def check(self, **_kwargs):
        self.check_calls += 1
        raise AssertionError("scanner must not make per-symbol entitlement checks")


@contextmanager
def _server(state_path: Path, access: AccessProbe):
    server = ChartHTTPServer(
        ("127.0.0.1", 0), ChartAPIHandler,
        SimpleNamespace(realtime_path=state_path), access, state_path,
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
    state_path = tmp_path / "state.db"
    _make_state_db(state_path)
    access = AccessProbe()
    with _server(state_path, access) as server:
        status, payload = _get(server)

    assert status == 200
    assert payload["contract_version"] == "ccc-scanner-v1"
    assert payload["technical_scope"] == "ANONYMOUS"
    assert payload["count"] == 2
    assert [row["symbol"] for row in payload["rows"]] == ["AAA", "BBB"]
    assert all(tuple(row) == SCANNER_PUBLIC_KEYS + ("ccc",) for row in payload["rows"])
    assert all(row["ccc"] is None for row in payload["rows"])
    assert all(row[key] is None for row in payload["rows"] for key in (
        "ref_price", "change_pct", "total_volume", "ma10", "ma200",
        "distance_ma10_pct", "distance_ma200_pct",
    ))
    serialized = json.dumps(payload)
    assert "PROTECTED_AAA" not in serialized
    assert "PROTECTED_BBB" not in serialized
    assert all(key not in payload["rows"][0] for key in SCANNER_CCC_KEYS)
    assert access.scope_calls == 0 and access.check_calls == 0


def test_watchlist_scope_enriches_only_allowed_symbol_once(tmp_path: Path) -> None:
    state_path = tmp_path / "state.db"
    _make_state_db(state_path)
    with sqlite3.connect(state_path) as connection:
        connection.execute(
            "UPDATE stock_state_current SET reason_codes_json = ? WHERE symbol = ?",
            (json.dumps([123]), "BBB"),
        )
    access = AccessProbe(allowed={"AAA"})
    with _server(state_path, access) as server:
        status, payload = _get(server, authorization="Bearer session-token")

    assert status == 200
    assert payload["technical_scope"] == "WATCHLIST"
    first, second = payload["rows"]
    assert first["ccc"] is not None
    assert tuple(first["ccc"]) == SCANNER_CCC_KEYS
    assert first["ccc"]["reason_codes"] == ["REASON_AAA"]
    assert type(first["ccc"]["metrics_trusted"]) is bool
    assert first["ccc"]["metrics_trusted"] is True
    assert second["ccc"] is None
    assert "PROTECTED_BBB" not in json.dumps(payload)
    assert "REASON_BBB" not in json.dumps(payload)
    assert access.scope_calls == 1 and access.check_calls == 0


def test_full_market_enriches_all_rows(tmp_path: Path) -> None:
    state_path = tmp_path / "state.db"
    _make_state_db(state_path)
    access = AccessProbe(full_market=True)
    with _server(state_path, access) as server:
        status, payload = _get(server, authorization="Bearer session-token")
    assert status == 200
    assert payload["technical_scope"] == "FULL_MARKET"
    assert [row["ccc"]["signal_summary_vi"] for row in payload["rows"]] == [
        "PROTECTED_AAA", "PROTECTED_BBB",
    ]
    assert access.scope_calls == 1 and access.check_calls == 0


@pytest.mark.parametrize("error", [AuthenticationRequired, EntitlementServiceUnavailable])
def test_invalid_or_unavailable_scope_keeps_public_rows(tmp_path: Path, error) -> None:
    state_path = tmp_path / "state.db"
    _make_state_db(state_path)
    access = AccessProbe(error=error)
    with _server(state_path, access) as server:
        status, payload = _get(server, authorization="Bearer session-token")
    assert status == 200
    assert payload["technical_scope"] == "UNAVAILABLE"
    assert payload["count"] == 2
    assert all(row["ccc"] is None for row in payload["rows"])
    assert "PROTECTED_AAA" not in json.dumps(payload)
    assert access.scope_calls == 1 and access.check_calls == 0


def test_malformed_authorization_is_public_unavailable(tmp_path: Path) -> None:
    state_path = tmp_path / "state.db"
    _make_state_db(state_path)
    access = AccessProbe()
    with _server(state_path, access) as server:
        status, payload = _get(server, authorization="Basic bad-token")
    assert status == 200
    assert payload["technical_scope"] == "UNAVAILABLE"
    assert all(row["ccc"] is None for row in payload["rows"])
    assert access.scope_calls == 0


def test_projection_uses_one_current_state_select(tmp_path: Path) -> None:
    state_path = tmp_path / "state.db"
    _make_state_db(state_path)
    connection = sqlite3.connect(state_path)
    statements = []
    connection.set_trace_callback(statements.append)
    try:
        anonymous = build_scanner_projection(connection)
        anonymous_queries = [sql for sql in statements if "FROM stock_state_current" in sql]
        statements.clear()
        payload = build_scanner_projection(connection, visible_symbols={"AAA"})
    finally:
        connection.close()
    assert anonymous["count"] == 2
    assert len(anonymous_queries) == 1
    assert "day_rvol" not in anonymous_queries[0]
    assert payload["count"] == 2
    assert len([sql for sql in statements if "FROM stock_state_current" in sql]) == 1


def test_existing_health_and_public_detail_routes_remain_available(tmp_path: Path) -> None:
    state_path = tmp_path / "state.db"
    _make_state_db(state_path)
    access = AccessProbe()
    with _server(state_path, access) as server:
        health_status, health = _get(server, "/health")
        detail_status, detail = _get(server, "/v1/stock-detail/AAA")
    assert health_status == 200 and health["service"] == "ccc-chart-api"
    assert detail_status == 200 and detail["symbol"] == "AAA"
    assert "day_rvol" not in detail
    assert access.scope_calls == 0 and access.check_calls == 0
