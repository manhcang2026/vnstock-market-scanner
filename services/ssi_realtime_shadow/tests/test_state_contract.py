from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from app.daily_ma import MAResult
from app.market_session import VN_TZ, classify_market_session
from app.market_storage_schema import ensure_market_storage_schema
from app.price_momentum import PriceMomentum
from app.signal_demo import build_demo_items
from app.state_contract import (
    PROTECTED_CCC_INTELLIGENCE_KEYS,
    PUBLIC_CONTRACT_KEYS,
    PUBLIC_STOCK_DETAIL_KEYS,
    build_radar_projection,
    get_ccc_intelligence,
    get_current_state,
    get_public_stock_detail,
    list_current_states,
    serialize_stock_state,
)
from app.stock_state_current import LatestQuote, project_stock_state, upsert_stock_state_current


AT = datetime(2026, 9, 18, 10, 30, tzinfo=VN_TZ)


def projection(symbol: str = "FPT") -> dict[str, object]:
    return project_stock_state(
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


def test_all_demo_records_have_identical_ordered_contract_and_versions() -> None:
    items = build_demo_items()
    assert [item["signal_state"] for item in items] == [
        "NORMAL", "WATCHING", "FLOW_APPEARING", "FLOW_PRICE_CONFIRMED",
        "MOMENTUM_MAINTAINED", "MOMENTUM_WEAKENING", "SELLING_PRESSURE",
    ]
    for item in items:
        assert tuple(item) == PUBLIC_CONTRACT_KEYS
        assert item["contract_version"] == "ccc-state-v1"
        assert item["engine_version"] == "2.0.1-beta"
        assert item["config_version"] == "cfg-20260922-beta-002"
        assert isinstance(item["reason_codes"], list)
        assert isinstance(item["metrics_trusted"], bool)
        assert "reason_codes_json" not in item


def test_serializer_preserves_null_and_decodes_internal_reason_json() -> None:
    row = {key: None for key in PUBLIC_CONTRACT_KEYS}
    row.update(
        reason_codes_json='["BASELINE_INCOMPLETE"]',
        metrics_trusted=0,
    )
    result = serialize_stock_state(row)
    assert result["ato_rvol"] is None
    assert result["reason_codes"] == ["BASELINE_INCOMPLETE"]
    assert result["metrics_trusted"] is False


def test_current_state_upsert_transition_and_readers_are_deterministic() -> None:
    connection = sqlite3.connect(":memory:")
    ensure_market_storage_schema(connection, applied_at=AT)
    first = projection("FPT")
    upsert_stock_state_current(connection, first)
    initial = connection.execute(
        "SELECT previous_signal_state,state_changed_at,signal_at FROM stock_state_current"
    ).fetchone()
    assert initial == (None, None, None)

    transition_at = (AT + timedelta(minutes=1)).isoformat()
    changed = dict(first)
    changed.update(
        signal_state="WATCHING", signal_level=1, signal_direction="NEUTRAL",
        signal_summary_vi="Khối lượng đang tăng, tín hiệu giá chưa xác nhận.",
        reason_codes_json=json.dumps(["DAY_RVOL_ELEVATED"]),
        event_at=transition_at, updated_at=transition_at,
    )
    upsert_stock_state_current(connection, changed)
    transitioned = connection.execute(
        "SELECT previous_signal_state,state_changed_at,signal_at FROM stock_state_current"
    ).fetchone()
    assert transitioned == ("NORMAL", transition_at, transition_at)

    same = dict(changed)
    same["event_at"] = (AT + timedelta(minutes=2)).isoformat()
    same["updated_at"] = same["event_at"]
    upsert_stock_state_current(connection, same)
    assert connection.execute(
        "SELECT previous_signal_state,state_changed_at,signal_at FROM stock_state_current"
    ).fetchone() == transitioned
    assert connection.execute("SELECT COUNT(*) FROM stock_state_current").fetchone()[0] == 1

    one = get_current_state(connection, "fpt")
    assert one is not None and one["symbol"] == "FPT"
    assert one["reason_codes"] == ["DAY_RVOL_ELEVATED"]
    assert list_current_states(connection) == [one]
    connection.close()


def test_public_and_protected_stock_detail_projections_are_explicitly_split() -> None:
    connection = sqlite3.connect(":memory:")
    ensure_market_storage_schema(connection, applied_at=AT)
    row = projection("HPG")
    row.update(
        ma10=98.0,
        ma200=91.0,
        ma10_sessions=10,
        ma200_sessions=200,
        distance_ma10_pct=2.04,
        distance_ma200_pct=9.89,
        day_rvol=1.8,
        signal_state="FLOW_PRICE_CONFIRMED",
        signal_level=3,
        signal_direction="BULLISH",
        reason_codes_json=json.dumps(["DAY_RVOL_ELEVATED"]),
    )
    upsert_stock_state_current(connection, row)

    public = get_public_stock_detail(connection, "HPG")
    protected = get_ccc_intelligence(connection, "HPG")

    assert public is not None and tuple(public) == PUBLIC_STOCK_DETAIL_KEYS
    assert public["ma10"] == 98.0
    assert "day_rvol" not in public
    assert "signal_state" not in public
    assert "reason_codes" not in public
    assert "engine_version" not in public
    assert protected is not None
    assert tuple(protected) == PROTECTED_CCC_INTELLIGENCE_KEYS
    assert protected["day_rvol"] == 1.8
    assert protected["reason_codes"] == ["DAY_RVOL_ELEVATED"]
    connection.close()


def test_radar_never_returns_unauthorized_identities() -> None:
    connection = sqlite3.connect(":memory:")
    ensure_market_storage_schema(connection, applied_at=AT)
    for symbol, state, level in (
        ("HPG", "WATCHING", 1),
        ("FPT", "WATCHING", 1),
        ("SSI", "NORMAL", 0),
    ):
        row = projection(symbol)
        row.update(
            signal_state=state,
            signal_level=level,
            signal_direction="NEUTRAL",
        )
        upsert_stock_state_current(connection, row)

    anonymous = build_radar_projection(connection)
    watching = next(group for group in anonymous["groups"] if group["state"] == "WATCHING")
    assert watching == {
        "state": "WATCHING", "total": 2, "items": [], "hidden": 2
    }
    assert all(group["state"] != "NORMAL" for group in anonymous["groups"])

    ordinary = build_radar_projection(connection, visible_symbols={"HPG"})
    watching = next(group for group in ordinary["groups"] if group["state"] == "WATCHING")
    assert [item["symbol"] for item in watching["items"]] == ["HPG"]
    assert watching["hidden"] == 1

    full_market = build_radar_projection(connection, full_market=True)
    watching = next(group for group in full_market["groups"] if group["state"] == "WATCHING")
    assert {item["symbol"] for item in watching["items"]} == {"HPG", "FPT"}
    assert watching["hidden"] == 0
    connection.close()
