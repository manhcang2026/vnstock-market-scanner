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


def test_public_market_readers_use_canonical_shards_without_hot_fallback() -> None:
    compose = (SERVICE_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    chart = compose.split("  chart-api:", 1)[1].split("  live-ws:", 1)[0]
    live = compose.split("  live-ws:", 1)[1]
    collector = compose.split("  chart-api:", 1)[0]

    for service in (chart, live):
        assert "--canonical-market-dir" in service
        assert "/app/data" in service
        assert "./data:/app/data:ro" in service
        assert "ssi_shadow.db" not in service
        assert "--realtime" not in service
    assert "DATABASE_PATH: /app/data/ssi_shadow.db" in collector


@pytest.mark.parametrize("name", ["VOLUME_ENGINE_ENABLED", "LIVE_STATE_ENABLED"])
def test_invalid_retired_flag_is_rejected(name: str) -> None:
    with pytest.raises(RuntimeError, match=f"Invalid boolean environment variable {name}"):
        validate_collector_startup(_settings(), environ={name: "typo"})


@pytest.mark.parametrize("engine,signal", [(False, True), (True, False), (False, False)])
def test_main_rejects_disabled_canonical_flags_before_opening_storage(
    monkeypatch: pytest.MonkeyPatch, engine: bool, signal: bool
) -> None:
    monkeypatch.delenv("VOLUME_ENGINE_ENABLED", raising=False)
    monkeypatch.delenv("LIVE_STATE_ENABLED", raising=False)
    monkeypatch.setattr(
        main_module.Settings, "from_env", lambda: _settings(engine=engine, signal=signal)
    )
    def unexpected_storage(*args: object, **kwargs: object) -> None:
        pytest.fail("Invalid production configuration must not open storage")
    monkeypatch.setattr(main_module, "SQLiteStore", unexpected_storage)
    monkeypatch.setattr(main_module, "CanonicalMarketStore", unexpected_storage)
    with pytest.raises(RuntimeError, match="CANONICAL_COLLECTOR_CONFIGURATION_REQUIRED"):
        main_module.main()


def test_retired_executable_modules_and_service_files_are_absent() -> None:
    for name in (
        "live_state_runtime", "live_runtime_harness", "stock_state_build",
        "live_ready_check", "daily_finalize", "volume_baseline_build",
        "historical_bootstrap", "realtime_volume", "stock_state_current",
    ):
        assert not (SERVICE_ROOT / "app" / f"{name}.py").exists()
    systemd = SERVICE_ROOT / "ops" / "systemd"
    assert not list(systemd.glob("ccc-ssi-daily-finalize*"))


def test_active_canonical_entrypoints_have_no_v2_paths() -> None:
    paths = [SERVICE_ROOT / "app" / name for name in (
        "main.py", "settings.py", "collector.py", "canonical_live_engine.py",
        "canonical_state_reader.py", "canonical_eod.py", "canonical_premarket.py",
        "rebuild_engine.py",
    )]
    paths += list((SERVICE_ROOT / "ops" / "systemd").glob("ccc-canonical-*"))
    for path in paths:
        source = path.read_text(encoding="utf-8")
        for forbidden in (
            "MARKET_V2_DATABASE_PATH", "VOLUME_BASELINE_PATH", "SSI_HISTORY_PATH",
            "ccc_market_v2.db", "ccc_v2_baseline.db", "LiveStateRuntime",
            "RealtimeVolumeEngine", "ccc-ssi-daily-finalize",
        ):
            assert forbidden not in source, (path.name, forbidden)
