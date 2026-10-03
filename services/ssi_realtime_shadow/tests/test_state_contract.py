from __future__ import annotations

import sqlite3

import pytest

from app.signal_demo import build_demo_items
from app.state_contract import (
    CANONICAL_STATE_KEYS,
    PROTECTED_CCC_INTELLIGENCE_KEYS,
    PUBLIC_CONTRACT_KEYS,
    PUBLIC_STOCK_DETAIL_KEYS,
    serialize_ccc_intelligence,
    serialize_public_stock_detail,
    serialize_stock_state,
)


# Frozen API contract: independent of the legacy projector and table schema.
EXPECTED_CANONICAL_KEYS = tuple("""
contract_version symbol exchange trading_date event_at last_price ref_price
change_pct total_volume session_type day_rvol rvol15 rvol30 price5_pct price15_pct
ma10 ma200 distance_ma10_pct distance_ma200_pct ato_volume ato_avg_volume_10
ato_rvol ato_baseline_sessions_used ato_baseline_quality atc_volume
atc_avg_volume_10 atc_rvol atc_baseline_sessions_used atc_baseline_quality
atc_price_impact_pct baseline_sessions_used baseline_target_sessions
baseline_coverage_pct signal_state signal_level signal_direction reason_codes
signal_summary_vi previous_signal_state state_changed_at feed_status
quality_status metrics_trusted engine_version config_version
""".split())


def _state_row() -> dict[str, object]:
    return {
        "symbol": "HPG", "exchange": "HOSE", "trading_date": "2026-09-18",
        "event_at": "2026-09-18T10:30:00+07:00", "last_price": 100.0,
        "ref_price": 99.0, "change_pct": 1.01, "total_volume": 0,
        "session_type": "AM_CONTINUOUS", "ma10": 98.0, "ma200": None,
        "distance_ma10_pct": 2.04, "distance_ma200_pct": None,
        "feed_status": "LIVE", "quality_status": "TRUSTED",
        "day_rvol": 1.8, "signal_state": "FLOW_PRICE_CONFIRMED",
        "signal_level": 3, "signal_direction": "BULLISH",
        "reason_codes_json": '["DAY_RVOL_ELEVATED"]', "metrics_trusted": 1,
        "previous_signal_state": "WATCHING",
        "state_changed_at": "2026-09-18T10:29:00+07:00",
        "engine_version": "2.0.4-beta",
        "config_version": "cfg-20261002-context-001",
    }


def test_all_demo_records_have_identical_ordered_contract_and_versions() -> None:
    items = build_demo_items()
    assert [item["signal_state"] for item in items] == [
        "NORMAL", "WATCHING", "FLOW_APPEARING", "FLOW_PRICE_CONFIRMED",
        "MOMENTUM_MAINTAINED", "MOMENTUM_WEAKENING", "SELLING_PRESSURE",
    ]
    assert CANONICAL_STATE_KEYS == PUBLIC_CONTRACT_KEYS == EXPECTED_CANONICAL_KEYS
    for item in items:
        assert tuple(item) == EXPECTED_CANONICAL_KEYS
        assert item["contract_version"] == "ccc-state-v1"
        assert item["engine_version"] == "2.0.4-beta"
        assert item["config_version"] == "cfg-20261002-context-001"
        assert isinstance(item["reason_codes"], list)
        assert isinstance(item["metrics_trusted"], bool)
        assert "reason_codes_json" not in item


@pytest.mark.parametrize("sqlite_row", [False, True])
def test_serializers_preserve_order_values_nulls_and_projection_boundaries(sqlite_row) -> None:
    row = _state_row()
    # Exercise the supported sqlite3.Row input without any legacy schema/writer.
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        if sqlite_row:
            row = connection.execute(
                "SELECT " + ", ".join(f"? AS {name}" for name in row), tuple(row.values())
            ).fetchone()
        canonical = serialize_stock_state(row)
        public = serialize_public_stock_detail(row)
        protected = serialize_ccc_intelligence(row)

    expected_public = {
        "contract_version": "ccc-state-v1", "symbol": "HPG", "exchange": "HOSE",
        "trading_date": "2026-09-18", "event_at": "2026-09-18T10:30:00+07:00",
        "last_price": 100.0, "ref_price": 99.0, "change_pct": 1.01,
        "total_volume": 0, "session_type": "AM_CONTINUOUS", "ma10": 98.0,
        "ma200": None, "distance_ma10_pct": 2.04, "distance_ma200_pct": None,
        "feed_status": "LIVE", "quality_status": "TRUSTED",
    }
    assert public == expected_public
    assert tuple(public) == tuple(expected_public) == PUBLIC_STOCK_DETAIL_KEYS
    assert tuple(canonical) == EXPECTED_CANONICAL_KEYS
    assert tuple(protected) == PROTECTED_CCC_INTELLIGENCE_KEYS
    assert canonical["reason_codes"] == protected["reason_codes"] == ["DAY_RVOL_ELEVATED"]
    assert canonical["previous_signal_state"] == protected["previous_signal_state"] == "WATCHING"
    assert canonical["state_changed_at"] == "2026-09-18T10:29:00+07:00"
    assert canonical["metrics_trusted"] is protected["metrics_trusted"] is True
    assert canonical["total_volume"] == 0
    assert canonical["ato_volume"] is protected["ato_volume"] is None
    assert canonical["day_rvol"] == protected["day_rvol"] == 1.8
    assert all(key not in public for key in (
        "day_rvol", "signal_state", "reason_codes", "metrics_trusted",
        "engine_version", "config_version", "reason_codes_json",
    ))


def test_serializer_preserves_missing_values_without_inventing_zero() -> None:
    result = serialize_stock_state({"metrics_trusted": 0})
    assert result["ato_rvol"] is None
    assert result["total_volume"] is None
    assert result["reason_codes"] == []
    assert result["metrics_trusted"] is False
    assert tuple(result) == EXPECTED_CANONICAL_KEYS


@pytest.mark.parametrize("reasons", ["invalid", "{}", "[123]"])
def test_protected_serializers_reject_bad_reasons_but_public_projection_does_not(reasons) -> None:
    row = _state_row() | {"reason_codes_json": reasons}
    for serializer in (serialize_stock_state, serialize_ccc_intelligence):
        with pytest.raises(ValueError, match="reason_codes_json"):
            serializer(row)
    assert serialize_public_stock_detail(row)["symbol"] == "HPG"
