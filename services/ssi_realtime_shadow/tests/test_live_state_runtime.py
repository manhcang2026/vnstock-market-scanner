from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import app.live_state_runtime as live_module

from app.live_runtime_harness import LiveRuntimeHarness
from app.live_state_runtime import LiveStateRuntime
from app.market_session import VN_TZ
from app.market_storage_schema import ensure_market_storage_schema
from app.realtime_volume import RealtimeVolumeEngine, VolumeEvent
from app.state_contract import PUBLIC_CONTRACT_KEYS, get_current_state
from app.storage import SQLiteStore
from app.volume_baseline import (
    BASELINE_SCHEMA,
    COVERAGE_PROOF,
    prove_replay_volume_session,
    volume_market_grid,
)


DAY = "2026-09-21"


def _at(minute: str, day: str = DAY) -> datetime:
    return datetime.fromisoformat(f"{day}T{minute}:00").replace(tzinfo=VN_TZ)


def _baseline(path: Path, *, day: str = DAY, sessions: int = 10) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(BASELINE_SCHEMA)
    connection.executemany(
        "INSERT INTO volume_baseline_metadata(key,value) VALUES (?,?)",
        (
            ("schema_version", "2"),
            ("lookback", "10"),
            ("coverage_proof", COVERAGE_PROOF),
            ("as_of_date", day),
        ),
    )
    connection.execute(
        "INSERT INTO volume_baseline_coverage ("
        "symbol,exchange,available_sessions,baseline_sessions_used,"
        "active_sessions_available,active_sessions_used,"
        "first_history_date,last_history_date) VALUES "
        "('SHS','HNX',10,?,10,?,'2026-09-07','2026-09-18')",
        (sessions, sessions),
    )
    for index, point in enumerate(volume_market_grid("HNX"), start=1):
        connection.execute(
            "INSERT INTO volume_baseline VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "SHS", "HNX", point.minute, point.session_segment, sessions,
                float(index),
                15.0 if point.rolling_15_ready else None,
                30.0 if point.rolling_30_ready else None,
                None,
            ),
        )
    connection.commit()
    connection.close()


def _market(path: Path) -> None:
    connection = sqlite3.connect(path)
    ensure_market_storage_schema(connection, applied_at=_at("08:00"))
    cutoff = date.fromisoformat(DAY)
    for offset in range(200, 0, -1):
        session = (cutoff - timedelta(days=offset)).isoformat()
        connection.execute(
            """
            INSERT INTO daily_bars (
                symbol,trading_date,exchange,open,high,low,close,volume,value,
                source,quality_status,finalized_at
            ) VALUES ('SHS',?,'HNX',100,100,100,100,1000,NULL,
                      'SSI_DAILY_OHLC','TRUSTED',?)
            """,
            (session, f"{session}T15:01:00+07:00"),
        )
    connection.commit()
    connection.close()


def _hot(store: SQLiteStore, *, unsafe_minute: str | None = None) -> None:
    cumulative = 0
    moment = _at("09:00")
    end = _at("09:30")
    while moment <= end:
        minute = moment.strftime("%H:%M")
        cumulative += 10
        unsafe = minute == unsafe_minute
        store.upsert_minute_bar(
            trading_date=DAY,
            minute=minute,
            symbol="SHS",
            price=100,
            volume_delta=10,
            total_volume=cumulative,
            is_partial=unsafe,
            exchange="HNX",
            quality_status="PARTIAL" if unsafe else "TRUSTED",
            has_gap=False,
            gap_from=None,
            gap_to=None,
            updated_at=moment.isoformat(),
        )
        moment += timedelta(minutes=1)
    store.upsert_latest_quote(
        {
            "symbol": "SHS", "trading_date": DAY, "event_time": "09:31:30",
            "last_price": 120, "total_volume": cumulative, "ref_price": 100,
            "open": 100, "high": 120, "low": 100, "close": 120,
            "bid_price1": 119, "bid_vol1": 1000,
            "ask_price1": 120, "ask_vol1": 1000,
            "change": 20, "ratio_change": 20, "exchange": "HNX",
            "trading_session": "LO", "trading_status": "OPEN",
            "updated_at": _at("09:31").isoformat(),
        }
    )
    store.commit()


