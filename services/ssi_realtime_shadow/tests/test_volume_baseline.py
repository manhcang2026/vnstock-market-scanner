from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import pytest

from app.storage import SQLiteStore
from app.volume_baseline import build_volume_baseline, volume_market_grid
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


def _weekdays(start: date, count: int) -> list[str]:
    values: list[str] = []
    current = start
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current.isoformat())
        current += timedelta(days=1)
    return values


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
    assert not grid["13:13"].rolling_15_ready
    assert grid["13:14"].rolling_15_ready
    assert not grid["13:28"].rolling_30_ready
    assert grid["13:29"].rolling_30_ready
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
    assert hnx["14:45"].session_segment == "CLOSE_BUCKET"
    assert upcom["14:59"].is_continuous
    assert not upcom["09:13"].rolling_15_ready
    assert upcom["09:14"].rolling_15_ready
    assert not upcom["09:28"].rolling_30_ready
    assert upcom["09:29"].rolling_30_ready
    assert "15:00" not in upcom


def test_volume_baseline_cli_accepts_sample_arguments() -> None:
    args = build_parser().parse_args(
        [
            "--history-db",
            "/app/data/ssi_history_v2.db",
            "--output-db",
            "/app/data/ccc_v2_baseline.db",
            "--lookback",
            "10",
            "--symbols",
            "HPG,SSI,VIX",
        ]
    )
    assert args.lookback == 10
    assert args.symbols == ["HPG", "SSI", "VIX"]


@pytest.mark.parametrize(("symbol", "exchange"), [("SHS", "HNX"), ("BSR", "UPCOM")])
def test_hnx_upcom_morning_windows_use_exact_closed_bar_count(
    tmp_path: Path, symbol: str, exchange: str
) -> None:
    history = tmp_path / f"{exchange}-history.db"
    output = tmp_path / f"{exchange}-baseline.db"
    _history_db(
        history,
        [
            (symbol, exchange, "2026-09-10", "09:00", 100),
            (symbol, exchange, "2026-09-10", "09:14", 14),
            (symbol, exchange, "2026-09-10", "09:15", 999),
            (symbol, exchange, "2026-09-10", "09:29", 29),
            (symbol, exchange, "2026-09-10", "09:30", 777),
        ],
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
        [
            ("HPG", "HOSE", "2026-09-10", "09:15", 5000),
            ("HPG", "HOSE", "2026-09-10", "09:16", 100),
            ("HPG", "HOSE", "2026-09-10", "09:30", 14),
            ("HPG", "HOSE", "2026-09-10", "09:31", 999),
            ("HPG", "HOSE", "2026-09-10", "09:45", 29),
            ("HPG", "HOSE", "2026-09-10", "09:46", 777),
        ],
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
    [("HPG", "HOSE"), ("SHS", "HNX"), ("BSR", "UPCOM")],
)
def test_afternoon_windows_use_exact_closed_bar_count(
    tmp_path: Path, symbol: str, exchange: str
) -> None:
    history = tmp_path / f"{exchange}-pm-history.db"
    output = tmp_path / f"{exchange}-pm-baseline.db"
    _history_db(
        history,
        [
            (symbol, exchange, "2026-09-10", "13:00", 100),
            (symbol, exchange, "2026-09-10", "13:14", 14),
            (symbol, exchange, "2026-09-10", "13:15", 999),
            (symbol, exchange, "2026-09-10", "13:29", 29),
            (symbol, exchange, "2026-09-10", "13:30", 777),
        ],
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
        [
            ("HPG", "HOSE", "2026-09-09", "09:15", 100),
            ("HPG", "HOSE", "2026-09-09", "14:45", 50),
            ("HPG", "HOSE", "2026-09-10", "09:16", 20),
        ],
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
    assert opening["historical_sessions"] == 2
    assert closing["avg_cumulative_volume"] == 85
    assert closing["historical_sessions"] == 2
    assert closing["avg_volume_15"] is None
    connection.close()


def test_missing_hnx_close_contributes_final_cumulative_sample(
    tmp_path: Path,
) -> None:
    history = tmp_path / "hnx-close-history.db"
    output = tmp_path / "hnx-close-baseline.db"
    _history_db(
        history,
        [
            ("SHS", "HNX", "2026-09-09", "09:00", 100),
            ("SHS", "HNX", "2026-09-09", "14:45", 50),
            ("SHS", "HNX", "2026-09-10", "09:00", 20),
        ],
    )
    build_volume_baseline(history_db=history, output_db=output)

    connection = _connect(output)
    closing = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='14:45'"
    ).fetchone()
    assert closing["avg_cumulative_volume"] == 85
    assert closing["historical_sessions"] == 2
    assert closing["avg_volume_15"] is None
    connection.close()


def test_hose_opening_and_close_affect_cumulative_but_not_rolling(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    _history_db(
        history,
        [
            ("HPG", "HOSE", "2026-09-10", "09:15", 100),
            ("HPG", "HOSE", "2026-09-10", "09:16", 10),
            ("HPG", "HOSE", "2026-09-10", "14:45", 50),
        ],
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


def test_continuous_no_trade_minutes_zero_fill_volume_without_ohlc(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    _history_db(
        history,
        [("SHS", "HNX", "2026-09-10", "09:01", 75)],
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
    assert row["historical_sessions"] == 1
    assert not {"open", "high", "low", "close"} & columns
    assert connection.execute(
        "SELECT 1 FROM volume_baseline WHERE minute='11:30'"
    ).fetchone() is None
    connection.close()


def test_lunch_keeps_day_cumulative_and_resets_rolling_window(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.db"
    output = tmp_path / "baseline.db"
    _history_db(
        history,
        [
            ("SHS", "HNX", "2026-09-10", "11:29", 100),
            ("SHS", "HNX", "2026-09-10", "13:15", 7),
        ],
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


def test_lookback_uses_latest_ten_sessions_and_coverage_keeps_all_history(
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
    build_volume_baseline(history_db=history, output_db=output, lookback=10)

    connection = _connect(output)
    coverage = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol='SHS'"
    ).fetchone()
    baseline = connection.execute(
        "SELECT * FROM volume_baseline WHERE symbol='SHS' AND minute='09:15'"
    ).fetchone()
    assert coverage["available_sessions"] == 12
    assert coverage["baseline_sessions_used"] == 10
    assert coverage["first_history_date"] == dates[0]
    assert coverage["last_history_date"] == dates[-1]
    assert baseline["historical_sessions"] == 10
    assert baseline["avg_volume_15"] == 7.5
    connection.close()


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
    assert connection.execute(
        "SELECT MIN(historical_sessions) FROM volume_baseline WHERE symbol='HPG'"
    ).fetchone()[0] == 4
    assert no_history["available_sessions"] == 0
    assert no_history["baseline_sessions_used"] == 0
    assert no_history["first_history_date"] is None
    assert summary.symbols_without_history == 1
    connection.close()


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
