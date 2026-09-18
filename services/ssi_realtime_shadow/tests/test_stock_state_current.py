from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime
from types import MappingProxyType

import pytest

from app.daily_ma import MAResult
from app.market_session import VN_TZ, classify_market_session
from app.market_storage_schema import ensure_market_storage_schema
from app.price_momentum import PriceMomentum
from app.realtime_volume import VolumeSnapshot
from app.stock_state_current import (
    SIGNAL_SUMMARY_VI,
    LatestQuote,
    project_stock_state,
    upsert_stock_state_current,
)


DATE = "2026-09-18"
AT = datetime(2026, 9, 18, 9, 30, tzinfo=VN_TZ)


def _quote() -> LatestQuote:
    return LatestQuote(
        symbol="HPG",
        exchange="HOSE",
        trading_date=DATE,
        event_at=AT,
        updated_at=AT.isoformat(),
        last_price=110,
        total_volume=1000,
        ref_price=100,
    )


def _ma(*, ready: bool = True) -> MAResult:
    return MAResult(
        symbol="HPG",
        as_of_date=DATE,
        ma10=100 if ready else None,
        ma200=90 if ready else None,
        ma10_sessions=10 if ready else 0,
        ma200_sessions=200 if ready else 0,
        latest_completed_session="2026-09-17" if ready else None,
        ma10_reason=None if ready else "INSUFFICIENT_SESSIONS:0/10",
        ma200_reason=None if ready else "INSUFFICIENT_SESSIONS:0/200",
    )


def _volume() -> VolumeSnapshot:
    return VolumeSnapshot(
        symbol="HPG",
        exchange="HOSE",
        trading_date=DATE,
        as_of_minute="09:29",
        cumulative_volume=1000,
        avg_cumulative_volume=500,
        day_rvol=2,
        volume_15=300,
        avg_volume_15=150,
        rvol_15=2,
        volume_30=None,
        avg_volume_30=None,
        rvol_30=None,
        opening_volume=100,
        avg_opening_volume=50,
        opening_rvol=2,
        historical_sessions=10,
        available_sessions=10,
        baseline_sessions_used=10,
        active_sessions_available=10,
        active_sessions_used=10,
        first_history_date="2026-09-04",
        last_history_date="2026-09-17",
        quality_status="TRUSTED",
        metrics_trusted=True,
        metric_availability=MappingProxyType({}),
        reasons=("OK",),
    )


def _project(
    volume: VolumeSnapshot | None,
    *,
    ma_ready: bool = True,
    baseline_coverage_proven: bool = False,
) -> dict[str, object]:
    return project_stock_state(
        quote=_quote(),
        session=classify_market_session("HOSE", AT),
        volume=volume,
        moving_averages=_ma(ready=ma_ready),
        price_momentum=PriceMomentum(1.0, None),
        baseline_coverage_proven=baseline_coverage_proven,
    )


@pytest.mark.parametrize(
    "volume",
    [
        replace(
            _volume(),
            baseline_sessions_used=9,
            active_sessions_used=9,
            metrics_trusted=True,
            reasons=("INSUFFICIENT_HISTORY",),
        ),
        replace(
            _volume(),
            baseline_sessions_used=0,
            active_sessions_used=0,
            metrics_trusted=True,
            reasons=("NO_BASELINE",),
        ),
        replace(
            _volume(),
            metrics_trusted=False,
            quality_status="GAP",
            reasons=("CURRENT_GAP", "CURRENT_PARTIAL", "NON_TRUSTED_QUALITY"),
        ),
        replace(_volume(), active_sessions_used=9),
    ],
)
def test_incomplete_or_untrusted_volume_never_claims_unified_trust(
    volume: VolumeSnapshot,
) -> None:
    projected = _project(volume)

    assert projected["metrics_trusted"] == 0
    assert projected["quality_status"] in {"DEGRADED", "UNAVAILABLE"}


def test_null_moving_averages_and_dependents_remain_null() -> None:
    projected = _project(_volume(), ma_ready=False)

    assert projected["ma10"] is None
    assert projected["ma200"] is None
    assert projected["distance_ma10_pct"] is None
    assert projected["distance_ma200_pct"] is None
    assert projected["above_ma10"] is None
    assert projected["above_ma200"] is None


def test_ready_moving_averages_and_distances_are_preserved() -> None:
    projected = _project(_volume(), ma_ready=True)
    assert projected["ma10"] == 100
    assert projected["ma200"] == 90
    assert projected["distance_ma10_pct"] == pytest.approx(10.0)
    assert projected["distance_ma200_pct"] == pytest.approx(22.222222)
    assert projected["above_ma10"] == 1
    assert projected["above_ma200"] == 1


def test_full_but_unproven_legacy_baseline_remains_degraded() -> None:
    assert _project(_volume())["metrics_trusted"] == 0
    assert _project(
        _volume(), baseline_coverage_proven=True
    )["metrics_trusted"] == 1


def test_upsert_keeps_one_row_and_watching_signal_creates_no_events() -> None:
    connection = sqlite3.connect(":memory:")
    ensure_market_storage_schema(connection, applied_at=AT)
    first = _project(_volume())
    upsert_stock_state_current(connection, first)
    second = dict(first)
    second["last_price"] = 111
    upsert_stock_state_current(connection, second)
    connection.commit()

    row = connection.execute(
        "SELECT last_price, signal_state, signal_level, signal_summary_vi "
        "FROM stock_state_current WHERE symbol='HPG'"
    ).fetchone()
    assert connection.execute("SELECT COUNT(*) FROM stock_state_current").fetchone()[0] == 1
    assert row == (
        111,
        "WATCHING",
        1,
        "Khối lượng đang tăng, tín hiệu giá chưa xác nhận.",
    )
    assert connection.execute("SELECT COUNT(*) FROM signal_events").fetchone()[0] == 0
