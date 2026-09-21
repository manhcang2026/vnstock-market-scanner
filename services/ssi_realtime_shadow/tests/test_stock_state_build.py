from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.market_session import VN_TZ
from app.market_storage_schema import ensure_market_storage_schema
from app.stock_state_build import build_stock_state_current, main
from app.state_contract import PUBLIC_CONTRACT_KEYS, get_current_state
from app.storage import SCHEMA
from app.volume_baseline import BASELINE_SCHEMA, COVERAGE_PROOF, volume_market_grid


TRADING_DATE = "2026-09-18"  # Friday; the builder may be run on the weekend.


def _write_realtime(
    path: Path,
    *,
    data_source: str = "SSI_STREAM",
    is_partial: bool = False,
    has_gap: bool = False,
    quality_status: str = "TRUSTED",
    row_volume: int = 10,
) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    grid = volume_market_grid("UPCOM")
    cumulative = 0
    for point in grid:
        cumulative += row_volume
        close = 100.0
        connection.execute(
            """
            INSERT INTO minute_bars (
                trading_date, minute, symbol, open, high, low, close, volume,
                last_total_volume, event_count, is_partial, exchange,
                quality_status, has_gap, data_source, updated_at
            ) VALUES (?, ?, 'VGI', ?, ?, ?, ?, ?, ?, 1, ?, 'UPCOM',
                      ?, ?, ?, ?)
            """,
            (
                TRADING_DATE,
                point.minute,
                close,
                close,
                close,
                close,
                row_volume,
                cumulative,
                int(is_partial),
                quality_status,
                int(has_gap),
                data_source,
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


def _write_baseline(
    path: Path,
    *,
    proof: str | None = None,
    as_of_date: str = TRADING_DATE,
    sessions_used: int = 10,
) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(BASELINE_SCHEMA)
    connection.executemany(
        "INSERT INTO volume_baseline_metadata(key, value) VALUES (?, ?)",
        (("schema_version", "2"), ("lookback", "10")),
    )
    if proof is not None:
        connection.executemany(
            "INSERT INTO volume_baseline_metadata(key, value) VALUES (?, ?)",
            (("coverage_proof", proof), ("as_of_date", as_of_date)),
        )
    connection.execute(
        """
        INSERT INTO volume_baseline_coverage (
            symbol, exchange, available_sessions, baseline_sessions_used,
            active_sessions_available, active_sessions_used,
            first_history_date, last_history_date
        ) VALUES (
            'VGI', 'UPCOM', 10, ?, 10, ?, '2026-09-04', '2026-09-17'
        )
        """,
        (sessions_used, sessions_used),
    )
    for index, point in enumerate(volume_market_grid("UPCOM"), start=1):
        connection.execute(
            """
            INSERT INTO volume_baseline (
                symbol, exchange, minute, session_segment, historical_sessions,
                avg_cumulative_volume, avg_volume_15, avg_volume_30,
                avg_opening_volume
            ) VALUES ('VGI', 'UPCOM', ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                point.minute,
                point.session_segment,
                sessions_used,
                index * 5,
                75 if point.rolling_15_ready else None,
                150 if point.rolling_30_ready else None,
            ),
        )
    connection.commit()
    connection.close()


def _write_daily_history(path: Path, *, current_volume: int = 2700) -> None:
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
    connection.execute(
        """
        INSERT INTO daily_bars (
            symbol, trading_date, exchange, open, high, low, close,
            volume, value, source, quality_status, finalized_at
        ) VALUES ('VGI', ?, 'UPCOM', 100, 120, 99, 120,
                  ?, NULL, 'SSI_DAILY_OHLC', 'TRUSTED', ?)
        """,
        (TRADING_DATE, current_volume, f"{TRADING_DATE}T15:01:00+07:00"),
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
    assert first["replay_day_audit"]["replay_day_completeness_proven"] is True

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
    assert row["signal_state"] == "WATCHING"
    assert row["signal_level"] == 1
    assert row["signal_at"] == row["event_at"]
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


@pytest.mark.parametrize(
    ("proof", "as_of_date", "sessions_used", "expected_trusted"),
    [
        (COVERAGE_PROOF, TRADING_DATE, 10, 1),
        (COVERAGE_PROOF, TRADING_DATE, 9, 0),
        (None, TRADING_DATE, 10, 0),
        (COVERAGE_PROOF, "2026-09-17", 10, 0),
    ],
)
def test_baseline_proof_metadata_and_exact_coverage_gate_state_trust(
    tmp_path: Path,
    proof: str | None,
    as_of_date: str,
    sessions_used: int,
    expected_trusted: int,
) -> None:
    realtime = tmp_path / "ssi_shadow.db"
    baseline = tmp_path / "ccc_v2_baseline.db"
    market = tmp_path / "ccc_market_v2.db"
    _write_realtime(realtime)
    _write_baseline(
        baseline,
        proof=proof,
        as_of_date=as_of_date,
        sessions_used=sessions_used,
    )
    _write_daily_history(market)

    summary = build_stock_state_current(
        realtime_db=realtime, baseline_db=baseline, market_db=market
    )
    connection = sqlite3.connect(market)
    state = connection.execute(
        "SELECT metrics_trusted,quality_status FROM stock_state_current WHERE symbol='VGI'"
    ).fetchone()
    connection.close()
    assert state[0] == expected_trusted
    assert summary["baseline_proven_symbol_count"] == expected_trusted
    assert summary["replay_day_audit"]["replay_day_completeness_proven"] is True
    if expected_trusted:
        assert state[1] == "TRUSTED"
    else:
        assert state[1] == "DEGRADED"


def _write_yearly_history(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.commit()
    connection.close()


def _write_auction_history(market: Path) -> None:
    connection = sqlite3.connect(market)
    dates = [
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT trading_date FROM daily_bars "
            "WHERE trading_date < ? ORDER BY trading_date DESC LIMIT 10",
            (TRADING_DATE,),
        )
    ]
    for index, trading_date in enumerate(dates):
        timestamp = f"{trading_date}T15:01:00+07:00"
        connection.execute(
            """
            INSERT INTO auction_session_history (
                symbol,trading_date,exchange,auction_type,auction_price,
                pre_auction_price,auction_volume,provider_session,source,
                quality,proof_code,finalized,created_at,updated_at
            ) VALUES ('VGI',?,'UPCOM','OPEN_AUCTION',100,NULL,400,
                      'ATO','SSI_STREAM','PROVEN','PROVIDER_SESSION_ATO',1,?,?)
            """,
            (trading_date, timestamp, timestamp),
        )
        proven = index < 5
        connection.execute(
            """
            INSERT INTO auction_session_history (
                symbol,trading_date,exchange,auction_type,auction_price,
                pre_auction_price,auction_volume,provider_session,source,
                quality,proof_code,finalized,created_at,updated_at
            ) VALUES ('VGI',?,'UPCOM','CLOSE_AUCTION',100,100,500,?,?,?,?,1,?,?)
            """,
            (
                trading_date,
                "ATC" if proven else None,
                "SSI_STREAM" if proven else "SSI_REST",
                "PROVEN" if proven else "INFERRED_BOUNDARY",
                "PROVIDER_SESSION_ATC"
                if proven
                else "CROSS_PROVIDER_BOUNDARY_CONFIRMED_V1",
                timestamp,
                timestamp,
            ),
        )
    connection.commit()
    connection.close()


def _write_current_auction_buckets(realtime: Path) -> None:
    connection = sqlite3.connect(realtime)
    rows = (
        (
            "OPEN_AUCTION", "ATO", 102.0, None, 1000, 0, 1000,
            "2026-09-18T09:00:00+07:00", "2026-09-18T09:15:00+07:00",
        ),
        (
            "CLOSE_AUCTION", "ATC", 118.0, 120.0, 1250, 1450, 2700,
            "2026-09-18T14:30:00+07:00", "2026-09-18T14:45:00+07:00",
        ),
    )
    for auction_type, session, price, pre, volume, start, end, first, last in rows:
        connection.execute(
            """
            INSERT INTO auction_session_buckets (
                symbol,trading_date,exchange,auction_type,provider_session,
                auction_price,pre_auction_price,auction_volume,start_total_volume,
                end_total_volume,event_count,out_of_order_events,first_event_at,
                last_event_at,quality_status,finalized,data_source,updated_at
            ) VALUES ('VGI',?,'UPCOM',?,?,?,?,?,?,?,1,0,?,?,'TRUSTED',1,
                      'SSI_STREAM',?)
            """,
            (
                TRADING_DATE, auction_type, session, price, pre, volume,
                start, end, first, last, last,
            ),
        )
    connection.commit()
    connection.close()


def _set_latest_price(realtime: Path, price: float) -> None:
    connection = sqlite3.connect(realtime)
    connection.execute(
        "UPDATE latest_quotes SET last_price=?, close=?, change=?, ratio_change=?",
        (price, price, price - 100, price - 100),
    )
    connection.commit()
    connection.close()


def test_replay_day_accepts_complete_trusted_ssi_stream(tmp_path: Path) -> None:
    realtime = tmp_path / "ssi_shadow.db"
    baseline = tmp_path / "ccc_v2_baseline.db"
    market = tmp_path / "ccc_market_v2.db"
    _write_realtime(realtime, data_source="SSI_STREAM")
    _write_baseline(baseline, proof=COVERAGE_PROOF)
    _write_daily_history(market)

    summary = build_stock_state_current(
        realtime_db=realtime, baseline_db=baseline, market_db=market
    )
    assert summary["replay_day_audit"]["replay_day_completeness_proven"] is True
    assert summary["baseline_proven_symbol_count"] == 1
    assert summary["trusted_state_count"] == 1


@pytest.mark.parametrize(
    ("realtime_options", "daily_volume", "reason"),
    [
        ({"has_gap": True}, 2700, "UNSAFE_INTRADAY"),
        ({"is_partial": True}, 2700, "UNSAFE_INTRADAY"),
        ({}, 2701, "VOLUME_MISMATCH"),
        ({"data_source": "LEGACY_UNVERIFIED"}, 2700, "UNSAFE_INTRADAY"),
    ],
)
def test_replay_day_rejects_unsafe_or_unreconciled_stream_rows(
    tmp_path: Path,
    realtime_options: dict[str, object],
    daily_volume: int,
    reason: str,
) -> None:
    realtime = tmp_path / "ssi_shadow.db"
    baseline = tmp_path / "ccc_v2_baseline.db"
    market = tmp_path / "ccc_market_v2.db"
    _write_realtime(realtime, **realtime_options)
    _write_baseline(baseline, proof=COVERAGE_PROOF)
    _write_daily_history(market, current_volume=daily_volume)

    summary = build_stock_state_current(
        realtime_db=realtime, baseline_db=baseline, market_db=market
    )
    audit = summary["replay_day_audit"]
    assert audit["replay_day_completeness_proven"] is False
    assert audit["failure_samples"][0]["reason"] == reason
    assert summary["baseline_proven_symbol_count"] == 0
    assert summary["trusted_state_count"] == 0


@pytest.mark.parametrize(
    ("later_price", "expected_state"),
    ((100.0, "MOMENTUM_MAINTAINED"), (99.0, "MOMENTUM_WEAKENING")),
)
def test_real_materializer_wires_same_day_previous_signal_state(
    tmp_path: Path, later_price: float, expected_state: str
) -> None:
    realtime = tmp_path / "ssi_shadow.db"
    baseline = tmp_path / "ccc_v2_baseline.db"
    market = tmp_path / "ccc_market_v2.db"
    _write_realtime(realtime)
    _write_baseline(baseline, proof=COVERAGE_PROOF)
    _write_daily_history(market)

    build_stock_state_current(
        realtime_db=realtime, baseline_db=baseline, market_db=market
    )
    connection = sqlite3.connect(market)
    assert connection.execute(
        "SELECT signal_state FROM stock_state_current WHERE symbol='VGI'"
    ).fetchone()[0] == "FLOW_PRICE_CONFIRMED"
    connection.close()

    _set_latest_price(realtime, later_price)
    build_stock_state_current(
        realtime_db=realtime, baseline_db=baseline, market_db=market
    )
    connection = sqlite3.connect(market)
    row = connection.execute(
        "SELECT signal_state,previous_signal_state FROM stock_state_current "
        "WHERE symbol='VGI'"
    ).fetchone()
    connection.close()
    assert row == (expected_state, "FLOW_PRICE_CONFIRMED")


def test_real_materializer_does_not_reuse_previous_day_signal_state(
    tmp_path: Path,
) -> None:
    realtime = tmp_path / "ssi_shadow.db"
    baseline = tmp_path / "ccc_v2_baseline.db"
    market = tmp_path / "ccc_market_v2.db"
    _write_realtime(realtime)
    _write_baseline(baseline, proof=COVERAGE_PROOF)
    _write_daily_history(market)
    build_stock_state_current(
        realtime_db=realtime, baseline_db=baseline, market_db=market
    )
    connection = sqlite3.connect(market)
    connection.execute(
        "UPDATE stock_state_current SET trading_date='2026-09-17' WHERE symbol='VGI'"
    )
    connection.commit()
    connection.close()
    _set_latest_price(realtime, 100.0)

    build_stock_state_current(
        realtime_db=realtime, baseline_db=baseline, market_db=market
    )
    connection = sqlite3.connect(market)
    row = connection.execute(
        "SELECT trading_date,signal_state,previous_signal_state "
        "FROM stock_state_current WHERE symbol='VGI'"
    ).fetchone()
    connection.close()
    assert row == (TRADING_DATE, "WATCHING", None)


def test_real_materializer_populates_canonical_ato_atc_and_frontend_contract(
    tmp_path: Path,
) -> None:
    realtime = tmp_path / "ssi_shadow.db"
    baseline = tmp_path / "ccc_v2_baseline.db"
    market = tmp_path / "ccc_market_v2.db"
    history = tmp_path / "ssi_history_2026.db"
    _write_realtime(realtime)
    _write_current_auction_buckets(realtime)
    _write_baseline(baseline, proof=COVERAGE_PROOF)
    _write_daily_history(market)
    _write_auction_history(market)
    _write_yearly_history(history)

    summary = build_stock_state_current(
        realtime_db=realtime,
        baseline_db=baseline,
        market_db=market,
        history_db=history,
    )
    connection = sqlite3.connect(market)
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT * FROM stock_state_current WHERE symbol='VGI'"
    ).fetchone()
    assert row["ato_baseline_sessions_used"] == 10
    assert row["ato_baseline_quality"] == "PROVEN"
    assert row["ato_avg_volume_10"] == 400
    assert row["ato_volume"] == 1000
    assert row["ato_rvol"] == pytest.approx(2.5)
    assert row["atc_baseline_sessions_used"] == 10
    assert row["atc_baseline_quality"] == "MIXED"
    assert row["atc_avg_volume_10"] == 500
    assert row["atc_volume"] == 1250
    assert row["atc_rvol"] == pytest.approx(2.5)
    assert row["atc_price_impact_pct"] == pytest.approx(-1.6666667)
    frontend = get_current_state(connection, "VGI")
    connection.close()
    assert frontend is not None
    assert tuple(frontend) == PUBLIC_CONTRACT_KEYS
    assert frontend["ato_rvol"] == pytest.approx(2.5)
    assert frontend["atc_rvol"] == pytest.approx(2.5)
    assert summary["auction_history_status"] == "AVAILABLE"
    assert summary["auction_metric_audit"][0]["status"] == "AVAILABLE"


def test_real_materializer_does_not_turn_0915_continuous_data_into_ato(
    tmp_path: Path,
) -> None:
    realtime = tmp_path / "ssi_shadow.db"
    baseline = tmp_path / "ccc_v2_baseline.db"
    market = tmp_path / "ccc_market_v2.db"
    history = tmp_path / "ssi_history_2026.db"
    _write_realtime(realtime)
    _write_baseline(baseline, proof=COVERAGE_PROOF)
    _write_daily_history(market)
    _write_auction_history(market)
    _write_yearly_history(history)
    build_stock_state_current(
        realtime_db=realtime,
        baseline_db=baseline,
        market_db=market,
        history_db=history,
    )
    connection = sqlite3.connect(market)
    row = connection.execute(
        "SELECT ato_volume,ato_rvol FROM stock_state_current WHERE symbol='VGI'"
    ).fetchone()
    connection.close()
    assert row == (None, None)
