from datetime import datetime

import pytest

from app.market_session import (
    VN_TZ,
    SessionType,
    classify_market_session,
    market_feed_expected,
    market_feed_stale,
    rolling_window_ready,
)


def at(hour: int, minute: int, *, day: int = 14, second: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, second, tzinfo=VN_TZ)


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (8, 59, SessionType.CLOSED),
        (9, 0, SessionType.OPEN_AUCTION),
        (9, 14, SessionType.OPEN_AUCTION),
        (9, 15, SessionType.AM_CONTINUOUS),
        (9, 20, SessionType.AM_CONTINUOUS),
        (11, 29, SessionType.AM_CONTINUOUS),
        (11, 30, SessionType.LUNCH_BREAK),
        (12, 59, SessionType.LUNCH_BREAK),
        (13, 0, SessionType.PM_CONTINUOUS),
        (13, 5, SessionType.PM_CONTINUOUS),
        (13, 15, SessionType.PM_CONTINUOUS),
        (14, 29, SessionType.PM_CONTINUOUS),
        (14, 30, SessionType.CLOSE_AUCTION),
        (14, 44, SessionType.CLOSE_AUCTION),
        (14, 45, SessionType.POST_TRADING),
        (15, 0, SessionType.CLOSED),
    ],
)
def test_hose_boundaries(hour: int, minute: int, expected: SessionType) -> None:
    assert classify_market_session("HSX", at(hour, minute)).session_type is expected


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (9, 0, SessionType.AM_CONTINUOUS),
        (11, 30, SessionType.LUNCH_BREAK),
        (13, 0, SessionType.PM_CONTINUOUS),
        (14, 30, SessionType.CLOSE_AUCTION),
        (14, 45, SessionType.POST_TRADING),
        (14, 59, SessionType.POST_TRADING),
        (15, 0, SessionType.CLOSED),
    ],
)
def test_hnx_boundaries(hour: int, minute: int, expected: SessionType) -> None:
    assert classify_market_session("HNX", at(hour, minute)).session_type is expected


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (9, 0, SessionType.AM_CONTINUOUS),
        (11, 30, SessionType.LUNCH_BREAK),
        (13, 0, SessionType.PM_CONTINUOUS),
        (14, 45, SessionType.PM_CONTINUOUS),
        (14, 59, SessionType.PM_CONTINUOUS),
        (15, 0, SessionType.CLOSED),
    ],
)
def test_upcom_boundaries(hour: int, minute: int, expected: SessionType) -> None:
    assert classify_market_session("UPCO", at(hour, minute)).session_type is expected


@pytest.mark.parametrize("day", [19, 20])
def test_weekend_is_closed(day: int) -> None:
    for exchange in ("HOSE", "HNX", "UPCOM"):
        assert classify_market_session(exchange, at(10, 0, day=day)).session_type is SessionType.CLOSED


def test_pm_elapsed_minutes_reset_at_lunch() -> None:
    session = classify_market_session("HOSE", at(13, 5))
    assert session.exchange == "HOSE"
    assert session.trading_date.isoformat() == "2026-09-14"
    assert session.session_start == at(13, 0)
    assert session.session_end == at(14, 30)
    assert session.elapsed_valid_trading_minutes == 5
    assert session.session_id.endswith(":HOSE:PM_CONTINUOUS")
    assert session.is_continuous
    assert not session.is_auction
    assert not session.is_break
    assert not rolling_window_ready(session, 15)


def test_pm_fifteen_minute_window_becomes_ready_at_1315() -> None:
    session = classify_market_session("HOSE", at(13, 15))
    assert session.elapsed_valid_trading_minutes == 15
    assert rolling_window_ready(session, 15)


@pytest.mark.parametrize(
    ("exchange", "hour", "minute"),
    [
        ("HOSE", 9, 0),
        ("HOSE", 14, 30),
        ("HOSE", 14, 45),
        ("HNX", 14, 30),
        ("HNX", 14, 45),
    ],
)
def test_rolling_momentum_is_disabled_outside_continuous_trading(
    exchange: str, hour: int, minute: int
) -> None:
    session = classify_market_session(exchange, at(hour, minute))
    assert not session.is_continuous
    assert not rolling_window_ready(session, 1)


def test_feed_health_handles_zero_accepted_events_after_startup_grace() -> None:
    assert not market_feed_stale(
        at(9, 3),
        collector_started_at=at(8, 0),
        last_accepted_event_at=None,
        stale_after_seconds=180,
    )
    assert market_feed_stale(
        at(9, 3, second=1),
        collector_started_at=at(8, 0),
        last_accepted_event_at=None,
        stale_after_seconds=180,
    )


def test_feed_health_grace_starts_when_collector_starts_during_session() -> None:
    assert not market_feed_stale(
        at(9, 21),
        collector_started_at=at(9, 20),
        last_accepted_event_at=None,
        stale_after_seconds=180,
    )


def test_feed_health_grace_resets_after_lunch() -> None:
    assert not market_feed_stale(
        at(13, 3),
        collector_started_at=at(8, 0),
        last_accepted_event_at=at(11, 29),
        stale_after_seconds=180,
    )
    assert market_feed_stale(
        at(13, 3, second=1),
        collector_started_at=at(8, 0),
        last_accepted_event_at=at(11, 29),
        stale_after_seconds=180,
    )


@pytest.mark.parametrize(
    "moment",
    [at(12, 0), at(10, 0, day=19), at(15, 0)],
)
def test_feed_is_not_expected_during_break_weekend_or_closed(moment: datetime) -> None:
    assert not market_feed_expected(moment)
    assert not market_feed_stale(
        moment,
        collector_started_at=at(8, 0),
        last_accepted_event_at=None,
        stale_after_seconds=1,
    )
