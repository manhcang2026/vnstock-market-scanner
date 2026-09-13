from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Final
from zoneinfo import ZoneInfo


VN_TZ: Final = ZoneInfo("Asia/Ho_Chi_Minh")


class SessionType(str, Enum):
    OPEN_AUCTION = "OPEN_AUCTION"
    AM_CONTINUOUS = "AM_CONTINUOUS"
    LUNCH_BREAK = "LUNCH_BREAK"
    PM_CONTINUOUS = "PM_CONTINUOUS"
    CLOSE_AUCTION = "CLOSE_AUCTION"
    POST_TRADING = "POST_TRADING"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class MarketSession:
    exchange: str
    trading_date: date
    session_type: SessionType
    session_id: str
    session_start: datetime | None
    session_end: datetime | None
    elapsed_valid_trading_minutes: int
    is_continuous: bool
    is_auction: bool
    is_break: bool


@dataclass(frozen=True)
class _SessionDefinition:
    session_type: SessionType
    start: time
    end: time


_EXCHANGE_ALIASES: Final = {
    "HOSE": "HOSE",
    "HSX": "HOSE",
    "HNX": "HNX",
    "UPCOM": "UPCOM",
    "UPCO": "UPCOM",
}

_SESSIONS: Final = {
    "HOSE": (
        _SessionDefinition(SessionType.OPEN_AUCTION, time(9, 0), time(9, 15)),
        _SessionDefinition(SessionType.AM_CONTINUOUS, time(9, 15), time(11, 30)),
        _SessionDefinition(SessionType.LUNCH_BREAK, time(11, 30), time(13, 0)),
        _SessionDefinition(SessionType.PM_CONTINUOUS, time(13, 0), time(14, 30)),
        _SessionDefinition(SessionType.CLOSE_AUCTION, time(14, 30), time(14, 45)),
        _SessionDefinition(SessionType.POST_TRADING, time(14, 45), time(15, 0)),
    ),
    "HNX": (
        _SessionDefinition(SessionType.AM_CONTINUOUS, time(9, 0), time(11, 30)),
        _SessionDefinition(SessionType.LUNCH_BREAK, time(11, 30), time(13, 0)),
        _SessionDefinition(SessionType.PM_CONTINUOUS, time(13, 0), time(14, 30)),
        _SessionDefinition(SessionType.CLOSE_AUCTION, time(14, 30), time(14, 45)),
        _SessionDefinition(SessionType.POST_TRADING, time(14, 45), time(15, 0)),
    ),
    "UPCOM": (
        _SessionDefinition(SessionType.AM_CONTINUOUS, time(9, 0), time(11, 30)),
        _SessionDefinition(SessionType.LUNCH_BREAK, time(11, 30), time(13, 0)),
        _SessionDefinition(SessionType.PM_CONTINUOUS, time(13, 0), time(15, 0)),
    ),
}


def normalize_exchange(exchange: str) -> str:
    """Return the canonical exchange name or reject an unknown mapping."""
    normalized = str(exchange or "").strip().upper()
    try:
        return _EXCHANGE_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported exchange: {exchange!r}") from exc


def _localize(moment: datetime | None) -> datetime:
    if moment is None:
        return datetime.now(VN_TZ)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=VN_TZ)
    return moment.astimezone(VN_TZ)


def _at(trading_date: date, value: time) -> datetime:
    return datetime.combine(trading_date, value, tzinfo=VN_TZ)


def _closed(exchange: str, moment: datetime) -> MarketSession:
    trading_date = moment.date()
    return MarketSession(
        exchange=exchange,
        trading_date=trading_date,
        session_type=SessionType.CLOSED,
        session_id=f"{trading_date.isoformat()}:{exchange}:{SessionType.CLOSED.value}",
        session_start=None,
        session_end=None,
        elapsed_valid_trading_minutes=0,
        is_continuous=False,
        is_auction=False,
        is_break=False,
    )


