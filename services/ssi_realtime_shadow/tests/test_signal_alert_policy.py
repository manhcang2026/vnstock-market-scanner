from __future__ import annotations

from dataclasses import replace

import pytest

from app.signal_alert_policy import (
    SellingPressureAlertDecision,
    SellingPressureEpisodeState,
    evaluate_selling_pressure_alert,
)
from app.signal_engine import SignalDecision
from app.market_session import SessionType


DAY = "2026-09-25"


def project(
    state: SellingPressureEpisodeState,
    minute: str,
    signal_state: str,
    *,
    session_type: str = "AM_CONTINUOUS",
    trading_date: str = DAY,
) -> SellingPressureAlertDecision:
    return evaluate_selling_pressure_alert(
        state,
        trading_date=trading_date,
        projection_key=f"{trading_date}:{minute}",
        session_type=session_type,
        signal_state=signal_state,
    )


def enter_selling() -> SellingPressureAlertDecision:
    return project(SellingPressureEpisodeState(), "10:00", "SELLING_PRESSURE")


def test_first_selling_pressure_is_alert_eligible() -> None:
    result = enter_selling()
    assert result.alert_eligible
    assert result.starts_new_episode
    assert not result.same_episode_reentry


@pytest.mark.parametrize("watching_minutes", (1, 2))
def test_short_watching_only_gap_remains_same_episode(
    watching_minutes: int,
) -> None:
    result = enter_selling()
    for offset in range(1, watching_minutes + 1):
        result = project(result.state, f"10:0{offset}", "WATCHING")
    result = project(result.state, "10:05", "SELLING_PRESSURE")
    assert not result.alert_eligible
    assert not result.starts_new_episode
    assert result.same_episode_reentry


def test_three_watching_minutes_start_new_episode() -> None:
    result = enter_selling()
    for offset in range(1, 4):
        result = project(result.state, f"10:0{offset}", "WATCHING")
    result = project(result.state, "10:04", "SELLING_PRESSURE")
    assert result.alert_eligible
    assert result.starts_new_episode
    assert not result.same_episode_reentry


@pytest.mark.parametrize(
    "rearming_state",
    (
        "NORMAL",
        "FLOW_APPEARING",
        "FLOW_PRICE_CONFIRMED",
        "MOMENTUM_MAINTAINED",
        "MOMENTUM_WEAKENING",
    ),
)
def test_non_watching_intervening_state_rearms_immediately(
    rearming_state: str,
) -> None:
    first = enter_selling()
    recovered = project(first.state, "10:01", rearming_state)
    second = project(recovered.state, "10:02", "SELLING_PRESSURE")
    assert second.alert_eligible
    assert second.starts_new_episode


def test_lunch_duration_does_not_count_as_projected_watching_minutes() -> None:
    first = enter_selling()
    lunch = project(
        first.state, "12:15", "WATCHING", session_type="LUNCH_BREAK"
    )
    watching = project(
        lunch.state, "13:00", "WATCHING", session_type="PM_CONTINUOUS"
    )
    second = project(
        watching.state, "13:01", "SELLING_PRESSURE",
        session_type="PM_CONTINUOUS",
    )
    assert not second.alert_eligible
    assert second.same_episode_reentry


@pytest.mark.parametrize(
    "session_type",
    ("OPEN_AUCTION", "CLOSE_AUCTION", "CLOSED", "POST_TRADING"),
)
def test_inactive_and_auction_periods_do_not_rearm_or_count(
    session_type: str,
) -> None:
    first = enter_selling()
    ignored = project(first.state, "12:00", "NORMAL", session_type=session_type)
    second = project(first.state, "10:01", "SELLING_PRESSURE")
    assert ignored.state == first.state
    assert not second.alert_eligible


def test_first_selling_pressure_of_new_trading_day_is_always_eligible() -> None:
    first = enter_selling()
    next_day = project(
        first.state,
        "09:15",
        "SELLING_PRESSURE",
        trading_date="2026-09-28",
    )
    assert next_day.alert_eligible
    assert next_day.starts_new_episode


@pytest.mark.parametrize("session_type", tuple(SessionType))
def test_every_canonical_session_type_is_accepted(
    session_type: SessionType,
) -> None:
    project(
        SellingPressureEpisodeState(),
        "10:00",
        "WATCHING",
        session_type=session_type.value,
    )


def test_unknown_session_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="session_type"):
        project(
            SellingPressureEpisodeState(),
            "10:00",
            "WATCHING",
            session_type="AM_CONTINOUS",
        )


def test_immediate_repeat_of_last_projection_key_is_idempotent() -> None:
    first = enter_selling()
    duplicate = project(first.state, "10:00", "SELLING_PRESSURE")
    assert duplicate.state == first.state
    assert not duplicate.alert_eligible


def test_policy_does_not_mutate_canonical_signal_decision() -> None:
    canonical = SignalDecision(
        signal_state="SELLING_PRESSURE",
        signal_level=3,
        signal_direction="BEARISH",
        reason_codes=("PRICE15_STRONG_DOWN",),
        signal_summary_vi="Áp lực bán.",
    )
    original = replace(canonical)
    project(SellingPressureEpisodeState(), "10:00", canonical.signal_state)
    assert canonical == original
