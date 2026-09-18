from __future__ import annotations

from datetime import datetime

import pytest

from app.market_session import VN_TZ
from app.price_momentum import MinutePrice, calculate_price_momentum


DATE = "2026-09-18"


def _at(minute: str) -> datetime:
    return datetime.fromisoformat(f"{DATE}T{minute}:00").replace(tzinfo=VN_TZ)


def _price(minute: str, close: float = 100.0, **changes: object) -> MinutePrice:
    values: dict[str, object] = {
        "trading_date": DATE,
        "minute": minute,
        "close": close,
        "quality_status": "TRUSTED",
        "is_partial": False,
        "has_gap": False,
    }
    values.update(changes)
    return MinutePrice(**values)  # type: ignore[arg-type]


def test_price5_exact_boundary_uses_exact_same_session_anchor() -> None:
    result = calculate_price_momentum(
        exchange="HOSE",
        selected_at=_at("09:20"),
        current_price=110,
        minute_prices=[_price("09:15")],
    )

    assert result.price5_pct == pytest.approx(10)
    assert result.price15_pct is None


def test_price15_exact_boundary_uses_exact_same_session_anchor() -> None:
    result = calculate_price_momentum(
        exchange="HOSE",
        selected_at=_at("09:30"),
        current_price=115,
        minute_prices=[_price("09:15")],
    )

    assert result.price15_pct == pytest.approx(15)


def test_windows_are_null_before_sufficient_continuous_minutes() -> None:
    result = calculate_price_momentum(
        exchange="HOSE",
        selected_at=_at("09:19"),
        current_price=110,
        minute_prices=[_price("09:14")],
    )

    assert result.price5_pct is None
    assert result.price15_pct is None


def test_afternoon_window_never_reaches_across_lunch() -> None:
    too_early = calculate_price_momentum(
        exchange="HNX",
        selected_at=_at("13:04"),
        current_price=110,
        minute_prices=[_price("11:29", 100)],
    )
    boundary = calculate_price_momentum(
        exchange="HNX",
        selected_at=_at("13:05"),
        current_price=110,
        minute_prices=[_price("11:29", 1), _price("13:00", 100)],
    )

    assert too_early.price5_pct is None
    assert boundary.price5_pct == pytest.approx(10)
    assert boundary.price15_pct is None


@pytest.mark.parametrize("minute", ["09:10", "14:35"])
def test_ato_and_atc_are_not_continuous_windows(minute: str) -> None:
    result = calculate_price_momentum(
        exchange="HOSE",
        selected_at=_at(minute),
        current_price=110,
        minute_prices=[_price("09:05"), _price("14:30")],
    )

    assert result.price5_pct is None
    assert result.price15_pct is None


@pytest.mark.parametrize(
    "anchor",
    [
        None,
        _price("09:15", quality_status="GAP", has_gap=True),
        _price("09:15", quality_status="PARTIAL", is_partial=True),
    ],
)
def test_missing_or_untrusted_exact_anchor_returns_null_never_zero(
    anchor: MinutePrice | None,
) -> None:
    result = calculate_price_momentum(
        exchange="HOSE",
        selected_at=_at("09:20"),
        current_price=110,
        minute_prices=[] if anchor is None else [anchor],
    )

    assert result.price5_pct is None
