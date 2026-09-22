from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import pytest

from app.storage import SQLiteStore
from app.market_storage_schema import ensure_market_storage_schema
from app.realtime_volume import load_volume_baseline
from app.volume_baseline import (
    RawVolumeBar,
    SessionProof,
    build_symbol_volume_baseline,
    build_volume_baseline as _build_volume_baseline,
    prove_volume_session,
    select_volume_sessions,
    volume_market_grid,
)
from app.volume_baseline_build import build_parser


def _history_db(
    path: Path,
    bars: Iterable[tuple[str, str, str, str, int]],
    *,
    no_history_symbols: Iterable[str] = (),
) -> None:
    store = SQLiteStore(path)
    for symbol, exchange, trading_date, minute, volume in bars:
        store.insert_historical_bar(
            trading_date=trading_date,
            minute=minute,
            symbol=symbol,
            exchange=exchange,
            open_price=1,
            high=1,
            low=1,
            close=1,
            volume=volume,
            provider_time=f"{minute}:00",
            updated_at="fixed",
        )
    for symbol in no_history_symbols:
        store.mark_historical_checkpoint_running(
            symbol,
            "2026-08-17",
            "2026-09-11",
            1,
            "fixed",
        )
        store.mark_historical_checkpoint_failed(
            symbol,
            "2026-08-17",
            "2026-09-11",
            1,
            "NoDataFound",
            "fixed",
        )
    store.close()


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _daily_from_history(history: Path, daily: Path) -> str:
    source = sqlite3.connect(history)
    target = sqlite3.connect(daily)
    ensure_market_storage_schema(target)
    target.execute("DELETE FROM daily_bars")
    rows = source.execute(
        """
        SELECT symbol, trading_date, exchange, SUM(volume)
        FROM minute_bars GROUP BY symbol, trading_date, exchange
        """
    ).fetchall()
    target.executemany(
        """
        INSERT INTO daily_bars (
          symbol,trading_date,exchange,open,high,low,close,volume,value,
          source,quality_status,finalized_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [(*row[:3], 1, 1, 1, 1, row[3], None, "SSI_DAILY_OHLC", "TRUSTED", "fixed") for row in rows],
    )
    target.commit()
    latest = max(date.fromisoformat(str(row[1])) for row in rows)
    source.close()
    target.close()
    return (latest + timedelta(days=1)).isoformat()


def build_volume_baseline(*, history_db: Path, output_db: Path, **kwargs):
    daily_db = kwargs.pop("daily_db", output_db.with_name(output_db.stem + "-daily.db"))
    as_of_date = kwargs.pop("as_of_date", None)
    if as_of_date is None:
        as_of_date = _daily_from_history(history_db, daily_db)
    return _build_volume_baseline(
        history_db=history_db,
        daily_db=daily_db,
        output_db=output_db,
        as_of_date=as_of_date,
        **kwargs,
    )


def _weekdays(start: date, count: int) -> list[str]:
    values: list[str] = []
    current = start
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def _minimum_healthy_bars(
    bars: list[tuple[str, str, str, str, int]],
) -> list[tuple[str, str, str, str, int]]:
    """Repeat test session patterns across eight dates without changing averages."""
    patterns: dict[str, list[tuple[str, str, str, str, int]]] = {}
    for bar in bars:
        patterns.setdefault(bar[2], []).append(bar)
    source_dates = sorted(patterns)
    target_dates = _weekdays(date(2026, 8, 24), 8)
    result: list[tuple[str, str, str, str, int]] = []
    for index, trading_date in enumerate(target_dates):
        pattern = patterns[source_dates[index % len(source_dates)]]
        result.extend(
            (symbol, exchange, trading_date, minute, volume)
            for symbol, exchange, _, minute, volume in pattern
        )
    return result


def _selection_proof(
    trading_date: str,
    *,
    valid: bool = True,
    volume: int = 10,
    reason: str = "DAILY_MISSING",
) -> SessionProof:
    if not valid:
        return SessionProof("HPG", trading_date, None, None, 0, reason)
    return SessionProof(
        "HPG",
        trading_date,
        "HOSE",
        volume,
        volume,
        "PROVEN_ZERO" if volume == 0 else "PROVEN",
        ()
        if volume == 0
        else (RawVolumeBar(trading_date, "09:16", "HOSE", volume),),
    )


def test_hose_grid_separates_opening_continuous_and_close_buckets() -> None:
    points = volume_market_grid("HOSE")
    grid = {point.minute: point for point in points}
    assert len(points) == 226
    assert grid["09:15"].session_segment == "OPENING_BUCKET"
    assert not grid["09:15"].is_continuous
    assert grid["09:16"].session_segment == "AM_CONTINUOUS"
    assert grid["09:16"].is_continuous
    assert not grid["09:29"].rolling_15_ready
    assert grid["09:30"].rolling_15_ready
    assert not grid["09:44"].rolling_30_ready
    assert grid["09:45"].rolling_30_ready
    assert "11:30" not in grid
    assert not grid["13:13"].rolling_15_ready
    assert grid["13:14"].rolling_15_ready
    assert not grid["13:28"].rolling_30_ready
    assert grid["13:29"].rolling_30_ready
    assert "14:30" not in grid
    assert grid["14:45"].session_segment == "CLOSE_BUCKET"
    assert not grid["14:45"].is_continuous
    assert not grid["14:45"].rolling_15_ready


def test_hnx_and_upcom_grid_boundaries_follow_market_session_engine() -> None:
    hnx_points = volume_market_grid("HNX")
    upcom_points = volume_market_grid("UPCOM")
    hnx = {point.minute: point for point in hnx_points}
    upcom = {point.minute: point for point in upcom_points}
    assert len(hnx_points) == 241
    assert len(upcom_points) == 270
    assert hnx["09:00"].is_continuous
    assert not hnx["09:13"].rolling_15_ready
    assert hnx["09:14"].rolling_15_ready
    assert not hnx["09:28"].rolling_30_ready
    assert hnx["09:29"].rolling_30_ready
    assert "11:30" not in hnx
    assert "14:30" not in hnx
    assert hnx["14:45"].session_segment == "CLOSE_BUCKET"
    assert upcom["14:59"].is_continuous
    assert not upcom["09:13"].rolling_15_ready
    assert upcom["09:14"].rolling_15_ready
    assert not upcom["09:28"].rolling_30_ready
    assert upcom["09:29"].rolling_30_ready
    assert "11:30" not in upcom
    assert upcom["14:30"].is_continuous
    assert "15:00" not in upcom


def test_intraday_endpoint_grid_adds_noncontinuous_provider_boundaries() -> None:
    hose = {
        point.minute: point
        for point in volume_market_grid("HOSE", include_provider_boundaries=True)
    }
    hnx = {
        point.minute: point
        for point in volume_market_grid("HNX", include_provider_boundaries=True)
    }
    upcom = {
        point.minute: point
        for point in volume_market_grid("UPCOM", include_provider_boundaries=True)
    }

    for grid in (hose, hnx):
        for minute in ("11:30", "14:30"):
            assert grid[minute].session_segment == "PROVIDER_BOUNDARY"
            assert not grid[minute].is_continuous
            assert not grid[minute].rolling_15_ready
            assert not grid[minute].rolling_30_ready
    assert upcom["11:30"].session_segment == "PROVIDER_BOUNDARY"
    assert not upcom["11:30"].is_continuous
    assert upcom["14:30"].is_continuous


def test_volume_baseline_cli_accepts_sample_arguments() -> None:
    args = build_parser().parse_args(
        [
            "--history-db",
            "/app/data/ssi_history_v2.db",
            "--daily-db",
            "/app/data/ccc_market_v2.db",
            "--output-db",
            "/app/data/ccc_v2_baseline.db",
            "--as-of-date",
            "2026-09-18",
            "--lookback",
            "10",
            "--symbols",
            "HPG,SSI,VIX",
        ]
    )
    assert args.lookback == 10
    assert args.max_scan_sessions == 20
    assert args.symbols == ["HPG", "SSI", "VIX"]


def _selection(pattern: str, *, max_scan_sessions: int = 20):
    dates = list(reversed(_weekdays(date(2026, 8, 3), len(pattern))))
    proofs = [
        _selection_proof(trading_date, valid=marker == "V")
        for trading_date, marker in zip(dates, pattern)
    ]
    return select_volume_sessions(
        proofs,
        max_scan_sessions=max_scan_sessions,
    )


def test_exact_ten_healthy_sessions_are_full() -> None:
    selection = _selection("VVVVVVVVVV")

    assert len(selection.selected) == 10
    assert selection.coverage_tier == "FULL"
    assert selection.break_blocks == 0
    assert len(selection.scanned) == 10
    assert selection.stopped_reason == "TARGET_REACHED"


def test_one_isolated_broken_session_uses_an_older_valid_session() -> None:
    selection = _selection("VVVBVVVVVVV")

    assert len(selection.selected) == 10
    assert len(selection.skipped) == 1
    assert selection.break_blocks == 1
    assert selection.selected[-1].trading_date < selection.skipped[0].trading_date


def test_two_isolated_break_blocks_can_be_crossed() -> None:
    selection = _selection("VVBVVVBVVVVV")

    assert len(selection.selected) == 10
    assert len(selection.skipped) == 2
    assert selection.break_blocks == 2
    assert selection.stopped_reason == "TARGET_REACHED"


def test_third_separate_break_block_stops_selection() -> None:
    selection = _selection("VVBVVBVVBVVVV")

    assert len(selection.selected) == 6
    assert selection.break_blocks == 3
    assert selection.stopped_by_third_break_block
    assert len(selection.scanned) == 9


def test_third_break_block_makes_nine_selected_sessions_unusable() -> None:
    selection = _selection("VVVBVVVBVVVBVV")
    coverage, rows = build_symbol_volume_baseline(
        "HPG",
        selection,
        lookback=10,
        candidate_sessions=[proof.trading_date for proof in selection.scanned],
    )

    assert len(selection.selected) == 9
    assert selection.break_blocks == 3
    assert coverage.coverage_tier == "INSUFFICIENT"
    assert rows == []


def test_consecutive_bad_sessions_are_one_break_block() -> None:
    selection = _selection("VVBBBVVVVVVVV")

    assert len(selection.selected) == 10
    assert len(selection.skipped) == 3
    assert selection.break_blocks == 1
    assert selection.stopped_reason == "TARGET_REACHED"


@pytest.mark.parametrize(
    ("session_count", "expected_tier", "expect_rows"),
    [
        (9, "ACCEPTABLE", True),
        (8, "ACCEPTABLE_MINIMUM", True),
        (7, "INSUFFICIENT", False),
    ],
)
def test_coverage_tiers_control_usable_baseline_rows(
    session_count: int,
    expected_tier: str,
    expect_rows: bool,
) -> None:
    dates = list(reversed(_weekdays(date(2026, 8, 3), session_count)))
    selection = select_volume_sessions(
        [_selection_proof(item) for item in dates]
    )

    coverage, rows = build_symbol_volume_baseline(
        "HPG",
        selection,
        lookback=10,
        candidate_sessions=dates,
    )

    assert coverage.baseline_sessions_used == session_count
    assert coverage.coverage_tier == expected_tier
    assert bool(rows) is expect_rows
    if rows:
        assert {item.historical_sessions for item in rows} == {session_count}


def test_build_summary_reports_nine_and_eight_session_symbols(
    tmp_path: Path,
) -> None:
    history = tmp_path / "tier-summary-history.db"
    output = tmp_path / "tier-summary-baseline.db"
    dates = _weekdays(date(2026, 8, 24), 9)
    _history_db(
        history,
        [("HPG", "HOSE", item, "09:16", 10) for item in dates]
        + [("SHS", "HNX", item, "09:00", 20) for item in dates[1:]],
    )

    summary = build_volume_baseline(
        history_db=history,
        output_db=output,
        symbols=["HPG", "SHS"],
    )
    connection = _connect(output)
    coverage = {
        row["symbol"]: row
        for row in connection.execute(
            "SELECT * FROM volume_baseline_coverage ORDER BY symbol"
        )
    }
    row_counts = dict(
        connection.execute(
            "SELECT symbol, COUNT(*) FROM volume_baseline GROUP BY symbol"
        )
    )
    connection.close()

    assert summary.symbols_10_sessions == 0
    assert summary.symbols_9_sessions == 1
    assert summary.symbols_8_sessions == 1
    assert summary.symbols_under_8_sessions == 0
    assert summary.daily_missing_count == 1
    assert coverage["HPG"]["coverage_tier"] == "ACCEPTABLE"
    assert coverage["SHS"]["coverage_tier"] == "ACCEPTABLE_MINIMUM"
    assert coverage["SHS"]["break_blocks"] == 1
    assert row_counts["HPG"] > 0 and row_counts["SHS"] > 0


def test_selection_never_exceeds_max_scan_sessions() -> None:
    selection = _selection("VVVVVVVBBBVVVVVVVVVV", max_scan_sessions=10)

    assert len(selection.scanned) == 10
    assert len(selection.selected) == 7
    assert selection.exhausted_max_scan


def test_zero_volume_session_requires_trusted_daily_proof(tmp_path: Path) -> None:
    history_path = tmp_path / "zero-history.db"
    daily_path = tmp_path / "zero-daily.db"
    SQLiteStore(history_path).close()
    daily = sqlite3.connect(daily_path)
    ensure_market_storage_schema(daily)
    daily.execute(
        """
        INSERT INTO daily_bars (
          symbol,trading_date,exchange,open,high,low,close,volume,value,
          source,quality_status,finalized_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "HPG",
            "2026-09-10",
            "HOSE",
            1,
            1,
            1,
            1,
            0,
            None,
            "SSI_DAILY_OHLC",
            "TRUSTED",
            "fixed",
        ),
    )
    daily.commit()
    daily.close()

    history = _connect(history_path)
    daily = _connect(daily_path)
    try:
        proven_zero = prove_volume_session(
            history,
            daily,
            symbol="HPG",
            trading_date="2026-09-10",
        )
        missing_daily = prove_volume_session(
            history,
            daily,
            symbol="HPG",
            trading_date="2026-09-09",
        )
    finally:
        daily.close()
        history.close()

    assert proven_zero.reason == "PROVEN_ZERO" and proven_zero.proven
    assert missing_daily.reason == "DAILY_MISSING" and not missing_daily.proven


