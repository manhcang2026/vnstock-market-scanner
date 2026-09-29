from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import canonical_eod as eod_module
from app import canonical_premarket as premarket_module
from app.canonical_eod import EodTargetResolution
from app.settings import Settings


LEGACY_PATH_ENV = (
    "MARKET_V2_DATABASE_PATH",
    "VOLUME_BASELINE_PATH",
    "SSI_HISTORY_PATH",
)


def _canonical_metadata_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "metadata-key")
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    for name in LEGACY_PATH_ENV:
        monkeypatch.delenv(name, raising=False)


def _stub_exchange_map(monkeypatch: pytest.MonkeyPatch, module: object) -> None:
    def load(config: object) -> dict[str, str]:
        assert getattr(config, "supabase_url") == "https://example.supabase.co"
        assert getattr(config, "supabase_key") == "metadata-key"
        return {"AAA": "HOSE"}

    monkeypatch.setattr(module, "load_exchange_map", load)


def test_eod_resolve_target_needs_no_legacy_or_ssi_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _canonical_metadata_env(monkeypatch)
    monkeypatch.delenv("SSI_CONSUMER_ID", raising=False)
    monkeypatch.delenv("SSI_CONSUMER_SECRET", raising=False)
    _stub_exchange_map(monkeypatch, eod_module)
    monkeypatch.setattr(
        eod_module,
        "resolve_eod_target",
        lambda **_: EodTargetResolution(
            status="SKIP_NO_EOD_TARGET", reason="NO_CANONICAL_LIVE_EVIDENCE"
        ),
    )

    assert eod_module.main(
        ["--resolve-target", "--db-dir", str(tmp_path)]
    ) == 0


def test_eod_execution_initializes_without_legacy_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _canonical_metadata_env(monkeypatch)
    monkeypatch.setenv("SSI_CONSUMER_ID", "ssi-id")
    monkeypatch.setenv("SSI_CONSUMER_SECRET", "ssi-secret")
    monkeypatch.setenv("SSI_AUTH_TYPE", "Bearer")
    monkeypatch.setenv("SSI_URL", "https://ssi.example/")
    _stub_exchange_map(monkeypatch, eod_module)
    captured: dict[str, object] = {}

    def client(**kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(eod_module, "SSIHistoricalClient", client)

    assert eod_module.main(
        ["--date", "2026-09-28", "--db-dir", str(tmp_path)]
    ) == 0
    assert captured == {
        "base_url": "https://ssi.example/",
        "consumer_id": "ssi-id",
        "consumer_secret": "ssi-secret",
        "auth_type": "Bearer",
        "request_interval": 0.5,
    }


def test_premarket_check_initializes_without_legacy_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _canonical_metadata_env(monkeypatch)
    _stub_exchange_map(monkeypatch, premarket_module)
    monkeypatch.setattr(premarket_module, "premarket_refusal_reason", lambda **_: None)

    assert premarket_module.main(
        ["check", "--date", "2026-09-28", "--db-dir", str(tmp_path)]
    ) == 0


def test_premarket_validate_initializes_without_legacy_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _canonical_metadata_env(monkeypatch)
    _stub_exchange_map(monkeypatch, premarket_module)
    monkeypatch.setattr(
        premarket_module,
        "validate_rebuild",
        lambda **_: {
            "technical_baseline": 1,
            "volume_baseline_curve": 1,
            "current_state": 1,
        },
    )

    assert premarket_module.main(
        [
            "validate",
            "--date",
            "2026-09-28",
            "--engine-db",
            str(tmp_path / "ccc_engine.db"),
        ]
    ) == 0


@pytest.mark.parametrize("missing", LEGACY_PATH_ENV)
def test_collector_settings_still_require_legacy_paths(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setenv("SSI_CONSUMER_ID", "ssi-id")
    monkeypatch.setenv("SSI_CONSUMER_SECRET", "ssi-secret")
    monkeypatch.setenv("DATABASE_PATH", "data/hot.db")
    monkeypatch.setenv("MARKET_V2_DATABASE_PATH", "data/market.db")
    monkeypatch.setenv("VOLUME_BASELINE_PATH", "data/baseline.db")
    monkeypatch.setenv("SSI_HISTORY_PATH", "data/history.db")
    monkeypatch.delenv(missing)

    with pytest.raises(RuntimeError, match=missing):
        Settings.from_env()


def test_canonical_modules_and_wrappers_contain_no_legacy_path_dependencies() -> None:
    service_root = Path(__file__).resolve().parents[1]
    paths = (
        service_root / "app" / "canonical_eod.py",
        service_root / "app" / "canonical_premarket.py",
        service_root / "ops" / "systemd" / "ccc-canonical-eod-wrapper.sh",
        service_root / "ops" / "systemd" / "ccc-canonical-premarket-wrapper.sh",
    )
    forbidden = LEGACY_PATH_ENV + ("Settings.from_env",)
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert all(value not in content for value in forbidden), path
