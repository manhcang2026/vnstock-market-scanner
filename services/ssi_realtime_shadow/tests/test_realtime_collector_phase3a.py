from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import Thread

import pytest

from app.canonical_market_store import (
    MARKET_SCHEMA_VERSION,
    SCHEMA_SQL,
    CanonicalMarketStore,
    MinuteBar,
    RealtimeMarketEvent,
)
from app.collector import QuoteCollector
from app.main import (
    _ReconnectBackoff,
    _advance_minute_finalization,
    _reconnect_delay,
    _start_replacement_stream,
)
from app.market_session import VN_TZ


DAY = "2026-09-25"


def _moment(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 9, 25, hour, minute, second, tzinfo=VN_TZ)


def _event(**changes: object) -> dict[str, object]:
    event: dict[str, object] = {
        "Symbol": "HPG",
        "TradingDate": DAY,
        "Time": "09:11:10",
        "Market": "HOSE",
        "TradingSession": "LO",
        "LastPrice": 25.0,
        "TotalVol": 100,
    }
    event.update(changes)
    return event


def _collector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    now: list[datetime] | None = None,
    hook=None,
    universe: set[str] | None = None,
    started_at: datetime | None = None,
) -> tuple[QuoteCollector, CanonicalMarketStore]:
    clock = now or [_moment(9, 11, 10)]
    monkeypatch.setattr("app.collector._now_vn", lambda: clock[0])
    store = CanonicalMarketStore(tmp_path)
    collector = QuoteCollector(
        universe or {"HPG"},
        None,
        started_at=started_at or _moment(8, 30),
        canonical_store=store,
        post_commit_hook=hook,
    )
    return collector, store


@pytest.mark.parametrize(
    ("last_price", "total_volume", "expected_price", "expected_total"),
    [
        (25.0, 100, 25.0, 100),
        (None, 100, None, 100),
        (25.0, None, 25.0, None),
    ],
)
def test_partial_and_full_events_persist_independent_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    last_price: float | None,
    total_volume: int | None,
    expected_price: float | None,
    expected_total: int | None,
) -> None:
    collector, store = _collector(tmp_path, monkeypatch)
    collector.on_message(_event(LastPrice=last_price, TotalVol=total_volume))

    minute = store.connection(2026).execute("SELECT * FROM minute_bars").fetchone()
    assert minute["close"] == expected_price
    assert minute["provider_total_volume"] == expected_total
    assert collector.stats.canonical_events_written == 1
    assert collector.stats.partial_events_written == int(
        last_price is None or total_volume is None
    )


def test_completed_rest_session_locks_all_realtime_canonical_tables(
    tmp_path: Path,
) -> None:
    store = CanonicalMarketStore(tmp_path)
    prior = RealtimeMarketEvent(
        symbol="HPG",
        trading_date=DAY,
        event_at=_moment(14, 30),
        minute="14:30",
        exchange="HOSE",
        price=25,
        total_volume=100,
        provider_session="ATC",
    )
    store.write_realtime_event(prior, observed_at=_moment(14, 30))
    store.replace_rest_minute_sessions(
        [
            MinuteBar(
                "HPG", DAY, "14:29", exchange="HOSE", close=24,
                volume=90, provider_total_volume=90,
            )
        ]
    )
    connection = store.connection(2026)
    before = {
        table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
        for table in ("minute_bars", "latest_quotes", "auction_sessions")
    }

    result = store.write_realtime_event(
        RealtimeMarketEvent(
            symbol="HPG",
            trading_date=DAY,
            event_at=_moment(15, 0),
            minute="15:00",
            exchange="HOSE",
            price=30,
            total_volume=200,
            provider_session="ATC",
        ),
        observed_at=_moment(15, 0),
    )

    after = {
        table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
        for table in ("minute_bars", "latest_quotes", "auction_sessions")
    }
    assert after == before
    assert result.rest_session_locked is True
    assert result.latest_quote_updated is False
    assert result.late_event is False
    assert result.volume_regression is False
    assert result.volume_delta == 0
    assert result.effective_total_volume is None
    assert result.minute_was_finalized is False


