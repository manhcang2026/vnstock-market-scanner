"""Pure deterministic CCC V2 beta signal classifier."""

from __future__ import annotations

from dataclasses import dataclass

from .signal_config import SignalConfig


@dataclass(frozen=True, slots=True)
class TechnicalState:
    session_type: str
    last_price: float | None = None
    day_rvol: float | None = None
    rvol15: float | None = None
    rvol30: float | None = None
    price5_pct: float | None = None
    price15_pct: float | None = None
    ma10: float | None = None
    ma200: float | None = None
    distance_ma10_pct: float | None = None
    distance_ma200_pct: float | None = None
    recent_high_retreat_pct: float | None = None
    ato_rvol: float | None = None
    ato_gap_pct: float | None = None
    ato_baseline_sessions_used: int = 0
    ato_baseline_quality: str = "UNAVAILABLE"
    atc_rvol: float | None = None
    atc_volume_share_pct: float | None = None
    atc_price_impact_pct: float | None = None
    atc_baseline_sessions_used: int = 0
    atc_baseline_quality: str = "UNAVAILABLE"
    baseline_sessions_used: int = 0
    metrics_trusted: bool = False


@dataclass(frozen=True, slots=True)
class SignalDecision:
    signal_state: str
    signal_level: int
    signal_direction: str
    reason_codes: tuple[str, ...]
    signal_summary_vi: str


def _all(state: TechnicalState, conditions: tuple[tuple[str, str, float], ...]) -> bool:
    for field, operator, threshold in conditions:
        value = getattr(state, field)
        if value is None:
            return False
        if operator == ">=" and not value >= threshold:
            return False
        if operator == "<=" and not value <= threshold:
            return False
    return True


def _continuous_candidates(
    state: TechnicalState, previous: str | None, config: SignalConfig
) -> set[str]:
    raw = config.raw
    candidates: set[str] = {"NORMAL"}
    selling = raw["negative_flow"]["selling_pressure"]
    shock = raw["negative_flow"]["shock"]
    if _all(state, (
        ("rvol15", ">=", selling["rvol15_min"]),
        ("rvol30", ">=", selling["rvol30_min"]),
        ("price5_pct", "<=", selling["price5_pct_max"]),
        ("price15_pct", "<=", selling["price15_pct_max"]),
        ("day_rvol", ">=", selling["day_rvol_min"]),
    )) or _all(state, (
        ("rvol15", ">=", shock["rvol15_min"]),
        ("price5_pct", "<=", shock["price5_pct_max"]),
    )):
        candidates.add(str(shock["resulting_state"]))

    if previous in config.positive_previous_states:
        weakening = raw["negative_flow"]["momentum_weakening"]
        weak = _all(state, (
            ("price5_pct", "<=", weakening["price5_pct_max"]),
            ("price15_pct", "<=", weakening["price15_pct_max"]),
            ("rvol30", ">=", weakening["rvol30_min"]),
        ))
        if state.recent_high_retreat_pct is not None:
            weak = weak and state.recent_high_retreat_pct >= weakening["loss_from_recent_high_pct_min"]
        if weak:
            candidates.add("MOMENTUM_WEAKENING")

        maintained = raw["positive_flow"]["momentum_maintained"]
        keep = _all(state, (
            ("rvol30", ">=", maintained["rvol30_min"]),
            ("price15_pct", ">=", maintained["price15_pct_floor"]),
        ))
        if state.recent_high_retreat_pct is not None:
            keep = keep and state.recent_high_retreat_pct <= maintained["retain_recent_high_pct_max"]
        if keep:
            candidates.add("MOMENTUM_MAINTAINED")

    confirmed = raw["positive_flow"]["flow_price_confirmed"]
    if _all(state, (
        ("rvol30", ">=", confirmed["rvol30_min"]),
        ("price15_pct", ">=", confirmed["price15_pct_min"]),
        ("day_rvol", ">=", confirmed["day_rvol_min"]),
    )):
        candidates.add("FLOW_PRICE_CONFIRMED")
    appearing = raw["positive_flow"]["flow_appearing"]
    if _all(state, (
        ("rvol15", ">=", appearing["rvol15_min"]),
        ("rvol30", ">=", appearing["rvol30_min"]),
        ("price5_pct", ">=", appearing["price5_pct_min"]),
        ("price15_pct", ">=", appearing["price15_pct_min"]),
        ("day_rvol", ">=", appearing["day_rvol_min"]),
    )):
        candidates.add("FLOW_APPEARING")

    watching = raw["watching"]
    values = (
        state.day_rvol is not None and state.day_rvol >= watching["day_rvol_min"],
        state.rvol15 is not None and state.rvol15 >= watching["rvol15_min"],
        state.rvol30 is not None and state.rvol30 >= watching["rvol30_min"],
        state.price5_pct is not None and abs(state.price5_pct) >= watching["abs_price5_pct_min"],
        state.price15_pct is not None and abs(state.price15_pct) >= watching["abs_price15_pct_min"],
    )
    absorption = watching["absorption"]
    relevant = max(value for value in (state.rvol15, state.rvol30) if value is not None) if any(
        value is not None for value in (state.rvol15, state.rvol30)
    ) else None
    absorbed = (
        relevant is not None
        and state.price15_pct is not None
        and relevant >= absorption["rvol_min"]
        and abs(state.price15_pct) <= absorption["abs_price15_pct_max"]
    )
    if any(values) or absorbed:
        candidates.add("WATCHING")
    return candidates