def classify_market_session(
    exchange: str, moment: datetime | None = None
) -> MarketSession:
    """Classify one instant using Vietnam exchange clocks and half-open ranges."""
    canonical_exchange = normalize_exchange(exchange)
    local_moment = _localize(moment)
    if local_moment.weekday() >= 5:
        return _closed(canonical_exchange, local_moment)

    definition = next(
        (
            candidate
            for candidate in _SESSIONS[canonical_exchange]
            if candidate.start <= local_moment.time().replace(tzinfo=None) < candidate.end
        ),
        None,
    )
    if definition is None:
        return _closed(canonical_exchange, local_moment)

    session_start = _at(local_moment.date(), definition.start)
    session_end = _at(local_moment.date(), definition.end)
    is_continuous = definition.session_type in {
        SessionType.AM_CONTINUOUS,
        SessionType.PM_CONTINUOUS,
    }
    elapsed_minutes = (
        int((local_moment - session_start).total_seconds() // 60)
        if is_continuous
        else 0
    )
    is_auction = definition.session_type in {
        SessionType.OPEN_AUCTION,
        SessionType.CLOSE_AUCTION,
    }
    return MarketSession(
        exchange=canonical_exchange,
        trading_date=local_moment.date(),
        session_type=definition.session_type,
        session_id=(
            f"{local_moment.date().isoformat()}:{canonical_exchange}:"
            f"{definition.session_type.value}"
        ),
        session_start=session_start,
        session_end=session_end,
        elapsed_valid_trading_minutes=elapsed_minutes,
        is_continuous=is_continuous,
        is_auction=is_auction,
        is_break=definition.session_type is SessionType.LUNCH_BREAK,
    )


def rolling_window_ready(session: MarketSession, window_minutes: int) -> bool:
    """Return whether a rolling momentum window fits in this continuous session."""
    if window_minutes <= 0:
        raise ValueError("window_minutes must be positive")
    return (
        session.is_continuous
        and session.elapsed_valid_trading_minutes >= window_minutes
    )


def market_feed_expected(
    moment: datetime | None = None, exchange: str | None = None
) -> bool:
    """Return whether the SSI market feed should be active at this instant."""
    exchanges = (
        (normalize_exchange(exchange),) if exchange is not None else tuple(_SESSIONS)
    )
    return any(
        _session_expects_feed(classify_market_session(item, moment))
        for item in exchanges
    )


def _session_expects_feed(session: MarketSession) -> bool:
    return (
        session.is_continuous
        or session.is_auction
        or session.session_type is SessionType.POST_TRADING
    )


def _feed_window_start(moment: datetime, exchange: str | None = None) -> datetime | None:
    exchanges = (
        (normalize_exchange(exchange),) if exchange is not None else tuple(_SESSIONS)
    )
    starts: list[datetime] = []
    for item in exchanges:
        session = classify_market_session(item, moment)
        if not _session_expects_feed(session) or session.session_start is None:
            continue

        definitions = _SESSIONS[item]
        index = next(
            index
            for index, definition in enumerate(definitions)
            if definition.session_type is session.session_type
        )
        while index > 0:
            previous = definitions[index - 1]
            current = definitions[index]
            if (
                previous.end != current.start
                or previous.session_type is SessionType.LUNCH_BREAK
            ):
                break
            index -= 1
        starts.append(_at(moment.date(), definitions[index].start))
    return min(starts) if starts else None


def market_feed_stale(
    moment: datetime,
    *,
    collector_started_at: datetime,
    last_accepted_event_at: datetime | None,
    stale_after_seconds: int,
    exchange: str | None = None,
) -> bool:
    """Detect an inactive SSI feed, including one with no accepted events yet."""
    if stale_after_seconds < 0:
        raise ValueError("stale_after_seconds must not be negative")

    local_moment = _localize(moment)
    if not market_feed_expected(local_moment, exchange):
        return False

    window_start = _feed_window_start(local_moment, exchange)
    if window_start is None:
        return False

    grace_anchor = max(window_start, _localize(collector_started_at))
    if last_accepted_event_at is not None:
        grace_anchor = max(grace_anchor, _localize(last_accepted_event_at))
    return (local_moment - grace_anchor).total_seconds() > stale_after_seconds
