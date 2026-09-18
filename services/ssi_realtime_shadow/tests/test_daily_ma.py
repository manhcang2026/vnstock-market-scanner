from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from app.daily_ma import (
    DailyClose,
    DailyMAError,
    calculate_moving_averages,
    calculate_moving_averages_from_db,
)
from app.market_storage_schema import ensure_market_storage_schema


def closes(count: int, *, quality: str = "TRUSTED") -> list[DailyClose]:
    start = date(2025, 1, 1)
    return [
        DailyClose((start + timedelta(days=index)).isoformat(), float(index + 1), quality)
        for index in range(count)
    ]


@pytest.mark.parametrize("count", [0, 9])
def test_fewer_than_ten_sessions_never_produce_ma10(count: int) -> None:
    result = calculate_moving_averages(
        symbol="hpg", as_of_date="2026-09-18", bars=closes(count)
    )
    assert result.ma10 is None
    assert result.ma10_sessions == count
    assert result.ma200 is None
    assert result.ma200_sessions == count


def test_exact_ten_sessions_produce_arithmetic_ma10() -> None:
    result = calculate_moving_averages(
        symbol="HPG", as_of_date="2026-09-18", bars=closes(10)
    )
    assert result.ma10 == pytest.approx(5.5)
    assert result.ma10_sessions == 10
    assert result.ma10_reason is None
    assert result.ma200 is None


def test_eleven_sessions_use_latest_ten_only() -> None:
    result = calculate_moving_averages(
        symbol="HPG", as_of_date="2026-09-18", bars=reversed(closes(11))
    )
    assert result.ma10 == pytest.approx(6.5)
    assert result.latest_completed_session == "2025-01-11"


def test_199_sessions_never_produce_partial_ma200() -> None:
    result = calculate_moving_averages(
        symbol="HPG", as_of_date="2026-09-18", bars=closes(199)
    )
    assert result.ma200 is None
    assert result.ma200_sessions == 199
    assert result.ma200_reason == "INSUFFICIENT_SESSIONS:199/200"


def test_exact_200_sessions_produce_arithmetic_ma200() -> None:
    result = calculate_moving_averages(
        symbol="HPG", as_of_date="2026-09-18", bars=closes(200)
    )
    assert result.ma10 == pytest.approx(195.5)
    assert result.ma200 == pytest.approx(100.5)
    assert result.ma200_sessions == 200


def test_201_sessions_use_latest_200_only() -> None:
    result = calculate_moving_averages(
        symbol="HPG", as_of_date="2026-09-18", bars=closes(201)
    )
    assert result.ma200 == pytest.approx(101.5)


def test_as_of_date_and_later_rows_are_excluded() -> None:
    bars = closes(10) + [
        DailyClose("2026-09-18", 9999, "TRUSTED"),
        DailyClose("2026-09-19", 9999, "TRUSTED"),
    ]
    result = calculate_moving_averages(
        symbol="HPG", as_of_date="2026-09-18", bars=bars
    )
    assert result.ma10 == pytest.approx(5.5)
    assert result.latest_completed_session == "2025-01-10"


def test_calendar_gaps_and_weekends_do_not_change_session_arithmetic() -> None:
    bars = [
        DailyClose(day, float(index + 1), "TRUSTED")
        for index, day in enumerate(
            (
                "2026-08-31", "2026-09-01", "2026-09-03", "2026-09-04",
                "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10",
                "2026-09-11", "2026-09-14",
            )
        )
    ]
    result = calculate_moving_averages(
        symbol="HPG", as_of_date="2026-09-18", bars=bars
    )
    assert result.ma10 == pytest.approx(5.5)


@pytest.mark.parametrize("quality", ["DEGRADED", "UNAVAILABLE"])
def test_bad_recent_row_blocks_ma_without_reaching_farther_back(
    quality: str,
) -> None:
    bars = closes(11)
    bars[-5] = DailyClose(bars[-5].trading_date, bars[-5].close, quality)
    result = calculate_moving_averages(
        symbol="HPG", as_of_date="2026-09-18", bars=bars
    )
    assert result.ma10 is None
    assert result.ma10_sessions == 9
    assert result.ma10_reason == "UNTRUSTED_REQUIRED_WINDOW:9/10"


def test_unavailable_latest_row_blocks_ma200_instead_of_using_older_row() -> None:
    bars = closes(201)
    bars[-1] = DailyClose(bars[-1].trading_date, bars[-1].close, "UNAVAILABLE")
    result = calculate_moving_averages(
        symbol="HPG", as_of_date="2026-09-18", bars=bars
    )
    assert result.ma200 is None
    assert result.ma200_sessions == 199
    assert result.ma200_reason == "UNTRUSTED_REQUIRED_WINDOW:199/200"


def test_latest_completed_session_is_latest_trusted_valid_close() -> None:
    bars = closes(10)
    bars[-1] = DailyClose(bars[-1].trading_date, bars[-1].close, "DEGRADED")
    result = calculate_moving_averages(
        symbol="HPG", as_of_date="2026-09-18", bars=bars
    )
    assert result.latest_completed_session == "2025-01-09"


@pytest.mark.parametrize("bad_close", [float("nan"), float("inf"), 0, -1])
def test_invalid_recent_close_blocks_trusted_looking_ma(bad_close: float) -> None:
    bars = closes(10)
    bars[-1] = DailyClose(bars[-1].trading_date, bad_close, "TRUSTED")
    result = calculate_moving_averages(
        symbol="HPG", as_of_date="2026-09-18", bars=bars
    )
    assert result.ma10 is None
    assert result.ma10_sessions == 9


def test_conflicting_duplicate_session_is_rejected() -> None:
    bars = closes(10)
    bars.append(DailyClose(bars[-1].trading_date, 999, "TRUSTED"))
    with pytest.raises(DailyMAError, match="Conflicting"):
        calculate_moving_averages(
            symbol="HPG", as_of_date="2026-09-18", bars=bars
        )


def test_database_adapter_reads_only_dates_before_cutoff() -> None:
    connection = sqlite3.connect(":memory:")
    ensure_market_storage_schema(
        connection, applied_at="2026-09-18T10:00:00+07:00"
    )
    for index, bar in enumerate(closes(10)):
        connection.execute(
            """
            INSERT INTO daily_bars VALUES (
                ?, ?, 'HOSE', ?, ?, ?, ?, 100, NULL,
                'SSI_DAILY_OHLC', 'TRUSTED', '2026-09-18T10:00:00+07:00'
            )
            """,
            ("HPG", bar.trading_date, bar.close, bar.close, bar.close, bar.close),
        )
    connection.execute(
        """
        INSERT INTO daily_bars VALUES (
            'HPG', '2026-09-18', 'HOSE', 999, 999, 999, 999, 100, NULL,
            'SSI_DAILY_OHLC', 'TRUSTED', '2026-09-18T16:00:00+07:00'
        )
        """
    )
    connection.commit()
    result = calculate_moving_averages_from_db(
        connection, symbol="hpg", as_of_date="2026-09-18"
    )
    assert result.ma10 == pytest.approx(5.5)
    assert result.latest_completed_session == "2025-01-10"
    connection.close()