def _auction_candidates(state: TechnicalState, config: SignalConfig) -> set[str]:
    candidates = {"NORMAL"}
    if state.session_type == "OPEN_AUCTION":
        section = config.raw["opening_auction"]
        rvol = state.ato_rvol
        price = state.ato_gap_pct
        volume_share = None
        prefix = "opening"
    else:
        section = config.raw["closing_auction"]
        rvol = state.atc_rvol
        price = state.atc_price_impact_pct
        volume_share = state.atc_volume_share_pct
        prefix = "closing"
    thresholds = section["thresholds"]
    behavior = section["behavior"]
    watch_volume = rvol is not None and rvol >= thresholds[f"{prefix}_rvol_watch_min"]
    strong_volume = rvol is not None and rvol >= thresholds[f"{prefix}_rvol_strong_min"]
    if prefix == "closing":
        watch_volume = watch_volume or (
            volume_share is not None
            and volume_share >= thresholds["closing_volume_share_watch_pct"]
        )
        strong_volume = strong_volume or (
            volume_share is not None
            and volume_share >= thresholds["closing_volume_share_strong_pct"]
        )
        pos_watch = thresholds["positive_price_impact_watch_pct"]
        pos_strong = thresholds["positive_price_impact_strong_pct"]
        neg_watch = thresholds["negative_price_impact_watch_pct"]
        neg_strong = thresholds["negative_price_impact_strong_pct"]
        neutral = thresholds["neutral_price_impact_abs_pct_max"]
    else:
        pos_watch = thresholds["positive_gap_watch_pct"]
        pos_strong = thresholds["positive_gap_strong_pct"]
        neg_watch = thresholds["negative_gap_watch_pct"]
        neg_strong = thresholds["negative_gap_strong_pct"]
        neutral = thresholds["neutral_gap_abs_pct_max"]
    if strong_volume and price is not None and price >= pos_strong:
        candidates.add(behavior["strong_positive_state"])
    elif watch_volume and price is not None and price >= pos_watch:
        candidates.add(behavior["positive_watch_state"])
    if strong_volume and price is not None and price <= neg_strong:
        candidates.add(behavior["strong_negative_state"])
    elif watch_volume and price is not None and price <= neg_watch:
        candidates.add(behavior["negative_watch_state"])
    if watch_volume and price is not None and abs(price) <= neutral:
        candidates.add(behavior["high_volume_neutral_price_state"])
    if watch_volume:
        candidates.add("WATCHING")
    return candidates


