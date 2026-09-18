"""Validated loader for the locked CCC V2 beta signal configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml


EXPECTED_CONFIG_VERSION = "cfg-20260918-beta-001"
EXPECTED_ENGINE_VERSION = "2.0.0-beta"
EXPECTED_STATES = (
    "NORMAL",
    "WATCHING",
    "FLOW_APPEARING",
    "FLOW_PRICE_CONFIRMED",
    "MOMENTUM_MAINTAINED",
    "MOMENTUM_WEAKENING",
    "SELLING_PRESSURE",
)
EXPECTED_DIRECTIONS = {"NEUTRAL", "BULLISH", "BEARISH"}
EXPECTED_STATE_META = {
    "NORMAL": (0, "NEUTRAL"),
    "WATCHING": (1, "NEUTRAL"),
    "FLOW_APPEARING": (2, "BULLISH"),
    "FLOW_PRICE_CONFIRMED": (3, "BULLISH"),
    "MOMENTUM_MAINTAINED": (4, "BULLISH"),
    "MOMENTUM_WEAKENING": (2, "NEUTRAL"),
    "SELLING_PRESSURE": (3, "BEARISH"),
}
EXPECTED_PRIORITY = (
    "SELLING_PRESSURE",
    "MOMENTUM_WEAKENING",
    "MOMENTUM_MAINTAINED",
    "FLOW_PRICE_CONFIRMED",
    "FLOW_APPEARING",
    "WATCHING",
    "NORMAL",
)
CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "ccc_signal_v2_beta_config.yaml"
)


class SignalConfigError(ValueError):
    """Raised when the canonical signal configuration is missing or malformed."""


@dataclass(frozen=True, slots=True)
class StateDefinition:
    level: int
    direction: str
    summary_vi: str


@dataclass(frozen=True, slots=True)
class SignalConfig:
    config_version: str
    engine_version: str
    contract_version: str
    exact_previous_sessions: int
    states: Mapping[str, StateDefinition]
    evaluation_priority: tuple[str, ...]
    positive_previous_states: frozenset[str]
    reason_code_order: tuple[str, ...]
    raw: Mapping[str, Any]

    def section(self, *path: str) -> Mapping[str, Any]:
        value: Any = self.raw
        for key in path:
            if not isinstance(value, Mapping) or key not in value:
                raise SignalConfigError(f"missing config section: {'.'.join(path)}")
            value = value[key]
        if not isinstance(value, Mapping):
            raise SignalConfigError(f"config section is not a mapping: {'.'.join(path)}")
        return value


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SignalConfigError(f"{path} must be a mapping")
    return value


def _number(mapping: Mapping[str, Any], key: str, path: str) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SignalConfigError(f"{path}.{key} must be numeric")
    return float(value)


def _validate_thresholds(raw: Mapping[str, Any]) -> None:
    required = {
        "watching": (
            "day_rvol_min", "rvol15_min", "rvol30_min",
            "abs_price5_pct_min", "abs_price15_pct_min",
        ),
        "positive_flow.flow_appearing": (
            "rvol15_min", "rvol30_min", "price5_pct_min",
            "price15_pct_min", "day_rvol_min",
        ),
        "positive_flow.flow_price_confirmed": (
            "rvol30_min", "price15_pct_min", "day_rvol_min",
        ),
        "positive_flow.momentum_maintained": (
            "rvol30_min", "price15_pct_floor", "retain_recent_high_pct_max",
        ),
        "negative_flow.momentum_weakening": (
            "price5_pct_max", "price15_pct_max", "rvol30_min",
            "loss_from_recent_high_pct_min",
        ),
        "negative_flow.selling_pressure": (
            "rvol15_min", "rvol30_min", "price5_pct_max",
            "price15_pct_max", "day_rvol_min",
        ),
        "negative_flow.shock": ("rvol15_min", "price5_pct_max"),
        "opening_auction.thresholds": (
            "opening_rvol_watch_min", "opening_rvol_strong_min",
            "positive_gap_watch_pct", "positive_gap_strong_pct",
            "negative_gap_watch_pct", "negative_gap_strong_pct",
            "neutral_gap_abs_pct_max",
        ),
        "closing_auction.thresholds": (
            "closing_rvol_watch_min", "closing_rvol_strong_min",
            "closing_volume_share_watch_pct", "closing_volume_share_strong_pct",
            "positive_price_impact_watch_pct", "positive_price_impact_strong_pct",
            "negative_price_impact_watch_pct", "negative_price_impact_strong_pct",
            "neutral_price_impact_abs_pct_max",
        ),
    }
    for dotted, keys in required.items():
        current: Any = raw
        for part in dotted.split("."):
            current = _mapping(current, dotted).get(part)
        section = _mapping(current, dotted)
        for key in keys:
            _number(section, key, dotted)


def validate_signal_config(raw: Mapping[str, Any]) -> SignalConfig:
    if raw.get("config_version") != EXPECTED_CONFIG_VERSION:
        raise SignalConfigError("unexpected config_version")
    if raw.get("engine_version") != EXPECTED_ENGINE_VERSION:
        raise SignalConfigError("unexpected engine_version")
    locked = _mapping(raw.get("locked_rules"), "locked_rules")
    exact = locked.get("exact_previous_sessions")
    if exact != 10 or locked.get("allow_11th_session_substitution") is not False:
        raise SignalConfigError("exact previous-session rules are invalid")
    contract = _mapping(raw.get("contract"), "contract")
    contract_version = contract.get("signal_contract_version")
    if contract_version != "ccc-state-v1":
        raise SignalConfigError("unexpected signal contract version")

    state_model = _mapping(raw.get("state_model"), "state_model")
    states_raw = _mapping(state_model.get("states"), "state_model.states")
    if tuple(states_raw.keys()) != EXPECTED_STATES:
        raise SignalConfigError("state names or order do not match the locked model")
    states: dict[str, StateDefinition] = {}
    for name in EXPECTED_STATES:
        item = _mapping(states_raw[name], f"state_model.states.{name}")
        level = item.get("level")
        direction = item.get("direction")
        summary = item.get("summary_vi")
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 4:
            raise SignalConfigError(f"invalid level for {name}")
        if direction not in EXPECTED_DIRECTIONS:
            raise SignalConfigError(f"invalid direction for {name}")
        if (level, direction) != EXPECTED_STATE_META[name]:
            raise SignalConfigError(f"locked level/direction changed for {name}")
        if not isinstance(summary, str) or not summary.strip():
            raise SignalConfigError(f"missing Vietnamese summary for {name}")
        states[name] = StateDefinition(level, direction, summary)

    priority = tuple(state_model.get("evaluation_priority") or ())
    if priority != EXPECTED_PRIORITY:
        raise SignalConfigError("evaluation priority does not match the locked model")
    positive = frozenset(state_model.get("positive_previous_states") or ())
    if not positive or not positive <= set(EXPECTED_STATES):
        raise SignalConfigError("positive_previous_states is invalid")

    quality = _mapping(raw.get("quality"), "quality")
    if quality.get("required_baseline_sessions") != exact:
        raise SignalConfigError("quality baseline requirement does not match exact-10")
    if (
        quality.get("require_metrics_trusted_for_strong_signal") is not True
        or quality.get("strong_signal_requires_exact_baseline") is not True
    ):
        raise SignalConfigError("strong-signal quality gates must remain enabled")
    degraded = _mapping(quality.get("degraded_behavior"), "quality.degraded_behavior")
    expected_degraded = {
        "allow_normal": True,
        "allow_watching": True,
        "allow_strong_positive_signal": False,
        "allow_selling_pressure": False,
    }
    if any(degraded.get(key) is not value for key, value in expected_degraded.items()):
        raise SignalConfigError("degraded quality behavior is invalid")
    for section_name in ("opening_auction", "closing_auction"):
        section = _mapping(raw.get(section_name), section_name)
        baseline = _mapping(section.get("baseline"), f"{section_name}.baseline")
        if baseline.get("required_sessions") != exact:
            raise SignalConfigError(f"{section_name} baseline must require exact-10")
        allowed = baseline.get("allowed_quality")
        if not isinstance(allowed, list) or not allowed:
            raise SignalConfigError(f"{section_name} allowed_quality is invalid")

    reasons = _mapping(raw.get("reason_codes"), "reason_codes")
    reason_order = tuple(reasons.get("deterministic_order") or ())
    if len(reason_order) != len(set(reason_order)) or not reason_order:
        raise SignalConfigError("reason code order must be non-empty and unique")
    _validate_thresholds(raw)
    return SignalConfig(
        config_version=str(raw["config_version"]),
        engine_version=str(raw["engine_version"]),
        contract_version=str(contract_version),
        exact_previous_sessions=int(exact),
        states=MappingProxyType(states),
        evaluation_priority=priority,
        positive_previous_states=positive,
        reason_code_order=reason_order,
        raw=MappingProxyType(dict(raw)),
    )


def load_signal_config(path: Path | str = CONFIG_PATH) -> SignalConfig:
    canonical = Path(path)
    if not canonical.is_file():
        raise SignalConfigError(f"canonical signal config is missing: {canonical}")
    try:
        parsed = yaml.safe_load(canonical.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SignalConfigError(f"cannot load canonical signal config: {canonical}") from exc
    return validate_signal_config(_mapping(parsed, "root"))
