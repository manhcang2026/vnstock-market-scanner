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


def test_ato_uses_zero_start_only_when_day_start_is_proven(
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
        """SELECT start_total_volume,end_total_volume,auction_volume
           FROM auction_sessions WHERE auction_type='ATO'"""
    ).fetchone()
    assert tuple(row) == (0, 250, 250)


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
