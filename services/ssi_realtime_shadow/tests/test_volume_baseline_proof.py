from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.market_storage_schema import ensure_market_storage_schema
from app.storage import SQLiteStore
from app.volume_baseline import COVERAGE_PROOF, build_volume_baseline


def _daily_db(path: Path, rows: list[tuple[str, str, str, int]]) -> None:
    connection = sqlite3.connect(path)
    ensure_market_storage_schema(connection)
    connection.executemany(
        """
        INSERT INTO daily_bars (
          symbol,trading_date,exchange,open,high,low,close,volume,value,
          source,quality_status,finalized_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (symbol, trading_date, exchange, 1, 1, 1, 1, volume, None,
             "SSI_DAILY_OHLC", "TRUSTED", "fixed")
            for symbol, exchange, trading_date, volume in rows
        ],
    )
    connection.commit()
    connection.close()


def _history_db(
    path: Path,
    rows: list[tuple[str, str, str, str, int]],
) -> None:
    store = SQLiteStore(path)
    for symbol, exchange, trading_date, minute, volume in rows:
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
    store.close()


def _coverage(path: Path, symbol: str) -> sqlite3.Row:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol=?", (symbol,)
    ).fetchone()
    connection.close()
    assert row is not None
    return row


def _build(
    tmp_path: Path,
    *,
    history_rows: list[tuple[str, str, str, str, int]],
    daily_rows: list[tuple[str, str, str, int]],
    as_of_date: str = "2026-09-12",
    symbols: list[str] | None = None,
):
    history = tmp_path / "history.db"
    daily = tmp_path / "daily.db"
    output = tmp_path / "baseline.db"
    _history_db(history, history_rows)
    _daily_db(daily, daily_rows)
    summary = build_volume_baseline(
        history_db=history,
        daily_db=daily,
        output_db=output,
        as_of_date=as_of_date,
        symbols=symbols,
    )
    return history, daily, output, summary


def test_unproven_missing_session_is_not_zero_but_proven_missing_minute_is_zero(
    tmp_path: Path,
) -> None:
    dates = ["2026-09-10", "2026-09-11"]
    _, _, output, summary = _build(
        tmp_path,
        history_rows=[
            ("CAL", "HOSE", dates[0], "09:16", 1),
            ("CAL", "HOSE", dates[1], "09:16", 1),
            ("HPG", "HOSE", dates[1], "09:16", 10),
        ],
        daily_rows=[
            ("CAL", "HOSE", dates[0], 1),
            ("CAL", "HOSE", dates[1], 1),
            ("HPG", "HOSE", dates[1], 10),
        ],
        symbols=["HPG"],
    )
    coverage = _coverage(output, "HPG")
    assert coverage["available_sessions"] == 2
    assert coverage["baseline_sessions_used"] == 1
    assert summary.daily_missing_count == 1
    connection = sqlite3.connect(output)
    # 09:17 was absent but can be zero-filled inside the one reconciled session.
    row = connection.execute(
        "SELECT historical_sessions,avg_cumulative_volume FROM volume_baseline "
        "WHERE symbol='HPG' AND minute='09:17'"
    ).fetchone()
    connection.close()
    assert row == (1, 10.0)


def test_daily_zero_without_intraday_rows_is_a_proven_real_zero(tmp_path: Path) -> None:
    _, _, output, summary = _build(
        tmp_path,
        history_rows=[],
        daily_rows=[("VGI", "UPCOM", "2026-09-11", 0)],
        symbols=["VGI"],
    )
    assert _coverage(output, "VGI")["baseline_sessions_used"] == 1
    assert summary.symbols_zero_proven == 1
    connection = sqlite3.connect(output)
    assert connection.execute(
        "SELECT avg_cumulative_volume FROM volume_baseline "
        "WHERE symbol='VGI' AND minute='14:59'"
    ).fetchone()[0] == 0
    connection.close()


@pytest.mark.parametrize(
    ("mutation", "daily_exchange", "expected_counter"),
    [
        ("mismatch", "HOSE", "volume_mismatch_count"),
        ("partial", "HOSE", "unsafe_intraday_count"),
        ("gap", "HOSE", "unsafe_intraday_count"),
        ("nontrusted", "HOSE", "unsafe_intraday_count"),
        ("none", "HNX", "exchange_mismatch_count"),
    ],
)
def test_failed_reconciliation_excludes_session(
    tmp_path: Path,
    mutation: str,
    daily_exchange: str,
    expected_counter: str,
) -> None:
    history = tmp_path / "history.db"
    daily = tmp_path / "daily.db"
    output = tmp_path / "baseline.db"
    _history_db(history, [("HPG", "HOSE", "2026-09-11", "09:16", 10)])
    if mutation != "none":
        connection = sqlite3.connect(history)
        if mutation == "partial":
            connection.execute("UPDATE minute_bars SET is_partial=1")
        elif mutation == "gap":
            connection.execute("UPDATE minute_bars SET has_gap=1")
        elif mutation == "nontrusted":
            connection.execute("UPDATE minute_bars SET quality_status='DEGRADED'")
        connection.commit()
        connection.close()
    daily_volume = 11 if mutation == "mismatch" else 10
    _daily_db(daily, [("HPG", daily_exchange, "2026-09-11", daily_volume)])
    summary = build_volume_baseline(
        history_db=history,
        daily_db=daily,
        output_db=output,
        as_of_date="2026-09-12",
        symbols=["HPG"],
    )
    assert _coverage(output, "HPG")["baseline_sessions_used"] == 0
    assert getattr(summary, expected_counter) == 1


def test_exact_previous_ten_excludes_as_of_and_does_not_reach_back(tmp_path: Path) -> None:
    start = date(2026, 8, 31)
    dates: list[str] = []
    current = start
    while len(dates) < 12:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    as_of = dates[-1]
    history_rows = [("SHS", "HNX", item, "09:00", 10) for item in dates]
    daily_rows = [("SHS", "HNX", item, 10) for item in dates]
    history, daily, output, _ = _build(
        tmp_path,
        history_rows=history_rows,
        daily_rows=daily_rows,
        as_of_date=as_of,
        symbols=["SHS"],
    )
    connection = sqlite3.connect(history)
    # Corrupt one date inside the previous-ten window. dates[0] is the older 11th.
    connection.execute(
        "UPDATE minute_bars SET volume=9 WHERE symbol='SHS' AND trading_date=?",
        (dates[5],),
    )
    connection.commit()
    connection.close()
    history_before = history.read_bytes()
    daily_before = daily.read_bytes()
    first = build_volume_baseline(
        history_db=history,
        daily_db=daily,
        output_db=output,
        as_of_date=as_of,
        symbols=["SHS"],
    )
    second = build_volume_baseline(
        history_db=history,
        daily_db=daily,
        output_db=output,
        as_of_date=as_of,
        symbols=["SHS"],
    )
    coverage = _coverage(output, "SHS")
    assert first.candidate_market_sessions == 10
    assert first.sessions_unproven == 1
    assert coverage["baseline_sessions_used"] == 9
    assert coverage["first_history_date"] == dates[1]
    assert coverage["last_history_date"] == dates[-2]
    assert first.to_dict() == second.to_dict()
    assert history.read_bytes() == history_before
    assert daily.read_bytes() == daily_before
    connection = sqlite3.connect(output)
    metadata = dict(connection.execute("SELECT key,value FROM volume_baseline_metadata"))
    connection.close()
    assert metadata["coverage_proof"] == COVERAGE_PROOF
    assert metadata["as_of_date"] == as_of


def test_calendar_keeps_intraday_observed_date_when_daily_is_globally_missing(
    tmp_path: Path,
) -> None:
    start = date(2026, 8, 31)
    dates: list[str] = []
    current = start
    while len(dates) < 11:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    missing_daily_date = dates[-5]
    history_rows = [("HPG", "HOSE", item, "09:16", 10) for item in dates]
    daily_rows = [
        ("HPG", "HOSE", item, 10)
        for item in dates
        if item != missing_daily_date
    ]
    _, _, output, summary = _build(
        tmp_path,
        history_rows=history_rows,
        daily_rows=daily_rows,
        as_of_date=(date.fromisoformat(dates[-1]) + timedelta(days=1)).isoformat(),
        symbols=["HPG"],
    )

    coverage = _coverage(output, "HPG")
    assert summary.candidate_market_sessions == 10
    assert summary.daily_missing_count == 1
    assert coverage["baseline_sessions_used"] == 9
    assert coverage["first_history_date"] == dates[1]
    assert dates[0] != coverage["first_history_date"]
    assert summary.samples[0]["failures"][0]["trading_date"] == missing_daily_date
    assert summary.samples[0]["failures"][0]["reason"] == "DAILY_MISSING"


def test_historical_baseline_rejects_raw_stream_without_eod_journal(tmp_path: Path) -> None:
    history = tmp_path / "history.db"
    daily = tmp_path / "daily.db"
    output = tmp_path / "baseline.db"
    _history_db(history, [("HPG", "HOSE", "2026-09-11", "09:16", 10)])
    connection = sqlite3.connect(history)
    connection.execute("UPDATE minute_bars SET data_source='SSI_STREAM'")
    connection.commit()
    connection.close()
    _daily_db(daily, [("HPG", "HOSE", "2026-09-11", 10)])

    summary = build_volume_baseline(
        history_db=history,
        daily_db=daily,
        output_db=output,
        as_of_date="2026-09-12",
        symbols=["HPG"],
    )
    assert summary.candidate_market_sessions == 1
    assert summary.unsafe_intraday_count == 1
    assert _coverage(output, "HPG")["baseline_sessions_used"] == 0