@pytest.mark.parametrize(
    "proof",
    [
        None,
        ("minute", 1, "NO_DATA", 0),
        ("minute", 1, "FAILED", 0),
        ("daily", 1, "COMPLETED", 1),
        ("minute", 5, "COMPLETED", 1),
        ("minute", 1, "COMPLETED", 0),
    ],
)
def test_only_positive_completed_minute_resolution_one_proof_locks_stream(
    tmp_path: Path,
    proof: tuple[str, int, str, int] | None,
) -> None:
    store = CanonicalMarketStore(tmp_path)
    connection = store.connection(2026)
    if proof is not None:
        mode, resolution, status, rows_received = proof
        connection.execute(
            """INSERT INTO rest_session_status(
                   mode,symbol,trading_date,resolution,status,rows_received,updated_at
               ) VALUES(?,?,?,?,?,?,?)""",
            (mode, "HPG", DAY, resolution, status, rows_received, "test"),
        )
        connection.commit()

    result = store.write_realtime_event(
        RealtimeMarketEvent(
            symbol="HPG", trading_date=DAY, event_at=_moment(9, 11),
            minute="09:11", exchange="HOSE", price=25, total_volume=100,
            provider_session="LO",
        )
    )

    assert result.rest_session_locked is False
    assert connection.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0] == 1


def test_collector_rejects_post_rest_replay_before_all_projections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.collector._now_vn", lambda: _moment(15, 0))
    store = CanonicalMarketStore(tmp_path)
    store.replace_rest_minute_sessions(
        [
            MinuteBar(
                "HPG", DAY, "14:44", exchange="HOSE", close=25,
                volume=100, provider_total_volume=100,
            )
        ]
    )
    hooks: list[object] = []
    volume_events: list[object] = []
    collector = QuoteCollector(
        {"HPG"},
        None,
        started_at=_moment(8, 30),
        canonical_store=store,
        volume_event_handler=volume_events.append,
        post_commit_hook=lambda *args: hooks.append(args),
    )

    collector.on_message(_event(Time="14:45:00", LastPrice=26, TotalVol=110))
    collector.on_message(
        _event(
            Time="15:00:00", TradingSession="ATC", LastPrice=27, TotalVol=120
        )
    )

    connection = store.connection(2026)
    assert [
        tuple(row)
        for row in connection.execute(
            "SELECT minute,source,volume FROM minute_bars ORDER BY minute"
        )
    ] == [("14:44", "SSI_REST", 100)]
    assert connection.execute("SELECT COUNT(*) FROM latest_quotes").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM auction_sessions").fetchone()[0] == 0
    assert collector.stats.rejected_rest_completed_events == 2
    assert collector.stats.canonical_events_written == 0
    assert collector.stats.accepted_events == 0
    assert collector.stats.canonical_write_errors == 0
    assert collector.stats.post_commit_projection_errors == 0
    assert collector.stats.volume_shadow_events == 0
    assert hooks == [] and volume_events == []
    assert collector.snapshot_stats()["rejected_rest_completed_events"] == 2


def test_latest_quote_day_rollover_clears_previous_day_market_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector, store = _collector(tmp_path, monkeypatch)
    previous_at = datetime(2026, 9, 24, 14, 20, tzinfo=VN_TZ)
    store.write_realtime_event(
        RealtimeMarketEvent(
            symbol="HPG",
            trading_date="2026-09-24",
            event_at=previous_at,
            minute="14:20",
            exchange="HOSE",
            price=25,
            total_volume=10_000_000,
            provider_session="LO",
            ref_price=24,
            open=24.5,
            high=26,
            low=24,
            close=25,
            bid_price1=24.9,
            bid_vol1=100,
            ask_price1=25.1,
            ask_vol1=200,
            change=1,
            ratio_change=4.17,
            trading_status="TRADE",
        ),
        observed_at=previous_at,
    )

    collector.on_message(
        _event(
            Time="09:00:10",
            TradingSession="ATO",
            LastPrice=None,
            TotalVol=None,
        )
    )

    row = store.connection(2026).execute(
        "SELECT * FROM latest_quotes WHERE symbol='HPG'"
    ).fetchone()
    assert row["trading_date"] == DAY
    assert row["event_time"] == "09:00:10"
    assert row["provider_session"] == "ATO"
    assert row["exchange"] == "HOSE"
    for field in (
        "last_price",
        "last_price_at",
        "total_volume",
        "ref_price",
        "open",
        "high",
        "low",
        "close",
        "bid_price1",
        "bid_vol1",
        "ask_price1",
        "ask_vol1",
        "change",
        "ratio_change",
        "trading_status",
    ):
        assert row[field] is None