def _runtime(
    tmp_path: Path,
    *,
    unsafe_minute: str | None = None,
    sessions: int = 10,
):
    baseline = tmp_path / "baseline.db"
    market = tmp_path / "market.db"
    hot = tmp_path / "hot.db"
    _baseline(baseline, sessions=sessions)
    _market(market)
    store = SQLiteStore(hot)
    _hot(store, unsafe_minute=unsafe_minute)
    engine = RealtimeVolumeEngine(baseline)
    runtime = LiveStateRuntime(
        volume_engine=engine,
        hot_store=store,
        market_db_path=market,
        history_db_path=tmp_path / "missing-history.db",
        active_at=_at("09:31"),
    )
    return store, engine, runtime, market


def _set_quote(
    store: SQLiteStore, *, minute: str, price: float, total_volume: int
) -> None:
    store.upsert_latest_quote(
        {
            "symbol": "SHS", "trading_date": DAY,
            "event_time": f"{minute}:30", "last_price": price,
            "total_volume": total_volume, "ref_price": 100,
            "open": 100, "high": max(100, price), "low": min(100, price),
            "close": price, "bid_price1": price, "bid_vol1": 1000,
            "ask_price1": price, "ask_vol1": 1000,
            "change": price - 100, "ratio_change": price - 100,
            "exchange": "HNX", "trading_session": "LO",
            "trading_status": "OPEN", "updated_at": _at(minute).isoformat(),
        }
    )
    store.commit()


def test_live_trust_does_not_require_current_day_daily_ohlc(tmp_path: Path) -> None:
    store, engine, runtime, market = _runtime(tmp_path)
    snapshot = engine.get_snapshot("SHS")
    assert snapshot is not None and snapshot.metrics_trusted

    assert runtime.handle_snapshot(snapshot, observed_at=_at("09:31"))

    connection = sqlite3.connect(market)
    connection.row_factory = sqlite3.Row
    assert connection.execute(
        "SELECT COUNT(*) FROM daily_bars WHERE trading_date=?", (DAY,)
    ).fetchone()[0] == 0
    row = connection.execute(
        "SELECT * FROM stock_state_current WHERE symbol='SHS'"
    ).fetchone()
    assert row["metrics_trusted"] == 1
    assert row["quality_status"] == "TRUSTED"
    assert row["signal_state"] == "FLOW_PRICE_CONFIRMED"
    serialized = get_current_state(connection, "SHS")
    assert serialized is not None
    assert tuple(serialized) == PUBLIC_CONTRACT_KEYS
    assert serialized["contract_version"] == "ccc-state-v1"
    assert connection.execute("SELECT COUNT(*) FROM signal_events").fetchone()[0] == 0
    source = sqlite3.connect(store.path)
    source.row_factory = sqlite3.Row
    replay_proof = prove_replay_volume_session(
        source, connection, symbol="SHS", trading_date=DAY
    )
    assert not replay_proof.proven
    assert replay_proof.reason == "DAILY_MISSING"
    source.close()
    connection.close()
    runtime.close()
    store.close()


def test_restart_hydration_preserves_volume_and_continues_without_double_count(
    tmp_path: Path,
) -> None:
    store, engine, runtime, market = _runtime(tmp_path)
    before = engine.get_snapshot("SHS")
    assert before is not None
    before_cumulative = before.cumulative_volume
    runtime.close()

    restarted_engine = RealtimeVolumeEngine(tmp_path / "baseline.db")
    restarted = LiveStateRuntime(
        volume_engine=restarted_engine,
        hot_store=store,
        market_db_path=market,
        history_db_path=tmp_path / "missing-history.db",
        active_at=_at("09:31"),
    )
    hydrated = restarted_engine.get_snapshot("SHS")
    assert hydrated is not None
    assert hydrated.cumulative_volume == before_cumulative

    event = VolumeEvent(
        symbol="SHS", exchange="HNX", trading_date=DAY,
        event_time=_at("09:31"), minute="09:31", volume_delta=5,
        total_volume=315, quality_status="TRUSTED",
    )
    restarted_engine.on_event(event)
    restarted_engine.advance_time(_at("09:32"))
    after = restarted_engine.get_snapshot("SHS")
    assert after is not None
    assert after.cumulative_volume == before_cumulative + 5
    restarted.close()
    store.close()


