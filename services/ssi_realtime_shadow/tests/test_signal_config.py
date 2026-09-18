from __future__ import annotations

from copy import deepcopy

import pytest
import yaml

from app.signal_config import (
    CONFIG_PATH,
    EXPECTED_PRIORITY,
    EXPECTED_STATES,
    SignalConfigError,
    load_signal_config,
    validate_signal_config,
)


def test_canonical_config_loads_and_locks_versions_states_and_quality() -> None:
    config = load_signal_config()
    assert config.config_version == "cfg-20260918-beta-001"
    assert config.engine_version == "2.0.0-beta"
    assert config.exact_previous_sessions == 10
    assert tuple(config.states) == EXPECTED_STATES
    assert config.evaluation_priority == EXPECTED_PRIORITY
    assert config.states["SELLING_PRESSURE"].direction == "BEARISH"
    assert config.raw["quality"]["strong_signal_requires_exact_baseline"] is True


@pytest.mark.parametrize(
    "mutation",
    (
        lambda raw: raw.update(config_version="wrong"),
        lambda raw: raw["state_model"].update(evaluation_priority=["NORMAL"]),
        lambda raw: raw["state_model"]["states"]["NORMAL"].update(direction="UP"),
        lambda raw: raw["quality"].update(required_baseline_sessions=9),
        lambda raw: raw["watching"].update(day_rvol_min="1.3"),
    ),
)
def test_malformed_config_fails_fast(mutation) -> None:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    mutation(raw)
    with pytest.raises(SignalConfigError):
        validate_signal_config(deepcopy(raw))


def test_missing_config_fails_instead_of_generating_replacement(tmp_path) -> None:
    with pytest.raises(SignalConfigError, match="missing"):
        load_signal_config(tmp_path / "does-not-exist.yaml")
