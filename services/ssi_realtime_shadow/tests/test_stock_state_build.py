from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.market_session import VN_TZ
from app.market_storage_schema import ensure_market_storage_schema
from app.stock_state_build import build_stock_state_current, main
from app.storage import SCHEMA
from app.volume_baseline import BASELINE_SCHEMA, volume_market_grid


TRADING_DATE = "2026-09-18"  # Friday; the builder may be run on the weekend.


def _write_realtime(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    grid = volume_market_grid("UPCOM")
    cumulative = 0
    for point in grid:
        cumulative += 10
        close = 100.0
        connection.execute(
            """
            INSERT INTO minute_bars (
                trading_date, minute, symbol, open, high, low, close, volume,
                last_total_volume, event_count, is_partial, exchange,
                quality_status, has_gap, data_source, updated_at
            ) VALUES (?, ?, 'VGI', ?, ?, ?, ?, 10, ?, 1, 0, 'UPCOM',
                      'TRUSTED', 0, 'SSI_REST', ?)
            """,
            (
                TRADING_DATE,
                point.minute,
                close,
                close,
                close,
                close,
                cumulative,
                f"{TRADING_DATE}T{point.minute}:00+07:00",
            ),
        )
    connection.execute(
        """
        INSERT INTO latest_quotes (
            symbol, trading_date, event_time, last_price, total_volume,
            ref_price, open, high, low, close, bid_price1, bid_vol1,
            ask_price1, ask_vol1, change, ratio_change, exchange,
            trading_session, trading_status, updated_at
        ) VALUES (
            'VGI', ?, '14:59:00', 120, ?, 100, 100, 120, 99, 120,
            119, 1000, 120, 2000, 20, 20, 'UPCOM', 'C', 'OPEN', ?
        )
        """,
        (
            TRADING_DATE,
            cumulative,
            f"{TRADING_DATE}T14:59:00+07:00",
        ),
    )
    connection.commit()
    connection.close()


def _write_baseline(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(BASELINE_SCHEMA)
    connection.executemany(
        "INSERT INTO volume_baseline_metadata(key, value) VALUES (?, ?)",
        (("schema_version", "2"), ("lookback", "10")),
    )
    connection.execute(
        """
        INSERT INTO volume_baseline_coverage VALUES (
            'VGI', 'UPCOM', 10, 10, 10, 10, '2026-09-04', '2026-09-17'
        )
        """
    )
    for index, point in enumerate(volume_market_grid("UPCOM"), start=1):
        connection.execute(
            """
            INSERT INTO volume_baseline (
                symbol, exchange, minute, session_segment, historical_sessions,
                avg_cumulative_volume, avg_volume_15, avg_volume_30,
                avg_opening_volume
            ) VALUES ('VGI', 'UPCOM', ?, ?, 10, ?, ?, ?, NULL)
            """,
            (
                point.minute,
                point.session_segment,
                index * 5,
                75 if point.rolling_15_ready else None,
                150 if point.rolling_30_ready else None,
            ),
        )
    connection.commit()
    connection.close()


def _write_daily_history(path: Path) -> None:
    connection = sqlite3.connect(path)
    ensure_market_storage_schema(
        connection, applied_at=datetime(2026, 9, 18, tzinfo=VN_TZ)
    )
    cutoff = date.fromisoformat(TRADING_DATE)
    for days_back in range(200, 0, -1):
        trading_date = (cutoff - timedelta(days=days_back)).isoformat()
        connection.execute(
            """
            INSERT INTO daily_bars (
                symbol, trading_date, exchange, open, high, low, close,
                volume, value, source, quality_status, finalized_at
            ) VALUES ('VGI', ?, 'UPCOM', 100, 100, 100, 100,
                      1000, NULL, 'SSI_DAILY_OHLC', 'TRUSTED', ?)
            """,
            (trading_date, f"{trading_date}T15:01:00+07:00"),
        )
    connection.commit()
    connection.close()


def test_offline_builder_integrates_exact_ma_price_volume_and_is_idempotent(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    realtime = tmp_path / "ssi_shadow.db"
    baseline = tmp_path / "ccc_v2_baseline.db"
    market = tmp_path / "ccc_market_v2.db"
    _write_realtime(realtime)
    _write_baseline(baseline)
    _write_daily_history(market)

    first = build_stock_state_current(
        realtime_db=realtime, baseline_db=baseline, market_db=market
    )
    second = build_stock_state_current(
        realtime_db=realtime, baseline_db=baseline, market_db=market
    )

    assert first == second
    assert first["latest_trading_date"] == TRADING_DATE
    assert first["state_rows_written"] == 1
    assert first["baseline_10_10_count"] == 1
    assert first["ma10_ready_count"] == 1
    assert first["ma200_ready_count"] == 1
    assert first["price5_available_count"] == 1
    assert first["price15_available_count"] == 1
    assert first["trusted_state_count"] == 0
    assert first["degraded_unavailable_state_count"] == 1
    assert first["baseline_coverage_proven"] is False

    connection = sqlite3.connect(market)
    connection.row_factory = sqlite3.Row
    row = connection.execute("SELECT * FROM stock_state_current").fetchone()
    assert connection.execute("SELECT COUNT(*) FROM stock_state_current").fetchone()[0] == 1
    assert row["trading_date"] == TRADING_DATE
    assert row["ma10"] == pytest.approx(100)
    assert row["ma200"] == pytest.approx(100)
    assert row["price5_pct"] == pytest.approx(20)
    assert row["price15_pct"] == pytest.approx(20)
    assert row["metrics_trusted"] == 0
    assert row["quality_status"] == "DEGRADED"
    assert row["signal_state"] == "NORMAL"
    assert row["signal_level"] == 0
    assert row["signal_at"] is None
    assert row["previous_signal_state"] is None
    assert connection.execute("SELECT COUNT(*) FROM signal_events").fetchone()[0] == 0
    connection.close()

    assert main(
        [
            "--realtime-db", str(realtime),
            "--baseline-db", str(baseline),
            "--market-db", str(market),
        ]
    ) == 0
    cli_summary = json.loads(capsys.readouterr().out)
    assert cli_summary["latest_trading_date"] == TRADING_DATE
    assert cli_summary["sample"][0]["symbol"] == "VGI"
