from __future__ import annotations

from pathlib import Path

import pytest

from app.settings import ROOT, Settings


def _required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSI_CONSUMER_ID", "test-id")
    monkeypatch.setenv("SSI_CONSUMER_SECRET", "test-secret")


def test_volume_shadow_defaults_disabled_with_service_data_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _required_env(monkeypatch)
    monkeypatch.delenv("VOLUME_ENGINE_ENABLED", raising=False)
    monkeypatch.delenv("VOLUME_BASELINE_PATH", raising=False)
    monkeypatch.delenv("VOLUME_SHADOW_SYMBOLS", raising=False)

    settings = Settings.from_env()

    assert not settings.volume_engine_enabled
    assert settings.volume_baseline_path == ROOT / "data" / "ccc_v2_baseline.db"
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