@pytest.mark.parametrize("provider_session", ["ATO", "ATC"])
def test_missing_price_auction_event_updates_nullable_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_session: str,
) -> None:
    collector, store = _collector(tmp_path, monkeypatch)
    collector.on_message(
        _event(TradingSession=provider_session, LastPrice=0, TotalVol=None)
    )

    row = store.connection(2026).execute(
        "SELECT * FROM auction_sessions WHERE auction_type=?", (provider_session,)
    ).fetchone()
    assert row["auction_price"] is None
    assert row["auction_volume"] is None
    assert row["event_count"] == 1
    assert collector.stats.auction_events_processed == 1


def test_throwing_post_commit_hook_cannot_rollback_market_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_hook(*_args: object) -> None:
        raise RuntimeError("calculation failed")

    collector, store = _collector(tmp_path, monkeypatch, hook=broken_hook)
    collector.on_message(_event())

    assert store.connection(2026).execute(
        "SELECT COUNT(*) FROM minute_bars"
    ).fetchone()[0] == 1
    assert collector.stats.post_commit_projection_errors == 1


def test_throwing_volume_projection_cannot_rollback_market_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.collector._now_vn", lambda: _moment(9, 11, 10))
    store = CanonicalMarketStore(tmp_path)

    def broken_projection(_event: object) -> None:
        raise RuntimeError("baseline unavailable")

    collector = QuoteCollector(
        {"HPG"},
        None,
        started_at=_moment(8, 30),
        canonical_store=store,
        volume_event_handler=broken_projection,
    )
    collector.on_message(_event())

    assert store.connection(2026).execute(
        "SELECT COUNT(*) FROM minute_bars"
    ).fetchone()[0] == 1
    assert collector.stats.post_commit_projection_errors == 1


def test_late_event_corrects_history_without_rewinding_latest_and_stays_finalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 12, 8)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(_event(Time="09:12:08", LastPrice=26, TotalVol=150))
    collector.on_message(_event(Time="09:11:50", LastPrice=24, TotalVol=120))

    connection = store.connection(2026)
    historical = connection.execute(
        """SELECT close,is_finalized,quality_status FROM minute_bars
           WHERE minute='09:11'"""
    ).fetchone()
    latest = connection.execute(
        "SELECT event_time,last_price,total_volume FROM latest_quotes WHERE symbol='HPG'"
    ).fetchone()
    assert tuple(historical) == (24, 1, "LATE_CORRECTION")
    assert tuple(latest) == ("09:12:08", 26, 150)
    assert collector.stats.late_events_merged == 1
    assert collector.stats.latest_quote_skipped_late == 1

    collector.on_message(_event(Time="09:11:55", LastPrice=25, TotalVol=125))
    corrected = connection.execute(
        "SELECT close,is_finalized FROM minute_bars WHERE minute='09:11'"
    ).fetchone()
    assert tuple(corrected) == (25, 1)
    assert connection.execute(
        "SELECT volume FROM minute_bars WHERE minute='09:12'"
    ).fetchone()[0] == 25


