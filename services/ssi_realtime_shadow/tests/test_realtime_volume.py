from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app.market_session import VN_TZ
from app.realtime_volume import (
    BaselineValidationError,
    RealtimeVolumeEngine,
    VolumeEvent,
    load_volume_baseline,
)
from app.volume_baseline import BASELINE_SCHEMA, volume_market_grid


def _write_baseline(
    path: Path,
    *,
    symbols: tuple[tuple[str, str | None, int, int], ...] = (
        ("HPG", "HOSE", 10, 8),
        ("SHS", "HNX", 10, 7),
        ("VGI", "UPCOM", 10, 6),
    ),
    schema_version: int = 2,
    lookback: int = 10,
    day_denominator: float = 100.0,
    rvol15_denominator: float = 15.0,
    rvol30_denominator: float = 30.0,
    opening_denominator: float = 10.0,
) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(BASELINE_SCHEMA)
    connection.executemany(
        "INSERT INTO volume_baseline_metadata(key, value) VALUES (?, ?)",
        (("schema_version", str(schema_version)), ("lookback", str(lookback))),
    )
    for symbol, exchange, sessions, active_sessions in symbols:
        connection.execute(
            """
            INSERT INTO volume_baseline_coverage (
                symbol, exchange, available_sessions, baseline_sessions_used,
                active_sessions_available, active_sessions_used,
                first_history_date, last_history_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                exchange,
                sessions,
                sessions,
                active_sessions,
                active_sessions,
                "2026-08-31" if sessions else None,
                "2026-09-11" if sessions else None,
            ),
        )
        if exchange is None or sessions == 0:
            continue
        connection.executemany(
            """
            INSERT INTO volume_baseline (
                symbol, exchange, minute, session_segment,
                historical_sessions, avg_cumulative_volume,
                avg_volume_15, avg_volume_30, avg_opening_volume
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    symbol,
                    exchange,
                    point.minute,
                    point.session_segment,
                    sessions,
                    day_denominator,
                    rvol15_denominator if point.rolling_15_ready else None,
                    rvol30_denominator if point.rolling_30_ready else None,
                    opening_denominator if point.is_opening else None,
                )
                for point in volume_market_grid(exchange)
            ],
        )
    connection.commit()
    connection.close()


def _event(
    symbol: str,
    exchange: str,
    minute: str,
    volume_delta: int,
    *,
    trading_date: str = "2026-09-14",
    total_volume: int | None = None,
    quality_status: str = "TRUSTED",
    is_partial: bool = False,
    has_gap: bool = False,
) -> VolumeEvent:
    event_time = datetime.fromisoformat(f"{trading_date}T{minute}:30").replace(
        tzinfo=VN_TZ
    )
    return VolumeEvent(
        symbol=symbol,
        exchange=exchange,
        trading_date=trading_date,
        event_time=event_time,
        minute=minute,
        volume_delta=volume_delta,
        total_volume=total_volume,
        quality_status=quality_status,
        is_partial=is_partial,
        has_gap=has_gap,
    )


def _at(minute: str, trading_date: str = "2026-09-14") -> datetime:
    return datetime.fromisoformat(f"{trading_date}T{minute}:00").replace(tzinfo=VN_TZ)


def test_loads_schema_v2_baseline_as_immutable_memory_snapshot(
    tmp_path: Path,
) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)

    baseline = load_volume_baseline(path)

    assert baseline.schema_version == 2
    assert baseline.lookback == 10
    assert baseline.coverage["SHS"].active_sessions_used == 7
    assert baseline.points[("HPG", "09:30")].avg_volume_15 == 15
    with pytest.raises(TypeError):
        baseline.coverage["NEW"] = baseline.coverage["SHS"]  # type: ignore[index]


def test_wrong_schema_version_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path, schema_version=1)

    with pytest.raises(BaselineValidationError, match="schema_version=1"):
        load_volume_baseline(path)


