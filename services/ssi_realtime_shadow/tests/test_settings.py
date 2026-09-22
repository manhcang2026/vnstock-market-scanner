from __future__ import annotations

from pathlib import Path

import pytest

from app.settings import ROOT, Settings


def _required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSI_CONSUMER_ID", "test-id")
    monkeypatch.setenv("SSI_CONSUMER_SECRET", "test-secret")
    monkeypatch.setenv("DATABASE_PATH", "fixtures/hot.db")
    monkeypatch.setenv("VOLUME_BASELINE_PATH", "fixtures/baseline.db")
    monkeypatch.setenv("MARKET_V2_DATABASE_PATH", "fixtures/market.db")
    monkeypatch.setenv("SSI_HISTORY_PATH", "fixtures/history.db")


def test_volume_shadow_defaults_disabled_with_explicit_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_env(monkeypatch)
    monkeypatch.delenv("VOLUME_ENGINE_ENABLED", raising=False)
    monkeypatch.delenv("VOLUME_SHADOW_SYMBOLS", raising=False)

    settings = Settings.from_env()

    assert not settings.volume_engine_enabled
    assert settings.volume_baseline_path == ROOT / "fixtures" / "baseline.db"
    assert settings.volume_shadow_symbols == ("HPG", "SHS", "VGI")


@pytest.mark.parametrize("enabled", ["1", "TRUE", "yes", "On"])
def test_volume_shadow_boolean_true_values(
    monkeypatch: pytest.MonkeyPatch, enabled: str
) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("VOLUME_ENGINE_ENABLED", enabled)

    assert Settings.from_env().volume_engine_enabled


def test_volume_shadow_settings_normalize_relative_path_and_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("VOLUME_BASELINE_PATH", "fixtures/baseline.db")
    monkeypatch.setenv("VOLUME_SHADOW_SYMBOLS", " hpg,SHS,hpg, vgi ")

    settings = Settings.from_env()

    assert settings.volume_baseline_path == ROOT / Path("fixtures/baseline.db")
    assert settings.volume_shadow_symbols == ("HPG", "SHS", "VGI")


def test_invalid_volume_shadow_boolean_fails_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("VOLUME_ENGINE_ENABLED", "sometimes")

    with pytest.raises(RuntimeError, match="VOLUME_ENGINE_ENABLED"):
        Settings.from_env()


def test_live_state_defaults_disabled_and_explicit_paths_resolve_under_service_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_env(monkeypatch)
    monkeypatch.delenv("LIVE_STATE_ENABLED", raising=False)

    settings = Settings.from_env()

    assert not settings.live_state_enabled
    assert settings.market_v2_database_path == ROOT / "fixtures/market.db"
    assert settings.ssi_history_path == ROOT / "fixtures/history.db"


@pytest.mark.parametrize(
    "name",
    ("DATABASE_PATH", "VOLUME_BASELINE_PATH", "MARKET_V2_DATABASE_PATH", "SSI_HISTORY_PATH"),
)
def test_database_paths_are_explicit_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    _required_env(monkeypatch)
    monkeypatch.delenv(name)

    with pytest.raises(RuntimeError, match=name):
        Settings.from_env()


def test_live_state_requires_volume_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("LIVE_STATE_ENABLED", "true")
    monkeypatch.setenv("VOLUME_ENGINE_ENABLED", "false")

    with pytest.raises(RuntimeError, match="requires VOLUME_ENGINE_ENABLED"):
        Settings.from_env()


def test_live_paths_use_service_path_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    _required_env(monkeypatch)
    monkeypatch.setenv("MARKET_V2_DATABASE_PATH", "fixtures/market.db")
    monkeypatch.setenv("SSI_HISTORY_PATH", "fixtures/history.db")

    settings = Settings.from_env()

    assert settings.market_v2_database_path == ROOT / "fixtures/market.db"
    assert settings.ssi_history_path == ROOT / "fixtures/history.db"