def test_unsafe_hydration_remains_untrusted_and_old_day_is_not_loaded(
    tmp_path: Path,
) -> None:
    store, engine, runtime, _market_path = _runtime(
        tmp_path, unsafe_minute="09:10"
    )
    snapshot = engine.get_snapshot("SHS")
    assert snapshot is not None
    assert not snapshot.metrics_trusted
    assert "CURRENT_PARTIAL" in snapshot.reasons
    assert runtime.hydration_report.rows_hydrated == 31
    runtime.close()
    store.close()

    old_root = tmp_path / "old"
    old_root.mkdir()
    _baseline(old_root / "baseline.db")
    old_store = SQLiteStore(old_root / "hot.db")
    old_store.upsert_minute_bar(
        trading_date="2026-09-18", minute="09:00", symbol="SHS", price=100,
        volume_delta=99, total_volume=99, is_partial=False, exchange="HNX",
        quality_status="TRUSTED", has_gap=False, gap_from=None, gap_to=None,
        updated_at="2026-09-18T09:00:00+07:00",
    )
    old_store.commit()
    old_engine = RealtimeVolumeEngine(old_root / "baseline.db")
    report_runtime = LiveStateRuntime(
        volume_engine=old_engine,
        hot_store=old_store,
        market_db_path=old_root / "market.db",
        history_db_path=old_root / "history.db",
        active_at=_at("09:31"),
    )
    assert report_runtime.hydration_report.rows_seen == 0
    assert old_engine.get_snapshot("SHS") is None
    report_runtime.close()
    old_store.close()


def test_timer_advances_zero_volume_minute_without_fabricating_trade(
    tmp_path: Path,
) -> None:
    store, engine, runtime, market = _runtime(tmp_path)
    before = engine.get_snapshot("SHS")
    assert before is not None
    changed = engine.advance_time(_at("09:33"))
    assert changed["SHS"].as_of_minute == "09:32"
    assert changed["SHS"].cumulative_volume == before.cumulative_volume
    assert runtime.handle_snapshot(changed["SHS"], observed_at=_at("09:33"))
    connection = sqlite3.connect(market)
    assert connection.execute(
        "SELECT cumulative_volume FROM stock_state_current WHERE symbol='SHS'"
    ).fetchone()[0] == before.cumulative_volume
    connection.close()
    runtime.close()
    store.close()