def test_duplicate_baseline_key_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path, symbols=(("SHS", "HNX", 10, 7),))
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE volume_baseline RENAME TO original_baseline")
    connection.execute(
        "CREATE TABLE volume_baseline AS SELECT * FROM original_baseline"
    )
    connection.execute(
        "INSERT INTO volume_baseline SELECT * FROM original_baseline LIMIT 1"
    )
    connection.execute("DROP TABLE original_baseline")
    connection.commit()
    connection.close()

    with pytest.raises(BaselineValidationError, match="Duplicate volume baseline key"):
        load_volume_baseline(path)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("exchange", "HSX", "Non-canonical exchange"),
        ("minute", "25:00", "Malformed minute"),
    ],
)
def test_malformed_baseline_exchange_or_minute_fails(
    tmp_path: Path, column: str, value: str, message: str
) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path, symbols=(("HPG", "HOSE", 10, 8),))
    connection = sqlite3.connect(path)
    connection.execute(
        f"UPDATE volume_baseline SET {column}=? WHERE rowid=(SELECT MIN(rowid) FROM volume_baseline)",
        (value,),
    )
    connection.commit()
    connection.close()

    with pytest.raises(BaselineValidationError, match=message):
        load_volume_baseline(path)


def test_reload_success_atomically_swaps_baseline(tmp_path: Path) -> None:
    first_path = tmp_path / "first.db"
    second_path = tmp_path / "second.db"
    _write_baseline(first_path, day_denominator=100)
    _write_baseline(second_path, day_denominator=200)
    engine = RealtimeVolumeEngine(first_path)
    original = engine.baseline
    engine.on_event(_event("SHS", "HNX", "09:00", 100))
    engine.advance_time(_at("09:01"))
    assert engine.get_snapshot("SHS").day_rvol == 1

    replacement = engine.reload_baseline(second_path)

    assert engine.baseline is replacement
    assert engine.baseline is not original
    assert engine.baseline.points[("SHS", "09:14")].avg_cumulative_volume == 200
    assert engine.get_snapshot("SHS").day_rvol == 0.5


def test_reload_failure_keeps_previous_baseline(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    bad_path = tmp_path / "bad.db"
    _write_baseline(path)
    _write_baseline(bad_path, schema_version=99)
    engine = RealtimeVolumeEngine(path)
    original = engine.baseline

    with pytest.raises(BaselineValidationError):
        engine.reload_baseline(bad_path)

    assert engine.baseline is original


def test_event_exchange_must_match_trusted_baseline_exchange(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)

    with pytest.raises(ValueError, match="conflicts with baseline"):
        engine.on_event(_event("HPG", "HNX", "09:00", 1))


def test_trading_date_change_resets_intraday_symbol_state(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)
    engine.on_event(_event("SHS", "HNX", "09:00", 100))
    engine.advance_time(_at("09:15"))
    assert engine.get_snapshot("SHS").cumulative_volume == 100

    reset = engine.on_event(
        _event("SHS", "HNX", "09:00", 5, trading_date="2026-09-15")
    )
    assert reset.trading_date == "2026-09-15"
    assert reset.as_of_minute is None
    assert reset.cumulative_volume == 0
    engine.advance_time(_at("09:01", "2026-09-15"))
    assert engine.get_snapshot("SHS").cumulative_volume == 5


def test_hose_opening_bucket_is_excluded_from_rolling_volume(
    tmp_path: Path,
) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)
    engine.on_event(_event("HPG", "HOSE", "09:05", 10))
    opening = engine.on_event(_event("HPG", "HOSE", "09:16", 15))
    assert opening.as_of_minute == "09:15"
    assert opening.opening_volume == 10
    assert opening.opening_rvol == 1
    engine.advance_time(_at("09:31"))
    rolling = engine.get_snapshot("HPG")
    assert rolling.as_of_minute == "09:30"
    assert rolling.volume_15 == 15
    assert rolling.cumulative_volume == 25


def test_hose_close_bucket_updates_day_but_not_rolling_volume(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)
    engine.on_event(_event("HPG", "HOSE", "14:29", 15))
    before_close = engine.on_event(_event("HPG", "HOSE", "14:30", 50))
    assert before_close.as_of_minute == "14:29"
    assert before_close.volume_15 == 15

    engine.advance_time(_at("14:46"))

    at_close = engine.get_snapshot("HPG")
    assert at_close.as_of_minute == "14:45"
    assert at_close.cumulative_volume == 65
    assert at_close.volume_15 is None
    assert at_close.volume_30 is None


