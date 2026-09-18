from __future__ import annotations

from dataclasses import replace

import pytest

from app.signal_config import load_signal_config
from app.signal_engine import TechnicalState, classify_signal


CONFIG = load_signal_config()


def state(**changes: object) -> TechnicalState:
    base = TechnicalState(
        session_type="AM_CONTINUOUS",
        last_price=101,
        day_rvol=1.0,
        rvol15=1.0,
        rvol30=1.0,
        price5_pct=0.0,
        price15_pct=0.0,
        ma10=100,
        ma200=95,
        baseline_sessions_used=10,
        metrics_trusted=True,
    )
    return replace(base, **changes)


@pytest.mark.parametrize(
    ("expected", "previous", "changes"),
    (
        ("NORMAL", None, {}),
        ("WATCHING", None, {"rvol15": 1.50}),
        ("WATCHING", None, {"price15_pct": 0.90}),
        ("WATCHING", None, {"rvol30": 2.0, "price15_pct": 0.30}),
        ("FLOW_APPEARING", None, {"day_rvol": 1.2, "rvol15": 1.8, "rvol30": 1.8, "price5_pct": 0.5, "price15_pct": 0.8}),
        ("FLOW_PRICE_CONFIRMED", None, {"day_rvol": 1.4, "rvol30": 2.0, "price15_pct": 1.2}),
        ("MOMENTUM_MAINTAINED", "FLOW_APPEARING", {"rvol30": 1.4, "price15_pct": -0.2}),
        ("MOMENTUM_WEAKENING", "FLOW_PRICE_CONFIRMED", {"rvol30": 1.2, "price5_pct": -0.5, "price15_pct": -0.8}),
        ("SELLING_PRESSURE", None, {"day_rvol": 1.2, "rvol15": 1.8, "rvol30": 1.8, "price5_pct": -0.8, "price15_pct": -1.2}),
        ("SELLING_PRESSURE", None, {"rvol15": 2.5, "price5_pct": -1.5}),
    ),
)
def test_continuous_classification(expected: str, previous: str | None, changes: dict[str, object]) -> None:
    assert classify_signal(state(**changes), previous, CONFIG).signal_state == expected


def test_priority_direction_level_summary_and_reason_order_are_deterministic() -> None:
    technical = state(
        day_rvol=1.4, rvol15=2.5, rvol30=2.2,
        price5_pct=-1.5, price15_pct=-1.3,
    )
    first = classify_signal(technical, "FLOW_PRICE_CONFIRMED", CONFIG)
    second = classify_signal(technical, "FLOW_PRICE_CONFIRMED", CONFIG)
    assert first == second
    assert first.signal_state == "SELLING_PRESSURE"
    assert (first.signal_level, first.signal_direction) == (3, "BEARISH")
    assert first.signal_summary_vi == CONFIG.states["SELLING_PRESSURE"].summary_vi
    indexes = [CONFIG.reason_code_order.index(code) for code in first.reason_codes]
    assert indexes == sorted(indexes)


@pytest.mark.parametrize("metrics_trusted", (False,))
def test_untrusted_metrics_cannot_produce_strong_positive_or_selling(metrics_trusted: bool) -> None:
    positive = state(
        metrics_trusted=metrics_trusted, day_rvol=1.5, rvol15=2.5,
        rvol30=2.5, price5_pct=1.5, price15_pct=2.0,
    )
    negative = replace(positive, price5_pct=-2.0, price15_pct=-2.0)
    for technical in (positive, negative):
        result = classify_signal(technical, None, CONFIG)
        assert result.signal_state in {"NORMAL", "WATCHING"}
        assert "METRICS_UNTRUSTED" in result.reason_codes


def test_incomplete_baseline_blocks_strong_signal_but_allows_degraded_watching() -> None:
    technical = state(
        baseline_sessions_used=9, day_rvol=1.5, rvol15=2.0,
        rvol30=2.0, price5_pct=0.8, price15_pct=1.2,
    )
    result = classify_signal(technical, None, CONFIG)
    assert result.signal_state == "WATCHING"
    assert "BASELINE_INCOMPLETE" in result.reason_codes
    assert classify_signal(replace(technical, baseline_sessions_used=10), None, CONFIG).signal_state == "FLOW_PRICE_CONFIRMED"


def test_null_is_not_zero_and_null_ma_emits_no_ma_reason() -> None:
    result = classify_signal(
        state(day_rvol=None, rvol15=None, rvol30=None, price5_pct=None, price15_pct=None, ma10=None, ma200=None),
        None,
        CONFIG,
    )
    assert result.signal_state == "NORMAL"
    assert not {"ABOVE_MA10", "BELOW_MA10", "ABOVE_MA200", "BELOW_MA200"} & set(result.reason_codes)


def test_ma_context_preserves_above_below_and_never_emits_near() -> None:
    result = classify_signal(state(last_price=97, ma10=100, ma200=95), None, CONFIG)
    assert "BELOW_MA10" in result.reason_codes
    assert "ABOVE_MA200" in result.reason_codes
    assert all(not code.startswith("NEAR_MA") for code in result.reason_codes)


def test_recent_high_is_optional_but_applied_when_available() -> None:
    candidate = state(rvol30=1.4, price15_pct=0.0)
    assert classify_signal(candidate, "FLOW_APPEARING", CONFIG).signal_state == "MOMENTUM_MAINTAINED"
    assert classify_signal(replace(candidate, recent_high_retreat_pct=1.21), "FLOW_APPEARING", CONFIG).signal_state != "MOMENTUM_MAINTAINED"


def test_ato_and_atc_quality_gates_use_their_own_exact10_coverage() -> None:
    ato = state(
        session_type="OPEN_AUCTION", ato_rvol=2.5, ato_gap_pct=2.0,
        ato_baseline_sessions_used=10, ato_baseline_quality="PROVEN",
    )
    assert classify_signal(ato, None, CONFIG).signal_state == "FLOW_PRICE_CONFIRMED"
    assert classify_signal(replace(ato, ato_baseline_sessions_used=9), None, CONFIG).signal_state == "WATCHING"
    atc = state(
        session_type="CLOSE_AUCTION", atc_rvol=2.5,
        atc_price_impact_pct=-1.5, atc_baseline_sessions_used=10,
        atc_baseline_quality="INFERRED_BOUNDARY",
    )
    assert classify_signal(atc, None, CONFIG).signal_state == "SELLING_PRESSURE"
