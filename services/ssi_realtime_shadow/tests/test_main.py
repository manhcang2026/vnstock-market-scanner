from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import main as main_module
from app.main import runtime_health, validate_collector_startup


SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _settings(*, engine: bool = True, signal: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        canonical_engine_enabled=engine,
        canonical_signal_enabled=signal,
    )


@pytest.mark.parametrize("name", ["VOLUME_ENGINE_ENABLED", "LIVE_STATE_ENABLED"])
@pytest.mark.parametrize("value", ["1", "true", "YES", "On"])
def test_retired_legacy_true_flags_fail_closed(name: str, value: str) -> None:
    with pytest.raises(
        RuntimeError,
        match=rf"LEGACY_V2_RUNTIME_RETIRED: {name}=true",
    ):
        validate_collector_startup(_settings(), environ={name: value})


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {"VOLUME_ENGINE_ENABLED": "false", "LIVE_STATE_ENABLED": "0"},
    ],
)
def test_retired_legacy_false_or_absent_flags_are_allowed(
    environ: dict[str, str],
) -> None:
    validate_collector_startup(_settings(), environ=environ)


@pytest.mark.parametrize(
    ("engine", "signal", "expected"),
    [
        (False, True, "CANONICAL_ENGINE_ENABLED=true"),
        (True, False, "CANONICAL_SIGNAL_ENABLED=true"),
    ],
)
def test_canonical_collector_flags_are_required(
    engine: bool, signal: bool, expected: str
) -> None:
    with pytest.raises(
        RuntimeError, match=f"CANONICAL_COLLECTOR_CONFIGURATION_REQUIRED: {expected}"
    ):
        validate_collector_startup(
            _settings(engine=engine, signal=signal), environ={}
        )


def test_runtime_health_contains_only_canonical_engine_fields() -> None:
    stats = SimpleNamespace(
        state_writes=12,
        calculation_errors=2,
        canonical_signal_initialized=True,
        canonical_signal_writes=9,
        canonical_signal_events=3,
        canonical_signal_errors=1,
    )
    engine = SimpleNamespace(stats=lambda: stats)

    health = runtime_health(_settings(), engine)  # type: ignore[arg-type]

    assert health == {
        "canonical_engine_enabled": True,
        "canonical_engine_initialized": True,
        "canonical_engine_writes": 12,
        "canonical_engine_errors": 2,
        "canonical_signal_enabled": True,
        "canonical_signal_initialized": True,
        "canonical_signal_writes": 9,
        "canonical_signal_events": 3,
        "canonical_signal_errors": 1,
    }
    assert not any(key.startswith("live_state_") for key in health)


def test_runtime_health_reports_nonfatal_engine_initialization_failure() -> None:
    health = runtime_health(_settings(), None)

    assert health["canonical_engine_initialized"] is False
    assert health["canonical_engine_errors"] == 1
    assert health["canonical_signal_initialized"] is False
    assert health["canonical_signal_errors"] == 1


def test_production_main_has_no_v2_runtime_or_volume_handler() -> None:
    source = inspect.getsource(main_module)

    for forbidden in (
        "RealtimeVolumeEngine",
        "LiveStateRuntime",
        "VolumeShadowQALogger",
        "_start_volume_shadow",
        "_volume_event_handler",
        "_advance_volume_shadow",
        "volume_event_handler=",
    ):
        assert forbidden not in source
    assert "canonical_store=canonical_store" in source
    assert "canonical_engine.mark_dirty" in source
    main_source = inspect.getsource(main_module.main)
    assert main_source.index("validate_collector_startup(settings)") < main_source.index(
        "SQLiteStore("
    )
    assert main_source.index("validate_collector_startup(settings)") < main_source.index(
        "from ssi_fc_data.fc_md_client import MarketDataClient"
    )


def test_collector_compose_is_canonical_and_has_no_legacy_paths() -> None:
    compose = (SERVICE_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    collector = compose.split("  chart-api:", 1)[0]
    example = (SERVICE_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "CANONICAL_MARKET_DIR: /app/data" in collector
    assert "CANONICAL_ENGINE_PATH: /app/data/ccc_engine.db" in collector
    assert 'CANONICAL_ENGINE_ENABLED: "true"' in collector
    assert 'CANONICAL_SIGNAL_ENABLED: "true"' in collector
    for forbidden in (
        "VOLUME_BASELINE_PATH",
        "MARKET_V2_DATABASE_PATH",
        "SSI_HISTORY_PATH",
        "VOLUME_ENGINE_ENABLED",
        "LIVE_STATE_ENABLED",
    ):
        assert forbidden not in collector
        assert forbidden not in example
    assert "CANONICAL_ENGINE_ENABLED=true" in example
    assert "CANONICAL_SIGNAL_ENABLED=true" in example


def test_legacy_daily_finalize_wrapper_is_retired_noop() -> None:
    systemd = SERVICE_ROOT / "ops" / "systemd"
    wrapper = (systemd / "ccc-ssi-daily-finalize-wrapper.sh").read_text(
        encoding="utf-8"
    )

    assert "RETIRED" in wrapper
    assert "ccc-canonical-eod" in wrapper
    assert "exit 0" in wrapper
    for forbidden in (
        "MARKET_V2_DATABASE_PATH",
        "SSI_HISTORY_PATH",
        "VOLUME_BASELINE_PATH",
        "app.daily_finalize",
        "app.volume_baseline_build",
        "app.historical_bootstrap",
        "docker exec",
    ):
        assert forbidden not in wrapper
    assert "RETIRED" in (
        systemd / "ccc-ssi-daily-finalize.service"
    ).read_text(encoding="utf-8")
    assert "RETIRED" in (
        systemd / "ccc-ssi-daily-finalize.timer"
    ).read_text(encoding="utf-8")