def test_hnx_first_completed_rvol15_and_rvol30_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)
    engine.on_event(_event("SHS", "HNX", "09:00", 15))

    engine.advance_time(_at("09:14"))
    assert engine.get_snapshot("SHS").as_of_minute == "09:13"
    assert engine.get_snapshot("SHS").rvol_15 is None
    engine.advance_time(_at("09:15"))
    at_fifteen = engine.get_snapshot("SHS")
    assert at_fifteen.as_of_minute == "09:14"
    assert at_fifteen.volume_15 == 15
    assert at_fifteen.rvol_15 == 1

    engine.advance_time(_at("09:29"))
    assert engine.get_snapshot("SHS").as_of_minute == "09:28"
    assert engine.get_snapshot("SHS").rvol_30 is None
    engine.advance_time(_at("09:30"))
    at_thirty = engine.get_snapshot("SHS")
    assert at_thirty.as_of_minute == "09:29"
    assert at_thirty.volume_30 == 15
    assert at_thirty.rvol_30 == 0.5


def test_hose_first_completed_rvol15_and_rvol30_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)
    engine.on_event(_event("HPG", "HOSE", "09:16", 30))

    engine.advance_time(_at("09:30"))
    assert engine.get_snapshot("HPG").as_of_minute == "09:29"
    assert engine.get_snapshot("HPG").rvol_15 is None
    engine.advance_time(_at("09:31"))
    assert engine.get_snapshot("HPG").as_of_minute == "09:30"
    assert engine.get_snapshot("HPG").volume_15 == 30

    engine.advance_time(_at("09:45"))
    assert engine.get_snapshot("HPG").as_of_minute == "09:44"
    assert engine.get_snapshot("HPG").rvol_30 is None
    engine.advance_time(_at("09:46"))
    assert engine.get_snapshot("HPG").as_of_minute == "09:45"
    assert engine.get_snapshot("HPG").volume_30 == 30


@pytest.mark.parametrize(("symbol", "exchange"), [("HPG", "HOSE"), ("SHS", "HNX"), ("VGI", "UPCOM")])
def test_pm_windows_reset_without_morning_stitching(
    tmp_path: Path, symbol: str, exchange: str
) -> None:
    path = tmp_path / f"{exchange}.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)
    morning_minute = "09:16" if exchange == "HOSE" else "09:00"
    engine.on_event(_event(symbol, exchange, morning_minute, 100))
    engine.advance_time(_at("11:30"))
    assert engine.get_snapshot(symbol).cumulative_volume == 100
    engine.on_event(_event(symbol, exchange, "13:00", 15))

    engine.advance_time(_at("13:14"))
    assert engine.get_snapshot(symbol).as_of_minute == "13:13"
    assert engine.get_snapshot(symbol).rvol_15 is None
    engine.advance_time(_at("13:15"))
    at_fifteen = engine.get_snapshot(symbol)
    assert at_fifteen.as_of_minute == "13:14"
    assert at_fifteen.cumulative_volume == 115
    assert at_fifteen.volume_15 == 15
    assert at_fifteen.rvol_15 == 1

    engine.advance_time(_at("13:29"))
    assert engine.get_snapshot(symbol).rvol_30 is None
    engine.advance_time(_at("13:30"))
    at_thirty = engine.get_snapshot(symbol)
    assert at_thirty.as_of_minute == "13:29"
    assert at_thirty.volume_30 == 15
    assert at_thirty.rvol_30 == 0.5


def test_advance_time_finalizes_zero_minutes_without_new_symbol_event(
    tmp_path: Path,
) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)
    engine.on_event(_event("SHS", "HNX", "09:00", 15))

    changed = engine.advance_time(_at("09:15"))

    snapshot = changed["SHS"]
    assert snapshot.as_of_minute == "09:14"
    assert snapshot.volume_15 == 15
    assert snapshot.cumulative_volume == 15


def test_day_and_rolling_zero_denominators_return_none_not_infinity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(
        path,
        symbols=(("SHS", "HNX", 10, 7),),
        day_denominator=0,
        rvol15_denominator=0,
        rvol30_denominator=0,
    )
    engine = RealtimeVolumeEngine(path)
    engine.on_event(_event("SHS", "HNX", "09:00", 15))
    engine.advance_time(_at("09:30"))

    snapshot = engine.get_snapshot("SHS")
    assert snapshot.day_rvol is None
    assert snapshot.rvol_15 is None
    assert snapshot.rvol_30 is None
    assert "ZERO_DAY_DENOMINATOR" in snapshot.reasons
    assert "ZERO_RVOL15_DENOMINATOR" in snapshot.reasons
    assert "ZERO_RVOL30_DENOMINATOR" in snapshot.reasons


