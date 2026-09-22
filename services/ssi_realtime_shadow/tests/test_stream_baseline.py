from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.daily_finalize import finalize_day
from app.daily_history import DailyBar
from app.market_storage_schema import ensure_market_storage_schema
from app.storage import SCHEMA, SQLiteStore
from app.volume_baseline import (
    build_volume_baseline,
    load_candidate_market_sessions,
    prove_replay_volume_session,
    prove_volume_session,
)


SYMBOL = "FPT"
EXCHANGE = "HOSE"
MINUTES = ("09:15", "09:16", "09:30", "09:45", "14:45")


def _weekdays(start: date, count: int) -> list[str]:
    values: list[str] = []
    current = start
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def _volumes(seed: int) -> tuple[int, ...]:
    return (10 + seed, 100 + seed, 20 + seed, 30 + seed, 40 + seed)


def _daily_bar(trading_date: str, volumes: tuple[int, ...]) -> DailyBar:
    total = sum(volumes)
    return DailyBar(
        symbol=SYMBOL,
        trading_date=trading_date,
        exchange=EXCHANGE,
        open=100,
        high=105,
        low=99,
        close=103,
        volume=total,
        value=total * 103,
    )


def _insert_daily(connection: sqlite3.Connection, bar: DailyBar) -> None:
    connection.execute(
        """
        INSERT INTO daily_bars (
            symbol, trading_date, exchange, open, high, low, close,
            volume, value, source, quality_status, finalized_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SSI_DAILY_OHLC', 'TRUSTED', ?)
        """,
        (
            bar.symbol,
            bar.trading_date,
            bar.exchange,
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
            bar.value,
            bar.trading_date + "T16:00:00+07:00",
        ),
    )


