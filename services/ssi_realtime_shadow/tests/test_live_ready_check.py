from __future__ import annotations

from pathlib import Path

from app.live_ready_check import inspect_live_readiness, main
from app.storage import SQLiteStore
from tests.test_live_state_runtime import DAY, _baseline, _market


def _fixture(tmp_path: Path, *, baseline_day: str = DAY) -> dict[str, Path]:
    paths = {
        "hot_db": tmp_path / "hot.db",
        "market_db": tmp_path / "market.db",
        "history_db": tmp_path / "history.db",
        "baseline_db": tmp_path / "baseline.db",
    }
    hot = SQLiteStore(paths["hot_db"])
    hot.close()
    history = SQLiteStore(paths["history_db"])
    history.close()
    _market(paths["market_db"])
    _baseline(paths["baseline_db"], day=baseline_day)
    return paths


def test_ready_fixture_reports_locked_versions_and_ato_partial_warning(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)

    report = inspect_live_readiness(target_trading_date=DAY, **paths)

    assert report["blocking_errors"] == []
    assert report["ready_for_live_signal"] is True
    assert report["contract_version"] == "ccc-state-v1"
    assert report["config_version"] == "cfg-20260918-beta-001"
    assert report["engine_version"] == "2.0.0-beta"
    assert report["market_schema_version"] == 3
    assert report["baseline_symbols_exact10"] == 1
    assert "ATO_EXACT10_PARTIAL_EXPECTED:no_historical_bootstrap" in report["warnings"]
    assert main([
        "--trading-date", DAY,
        "--hot-db", str(paths["hot_db"]),
        "--market-db", str(paths["market_db"]),
        "--history-db", str(paths["history_db"]),
        "--baseline-db", str(paths["baseline_db"]),
    ]) == 0


def test_stale_baseline_is_blocking(tmp_path: Path) -> None:
    paths = _fixture(tmp_path, baseline_day="2026-09-18")

    report = inspect_live_readiness(target_trading_date=DAY, **paths)

    assert "BASELINE_DATE_MISMATCH" in report["blocking_errors"]
    assert report["ready_for_live_signal"] is False


def test_missing_market_and_history_are_reported_without_masking(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    paths["market_db"].unlink()
    paths["history_db"].unlink()

    report = inspect_live_readiness(target_trading_date=DAY, **paths)

    assert "MARKET_DB_MISSING" in report["blocking_errors"]
    assert "HISTORY_DB_MISSING:auction_metrics_unavailable" in report["warnings"]
    assert report["history_db_exists"] is False
    assert report["auction_atc_exact10_symbols"] == 0
    assert report["ready_for_live_signal"] is False