def test_volume_only_event_preserves_price_and_its_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 11, 10)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(_event(Time="09:11:10", LastPrice=90, TotalVol=100))
    clock[0] = _moment(10, 0, 10)
    collector.on_message(_event(Time="10:00:10", LastPrice=None, TotalVol=200))

    row = store.connection(2026).execute(
        """SELECT event_time,last_price,last_price_at,total_volume
           FROM latest_quotes WHERE symbol='HPG'"""
    ).fetchone()
    assert tuple(row) == (
        "10:00:10",
        90,
        "09:11:10",
        200,
    )


def test_existing_market_db_adds_nullable_price_provenance_without_data_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ccc_market_2026.db"
    connection = sqlite3.connect(path)
    legacy_schema = SCHEMA_SQL.replace(
        "    event_time TEXT,\n    last_price REAL,\n    last_price_at TEXT,\n",
        "    event_time TEXT,\n    last_price REAL,\n",
        1,
    )
    connection.executescript(legacy_schema)
    connection.execute(
        """INSERT INTO latest_quotes(
               symbol,trading_date,event_time,last_price,total_volume,updated_at
           ) VALUES('HPG', ?, '10:00:10', 90, 200, 'before-migration')""",
        (DAY,),
    )
    connection.execute(
        """INSERT INTO schema_meta(key,value,updated_at)
           VALUES('schema_version','3','before-migration')"""
    )
    connection.commit()
    connection.close()

    with CanonicalMarketStore(tmp_path) as store:
        migrated = store.connection(2026)
        columns = {
            row[1] for row in migrated.execute("PRAGMA table_info(latest_quotes)")
        }
        row = migrated.execute(
            """SELECT event_time,last_price,last_price_at,total_volume,updated_at
               FROM latest_quotes WHERE symbol='HPG'"""
        ).fetchone()
        version = migrated.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]

    assert "last_price_at" in columns
    assert tuple(row) == ("10:00:10", 90, None, 200, "before-migration")
    assert version == MARKET_SCHEMA_VERSION == "4"


def test_minute_finalizes_at_three_second_grace_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 12, 2)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(_event(Time="09:11:59"))
    connection = store.connection(2026)
    assert connection.execute(
        "SELECT is_finalized FROM minute_bars"
    ).fetchone()[0] == 0

    assert collector.advance_time(_moment(9, 12, 3)) == 1
    assert connection.execute(
        "SELECT is_finalized FROM minute_bars"
    ).fetchone()[0] == 1


def test_canonical_connection_supports_cross_thread_write_finalize_and_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 12, 2)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    errors: list[BaseException] = []
    finalized: list[int] = []

    def write() -> None:
        try:
            collector.on_message(_event(Time="09:11:59"))
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    def finalize_and_read() -> None:
        try:
            finalized.append(collector.advance_time(_moment(9, 12, 3)))
            with store._lock:
                row = store.connection(2026).execute(
                    "SELECT is_finalized FROM minute_bars"
                ).fetchone()
            finalized.append(int(row[0]))
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    writer = Thread(target=write)
    writer.start()
    writer.join()
    finalizer = Thread(target=finalize_and_read)
    finalizer.start()
    finalizer.join()

    assert errors == []
    assert finalized == [1, 1]


def test_finalization_rolls_back_on_error_and_can_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 12, 2)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(_event(Time="09:11:59"))
    connection = store.connection(2026)
    connection.executescript(
        """CREATE TRIGGER fail_minute_finalization
           BEFORE UPDATE OF is_finalized ON minute_bars
           WHEN NEW.is_finalized = 1
           BEGIN
               SELECT RAISE(ABORT, 'temporary finalize failure');
           END;"""
    )
    connection.commit()

    with pytest.raises(sqlite3.DatabaseError, match="temporary finalize failure"):
        store.finalize_due_minutes(_moment(9, 12, 3))
    assert not connection.in_transaction
    assert connection.execute(
        "SELECT is_finalized FROM minute_bars"
    ).fetchone()[0] == 0

    connection.execute("DROP TRIGGER fail_minute_finalization")
    connection.commit()
    assert store.finalize_due_minutes(_moment(9, 12, 3)) == 1


