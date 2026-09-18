"""Pure Price5/Price15 calculations over canonical continuous-session prices."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from .market_session import VN_TZ, classify_market_session, normalize_exchange


@dataclass(frozen=True, slots=True)
class MinutePrice:
    """One canonical SSI one-minute close that may be used as an anchor."""

    trading_date: str
    minute: str
    close: float
    quality_status: str = "TRUSTED"
    is_partial: bool = False
    has_gap: bool = False


@dataclass(frozen=True, slots=True)
class PriceMomentum:
    price5_pct: float | None
    price15_pct: float | None


def _localize(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=VN_TZ)
    return moment.astimezone(VN_TZ)


def _valid_anchor(point: MinutePrice) -> bool:
    return (
        str(point.quality_status or "").strip().upper() == "TRUSTED"
        and not point.is_partial
        and not point.has_gap
        and math.isfinite(float(point.close))
        and float(point.close) > 0
    )


def _percentage(current: float, anchor: float | None) -> float | None:
    if anchor is None or anchor <= 0:
        return None
    return (current / anchor - 1.0) * 100.0


def calculate_price_momentum(
    *,
    exchange: str,
    selected_at: datetime,
    current_price: float,
    minute_prices: Iterable[MinutePrice],
) -> PriceMomentum:
    """Calculate exact same-session Price5 and Price15 percentage points.

    An anchor must exist at the exact clock minute. Missing or non-trusted rows
    are not replaced by zero or by an older price. Auctions, lunch and closed
    periods are not continuous-price windows.
    """
    canonical_exchange = normalize_exchange(exchange)
    local_selected = _localize(selected_at)
    price = float(current_price)
    if not math.isfinite(price) or price <= 0:
        return PriceMomentum(None, None)

    selected_session = classify_market_session(canonical_exchange, local_selected)
    if not selected_session.is_continuous:
        return PriceMomentum(None, None)

    anchors: dict[tuple[str, str], float] = {}
    for point in minute_prices:
        try:
            parsed_date = date.fromisoformat(str(point.trading_date))
            parsed_minute = datetime.strptime(str(point.minute), "%H:%M").time()
        except ValueError:
            continue
        anchor_at = datetime.combine(parsed_date, parsed_minute, tzinfo=VN_TZ)
        anchor_session = classify_market_session(canonical_exchange, anchor_at)
        if (
            anchor_session.is_continuous
            and anchor_session.session_type is selected_session.session_type
            and _valid_anchor(point)
        ):
            anchors[(parsed_date.isoformat(), point.minute)] = float(point.close)

    def value(window: int) -> float | None:
        anchor_at = local_selected.replace(second=0, microsecond=0) - timedelta(
            minutes=window
        )
        anchor_session = classify_market_session(canonical_exchange, anchor_at)
        if (
            not anchor_session.is_continuous
            or anchor_session.session_type is not selected_session.session_type
        ):
            return None
        anchor = anchors.get(
            (anchor_at.date().isoformat(), anchor_at.strftime("%H:%M"))
        )
        return _percentage(price, anchor)

    return PriceMomentum(price5_pct=value(5), price15_pct=value(15))
