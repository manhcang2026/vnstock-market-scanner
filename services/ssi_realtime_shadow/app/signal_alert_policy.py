"""Pure notification-episode policy for canonical signal projections."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .market_session import SessionType


SELLING_PRESSURE = "SELLING_PRESSURE"
WATCHING = "WATCHING"
VALID_SESSION_TYPES = frozenset(item.value for item in SessionType)
CONTINUOUS_SESSIONS = frozenset({
    SessionType.AM_CONTINUOUS.value,
    SessionType.PM_CONTINUOUS.value,
})
REARMING_STATES = frozenset({
    "NORMAL",
    "FLOW_APPEARING",
    "FLOW_PRICE_CONFIRMED",
    "MOMENTUM_MAINTAINED",
    "MOMENTUM_WEAKENING",
})
VALID_STATES = REARMING_STATES | {WATCHING, SELLING_PRESSURE}
DEFAULT_MERGE_WATCHING_GAP_MINUTES = 2


@dataclass(frozen=True, slots=True)
class SellingPressureEpisodeState:
    """Notifier-owned state; canonical signal records remain untouched."""

    trading_date: str | None = None
    alert_armed: bool = True
    watching_gap_minutes: int = 0
    last_projection_key: str | None = None


@dataclass(frozen=True, slots=True)
class SellingPressureAlertDecision:
    state: SellingPressureEpisodeState
    alert_eligible: bool = False
    starts_new_episode: bool = False
    same_episode_reentry: bool = False


def evaluate_selling_pressure_alert(
    policy_state: SellingPressureEpisodeState,
    *,
    trading_date: str,
    projection_key: str,
    session_type: str,
    signal_state: str,
    merge_watching_gap_minutes: int = DEFAULT_MERGE_WATCHING_GAP_MINUTES,
) -> SellingPressureAlertDecision:
    """Reduce one finalized projected symbol-minute into alert episode state.

    For one symbol and trading day, the caller must supply projections in
    chronological order and use a ``projection_key`` that uniquely identifies
    each projected market minute. An immediate repeat of the last key is
    idempotent. Arbitrary old or out-of-order historical projections are outside
    this helper's contract. Wall-clock gaps are never inferred; only supplied
    continuous-market projections can count toward the WATCHING gap.
    """
    if merge_watching_gap_minutes < 0:
        raise ValueError("merge_watching_gap_minutes must not be negative")
    if not trading_date:
        raise ValueError("trading_date must not be empty")
    if not projection_key:
        raise ValueError("projection_key must not be empty")
    if session_type not in VALID_SESSION_TYPES:
        raise ValueError("session_type is invalid")
    if signal_state not in VALID_STATES:
        raise ValueError("signal_state is invalid")

    current = policy_state
    if current.trading_date != trading_date:
        current = SellingPressureEpisodeState(trading_date=trading_date)

    if session_type not in CONTINUOUS_SESSIONS:
        return SellingPressureAlertDecision(state=current)
    if current.last_projection_key == projection_key:
        return SellingPressureAlertDecision(state=current)

    if signal_state == SELLING_PRESSURE:
        alert_eligible = current.alert_armed
        same_episode_reentry = (
            not current.alert_armed and current.watching_gap_minutes > 0
        )
        next_state = replace(
            current,
            alert_armed=False,
            watching_gap_minutes=0,
            last_projection_key=projection_key,
        )
        return SellingPressureAlertDecision(
            state=next_state,
            alert_eligible=alert_eligible,
            starts_new_episode=alert_eligible,
            same_episode_reentry=same_episode_reentry,
        )

    if signal_state == WATCHING and not current.alert_armed:
        gap = current.watching_gap_minutes + 1
        next_state = replace(
            current,
            alert_armed=gap > merge_watching_gap_minutes,
            watching_gap_minutes=gap,
            last_projection_key=projection_key,
        )
        return SellingPressureAlertDecision(state=next_state)

    next_state = replace(
        current,
        alert_armed=signal_state in REARMING_STATES or current.alert_armed,
        watching_gap_minutes=0,
        last_projection_key=projection_key,
    )
    return SellingPressureAlertDecision(state=next_state)
