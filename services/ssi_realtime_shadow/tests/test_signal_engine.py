from __future__ import annotations

from dataclasses import replace
from copy import deepcopy

import pytest
import yaml

from app.signal_config import CONFIG_PATH, load_signal_config, validate_signal_config
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


@pytest.mark.parametrize("sessions", (10, 9, 8))
def test_usable_continuous_baseline_can_emit_same_strong_signal(
    sessions: int,
) -> None:
    technical = state(
        baseline_sessions_used=sessions, day_rvol=1.5, rvol15=2.0,
        rvol30=2.0, price5_pct=0.8, price15_pct=1.2,
    )
    result = classify_signal(technical, None, CONFIG)
    assert result.signal_state == "FLOW_PRICE_CONFIRMED"
    assert ("BASELINE_INCOMPLETE" in result.reason_codes) is (sessions < 10)


def test_seven_session_baseline_blocks_strong_but_preserves_watching() -> None:
    technical = state(
        baseline_sessions_used=7, day_rvol=1.5, rvol15=2.0,
        rvol30=2.0, price5_pct=0.8, price15_pct=1.2,
    )
    result = classify_signal(technical, None, CONFIG)
    assert result.signal_state == "WATCHING"
    assert "BASELINE_INCOMPLETE" in result.reason_codes


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
    for sessions in (9, 8):
        assert classify_signal(
            replace(ato, ato_baseline_sessions_used=sessions), None, CONFIG
        ).signal_state == "WATCHING"
    atc = state(
        session_type="CLOSE_AUCTION", atc_rvol=2.5,
        atc_price_impact_pct=-1.5, atc_baseline_sessions_used=10,
        atc_baseline_quality="INFERRED_BOUNDARY",
    )
    assert classify_signal(atc, None, CONFIG).signal_state == "SELLING_PRESSURE"
    assert classify_signal(
        replace(atc, atc_baseline_sessions_used=8), None, CONFIG
    ).signal_state == "WATCHING"


@pytest.mark.parametrize(
    ("session_type", "previous", "expected"),
    (
        ("LUNCH_BREAK", None, "NORMAL"),
        ("LUNCH_BREAK", "FLOW_PRICE_CONFIRMED", "FLOW_PRICE_CONFIRMED"),
        ("CLOSED", None, "NORMAL"),
        ("POST_TRADING", "FLOW_APPEARING", "FLOW_APPEARING"),
    ),
)
def test_inactive_sessions_do_not_invent_signals_and_preserve_safe_state(
    session_type: str, previous: str | None, expected: str
) -> None:
    stale_strong = state(
        session_type=session_type,
        day_rvol=2.0,
        rvol15=3.0,
        rvol30=3.0,
        price5_pct=-2.0,
        price15_pct=-2.0,
    )
    assert classify_signal(stale_strong, previous, CONFIG).signal_state == expected


def _config_with(path: tuple[str, ...], value: object):
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    current = raw
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    return validate_signal_config(deepcopy(raw))


def test_classifier_respects_disabled_continuous_and_auction_sections() -> None:
    confirmed_off = _config_with(
        ("positive_flow", "flow_price_confirmed", "enabled"), False
    )
    confirmed = state(day_rvol=1.4, rvol30=2.0, price15_pct=1.2)
    assert classify_signal(confirmed, None, confirmed_off).signal_state == "WATCHING"

    watching_off = _config_with(("watching", "enabled"), False)
    assert classify_signal(state(day_rvol=1.3), None, watching_off).signal_state == "NORMAL"

    auction_off = _config_with(("opening_auction", "enabled"), False)
    ato = state(
        session_type="OPEN_AUCTION", ato_rvol=3.0, ato_gap_pct=3.0,
        ato_baseline_sessions_used=10, ato_baseline_quality="PROVEN",
    )
    assert classify_signal(ato, None, auction_off).signal_state == "NORMAL"

    shock_off = _config_with(("negative_flow", "shock", "enabled"), False)
    shock = state(rvol15=2.5, price5_pct=-1.5)
    assert classify_signal(shock, None, shock_off).signal_state == "WATCHING"


@pytest.mark.parametrize(
    ("field", "value", "base", "strong"),
    (
        ("price5_pct", 0.60, "PRICE5_UP", "PRICE5_STRONG_UP"),
        ("price15_pct", 1.20, "PRICE15_UP", "PRICE15_STRONG_UP"),
        ("price5_pct", -0.80, "PRICE5_DOWN", "PRICE5_STRONG_DOWN"),
        ("price15_pct", -1.20, "PRICE15_DOWN", "PRICE15_STRONG_DOWN"),
    ),
)
def test_strong_price_reason_always_implies_base_direction(
    field: str, value: float, base: str, strong: str
) -> None:
    result = classify_signal(state(**{field: value}), None, CONFIG)
    assert strong in result.reason_codes
    assert base in result.reason_codes