def test_periodic_finalization_failure_is_fail_open() -> None:
    class BrokenCollector:
        def advance_time(self, _now: datetime) -> int:
            raise sqlite3.OperationalError("database temporarily busy")

    assert _advance_minute_finalization(BrokenCollector(), _moment(9, 12, 3)) == 0


def test_normal_event_does_not_scan_all_unfinalized_or_daily_minutes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector, store = _collector(tmp_path, monkeypatch)
    connection = store.connection(2026)
    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    collector.on_message(_event())
    connection.set_trace_callback(None)

    normalized = [" ".join(statement.upper().split()) for statement in statements]
    assert not any("WHERE IS_FINALIZED=0" in statement for statement in normalized)
    assert not any(
        "SELECT MINUTE,PROVIDER_TOTAL_VOLUME,VOLUME FROM MINUTE_BARS" in statement
        for statement in normalized
    )


def test_minute_quality_is_based_on_merged_price_and_volume_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector, store = _collector(tmp_path, monkeypatch)
    collector.on_message(_event(Time="09:11:10", LastPrice=25, TotalVol=100))
    collector.on_message(_event(Time="09:11:20", LastPrice=26, TotalVol=None))
    collector.on_message(_event(Time="09:11:30", LastPrice=None, TotalVol=120))

    row = store.connection(2026).execute(
        """SELECT close,provider_total_volume,quality_status
           FROM minute_bars WHERE minute='09:11'"""
    ).fetchone()
    assert tuple(row) == (26, 120, "TRUSTED")
    assert collector.stats.partial_events_written == 2


def test_volume_regression_keeps_price_and_price_anomaly_keeps_volume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 11, 20)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(_event(Time="09:11:10", LastPrice=25, TotalVol=100))
    collector.on_message(_event(Time="09:11:20", LastPrice=26, TotalVol=90))
    collector.on_message(_event(Time="09:11:30", LastPrice=0, TotalVol=120))

    row = store.connection(2026).execute(
        "SELECT close,provider_total_volume,quality_status FROM minute_bars"
    ).fetchone()
    assert tuple(row) == (26, 120, "VOLUME_REGRESSION")
    assert collector.stats.canonical_events_written == 3


def test_lunch_boundaries_never_create_fake_minutes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(13, 0, 5)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(_event(Time="11:29:59", LastPrice=25, TotalVol=100))
    collector.on_message(_event(Time="13:00:01", LastPrice=26, TotalVol=120))
    collector.advance_time(clock[0])

    rows = store.connection(2026).execute(
        "SELECT minute FROM minute_bars ORDER BY minute"
    ).fetchall()
    assert [row[0] for row in rows] == ["11:29", "13:00"]


def test_atc_pre_auction_price_uses_latest_valid_continuous_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(14, 30, 1)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(_event(Time="14:29:59", LastPrice=25, TotalVol=100))
    collector.on_message(
        _event(Time="14:30:01", TradingSession="ATC", LastPrice=None, TotalVol=110)
    )

    row = store.connection(2026).execute(
        "SELECT pre_auction_price,auction_price FROM auction_sessions WHERE auction_type='ATC'"
    ).fetchone()
    assert tuple(row) == (25, None)


def test_ato_during_auction_uses_proven_zero_start_but_is_not_finalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 0, 10)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(
        _event(Time="09:00:10", TradingSession="ATO", TotalVol=100)
    )
    collector.on_message(
        _event(Time="09:00:20", TradingSession="ATO", TotalVol=250)
    )

    row = store.connection(2026).execute(
        """SELECT start_total_volume,end_total_volume,auction_volume,finalized
           FROM auction_sessions WHERE auction_type='ATO'"""
    ).fetchone()
    assert tuple(row) == (0, 250, 250, 0)


def test_mid_session_ato_does_not_fabricate_zero_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 10, 10)]
    collector, store = _collector(
        tmp_path,
        monkeypatch,
        now=clock,
        started_at=_moment(9, 5),
    )
    collector.on_message(
        _event(Time="09:10:10", TradingSession="ATO", TotalVol=100)
    )
    collector.on_message(
        _event(Time="09:10:20", TradingSession="ATO", TotalVol=250)
    )

    row = store.connection(2026).execute(
        """SELECT start_total_volume,end_total_volume,auction_volume
           FROM auction_sessions WHERE auction_type='ATO'"""
    ).fetchone()
    assert tuple(row) == (None, 250, None)