def test_harness_uses_one_volume_engine_call_per_normalized_event(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.db"
    _baseline(baseline)
    store = SQLiteStore(tmp_path / "hot.db")
    runtime = LiveStateRuntime(
        volume_engine=RealtimeVolumeEngine(baseline),
        hot_store=store,
        market_db_path=tmp_path / "market.db",
        history_db_path=tmp_path / "history.db",
        active_at=_at("08:50"),
    )
    harness = LiveRuntimeHarness(
        universe={"SHS"}, store=store, volume_engine=runtime.volume_engine,
        live_runtime=runtime, started_at=_at("08:50"),
    )
    harness.feed(
        {
            "Symbol": "SHS", "Market": "HNX", "TradingDate": DAY,
            "Time": "09:00:30", "LastPrice": 100, "TotalVol": 10,
            "RefPrice": 100, "TradingSession": "LO",
        }
    )
    assert harness.volume_engine_calls == 1
    assert harness.collector.stats.volume_shadow_events == 1
    runtime.close()
    store.close()


def test_once_per_minute_lifecycle_and_inactive_session_preservation(
    tmp_path: Path,
) -> None:
    store, engine, runtime, market = _runtime(tmp_path)
    initial = engine.get_snapshot("SHS")
    assert initial is not None
    assert runtime.handle_snapshot(initial, observed_at=_at("09:31"))
    assert not runtime.handle_snapshot(initial, observed_at=_at("09:31"))
    assert runtime.live_state_updates == 1

    # Repeated events in 09:31 refresh the exact price anchor but do not persist.
    store.upsert_minute_bar(
        trading_date=DAY, minute="09:31", symbol="SHS", price=120,
        volume_delta=10, total_volume=320, is_partial=False, exchange="HNX",
        quality_status="TRUSTED", has_gap=False, gap_from=None, gap_to=None,
        updated_at=_at("09:31").isoformat(),
    )
    _set_quote(store, minute="09:31", price=120, total_volume=320)
    event31 = VolumeEvent(
        symbol="SHS", exchange="HNX", trading_date=DAY,
        event_time=_at("09:31"), minute="09:31", volume_delta=10,
        total_volume=320, quality_status="TRUSTED",
    )
    same_minute = engine.on_event(event31)
    assert not runtime.handle_snapshot(same_minute, event=event31)

    # The next minute finalizes 09:31. Same-day positive state becomes maintained.
    store.upsert_minute_bar(
        trading_date=DAY, minute="09:32", symbol="SHS", price=120,
        volume_delta=10, total_volume=330, is_partial=False, exchange="HNX",
        quality_status="TRUSTED", has_gap=False, gap_from=None, gap_to=None,
        updated_at=_at("09:32").isoformat(),
    )
    _set_quote(store, minute="09:32", price=120, total_volume=330)
    event32 = VolumeEvent(
        symbol="SHS", exchange="HNX", trading_date=DAY,
        event_time=_at("09:32"), minute="09:32", volume_delta=10,
        total_volume=330, quality_status="TRUSTED",
    )
    snapshot32 = engine.on_event(event32)
    assert runtime.handle_snapshot(snapshot32, event=event32)

    connection = sqlite3.connect(market)
    assert connection.execute(
        "SELECT signal_state FROM stock_state_current WHERE symbol='SHS'"
    ).fetchone()[0] == "MOMENTUM_MAINTAINED"
    assert connection.execute("SELECT COUNT(*) FROM stock_state_current").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM signal_events").fetchone()[0] == 0

    lunch = engine.advance_time(_at("11:45"))["SHS"]
    assert runtime.handle_snapshot(lunch, observed_at=_at("11:45"))
    assert connection.execute(
        "SELECT signal_state FROM stock_state_current WHERE symbol='SHS'"
    ).fetchone()[0] == "MOMENTUM_MAINTAINED"
    connection.close()
    runtime.close()
    store.close()


def test_selling_pressure_and_incomplete_baseline_watching_paths(
    tmp_path: Path,
) -> None:
    selling_root = tmp_path / "selling"
    selling_root.mkdir()
    store, engine, runtime, market = _runtime(selling_root)
    _set_quote(store, minute="09:31", price=80, total_volume=310)
    snapshot = engine.get_snapshot("SHS")
    assert snapshot is not None
    assert runtime.handle_snapshot(snapshot, observed_at=_at("09:31"))
    connection = sqlite3.connect(market)
    assert connection.execute(
        "SELECT signal_state,metrics_trusted FROM stock_state_current"
    ).fetchone() == ("SELLING_PRESSURE", 1)
    connection.close()
    runtime.close()
    store.close()


def test_ma_and_exact10_history_are_cached_while_current_bucket_stays_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / "baseline.db"
    market = tmp_path / "market.db"
    history_path = tmp_path / "history.db"
    _baseline(baseline)
    _market(market)
    history = SQLiteStore(history_path)
    history.close()
    store = SQLiteStore(tmp_path / "hot.db")
    _hot(store)

    calls = {"ma": 0, "ato": 0, "atc": 0}
    real_ma = live_module.calculate_moving_averages_from_db
    real_ato = live_module.read_ato_exact10
    real_atc = live_module.read_atc_exact10

    def counted_ma(*args, **kwargs):
        calls["ma"] += 1
        return real_ma(*args, **kwargs)

    def counted_ato(*args, **kwargs):
        calls["ato"] += 1
        return real_ato(*args, **kwargs)

    def counted_atc(*args, **kwargs):
        calls["atc"] += 1
        return real_atc(*args, **kwargs)

    monkeypatch.setattr(live_module, "calculate_moving_averages_from_db", counted_ma)
    monkeypatch.setattr(live_module, "read_ato_exact10", counted_ato)
    monkeypatch.setattr(live_module, "read_atc_exact10", counted_atc)
    engine = RealtimeVolumeEngine(baseline)
    runtime = LiveStateRuntime(
        volume_engine=engine, hot_store=store, market_db_path=market,
        history_db_path=history_path, active_at=_at("09:31"),
    )
    snapshot = engine.get_snapshot("SHS")
    assert snapshot is not None
    assert runtime.handle_snapshot(snapshot, observed_at=_at("09:31"))

    bucket = {
        "symbol": "SHS", "trading_date": DAY, "exchange": "HNX",
        "auction_type": "CLOSE_AUCTION", "provider_session": "ATC",
        "auction_price": 101, "pre_auction_price": 100,
        "auction_volume": 50, "start_total_volume": 300,
        "end_total_volume": 350, "event_count": 1,
        "out_of_order_events": 0, "first_event_at": _at("14:30").isoformat(),
        "last_event_at": _at("14:30").isoformat(),
        "quality_status": "TRUSTED", "finalized": False,
        "data_source": "SSI_STREAM", "updated_at": _at("14:30").isoformat(),
    }
    store.upsert_auction_bucket(bucket)
    store.commit()
    assert runtime.handle_snapshot(
        snapshot, observed_at=_at("09:31"), force=True
    )
    bucket["auction_volume"] = 75
    bucket["end_total_volume"] = 375
    store.upsert_auction_bucket(bucket)
    store.commit()
    assert runtime.handle_snapshot(
        snapshot, observed_at=_at("09:31"), force=True
    )

    assert calls == {"ma": 1, "ato": 1, "atc": 1}
    connection = sqlite3.connect(market)
    assert connection.execute(
        "SELECT atc_volume FROM stock_state_current WHERE symbol='SHS'"
    ).fetchone()[0] == 75
    connection.close()
    runtime.close()
    store.close()


def test_candidate_sessions_are_shared_per_date_and_reloaded_on_rollover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / "baseline.db"
    market = tmp_path / "market.db"
    history_path = tmp_path / "history.db"
    _baseline(baseline)
    _market(market)
    history = SQLiteStore(history_path)
    history.close()
    store = SQLiteStore(tmp_path / "hot.db")

    loader_calls = 0
    candidate_tuples: list[tuple[str, ...]] = []
    real_loader = live_module.load_candidate_market_sessions
    real_ato = live_module.read_ato_exact10
    real_atc = live_module.read_atc_exact10

    def counted_loader(*args, **kwargs):
        nonlocal loader_calls
        loader_calls += 1
        return real_loader(*args, **kwargs)

    def capture_ato(*args, **kwargs):
        candidate_tuples.append(kwargs["candidate_dates"])
        return real_ato(*args, **kwargs)

    def capture_atc(*args, **kwargs):
        candidate_tuples.append(kwargs["candidate_dates"])
        return real_atc(*args, **kwargs)

    monkeypatch.setattr(
        live_module, "load_candidate_market_sessions", counted_loader
    )
    monkeypatch.setattr(live_module, "read_ato_exact10", capture_ato)
    monkeypatch.setattr(live_module, "read_atc_exact10", capture_atc)

    runtime = LiveStateRuntime(
        volume_engine=RealtimeVolumeEngine(baseline),
        hot_store=store,
        market_db_path=market,
        history_db_path=history_path,
        active_at=_at("08:50"),
        hydrate_volume=False,
    )
    symbols = ("SHS", "AAA", "BBB")
    for symbol in symbols:
        runtime._auction_history(symbol, DAY)

    assert loader_calls == 1
    assert len(candidate_tuples) == 2 * len(symbols)
    assert all(isinstance(item, tuple) for item in candidate_tuples)
    assert all(item is candidate_tuples[0] for item in candidate_tuples)

    runtime._ma_cache[(DAY, "SHS")] = None  # type: ignore[assignment]
    runtime._previous_state[(DAY, "SHS")] = "WATCHING"
    next_day = "2026-09-22"
    runtime._roll_date(next_day)
    assert runtime._ma_cache == {}
    assert runtime._auction_cache == {}
    assert runtime._previous_state == {}

    candidate_tuples.clear()
    for symbol in symbols:
        runtime._auction_history(symbol, next_day)

    assert loader_calls == 2
    assert len(candidate_tuples) == 2 * len(symbols)
    assert all(item is candidate_tuples[0] for item in candidate_tuples)
    runtime.close()
    store.close()


def test_history_reads_work_from_callback_thread_under_runtime_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / "baseline.db"
    market = tmp_path / "market.db"
    history_path = tmp_path / "history.db"
    _baseline(baseline)
    _market(market)
    history = SQLiteStore(history_path)
    history.close()
    store = SQLiteStore(tmp_path / "hot.db")
    _hot(store)

    creator_thread = threading.get_ident()
    loader_calls = 0
    history_read_threads: list[int] = []
    real_loader = live_module.load_candidate_market_sessions
    real_ato = live_module.read_ato_exact10
    real_atc = live_module.read_atc_exact10

    def counted_loader(*args, **kwargs):
        nonlocal loader_calls
        loader_calls += 1
        return real_loader(*args, **kwargs)

    def locked_ato(*args, **kwargs):
        assert runtime._lock._is_owned()
        history_read_threads.append(threading.get_ident())
        return real_ato(*args, **kwargs)

    def locked_atc(*args, **kwargs):
        assert runtime._lock._is_owned()
        history_read_threads.append(threading.get_ident())
        return real_atc(*args, **kwargs)

    monkeypatch.setattr(
        live_module, "load_candidate_market_sessions", counted_loader
    )
    monkeypatch.setattr(live_module, "read_ato_exact10", locked_ato)
    monkeypatch.setattr(live_module, "read_atc_exact10", locked_atc)

    engine = RealtimeVolumeEngine(baseline)
    runtime = LiveStateRuntime(
        volume_engine=engine,
        hot_store=store,
        market_db_path=market,
        history_db_path=history_path,
        active_at=_at("09:31"),
    )
    snapshot = engine.get_snapshot("SHS")
    assert snapshot is not None

    outcomes: list[bool] = []
    errors: list[BaseException] = []
    callback_threads: list[int] = []

    def project_from_callback_thread() -> None:
        callback_threads.append(threading.get_ident())
        try:
            outcomes.append(
                runtime.handle_snapshot(snapshot, observed_at=_at("09:31"))
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    worker = threading.Thread(target=project_from_callback_thread)
    worker.start()
    worker.join()

    assert errors == []
    assert outcomes == [True]
    assert callback_threads and callback_threads[0] != creator_thread
    assert history_read_threads == [callback_threads[0], callback_threads[0]]
    assert loader_calls == 1
    assert runtime.last_error is None
    assert runtime._candidate_dates_trading_date == DAY
    runtime.close()
    store.close()


def test_new_trading_date_invalidates_ma_and_resets_previous_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, engine, runtime, market = _runtime(tmp_path)
    calls = 0
    real_ma = live_module.calculate_moving_averages_from_db

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_ma(*args, **kwargs)

    monkeypatch.setattr(live_module, "calculate_moving_averages_from_db", counted)
    snapshot = engine.get_snapshot("SHS")
    assert snapshot is not None
    assert runtime.handle_snapshot(snapshot, observed_at=_at("09:31"))
    assert runtime.handle_snapshot(
        snapshot, observed_at=_at("09:31"), force=True
    )
    assert calls == 1

    next_day = "2026-09-22"
    store.upsert_latest_quote(
        {
            "symbol": "SHS", "trading_date": next_day,
            "event_time": "09:31:00", "last_price": 120,
            "total_volume": 310, "ref_price": 100, "open": 100,
            "high": 120, "low": 100, "close": 120,
            "bid_price1": 119, "bid_vol1": 1, "ask_price1": 120,
            "ask_vol1": 1, "change": 20, "ratio_change": 20,
            "exchange": "HNX", "trading_session": "LO",
            "trading_status": "OPEN",
            "updated_at": f"{next_day}T09:31:00+07:00",
        }
    )
    store.commit()
    next_snapshot = replace(snapshot, trading_date=next_day)
    assert runtime.handle_snapshot(
        next_snapshot, observed_at=_at("09:31", next_day)
    )
    assert calls == 2
    connection = sqlite3.connect(market)
    row = connection.execute(
        "SELECT trading_date,previous_signal_state FROM stock_state_current"
    ).fetchone()
    assert row == (next_day, None)
    connection.close()
    runtime.close()
    store.close()

    for sessions in (9, 8):
        accepted_root = tmp_path / f"accepted-{sessions}"
        accepted_root.mkdir()
        store, engine, runtime, market = _runtime(
            accepted_root, sessions=sessions
        )
        snapshot = engine.get_snapshot("SHS")
        assert snapshot is not None
        assert runtime.handle_snapshot(snapshot, observed_at=_at("09:31"))
        connection = sqlite3.connect(market)
        row = connection.execute(
            "SELECT signal_state,metrics_trusted,reason_codes_json "
            "FROM stock_state_current"
        ).fetchone()
        assert row[0] == "FLOW_PRICE_CONFIRMED"
        assert row[1] == 1
        assert "BASELINE_INCOMPLETE" in row[2]
        connection.close()
        runtime.close()
        store.close()