def test_no_baseline_symbol_returns_safe_unavailable_metrics(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path, symbols=(("NOHIST", None, 0, 0),))
    engine = RealtimeVolumeEngine(path)
    engine.on_event(_event("NOHIST", "HNX", "09:00", 10))
    engine.advance_time(_at("09:30"))

    snapshot = engine.get_snapshot("NOHIST")
    assert snapshot.cumulative_volume == 10
    assert snapshot.day_rvol is None
    assert snapshot.rvol_15 is None
    assert snapshot.rvol_30 is None
    assert snapshot.baseline_sessions_used == 0
    assert "NO_BASELINE" in snapshot.reasons


@pytest.mark.parametrize(
    ("quality_status", "is_partial", "has_gap", "expected_reason"),
    [
        ("PARTIAL", True, False, "CURRENT_PARTIAL"),
        ("GAP", True, True, "CURRENT_GAP"),
        ("MISSING_TOTAL_VOLUME", False, False, "NON_TRUSTED_QUALITY"),
    ],
)
def test_gap_partial_and_nontrusted_quality_propagate_to_completed_metrics(
    tmp_path: Path,
    quality_status: str,
    is_partial: bool,
    has_gap: bool,
    expected_reason: str,
) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)
    engine.on_event(
        _event(
            "SHS",
            "HNX",
            "09:00",
            10,
            quality_status=quality_status,
            is_partial=is_partial,
            has_gap=has_gap,
        )
    )
    engine.advance_time(_at("09:15"))

    snapshot = engine.get_snapshot("SHS")
    assert snapshot.quality_status == quality_status
    assert not snapshot.metrics_trusted
    assert expected_reason in snapshot.reasons


def test_current_partial_minute_is_not_used_in_completed_rvol(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)
    engine.on_event(_event("SHS", "HNX", "09:00", 15))
    engine.advance_time(_at("09:15"))
    before = engine.get_snapshot("SHS")

    current = engine.on_event(
        _event(
            "SHS",
            "HNX",
            "09:15",
            999,
            quality_status="PARTIAL",
            is_partial=True,
        )
    )

    assert before.as_of_minute == "09:14"
    assert current.as_of_minute == "09:14"
    assert current.volume_15 == 15
    assert current.rvol_15 == 1
    assert current.quality_status == "PARTIAL"


def test_snapshot_exposes_baseline_and_active_session_coverage(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)
    engine.on_event(_event("SHS", "HNX", "09:00", 15))
    engine.advance_time(_at("09:15"))

    snapshot = engine.get_snapshot("SHS")
    assert snapshot.historical_sessions == 10
    assert snapshot.available_sessions == 10
    assert snapshot.baseline_sessions_used == 10
    assert snapshot.active_sessions_available == 7
    assert snapshot.active_sessions_used == 7
    assert snapshot.first_history_date == "2026-08-31"
    assert snapshot.last_history_date == "2026-09-11"


@pytest.mark.parametrize(
    "changes",
    [
        {"exchange": "HSX"},
        {"minute": "9:00"},
        {"volume_delta": -1},
        {"event_time": datetime(2026, 9, 14, 9, 1, tzinfo=VN_TZ)},
    ],
)
def test_volume_event_rejects_noncanonical_or_inconsistent_values(
    changes: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "symbol": "HPG",
        "exchange": "HOSE",
        "trading_date": "2026-09-14",
        "event_time": _at("09:00"),
        "minute": "09:00",
        "volume_delta": 0,
        "total_volume": 0,
        "quality_status": "TRUSTED",
    }
    values.update(changes)
    with pytest.raises(ValueError):
        VolumeEvent(**values)  # type: ignore[arg-type]


def test_get_all_snapshots_returns_only_initialized_symbols(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    _write_baseline(path)
    engine = RealtimeVolumeEngine(path)
    engine.on_event(_event("HPG", "HOSE", "09:16", 1))
    engine.on_event(_event("SHS", "HNX", "09:00", 1))

    snapshots = engine.get_all_snapshots()

    assert set(snapshots) == {"HPG", "SHS"}
    assert "VGI" not in snapshots