def _reason_codes(state: TechnicalState, config: SignalConfig) -> tuple[str, ...]:
    raw = config.raw
    found: set[str] = set()
    if not state.metrics_trusted:
        found.add("METRICS_UNTRUSTED")
    if state.session_type == "OPEN_AUCTION":
        baseline_complete = (
            state.ato_baseline_sessions_used == config.exact_previous_sessions
            and state.ato_baseline_quality == "PROVEN"
        )
    elif state.session_type == "CLOSE_AUCTION":
        baseline_complete = (
            state.atc_baseline_sessions_used == config.exact_previous_sessions
            and state.atc_baseline_quality in {"PROVEN", "MIXED", "INFERRED_BOUNDARY"}
        )
    else:
        baseline_complete = state.baseline_sessions_used == config.exact_previous_sessions
    if not baseline_complete:
        found.add("BASELINE_INCOMPLETE")
    watch = raw["watching"]
    if state.day_rvol is not None and state.day_rvol >= watch["day_rvol_min"]:
        found.add("DAY_RVOL_ELEVATED")
    for minutes in (15, 30):
        value = getattr(state, f"rvol{minutes}")
        if value is not None and value >= watch[f"rvol{minutes}_min"]:
            found.add(f"RVOL{minutes}_ELEVATED")
        strong = raw["positive_flow"]["flow_appearing"][f"rvol{minutes}_min"]
        if value is not None and value >= strong:
            found.add(f"RVOL{minutes}_STRONG")
    price_thresholds = {
        5: (watch["abs_price5_pct_min"], raw["positive_flow"]["flow_appearing"]["price5_pct_min"]),
        15: (watch["abs_price15_pct_min"], raw["positive_flow"]["flow_price_confirmed"]["price15_pct_min"]),
    }
    for minutes, (regular, strong) in price_thresholds.items():
        value = getattr(state, f"price{minutes}_pct")
        if value is None:
            continue
        if value >= regular:
            found.add(f"PRICE{minutes}_UP")
        if value >= strong:
            found.add(f"PRICE{minutes}_STRONG_UP")
        if value <= -regular:
            found.add(f"PRICE{minutes}_DOWN")
        if value <= -strong:
            found.add(f"PRICE{minutes}_STRONG_DOWN")
    relevant = [value for value in (state.rvol15, state.rvol30) if value is not None]
    absorption = watch["absorption"]
    if relevant and state.price15_pct is not None and max(relevant) >= absorption["rvol_min"] and abs(state.price15_pct) <= absorption["abs_price15_pct_max"]:
        found.add("HIGH_VOLUME_PRICE_ABSORPTION")

    if state.ato_rvol is not None:
        ato = raw["opening_auction"]["thresholds"]
        if state.ato_rvol >= ato["opening_rvol_watch_min"]:
            found.add("ATO_RVOL_ELEVATED")
        if state.ato_rvol >= ato["opening_rvol_strong_min"]:
            found.add("ATO_RVOL_STRONG")
        if state.ato_gap_pct is not None:
            if state.ato_gap_pct >= ato["positive_gap_watch_pct"]: found.add("ATO_GAP_UP")
            if state.ato_gap_pct >= ato["positive_gap_strong_pct"]: found.add("ATO_GAP_STRONG_UP")
            if state.ato_gap_pct <= ato["negative_gap_watch_pct"]: found.add("ATO_GAP_DOWN")
            if state.ato_gap_pct <= ato["negative_gap_strong_pct"]: found.add("ATO_GAP_STRONG_DOWN")
    if state.atc_rvol is not None or state.atc_volume_share_pct is not None:
        atc = raw["closing_auction"]["thresholds"]
        if state.atc_rvol is not None and state.atc_rvol >= atc["closing_rvol_watch_min"]: found.add("ATC_RVOL_ELEVATED")
        if state.atc_rvol is not None and state.atc_rvol >= atc["closing_rvol_strong_min"]: found.add("ATC_RVOL_STRONG")
        if state.atc_volume_share_pct is not None and state.atc_volume_share_pct >= atc["closing_volume_share_watch_pct"]: found.add("ATC_VOLUME_SHARE_HIGH")
        if state.atc_volume_share_pct is not None and state.atc_volume_share_pct >= atc["closing_volume_share_strong_pct"]: found.add("ATC_VOLUME_SHARE_STRONG")
        impact = state.atc_price_impact_pct
        if impact is not None:
            if impact >= atc["positive_price_impact_watch_pct"]: found.add("ATC_PRICE_UP")
            if impact >= atc["positive_price_impact_strong_pct"]: found.add("ATC_PRICE_STRONG_UP")
            if impact <= atc["negative_price_impact_watch_pct"]: found.add("ATC_PRICE_DOWN")
            if impact <= atc["negative_price_impact_strong_pct"]: found.add("ATC_PRICE_STRONG_DOWN")
    if state.last_price is not None and state.ma10 is not None:
        found.add("ABOVE_MA10" if state.last_price > state.ma10 else "BELOW_MA10")
    if state.last_price is not None and state.ma200 is not None:
        found.add("ABOVE_MA200" if state.last_price > state.ma200 else "BELOW_MA200")
    return tuple(code for code in config.reason_code_order if code in found)


def classify_signal(
    state: TechnicalState,
    previous_signal_state: str | None,
    config: SignalConfig,
) -> SignalDecision:
    """Classify technical state without storage or clock access."""
    if previous_signal_state is not None and previous_signal_state not in config.states:
        raise ValueError("previous_signal_state is invalid")
    candidates = (
        _auction_candidates(state, config)
        if state.session_type in {"OPEN_AUCTION", "CLOSE_AUCTION"}
        else _continuous_candidates(state, previous_signal_state, config)
    )
    exact = state.baseline_sessions_used == config.exact_previous_sessions
    if state.session_type == "OPEN_AUCTION":
        exact = (
            state.ato_baseline_sessions_used == config.exact_previous_sessions
            and state.ato_baseline_quality == "PROVEN"
        )
    elif state.session_type == "CLOSE_AUCTION":
        exact = (
            state.atc_baseline_sessions_used == config.exact_previous_sessions
            and state.atc_baseline_quality in {"PROVEN", "MIXED", "INFERRED_BOUNDARY"}
        )
    if not state.metrics_trusted or not exact:
        candidates -= {
            "FLOW_APPEARING", "FLOW_PRICE_CONFIRMED",
            "MOMENTUM_MAINTAINED", "SELLING_PRESSURE",
        }
    chosen = next(name for name in config.evaluation_priority if name in candidates)
    definition = config.states[chosen]
    return SignalDecision(
        chosen,
        definition.level,
        definition.direction,
        _reason_codes(state, config),
        definition.summary_vi,
    )