def _insert_stream_source(
    source_path: Path,
    trading_date: str,
    volumes: tuple[int, ...],
    *,
    data_source: str = "SSI_REST",
) -> None:
    connection = sqlite3.connect(source_path)
    cumulative = 0
    rows = []
    for minute, volume in zip(MINUTES, volumes, strict=True):
        cumulative += volume
        rows.append(
            (
                trading_date,
                minute,
                SYMBOL,
                100,
                105,
                99,
                103,
                volume,
                cumulative,
                2,
                0,
                EXCHANGE,
                "TRUSTED",
                0,
                None,
                None,
                data_source,
                minute + ":00",
                trading_date + "T15:30:00+07:00",
            )
        )
    connection.executemany(
        """
        INSERT INTO minute_bars (
            trading_date, minute, symbol, open, high, low, close, volume,
            last_total_volume, event_count, is_partial, exchange,
            quality_status, has_gap, gap_from, gap_to, data_source,
            provider_time, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    connection.commit()
    connection.close()


def _fixture(tmp_path: Path):
    source = tmp_path / "ssi_shadow.db"
    history = tmp_path / "ssi_history_2026.db"
    market = tmp_path / "market.db"
    output = tmp_path / "baseline.db"
    source_connection = sqlite3.connect(source)
    source_connection.executescript(SCHEMA)
    source_connection.commit()
    source_connection.close()

    old_dates = _weekdays(date(2026, 8, 31), 10)
    store = SQLiteStore(history)
    old_volumes: dict[str, tuple[int, ...]] = {}
    for index, trading_date in enumerate(old_dates):
        volumes = _volumes(index)
        old_volumes[trading_date] = volumes
        for minute, volume in zip(MINUTES, volumes, strict=True):
            store.insert_historical_bar(
                trading_date=trading_date,
                minute=minute,
                symbol=SYMBOL,
                exchange=EXCHANGE,
                open_price=100,
                high=105,
                low=99,
                close=103,
                volume=volume,
                provider_time=minute + ":00",
                updated_at=trading_date + "T15:30:00+07:00",
            )
    store.close()

    market_connection = sqlite3.connect(market)
    ensure_market_storage_schema(
        market_connection, applied_at="2026-09-01T16:00:00+07:00"
    )
    for trading_date in old_dates:
        _insert_daily(
            market_connection,
            _daily_bar(trading_date, old_volumes[trading_date]),
        )
    market_connection.commit()
    market_connection.close()
    return source, history, market, output, old_dates, old_volumes


def _finalize_rest_day(
    source: Path,
    history: Path,
    market: Path,
    trading_date: str,
    volumes: tuple[int, ...],
) -> None:
    _insert_stream_source(source, trading_date, volumes)
    result = finalize_day(
        source_path=source,
        history_path=history,
        market_path=market,
        trading_date=trading_date,
        daily_bars=(_daily_bar(trading_date, volumes),),
        dry_run=False,
        now=datetime.combine(
            date.fromisoformat(trading_date),
            datetime.min.time().replace(hour=16),
            tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
        ),
    )
    assert result.status == "PASS"


def _coverage(path: Path) -> sqlite3.Row:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT * FROM volume_baseline_coverage WHERE symbol=?", (SYMBOL,)
    ).fetchone()
    connection.close()
    assert row is not None
    return row


def test_real_baseline_keeps_exact10_as_rest_days_advance(
    tmp_path: Path,
) -> None:
    source, history, market, output, old_dates, old_volumes = _fixture(tmp_path)
    new_dates = _weekdays(date(2026, 9, 14), 5)
    stream_volumes: dict[str, tuple[int, ...]] = {}

    first_volumes = _volumes(100)
    stream_volumes[new_dates[0]] = first_volumes
    _finalize_rest_day(source, history, market, new_dates[0], first_volumes)
    first_summary = build_volume_baseline(
        history_db=history,
        daily_db=market,
        output_db=output,
        as_of_date="2026-09-15",
        lookback=10,
        symbols=[SYMBOL],
    )

    history_connection = sqlite3.connect(history)
    history_connection.row_factory = sqlite3.Row
    market_connection = sqlite3.connect(market)
    market_connection.row_factory = sqlite3.Row
    first_candidates = load_candidate_market_sessions(
        history_connection,
        market_connection,
        as_of_date="2026-09-15",
        lookback=10,
    )
    assert first_candidates == old_dates[1:] + [new_dates[0]]
    assert old_dates[0] not in first_candidates
    source_counts = dict(
        history_connection.execute(
            """
            SELECT data_source, COUNT(DISTINCT trading_date)
            FROM minute_bars WHERE symbol=? AND trading_date IN (
                SELECT DISTINCT trading_date FROM minute_bars WHERE symbol=?
                ORDER BY trading_date DESC LIMIT 10
            ) GROUP BY data_source
            """,
            (SYMBOL, SYMBOL),
        )
    )
    assert source_counts == {"SSI_REST": 10}
    history_connection.close()
    market_connection.close()

    coverage = _coverage(output)
    assert first_summary.candidate_market_sessions == 10
    assert first_summary.symbols_10_10_proven == 1
    assert coverage["baseline_sessions_used"] == 10
    assert coverage["first_history_date"] == old_dates[1]
    assert coverage["last_history_date"] == new_dates[0]

    selected_volumes = [old_volumes[value] for value in old_dates[1:]] + [first_volumes]
    expected_cumulative = sum(sum(values) for values in selected_volumes) / 10
    expected_rvol15 = sum(values[1] + values[2] for values in selected_volumes) / 10
    expected_rvol30 = sum(
        values[1] + values[2] + values[3] for values in selected_volumes
    ) / 10
    connection = sqlite3.connect(output)
    cumulative = connection.execute(
        "SELECT historical_sessions, avg_cumulative_volume FROM volume_baseline "
        "WHERE symbol=? AND minute='14:45'",
        (SYMBOL,),
    ).fetchone()
    rvol15 = connection.execute(
        "SELECT historical_sessions, avg_volume_15 FROM volume_baseline "
        "WHERE symbol=? AND minute='09:30'",
        (SYMBOL,),
    ).fetchone()
    rvol30 = connection.execute(
        "SELECT historical_sessions, avg_volume_30 FROM volume_baseline "
        "WHERE symbol=? AND minute='09:45'",
        (SYMBOL,),
    ).fetchone()
    connection.close()
    assert cumulative == (10, expected_cumulative)
    assert rvol15 == (10, expected_rvol15)
    assert rvol30 == (10, expected_rvol30)

    for offset, trading_date in enumerate(new_dates[1:], start=101):
        volumes = _volumes(offset)
        stream_volumes[trading_date] = volumes
        _finalize_rest_day(source, history, market, trading_date, volumes)
    final_summary = build_volume_baseline(
        history_db=history,
        daily_db=market,
        output_db=output,
        as_of_date="2026-09-21",
        lookback=10,
        symbols=[SYMBOL],
    )
    history_connection = sqlite3.connect(history)
    history_connection.row_factory = sqlite3.Row
    market_connection = sqlite3.connect(market)
    market_connection.row_factory = sqlite3.Row
    final_candidates = load_candidate_market_sessions(
        history_connection,
        market_connection,
        as_of_date="2026-09-21",
        lookback=10,
    )
    assert final_candidates == old_dates[5:] + new_dates
    assert final_summary.symbols_10_10_proven == 1
    assert _coverage(output)["baseline_sessions_used"] == 10
    final_sources = dict(
        history_connection.execute(
            """
            SELECT data_source, COUNT(DISTINCT trading_date)
            FROM minute_bars WHERE symbol=? AND trading_date>=?
            GROUP BY data_source
            """,
            (SYMBOL, final_candidates[0]),
        )
    )
    assert final_sources == {"SSI_REST": 10}
    history_connection.close()
    market_connection.close()


def test_rest_finalized_history_is_canonical_proof(tmp_path: Path) -> None:
    source, history, market, _, old_dates, _ = _fixture(tmp_path)
    stream_date = "2026-09-14"
    _finalize_rest_day(source, history, market, stream_date, _volumes(100))
    history_connection = sqlite3.connect(history)
    history_connection.row_factory = sqlite3.Row
    market_connection = sqlite3.connect(market)
    market_connection.row_factory = sqlite3.Row
    assert prove_volume_session(
        history_connection,
        market_connection,
        symbol=SYMBOL,
        trading_date=old_dates[-1],
    ).proven
    stream_proof = prove_volume_session(
        history_connection,
        market_connection,
        symbol=SYMBOL,
        trading_date=stream_date,
    )
    assert stream_proof.proven
    assert {bar.data_source for bar in stream_proof.bars} == {"SSI_REST"}
    history_connection.close()
    market_connection.close()


def test_raw_stream_without_write_journal_is_rejected_but_replay_is_unchanged(
    tmp_path: Path,
) -> None:
    _, history, market, _, _, _ = _fixture(tmp_path)
    raw_date = "2026-09-14"
    volumes = _volumes(100)
    _insert_stream_source(history, raw_date, volumes, data_source="SSI_STREAM")
    market_connection = sqlite3.connect(market)
    _insert_daily(market_connection, _daily_bar(raw_date, volumes))
    market_connection.commit()
    market_connection.close()
    history_connection = sqlite3.connect(history)
    history_connection.row_factory = sqlite3.Row
    market_connection = sqlite3.connect(market)
    market_connection.row_factory = sqlite3.Row
    historical = prove_volume_session(
        history_connection, market_connection, symbol=SYMBOL, trading_date=raw_date
    )
    replay = prove_replay_volume_session(
        history_connection, market_connection, symbol=SYMBOL, trading_date=raw_date
    )
    assert historical.reason == "UNSAFE_INTRADAY"
    assert replay.proven
    history_connection.close()
    market_connection.close()


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("partial", "UNSAFE_INTRADAY"),
        ("gap", "UNSAFE_INTRADAY"),
        ("quality", "UNSAFE_INTRADAY"),
        ("missing_daily", "DAILY_MISSING"),
    ],
)
def test_unsafe_or_missing_finalized_rest_is_rejected(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    source, history, market, _, _, _ = _fixture(tmp_path)
    stream_date = "2026-09-14"
    _finalize_rest_day(source, history, market, stream_date, _volumes(100))
    if mutation in {"partial", "gap", "quality"}:
        connection = sqlite3.connect(history)
        if mutation == "partial":
            connection.execute(
                "UPDATE minute_bars SET is_partial=1 WHERE trading_date=?",
                (stream_date,),
            )
        elif mutation == "gap":
            connection.execute(
                "UPDATE minute_bars SET has_gap=1 WHERE trading_date=?",
                (stream_date,),
            )
        else:
            connection.execute(
                "UPDATE minute_bars SET quality_status='VOLUME_REGRESSION' "
                "WHERE trading_date=?",
                (stream_date,),
            )
        connection.commit()
        connection.close()
    else:
        connection = sqlite3.connect(market)
        connection.execute(
            "DELETE FROM daily_bars WHERE trading_date=?", (stream_date,)
        )
        connection.commit()
        connection.close()
    history_connection = sqlite3.connect(history)
    history_connection.row_factory = sqlite3.Row
    market_connection = sqlite3.connect(market)
    market_connection.row_factory = sqlite3.Row
    proof = prove_volume_session(
        history_connection,
        market_connection,
        symbol=SYMBOL,
        trading_date=stream_date,
    )
    assert proof.reason == expected
    history_connection.close()
    market_connection.close()


def test_finalized_rest_daily_volume_difference_remains_proven(
    tmp_path: Path,
) -> None:
    source, history, market, _, _, _ = _fixture(tmp_path)
    stream_date = "2026-09-14"
    volumes = _volumes(100)
    _finalize_rest_day(source, history, market, stream_date, volumes)
    connection = sqlite3.connect(market)
    connection.execute(
        "UPDATE daily_bars SET volume=volume+1 WHERE trading_date=?",
        (stream_date,),
    )
    connection.commit()
    connection.close()

    history_connection = sqlite3.connect(history)
    history_connection.row_factory = sqlite3.Row
    market_connection = sqlite3.connect(market)
    market_connection.row_factory = sqlite3.Row
    proof = prove_volume_session(
        history_connection,
        market_connection,
        symbol=SYMBOL,
        trading_date=stream_date,
    )
    history_connection.close()
    market_connection.close()

    assert proof.reason == "PROVEN"
    assert proof.represented_intraday_volume == sum(volumes)
    assert proof.daily_volume == sum(volumes) + 1
    assert [bar.volume for bar in proof.bars] == list(volumes)