def test_ato_total_volume_regression_cannot_lower_high_watermark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 0, 10)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(
        _event(Time="09:00:10", TradingSession="ATO", TotalVol=250)
    )
    clock[0] = _moment(9, 0, 20)
    collector.on_message(
        _event(Time="09:00:20", TradingSession="ATO", TotalVol=200)
    )

    row = store.connection(2026).execute(
        """SELECT start_total_volume,end_total_volume,auction_volume
           FROM auction_sessions WHERE auction_type='ATO'"""
    ).fetchone()
    assert tuple(row) == (0, 250, 250)


def test_ato_retains_chronologically_latest_valid_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 10, 20)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(
        _event(
            Time="09:10:20", TradingSession="ATO", LastPrice=100, TotalVol=250
        )
    )
    clock[0] = _moment(9, 10, 30)
    collector.on_message(
        _event(
            Time="09:10:10", TradingSession="ATO", LastPrice=99, TotalVol=200
        )
    )

    row = store.connection(2026).execute(
        """SELECT auction_price,end_total_volume,last_event_at
           FROM auction_sessions WHERE auction_type='ATO'"""
    ).fetchone()
    assert tuple(row) == (100, 250, _moment(9, 10, 20).isoformat())


def test_hose_ato_finalizes_on_first_exit_event_without_minute_contamination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 0, 10)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(
        _event(Time="09:00:10", TradingSession="ATO", LastPrice=None, TotalVol=0)
    )
    clock[0] = _moment(9, 10, 10)
    collector.on_message(
        _event(Time="09:10:10", TradingSession="ATO", LastPrice=100, TotalVol=500)
    )
    clock[0] = _moment(9, 15, 0)
    collector.on_message(
        _event(Time="09:15:00", TradingSession="LO", LastPrice=999, TotalVol=700)
    )
    boundary = store.connection(2026).execute(
        """SELECT start_total_volume,end_total_volume,auction_volume,
                  auction_price,finalized,event_count,first_event_at,last_event_at
           FROM auction_sessions WHERE symbol='HPG' AND auction_type='ATO'"""
    ).fetchone()
    assert tuple(boundary) == (
        0,
        500,
        500,
        100,
        1,
        2,
        _moment(9, 0, 10).isoformat(),
        _moment(9, 10, 10).isoformat(),
    )

    clock[0] = _moment(9, 15, 20)
    collector.on_message(
        _event(Time="09:15:20", TradingSession="LO", LastPrice=101, TotalVol=700)
    )
    clock[0] = _moment(9, 15, 50)
    collector.on_message(
        _event(Time="09:15:50", TradingSession="LO", LastPrice=102, TotalVol=900)
    )

    unchanged = store.connection(2026).execute(
        """SELECT end_total_volume,auction_volume,auction_price,finalized,event_count
           FROM auction_sessions WHERE symbol='HPG' AND auction_type='ATO'"""
    ).fetchone()
    minute = store.connection(2026).execute(
        """SELECT close,provider_total_volume FROM minute_bars
           WHERE symbol='HPG' AND minute='09:15'"""
    ).fetchone()
    assert tuple(unchanged) == (500, 500, 100, 1, 2)
    assert tuple(minute) == (102, 900)


def test_ato_boundary_missing_price_finalizes_without_later_price_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 0, 10)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(
        _event(Time="09:00:10", TradingSession="ATO", LastPrice=None, TotalVol=0)
    )
    clock[0] = _moment(9, 14, 59)
    collector.on_message(
        _event(Time="09:14:59", TradingSession="ATO", LastPrice=None, TotalVol=500)
    )
    clock[0] = _moment(9, 15, 0)
    collector.on_message(
        _event(Time="09:15:00", TradingSession="LO", LastPrice=999, TotalVol=700)
    )
    clock[0] = _moment(9, 15, 20)
    collector.on_message(
        _event(Time="09:15:20", TradingSession="LO", LastPrice=101, TotalVol=700)
    )

    row = store.connection(2026).execute(
        """SELECT auction_price,end_total_volume,auction_volume,finalized
           FROM auction_sessions WHERE symbol='HPG' AND auction_type='ATO'"""
    ).fetchone()
    assert tuple(row) == (None, 500, 500, 1)


