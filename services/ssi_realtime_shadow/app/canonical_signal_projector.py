"""Adapter from canonical calculated state to the locked CCC signal classifier."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from .canonical_engine_store import CanonicalEngineStore, CurrentState, SignalState
from .canonical_market_store import utc_now
from .market_session import VN_TZ, classify_market_session
from .signal_config import SignalConfig, load_signal_config
from .signal_engine import TechnicalState, classify_signal


@dataclass(frozen=True, slots=True)
class SignalProjectionResult:
    state_written: bool
    event_appended: bool


def _session_type(state: CurrentState, observed_at: datetime) -> str:
    if not state.exchange:
        raise ValueError("canonical signal projection requires exchange")
    moment = (
        observed_at.replace(tzinfo=VN_TZ)
        if observed_at.tzinfo is None
        else observed_at.astimezone(VN_TZ)
    )
    return classify_market_session(state.exchange, moment).session_type.value


def _canonical_reasons(state: CurrentState) -> frozenset[str]:
    parsed = json.loads(state.reason_codes_json)
    if not isinstance(parsed, list) or not all(
        isinstance(item, str) for item in parsed
    ):
        raise ValueError("canonical reason_codes_json must be a string array")
    return frozenset(parsed)


def build_technical_state(
    state: CurrentState,
    config: SignalConfig,
    observed_at: datetime,
) -> TechnicalState:
    """Map canonical continuous metrics without fabricating unavailable values."""
    sessions_used = min(
        int(state.day_rvol_sessions_used or 0),
        int(state.rvol15_sessions_used or 0),
        int(state.rvol30_sessions_used or 0),
    )
    reasons = _canonical_reasons(state)
    metrics_trusted = (
        sessions_used >= config.continuous_minimum_sessions
        and state.cumulative_volume is not None
        and "CURRENT_GAP" not in reasons
        and "NO_BASELINE" not in reasons
    )
    return TechnicalState(
        session_type=_session_type(state, observed_at),
        last_price=state.last_price,
        day_rvol=state.day_rvol,
        rvol15=state.rvol15,
        rvol30=state.rvol30,
        price5_pct=state.price5_pct,
        price15_pct=state.price15_pct,
        ma10=state.ma10,
        ma200=state.ma200,
        distance_ma10_pct=state.distance_ma10_pct,
        distance_ma200_pct=state.distance_ma200_pct,
        baseline_sessions_used=sessions_used,
        metrics_trusted=metrics_trusted,
    )


class CanonicalSignalProjector:
    def __init__(
        self,
        engine_store: CanonicalEngineStore,
        config: SignalConfig | None = None,
    ) -> None:
        self.engine_store = engine_store
        self.config = config or load_signal_config()

    def project(
        self, state: CurrentState, observed_at: datetime
    ) -> SignalProjectionResult:
        if not state.trading_date or not state.minute:
            raise ValueError("canonical signal projection requires date/minute")
        session_type = _session_type(state, observed_at)
        if session_type in {"OPEN_AUCTION", "CLOSE_AUCTION"}:
            return SignalProjectionResult(False, False)
        previous_row = self.engine_store.signal_row(state.symbol)
        previous = None
        if (
            previous_row is not None
            and previous_row["trading_date"] == state.trading_date
        ):
            previous = str(previous_row["signal_state"])
        technical = build_technical_state(state, self.config, observed_at)
        decision = classify_signal(technical, previous, self.config)
        timestamp = state.updated_at or utc_now()
        event_appended = self.engine_store.upsert_signal(
            SignalState(
                symbol=state.symbol,
                exchange=state.exchange,
                trading_date=state.trading_date,
                minute=state.minute,
                session_type=technical.session_type,
                signal_state=decision.signal_state,
                signal_level=decision.signal_level,
                signal_direction=decision.signal_direction,
                reason_codes_json=json.dumps(
                    list(decision.reason_codes),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                signal_summary_vi=decision.signal_summary_vi,
                metrics_trusted=int(technical.metrics_trusted),
                baseline_sessions_used=technical.baseline_sessions_used,
                engine_version=self.config.engine_version,
                config_version=self.config.config_version,
                updated_at=timestamp,
            )
        )
        return SignalProjectionResult(True, event_appended)
