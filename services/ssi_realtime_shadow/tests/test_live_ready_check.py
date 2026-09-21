from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import app.live_ready_check as readiness_module

from app.live_ready_check import inspect_live_readiness, main
from app.storage import SQLiteStore
from tests.test_live_state_runtime import DAY, _baseline, _market


def _fixture(
    tmp_path: Path, *, baseline_day: str = DAY, sessions: int = 10
) -> dict[str, Path]:
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
    _baseline(paths["baseline_db"], day=baseline_day, sessions=sessions)
    return paths


def test_ready_fixture_reports_locked_versions_and_ato_partial_warning(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)

    report = inspect_live_readiness(target_trading_date=DAY, **paths)

    assert report["blocking_errors"] == []
    assert report["ready_for_live_signal"] is True
    assert report["contract_version"] == "ccc-state-v1"
    assert report["config_version"] == "cfg-20260922-beta-002"
    assert report["engine_version"] == "2.0.1-beta"
    assert report["market_schema_version"] == 3
    assert report["baseline_symbols_exact10"] == 1
    assert report["baseline_symbols_usable"] == 1
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


@pytest.mark.parametrize("sessions", (9, 8))
def test_accepted_partial_baseline_is_ready_for_live_signal(
    tmp_path: Path, sessions: int
) -> None:
    paths = _fixture(tmp_path, sessions=sessions)

    report = inspect_live_readiness(target_trading_date=DAY, **paths)

    assert report["blocking_errors"] == []
    assert report["ready_for_live_signal"] is True
    assert report["baseline_symbols_exact10"] == 0
    assert report[f"baseline_symbols_accepted{sessions}"] == 1
    assert report["baseline_symbols_usable"] == 1


def test_many_symbols_share_one_candidate_session_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path)
    market = sqlite3.connect(paths["market_db"])
    for symbol in ("AAA", "BBB"):
        market.execute(
            """
            INSERT INTO daily_bars (
                symbol,trading_date,exchange,open,high,low,close,volume,value,
                source,quality_status,finalized_at
            )
            SELECT ?,trading_date,exchange,open,high,low,close,volume,value,
                   source,quality_status,finalized_at
            FROM daily_bars WHERE symbol='SHS'
            """,
            (symbol,),
        )
    market.commit()
    market.close()

    calls = {"loader": 0, "ato": 0, "atc": 0}
    real_loader = readiness_module.load_candidate_market_sessions
    real_ato = readiness_module.read_ato_exact10
    real_atc = readiness_module.read_atc_exact10

    def counted_loader(*args, **kwargs):
        calls["loader"] += 1
        return real_loader(*args, **kwargs)

    def counted_ato(*args, **kwargs):
        calls["ato"] += 1
        assert isinstance(kwargs["candidate_dates"], tuple)
        return real_ato(*args, **kwargs)

    def counted_atc(*args, **kwargs):
        calls["atc"] += 1
        assert isinstance(kwargs["candidate_dates"], tuple)
        return real_atc(*args, **kwargs)

    monkeypatch.setattr(
        readiness_module, "load_candidate_market_sessions", counted_loader
    )
    monkeypatch.setattr(readiness_module, "read_ato_exact10", counted_ato)
    monkeypatch.setattr(readiness_module, "read_atc_exact10", counted_atc)

    report = inspect_live_readiness(target_trading_date=DAY, **paths)

    assert report["daily_symbols_total"] == 3
    assert calls == {"loader": 1, "ato": 3, "atc": 3}
    assert report["blocking_errors"] == []
    assert "ATO_EXACT10_PARTIAL_EXPECTED:no_historical_bootstrap" in report["warnings"]


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