def test_ato_unknown_start_stays_unknown_at_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 10, 10)]
    collector, store = _collector(
        tmp_path, monkeypatch, now=clock, started_at=_moment(9, 5)
    )
    collector.on_message(
        _event(Time="09:10:10", TradingSession="ATO", LastPrice=90, TotalVol=250)
    )
    clock[0] = _moment(9, 15, 0)
    collector.on_message(
        _event(Time="09:15:00", TradingSession="LO", LastPrice=100, TotalVol=500)
    )

    row = store.connection(2026).execute(
        """SELECT start_total_volume,end_total_volume,auction_volume,
                  auction_price,finalized
           FROM auction_sessions WHERE symbol='HPG' AND auction_type='ATO'"""
    ).fetchone()
    assert tuple(row) == (None, 250, None, 90, 1)


def test_later_transition_finalizes_only_stored_ato_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 0, 10)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(
        _event(Time="09:00:10", TradingSession="ATO", LastPrice=None, TotalVol=0)
    )
    clock[0] = _moment(9, 14, 59)
    collector.on_message(
        _event(Time="09:14:59", TradingSession="ATO", LastPrice=None, TotalVol=0)
    )
    clock[0] = _moment(9, 15, 20)
    collector.on_message(
        _event(Time="09:15:20", TradingSession="LO", LastPrice=101, TotalVol=700)
    )
    clock[0] = _moment(9, 16, 0)
    collector.on_message(
        _event(Time="09:16:00", TradingSession="LO", LastPrice=102, TotalVol=900)
    )

    row = store.connection(2026).execute(
        """SELECT end_total_volume,auction_volume,auction_price,finalized,event_count
           FROM auction_sessions WHERE symbol='HPG' AND auction_type='ATO'"""
    ).fetchone()
    assert tuple(row) == (0, 0, None, 1, 2)


def test_late_ato_event_cannot_modify_any_finalized_summary_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_moment(9, 0, 10)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(
        _event(Time="09:00:10", TradingSession="ATO", LastPrice=None, TotalVol=0)
    )
    clock[0] = _moment(9, 10, 10)
    collector.on_message(
        _event(Time="09:10:10", TradingSession="ATO", LastPrice=100, TotalVol=500)
    )
    clock[0] = _moment(9, 15, 0)
    collector.on_message(
        _event(Time="09:15:00", TradingSession="LO", LastPrice=999, TotalVol=700)
    )
    connection = store.connection(2026)
    before = dict(
        connection.execute(
            """SELECT * FROM auction_sessions
               WHERE symbol='HPG' AND auction_type='ATO'"""
        ).fetchone()
    )
    clock[0] = _moment(9, 15, 10)
    collector.on_message(
        _event(Time="09:10:30", TradingSession="ATO", LastPrice=99, TotalVol=300)
    )

    after = dict(
        connection.execute(
            """SELECT * FROM auction_sessions
               WHERE symbol='HPG' AND auction_type='ATO'"""
        ).fetchone()
    )
    historical = connection.execute(
        """SELECT close,provider_total_volume FROM minute_bars
           WHERE symbol='HPG' AND minute='09:10'"""
    ).fetchone()
    assert before["event_count"] == 2
    assert after == before
    assert tuple(historical) == (99, 500)


