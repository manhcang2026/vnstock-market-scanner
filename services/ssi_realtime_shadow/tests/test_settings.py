from __future__ import annotations

from pathlib import Path

import pytest

from app.settings import ROOT, Settings


LEGACY_ENV = (
    "VOLUME_BASELINE_PATH",
    "MARKET_V2_DATABASE_PATH",
    "SSI_HISTORY_PATH",
)


def _required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSI_CONSUMER_ID", "test-id")
    monkeypatch.setenv("SSI_CONSUMER_SECRET", "test-secret")
    monkeypatch.setenv("DATABASE_PATH", "fixtures/hot.db")
    for name in LEGACY_ENV:
        monkeypatch.delenv(name, raising=False)


def test_settings_construct_without_legacy_database_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_env(monkeypatch)

    settings = Settings.from_env()

    assert settings.database_path == Path("fixtures/hot.db")
    assert settings.canonical_market_dir == ROOT / "data"
    assert settings.canonical_engine_path == ROOT / "data" / "ccc_engine.db"
    assert not settings.canonical_engine_enabled
    assert not settings.canonical_signal_enabled
    for retired in (
        "volume_engine_enabled",
        "live_state_enabled",
        "volume_baseline_path",
        "market_v2_database_path",
        "ssi_history_path",
        "volume_shadow_symbols",
    ):
        assert not hasattr(settings, retired)


def test_retired_flags_do_not_break_offline_settings_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("VOLUME_ENGINE_ENABLED", "true")
    monkeypatch.setenv("LIVE_STATE_ENABLED", "true")

    settings = Settings.from_env()

    assert settings.database_path == Path("fixtures/hot.db")


def test_database_path_remains_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.delenv("DATABASE_PATH")

    with pytest.raises(RuntimeError, match="DATABASE_PATH"):
        Settings.from_env()


def test_canonical_collector_settings_parse_explicit_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("CANONICAL_MARKET_DIR", "fixtures/market")
    monkeypatch.setenv("CANONICAL_ENGINE_PATH", "fixtures/canonical-engine.db")
    monkeypatch.setenv("CANONICAL_ENGINE_ENABLED", "true")
    monkeypatch.setenv("CANONICAL_SIGNAL_ENABLED", "true")

    settings = Settings.from_env()

    assert settings.canonical_market_dir == ROOT / "fixtures" / "market"
    assert settings.canonical_engine_path == ROOT / "fixtures" / "canonical-engine.db"
    assert settings.canonical_engine_enabled
    assert settings.canonical_signal_enabled


@pytest.mark.parametrize(
    "name", ("CANONICAL_ENGINE_ENABLED", "CANONICAL_SIGNAL_ENABLED")
)
def test_invalid_canonical_boolean_fails_deterministically(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv(name, "sometimes")

    with pytest.raises(RuntimeError, match=name):
        Settings.from_env()