def test_untrusted_provider_and_missing_intraday_are_not_zero_filled(
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "provider-history.db"
    daily_path = tmp_path / "provider-daily.db"
    _history_db(
        history_path,
        [("HPG", "HOSE", "2026-09-10", "09:16", 10)],
    )
    history_write = sqlite3.connect(history_path)
    history_write.execute(
        "UPDATE minute_bars SET data_source='KBS' WHERE symbol='HPG'"
    )
    history_write.commit()
    history_write.close()

    daily = sqlite3.connect(daily_path)
    ensure_market_storage_schema(daily)
    daily.executemany(
        """
        INSERT INTO daily_bars (
          symbol,trading_date,exchange,open,high,low,close,volume,value,
          source,quality_status,finalized_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                "HPG",
                trading_date,
                "HOSE",
                1,
                1,
                1,
                1,
                10,
                None,
                "SSI_DAILY_OHLC",
                "TRUSTED",
                "fixed",
            )
            for trading_date in ("2026-09-10", "2026-09-09")
        ],
    )
    daily.commit()
    daily.close()

    history = _connect(history_path)
    daily = _connect(daily_path)
    try:
        mixed_provider = prove_volume_session(
            history,
            daily,
            symbol="HPG",
            trading_date="2026-09-10",
        )
        missing_intraday = prove_volume_session(
            history,
            daily,
            symbol="HPG",
            trading_date="2026-09-09",
        )
    finally:
        daily.close()
        history.close()

    selection = select_volume_sessions([mixed_provider, missing_intraday])
    coverage, rows = build_symbol_volume_baseline(
        "HPG",
        selection,
        lookback=10,
        candidate_sessions=["2026-09-09", "2026-09-10"],
    )
    assert mixed_provider.reason == "UNSAFE_INTRADAY"
    assert missing_intraday.reason == "INTRADAY_MISSING"
    assert coverage.baseline_sessions_used == 0
    assert coverage.coverage_tier == "INSUFFICIENT"
    assert rows == []


@pytest.mark.parametrize(("symbol", "exchange"), [("SHS", "HNX"), ("VGI", "UPCOM")])
def test_hnx_upcom_morning_windows_use_exact_closed_bar_count(
    tmp_path: Path, symbol: str, exchange: str
) -> None:
    history = tmp_path / f"{exchange}-history.db"
    output = tmp_path / f"{exchange}-baseline.db"
    _history_db(
        history,
        _minimum_healthy_bars([
            (symbol, exchange, "2026-09-10", "09:00", 100),
            (symbol, exchange, "2026-09-10", "09:14", 14),
            (symbol, exchange, "2026-09-10", "09:15", 999),
            (symbol, exchange, "2026-09-10", "09:29", 29),
            (symbol, exchange, "2026-09-10", "09:30", 777),
        ]),
    )
    build_volume_baseline(history_db=history, output_db=output)

    connection = _connect(output)
    values = {
        row["minute"]: row
        for row in connection.execute(
            "SELECT * FROM volume_baseline WHERE symbol=? "
            "AND minute IN ('09:14','09:15','09:29','09:30')",
            (symbol,),
        )
    }
    assert values["09:14"]["avg_volume_15"] == 114
    assert values["09:15"]["avg_volume_15"] == 1013
    assert values["09:29"]["avg_volume_30"] == 1142
    assert values["09:30"]["avg_volume_30"] == 1819
    connection.close()


def test_hose_morning_windows_exclude_opening_and_use_exact_bar_count(
    tmp_path: Path,
) -> None:
    history = tmp_path / "hose-history.db"
    output = tmp_path / "hose-baseline.db"
    _history_db(
        history,
        _minimum_healthy_bars([
            ("HPG", "HOSE", "2026-09-10", "09:15", 5000),
            ("HPG", "HOSE", "2026-09-10", "09:16", 100),
            ("HPG", "HOSE", "2026-09-10", "09:30", 14),
            ("HPG", "HOSE", "2026-09-10", "09:31", 999),
            ("HPG", "HOSE", "2026-09-10", "09:45", 29),
            ("HPG", "HOSE", "2026-09-10", "09:46", 777),
        ]),
    )
    build_volume_baseline(history_db=history, output_db=output)

    connection = _connect(output)
    values = {
        row["minute"]: row
        for row in connection.execute(
            "SELECT * FROM volume_baseline WHERE symbol='HPG' "
            "AND minute IN ('09:30','09:31','09:45','09:46')"
        )
    }
    assert values["09:30"]["avg_volume_15"] == 114
    assert values["09:31"]["avg_volume_15"] == 1013
    assert values["09:45"]["avg_volume_30"] == 1142
    assert values["09:46"]["avg_volume_30"] == 1819
    connection.close()


@pytest.mark.parametrize(
    ("symbol", "exchange"),
    [("HPG", "HOSE"), ("SHS", "HNX"), ("VGI", "UPCOM")],
)
def test_afternoon_windows_use_exact_closed_bar_count(
    tmp_path: Path, symbol: str, exchange: str
) -> None:
    history = tmp_path / f"{exchange}-pm-history.db"
    output = tmp_path / f"{exchange}-pm-baseline.db"
    _history_db(
        history,
        _minimum_healthy_bars([
            (symbol, exchange, "2026-09-10", "13:00", 100),
            (symbol, exchange, "2026-09-10", "13:14", 14),
            (symbol, exchange, "2026-09-10", "13:15", 999),
            (symbol, exchange, "2026-09-10", "13:29", 29),
            (symbol, exchange, "2026-09-10", "13:30", 777),
        ]),
    )
    build_volume_baseline(history_db=history, output_db=output)

    connection = _connect(output)
    values = {
        row["minute"]: row
        for row in connection.execute(
            "SELECT * FROM volume_baseline WHERE symbol=? "
            "AND minute IN ('13:14','13:15','13:29','13:30')",
            (symbol,),
        )
    }
    assert values["13:14"]["avg_volume_15"] == 114
    assert values["13:15"]["avg_volume_15"] == 1013
    assert values["13:29"]["avg_volume_30"] == 1142
    assert values["13:30"]["avg_volume_30"] == 1819
    connection.close()


def test_missing_hose_auction_rows_contribute_zero_samples(tmp_path: Path) -> None:
    history = tmp_path / "hose-auction-history.db"
    output = tmp_path / "hose-auction-baseline.db"
    _history_db(
        history,
        _minimum_healthy_bars([
            ("HPG", "HOSE", "2026-09-09", "09:15", 100),
            ("HPG", "HOSE", "2026-09-09", "14:45", 50),
            ("HPG", "HOSE", "2026-09-10", "09:16", 20),
        ]),
    )
    build_volume_baseline(history_db=history, output_db=output)

    connection = _connect(output)
    opening = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='HPG' AND minute='09:15'"
    ).fetchone()
    closing = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='HPG' AND minute='14:45'"
    ).fetchone()
    assert opening["avg_opening_volume"] == 50
    assert opening["avg_cumulative_volume"] == 50
    assert opening["historical_sessions"] == 8
    assert closing["avg_cumulative_volume"] == 85
    assert closing["historical_sessions"] == 8
    assert closing["avg_volume_15"] is None
    connection.close()


def test_missing_hnx_close_contributes_final_cumulative_sample(
    tmp_path: Path,
) -> None:
    history = tmp_path / "hnx-close-history.db"
    output = tmp_path / "hnx-close-baseline.db"
    _history_db(
        history,
        _minimum_healthy_bars([
            ("SHS", "HNX", "2026-09-09", "09:00", 100),
            ("SHS", "HNX", "2026-09-09", "14:45", 50),
            ("SHS", "HNX", "2026-09-10", "09:00", 20),
        ]),
    )
    build_volume_baseline(history_db=history, output_db=output)

    connection = _connect(output)
    closing = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='14:45'"
    ).fetchone()
    assert closing["avg_cumulative_volume"] == 85
    assert closing["historical_sessions"] == 8
    assert closing["avg_volume_15"] is None
    connection.close()


def test_hose_opening_and_close_affect_cumulative_but_not_rolling(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    _history_db(
        history,
        _minimum_healthy_bars([
            ("HPG", "HOSE", "2026-09-10", "09:15", 100),
            ("HPG", "HOSE", "2026-09-10", "09:16", 10),
            ("HPG", "HOSE", "2026-09-10", "14:45", 50),
        ]),
    )
    build_volume_baseline(history_db=history, output_db=output)

    connection = _connect(output)
    opening = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='HPG' AND minute='09:15'"
    ).fetchone()
    continuous = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='HPG' AND minute='09:30'"
    ).fetchone()
    closing = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='HPG' AND minute='14:45'"
    ).fetchone()
    assert opening["avg_opening_volume"] == 100
    assert opening["avg_volume_15"] is None
    assert continuous["avg_cumulative_volume"] == 110
    assert continuous["avg_volume_15"] == 10
    assert closing["avg_cumulative_volume"] == 160
    assert closing["avg_volume_15"] is None
    assert closing["avg_volume_30"] is None
    connection.close()


def test_provider_boundaries_affect_cumulative_but_not_continuous_rolling(
    tmp_path: Path,
) -> None:
    history = tmp_path / "provider-boundary-history.db"
    output = tmp_path / "provider-boundary-baseline.db"
    _history_db(
        history,
        _minimum_healthy_bars(
            [
                ("HPG", "HOSE", "2026-09-10", "11:29", 100),
                ("HPG", "HOSE", "2026-09-10", "11:30", 7),
                ("HPG", "HOSE", "2026-09-10", "14:29", 20),
                ("HPG", "HOSE", "2026-09-10", "14:30", 9),
            ]
        ),
    )
    build_volume_baseline(history_db=history, output_db=output)

    connection = _connect(output)
    values = {
        row["minute"]: row
        for row in connection.execute(
            "SELECT * FROM volume_baseline WHERE symbol='HPG' "
            "AND minute IN ('11:29','11:30','13:14','14:29','14:30')"
        )
    }
    connection.close()

    assert values["11:29"]["avg_cumulative_volume"] == 100
    assert values["11:30"]["avg_cumulative_volume"] == 107
    assert values["11:30"]["session_segment"] == "PROVIDER_BOUNDARY"
    assert values["11:30"]["avg_volume_15"] is None
    assert values["11:30"]["avg_volume_30"] is None
    assert values["13:14"]["avg_cumulative_volume"] == 107
    assert values["13:14"]["avg_volume_15"] == 0
    assert values["14:29"]["avg_cumulative_volume"] == 127
    assert values["14:29"]["avg_volume_15"] == 20
    assert values["14:29"]["avg_volume_30"] == 20
    assert values["14:30"]["avg_cumulative_volume"] == 136
    assert values["14:30"]["session_segment"] == "PROVIDER_BOUNDARY"
    assert values["14:30"]["avg_volume_15"] is None
    assert values["14:30"]["avg_volume_30"] is None


def test_continuous_no_trade_minutes_zero_fill_volume_without_ohlc(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    _history_db(
        history,
        _minimum_healthy_bars(
            [("SHS", "HNX", "2026-09-10", "09:01", 75)]
        ),
    )
    build_volume_baseline(history_db=history, output_db=output)

    connection = _connect(output)
    row = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='09:15'"
    ).fetchone()
    columns = {
        item["name"]
        for item in connection.execute("PRAGMA table_info(volume_baseline)")
    }
    assert row["avg_volume_15"] == 75
    assert row["historical_sessions"] == 8
    assert not {"open", "high", "low", "close"} & columns
    boundary = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='11:30'"
    ).fetchone()
    assert boundary["session_segment"] == "PROVIDER_BOUNDARY"
    assert boundary["avg_cumulative_volume"] == 75
    assert boundary["avg_volume_15"] is None
    assert boundary["avg_volume_30"] is None
    connection.close()


def test_lunch_keeps_day_cumulative_and_resets_rolling_window(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    _history_db(
        history,
        _minimum_healthy_bars([
            ("SHS", "HNX", "2026-09-10", "11:29", 100),
            ("SHS", "HNX", "2026-09-10", "13:15", 7),
        ]),
    )
    build_volume_baseline(history_db=history, output_db=output)

    connection = _connect(output)
    at_open = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='13:00'"
    ).fetchone()
    at_fifteen = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='13:15'"
    ).fetchone()
    assert at_open["avg_cumulative_volume"] == 100
    assert at_open["avg_volume_15"] is None
    assert at_fifteen["avg_cumulative_volume"] == 107
    assert at_fifteen["avg_volume_15"] == 7
    connection.close()


def test_lookback_uses_only_exact_previous_ten_sessions(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    dates = _weekdays(date(2026, 8, 24), 12)
    _history_db(
        history,
        [
            ("SHS", "HNX", trading_date, "09:01", index)
            for index, trading_date in enumerate(dates, start=1)
        ],
    )
    summary = build_volume_baseline(
        history_db=history,
        output_db=output,
        lookback=10,
    )

    connection = _connect(output)
    coverage = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol='SHS'"
    ).fetchone()
    baseline = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='09:15'"
    ).fetchone()
    assert coverage["available_sessions"] == 10
    assert coverage["baseline_sessions_used"] == 10
    assert coverage["active_sessions_available"] == 10
    assert coverage["active_sessions_used"] == 10
    assert coverage["coverage_tier"] == "FULL"
    assert coverage["scanned_sessions"] == 10
    assert coverage["first_history_date"] == dates[2]
    assert coverage["last_history_date"] == dates[-1]
    assert baseline["historical_sessions"] == 10
    assert baseline["avg_volume_15"] == 7.5
    assert summary.symbols_10_sessions == 1
    assert summary.symbols_9_sessions == 0
    assert summary.symbols_8_sessions == 0
    assert summary.symbols_under_8_sessions == 0
    assert summary.samples[0]["selected_dates"] == list(reversed(dates[-10:]))
    assert summary.samples[0]["skipped_dates"] == []
    assert summary.samples[0]["coverage_tier"] == "FULL"
    connection.close()


def test_opening_average_keeps_exact_previous_ten_window(
    tmp_path: Path,
) -> None:
    history = tmp_path / "opening-window-history.db"
    daily = tmp_path / "opening-window-daily.db"
    output = tmp_path / "opening-window-baseline.db"
    dates = _weekdays(date(2026, 8, 24), 11)
    _history_db(
        history,
        [
            ("HPG", "HOSE", trading_date, "09:15", index)
            for index, trading_date in enumerate(dates, start=1)
        ],
    )
    as_of_date = _daily_from_history(history, daily)
    broken_date = dates[5]
    history_write = sqlite3.connect(history)
    history_write.execute(
        "UPDATE minute_bars SET quality_status='DEGRADED' "
        "WHERE symbol='HPG' AND trading_date=?",
        (broken_date,),
    )
    history_write.commit()
    history_write.close()

    _build_volume_baseline(
        history_db=history,
        daily_db=daily,
        output_db=output,
        as_of_date=as_of_date,
        symbols=["HPG"],
    )
    connection = _connect(output)
    opening = connection.execute(
        "SELECT avg_cumulative_volume, avg_opening_volume "
        "FROM volume_baseline WHERE symbol='HPG' AND minute='09:15'"
    ).fetchone()
    coverage = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol='HPG'"
    ).fetchone()
    connection.close()

    exact_window_values = [value for value in range(2, 12) if value != 6]
    assert coverage["available_sessions"] == 10
    assert coverage["baseline_sessions_used"] == 9
    assert coverage["first_history_date"] == dates[1]
    assert coverage["skipped_sessions"] == 1
    assert opening["avg_cumulative_volume"] == (
        sum(exact_window_values) / len(exact_window_values)
    )
    assert opening["avg_opening_volume"] == (
        sum(exact_window_values) / len(exact_window_values)
    )


def test_four_sessions_report_four_and_no_history_symbol_does_not_fail(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    dates = _weekdays(date(2026, 9, 1), 4)
    _history_db(
        history,
        [("HPG", "HOSE", item, "09:16", 10) for item in dates],
        no_history_symbols=["NOHIST"],
    )
    summary = build_volume_baseline(history_db=history, output_db=output)

    connection = _connect(output)
    hpg_coverage = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol='HPG'"
    ).fetchone()
    no_history = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol='NOHIST'"
    ).fetchone()
    assert hpg_coverage["available_sessions"] == 4
    assert hpg_coverage["baseline_sessions_used"] == 4
    assert hpg_coverage["coverage_tier"] == "INSUFFICIENT"
    assert connection.execute(
        "SELECT COUNT(*) FROM volume_baseline WHERE symbol='HPG'"
    ).fetchone()[0] == 0
    assert no_history["available_sessions"] == 4
    assert no_history["baseline_sessions_used"] == 0
    assert no_history["active_sessions_available"] == 0
    assert no_history["active_sessions_used"] == 0
    assert no_history["first_history_date"] is None
    assert no_history["last_history_date"] is None
    assert connection.execute(
        "SELECT COUNT(*) FROM volume_baseline WHERE symbol='NOHIST'"
    ).fetchone()[0] == 0
    assert summary.symbols_without_history == 1
    assert summary.symbols_under_8_sessions == 2
    assert summary.symbols_no_history == 1
    snapshot = load_volume_baseline(output)
    assert snapshot.coverage["HPG"].baseline_sessions_used == 4
    assert not any(key[0] == "HPG" for key in snapshot.points)
    connection.close()


def test_global_calendar_does_not_zero_fill_whole_missing_sessions(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    dates = _weekdays(date(2026, 8, 24), 10)
    calendar_bars = [("VNM", "HOSE", item, "09:16", 1) for item in dates]
    _history_db(
        history,
        calendar_bars
        + [
            ("SHS", "HNX", dates[0], "09:00", 100),
            ("SHS", "HNX", dates[-1], "09:14", 300),
        ],
    )

    build_volume_baseline(
        history_db=history, output_db=output, symbols=["SHS"], lookback=10
    )

    connection = _connect(output)
    coverage = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol='SHS'"
    ).fetchone()
    rolling = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='09:14'"
    ).fetchone()
    rolling_30 = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='09:29'"
    ).fetchone()
    close = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='14:45'"
    ).fetchone()
    assert coverage["available_sessions"] == 10
    assert coverage["baseline_sessions_used"] == 2
    assert coverage["active_sessions_available"] == 2
    assert coverage["active_sessions_used"] == 2
    assert coverage["first_history_date"] == dates[0]
    assert coverage["last_history_date"] == dates[-1]
    assert coverage["coverage_tier"] == "INSUFFICIENT"
    assert rolling is None
    assert rolling_30 is None
    assert close is None
    connection.close()


def test_global_calendar_excludes_unproven_trailing_missing_sessions(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    dates = _weekdays(date(2026, 8, 24), 10)
    _history_db(
        history,
        [("VNM", "HOSE", item, "09:16", 1) for item in dates]
        + [
            ("HPG", "HOSE", dates[0], "09:15", 100),
            ("HPG", "HOSE", dates[4], "09:16", 100),
        ],
    )

    build_volume_baseline(history_db=history, output_db=output, symbols=["HPG"])

    connection = _connect(output)
    coverage = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol='HPG'"
    ).fetchone()
    opening = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='HPG' AND minute='09:15'"
    ).fetchone()
    close = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='HPG' AND minute='14:45'"
    ).fetchone()
    assert coverage["available_sessions"] == 10
    assert coverage["active_sessions_available"] == 2
    assert coverage["last_history_date"] == dates[4]
    assert coverage["coverage_tier"] == "INSUFFICIENT"
    assert opening is None
    assert close is None
    connection.close()


def test_newly_observed_symbol_keeps_exact_candidate_window_but_uses_only_proven(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    dates = _weekdays(date(2026, 8, 24), 10)
    _history_db(
        history,
        [("VNM", "HOSE", item, "09:16", 1) for item in dates]
        + [
            ("NEW", "HNX", dates[7], "09:00", 90),
            ("NEW", "HNX", dates[9], "09:00", 30),
        ],
    )

    build_volume_baseline(history_db=history, output_db=output, symbols=["NEW"])

    connection = _connect(output)
    coverage = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol='NEW'"
    ).fetchone()
    row = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='NEW' AND minute='09:14'"
    ).fetchone()
    assert coverage["available_sessions"] == 10
    assert coverage["baseline_sessions_used"] == 2
    assert coverage["active_sessions_available"] == 2
    assert coverage["active_sessions_used"] == 2
    assert coverage["first_history_date"] == dates[7]
    assert coverage["last_history_date"] == dates[9]
    assert coverage["coverage_tier"] == "INSUFFICIENT"
    assert row is None
    connection.close()


def test_active_sessions_used_only_counts_active_dates_inside_lookback(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    dates = _weekdays(date(2026, 8, 24), 12)
    _history_db(
        history,
        [("VNM", "HOSE", item, "09:16", 1) for item in dates]
        + [
            ("SHS", "HNX", dates[0], "09:00", 100),
            ("SHS", "HNX", dates[-1], "09:00", 200),
        ],
    )

    build_volume_baseline(
        history_db=history, output_db=output, symbols=["SHS"], lookback=10
    )

    connection = _connect(output)
    coverage = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol='SHS'"
    ).fetchone()
    row = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='09:14'"
    ).fetchone()
    assert coverage["available_sessions"] == 10
    assert coverage["baseline_sessions_used"] == 1
    assert coverage["active_sessions_available"] == 1
    assert coverage["active_sessions_used"] == 1
    assert coverage["first_history_date"] == dates[-1]
    assert coverage["last_history_date"] == dates[-1]
    assert coverage["coverage_tier"] == "INSUFFICIENT"
    assert row is None
    connection.close()


def test_existing_derived_coverage_schema_migrates_without_touching_raw_db(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    _history_db(history, [("HPG", "HOSE", "2026-09-10", "09:16", 10)])
    connection = sqlite3.connect(output)
    connection.execute(
        """
        CREATE TABLE volume_baseline_coverage (
            symbol TEXT PRIMARY KEY,
            exchange TEXT,
            available_sessions INTEGER NOT NULL,
            baseline_sessions_used INTEGER NOT NULL,
            first_history_date TEXT,
            last_history_date TEXT
        )
        """
    )
    connection.commit()
    connection.close()
    raw_before = history.read_bytes()

    build_volume_baseline(history_db=history, output_db=output, symbols=["HPG"])

    connection = _connect(output)
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(volume_baseline_coverage)")
    }
    coverage = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol='HPG'"
    ).fetchone()
    assert {"active_sessions_available", "active_sessions_used"} <= columns
    assert coverage["active_sessions_available"] == 1
    assert coverage["active_sessions_used"] == 1
    assert connection.execute(
        "SELECT value FROM volume_baseline_metadata WHERE key='schema_version'"
    ).fetchone()[0] == "2"
    connection.close()
    assert history.read_bytes() == raw_before


def test_rebuild_is_deterministic_idempotent_and_raw_history_is_unchanged(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    _history_db(
        history,
        [("BSR", "UPCOM", "2026-09-10", "14:59", 25)],
    )
    raw_before = history.read_bytes()
    build_volume_baseline(history_db=history, output_db=output, symbols=["BSR"])
    connection = _connect(output)
    first = [
        tuple(row)
        for row in connection.execute(
            "SELECT * FROM volume_baseline ORDER BY symbol, minute"
        )
    ]
    first_coverage = [
        tuple(row)
        for row in connection.execute(
            "SELECT * FROM volume_baseline_coverage ORDER BY symbol"
        )
    ]
    connection.close()

    build_volume_baseline(history_db=history, output_db=output, symbols=["BSR"])
    connection = _connect(output)
    second = [
        tuple(row)
        for row in connection.execute(
            "SELECT * FROM volume_baseline ORDER BY symbol, minute"
        )
    ]
    second_coverage = [
        tuple(row)
        for row in connection.execute(
            "SELECT * FROM volume_baseline_coverage ORDER BY symbol"
        )
    ]
    connection.close()
    assert first == second
    assert first_coverage == second_coverage
    assert history.read_bytes() == raw_before
