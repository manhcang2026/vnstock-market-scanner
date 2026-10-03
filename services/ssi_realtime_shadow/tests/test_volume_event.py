from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timezone

import pytest

from app.market_session import VN_TZ
from app.volume_event import BaselineValidationError, VolumeEvent


def _event(**changes: object) -> VolumeEvent:
    values = {
        "symbol": "HPG",
        "exchange": "HOSE",
        "trading_date": "2026-09-14",
        "event_time": datetime(2026, 9, 14, 9, 0, tzinfo=VN_TZ),
        "minute": "09:00",
        "volume_delta": 0,
        "total_volume": 0,
        "quality_status": "TRUSTED",
    }
    return VolumeEvent(**(values | changes))


def test_normalized_event_preserves_exact_fields_values_and_immutability() -> None:
    event = _event(
        symbol=" hpg ", exchange=" hose ", quality_status=" partial ",
        volume_delta=123, total_volume=None, provider_total_volume=456,
        provider_session=" ato ", data_source=" ssi_stream ",
        is_partial=True, has_gap=True,
    )

    expected = {
        "symbol": "HPG",
        "exchange": "HOSE",
        "trading_date": "2026-09-14",
        "event_time": datetime(2026, 9, 14, 9, 0, tzinfo=VN_TZ),
        "minute": "09:00",
        "volume_delta": 123,
        "total_volume": None,
        "quality_status": "PARTIAL",
        "is_partial": True,
        "has_gap": True,
        "provider_session": "ATO",
        "provider_total_volume": 456,
        "data_source": "SSI_STREAM",
    }
    assert asdict(event) == expected
    assert tuple(asdict(event)) == tuple(expected)
    assert replace(event) == event
    with pytest.raises(FrozenInstanceError):
        event.volume_delta = 999


@pytest.mark.parametrize("exchange", ["HOSE", "HNX", "UPCOM"])
def test_zero_and_missing_volume_remain_distinct_and_defaults_are_preserved(exchange) -> None:
    zero = _event(exchange=exchange)
    missing = _event(exchange=exchange, total_volume=None)
    assert zero.total_volume == 0 and missing.total_volume is None
    assert zero.volume_delta == missing.volume_delta == 0
    assert zero.provider_total_volume is None
    assert zero.provider_session == ""
    assert zero.data_source == "SSI_STREAM"
    assert not zero.is_partial and not zero.has_gap


@pytest.mark.parametrize(
    "moment",
    [datetime(2026, 9, 14, 0, 0), datetime(2026, 9, 13, 17, 0, tzinfo=timezone.utc)],
)
def test_event_time_normalizes_to_vietnam_before_date_and_minute_validation(moment) -> None:
    event = _event(event_time=moment, minute="00:00")
    assert event.event_time == datetime(2026, 9, 14, 0, 0, tzinfo=VN_TZ)
    assert event.event_time.tzinfo == VN_TZ


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"symbol": " "}, "symbol is required"),
        ({"exchange": "HSX"}, "exchange must be canonical"),
        ({"event_time": "2026-09-14T09:00:00"}, "event_time must be a datetime"),
        ({"event_time": datetime(2026, 9, 15, 9, 0)}, "date does not match trading_date"),
        ({"event_time": datetime(2026, 9, 14, 9, 1)}, "event_time does not match minute"),
        ({"volume_delta": -1}, "volume_delta must not be negative"),
        ({"volume_delta": True}, "volume_delta must be an integer"),
        ({"volume_delta": 1.5}, "volume_delta must be an integer"),
        ({"total_volume": -1}, "total_volume must not be negative"),
        ({"total_volume": False}, "total_volume must be an integer or None"),
        ({"total_volume": "12"}, "total_volume must be an integer or None"),
        ({"provider_total_volume": -1}, "provider_total_volume must not be negative"),
        ({"provider_total_volume": True}, "provider_total_volume must be an integer or None"),
        ({"provider_total_volume": 1.5}, "provider_total_volume must be an integer or None"),
        ({"quality_status": " "}, "quality_status is required"),
    ],
)
def test_volume_event_rejects_noncanonical_or_inconsistent_values(changes, message) -> None:
    with pytest.raises(ValueError, match=message):
        _event(**changes)


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"minute": "9:00"}, "minute"),
        ({"minute": "25:00"}, "minute"),
        ({"trading_date": "20260914"}, "trading_date"),
        ({"trading_date": "2026-02-30"}, "trading_date"),
    ],
)
def test_date_and_minute_validation_preserve_exception_subtype(changes, field) -> None:
    with pytest.raises(BaselineValidationError, match=f"Malformed VolumeEvent {field}"):
        _event(**changes)