@pytest.mark.parametrize("exchange", ["HNX", "UPCOM"])
def test_non_hose_ato_code_is_raw_evidence_without_auction_bucket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exchange: str
) -> None:
    collector, store = _collector(tmp_path, monkeypatch)
    collector.on_message(
        _event(Market=exchange, TradingSession="ATO", LastPrice=25, TotalVol=100)
    )

    connection = store.connection(2026)
    minute = connection.execute(
        "SELECT provider_session FROM minute_bars WHERE symbol='HPG'"
    ).fetchone()[0]
    latest = connection.execute(
        "SELECT provider_session FROM latest_quotes WHERE symbol='HPG'"
    ).fetchone()[0]
    assert minute == latest == "ATO"
    assert connection.execute(
        "SELECT COUNT(*) FROM auction_sessions WHERE symbol='HPG'"
    ).fetchone()[0] == 0


def test_out_of_clock_hose_ato_is_raw_evidence_without_auction_bucket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = "HOSE"
    provider_session = "ATO"
    event_time = "10:00:00"
    hour, minute, second = (int(part) for part in event_time.split(":"))
    clock = [_moment(hour, minute, second)]
    collector, store = _collector(tmp_path, monkeypatch, now=clock)
    collector.on_message(
        _event(
            Market=exchange,
            Time=event_time,
            TradingSession=provider_session,
            LastPrice=25,
            TotalVol=100,
        )
    )

    connection = store.connection(2026)
    minute_row = connection.execute(
        """SELECT provider_session,close,provider_total_volume
           FROM minute_bars WHERE symbol='HPG'"""
    ).fetchone()
    latest = connection.execute(
        "SELECT provider_session,last_price FROM latest_quotes WHERE symbol='HPG'"
    ).fetchone()
    assert tuple(minute_row) == (provider_session, 25, 100)
    assert tuple(latest) == (provider_session, 25)
    assert connection.execute(
        "SELECT COUNT(*) FROM auction_sessions WHERE symbol='HPG'"
    ).fetchone()[0] == 0


def test_reconnect_backoff_remains_bounded_after_repeated_failures() -> None:
    delays = [_reconnect_delay(attempt) for attempt in range(20)]
    assert delays[:4] == [1, 2, 4, 8]
    assert delays[-1] == 60
    assert all(delay <= 60 for delay in delays)


def test_reconnect_backoff_resets_after_successful_reconnect() -> None:
    state = _ReconnectBackoff()
    assert state.ready(0)
    assert state.failed(0) == 1
    assert not state.ready(0.5)
    assert state.failed(1) == 2
    assert state.failed_attempts == 2
    assert state.succeeded() == 3
    assert state.failed_attempts == 0
    assert state.next_attempt_at == 0
    assert state.failed(100) == 1


def test_reconnect_starts_replacement_even_when_old_cleanup_throws() -> None:
    calls: list[str] = []

    class BrokenOldStream:
        def stop(self) -> None:
            calls.append("stop")
            raise RuntimeError("stop failed")

        def close(self) -> None:
            calls.append("close")
            raise RuntimeError("close failed")

    class ReplacementStream:
        def start(self, _on_message, _on_error, channel: str) -> None:
            calls.append(f"start:{channel}")

    replacement = ReplacementStream()
    result = _start_replacement_stream(
        BrokenOldStream(),
        lambda: replacement,
        lambda _message: None,
        lambda _error: None,
        "X:ALL",
    )

    assert result is replacement
    assert calls == ["stop", "close", "start:X:ALL"]


def test_collector_needs_no_baseline_and_universe_has_no_schema_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    universe = {f"S{index:04d}" for index in range(1001)}
    collector, store = _collector(
        tmp_path, monkeypatch, universe=universe
    )
    collector.on_message(_event(Symbol="S1000"))
    row = store.connection(2026).execute(
        "SELECT symbol FROM minute_bars"
    ).fetchone()
    assert row[0] == "S1000"


def test_unusable_provider_time_is_the_identity_rejection_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector, store = _collector(tmp_path, monkeypatch)
    collector.on_message(_event(Time="not-a-time"))
    assert store.connection(2026).execute(
        "SELECT COUNT(*) FROM minute_bars"
    ).fetchone()[0] == 0
    assert collector.stats.malformed_identity_events == 1
