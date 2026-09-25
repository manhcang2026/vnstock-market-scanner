from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread

import pytest

from app.canonical_engine_store import (
    CanonicalEngineStore,
    CurrentState,
    TechnicalBaseline,
    VolumeBaselinePoint,
)
from app.canonical_live_engine import CanonicalLiveEngine
from app.canonical_market_store import (
    MARKET_SCHEMA_VERSION,
    SCHEMA_SQL,
    CanonicalMarketStore,
    MinuteBar,
    RealtimeMarketEvent,
    RealtimeWriteResult,
)
from app.collector import QuoteCollector
from app.main import _advance_canonical_engine
from app.market_session import VN_TZ
from app.rebuild_engine import rebuild_engine


DAY = "2026-09-25"


def _at(minute: str, seconds: int = 0) -> datetime:
    hour, value = (int(part) for part in minute.split(":"))
    return datetime(2026, 9, 25, hour, value, seconds, tzinfo=VN_TZ)


def _after(minute: str) -> datetime:
    return _at(minute) + timedelta(minutes=1, seconds=3)


def _minute(
    minute: str,
    *,
    exchange: str = "HNX",
    close: float | None = 100,
    volume: int | None = 10,
    total: int | None = None,
    finalized: int = 1,
) -> MinuteBar:
    return MinuteBar(
        "AAA",
        DAY,
        minute,
        exchange=exchange,
        close=close,
        volume=volume,
        provider_total_volume=total,
        quality_status="TRUSTED",
        is_finalized=finalized,
    )


def _result() -> RealtimeWriteResult:
    return RealtimeWriteResult(True, False, False, False, 0, 0, False)


def _event(minute: str) -> RealtimeMarketEvent:
    return RealtimeMarketEvent(
        symbol="AAA",
        trading_date=DAY,
        event_at=_at(minute),
        minute=minute,
        exchange="HNX",
        price=100,
        total_volume=100,
    )


def _baseline(
    engine: CanonicalLiveEngine,
    *minutes: str,
    ma10: float | None = 100,
    ma200: float | None = 100,
    day_sessions: int = 10,
    sessions15: int = 9,
    sessions30: int = 8,
    denominator: float = 100,
) -> None:
    engine.engine_store.replace_as_of(
        as_of_date=DAY,
        technical=(
            TechnicalBaseline(
                "AAA", DAY, 99, ma10, 10 if ma10 else 0,
                ma200, 200 if ma200 else 0,
            ),
        ),
        volume=(
            VolumeBaselinePoint(
                "AAA", minute, DAY, denominator, day_sessions,
                denominator, sessions15, denominator, sessions30,
            )
            for minute in minutes
        ),
        current=(),
    )


def _state(engine: CanonicalLiveEngine) -> sqlite3.Row:
    row = engine.engine_store.current_row("AAA")
    assert row is not None
    return row


def _legacy_v3_shard(path: Path, trading_date: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    legacy_schema = SCHEMA_SQL.replace(
        "    event_time TEXT,\n    last_price REAL,\n    last_price_at TEXT,\n",
        "    event_time TEXT,\n    last_price REAL,\n",
        1,
    )
    connection.executescript(legacy_schema)
    connection.execute(
        """INSERT INTO minute_bars(
               symbol,trading_date,minute,exchange,close,volume,
               provider_total_volume,source,quality_status,is_finalized,
               event_count,updated_at
           ) VALUES('AAA',?,'09:20','HNX',110,10,100,'SSI','TRUSTED',1,1,
                    'before-migration')""",
        (trading_date,),
    )
    connection.execute(
        """INSERT INTO latest_quotes(
               symbol,trading_date,event_time,last_price,total_volume,exchange,
               provider_session,updated_at
           ) VALUES('AAA',?,'09:20:10',999,100,'HNX','LO',
                    'before-migration')""",
        (trading_date,),
    )
    connection.execute(
        """INSERT INTO schema_meta(key,value,updated_at)
           VALUES('schema_version','3','before-migration')"""
    )
    connection.commit()
    connection.close()


def _assert_v4_shard_preserved(path: Path, trading_date: str) -> None:
    connection = sqlite3.connect(path)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(latest_quotes)")
        }
        version = connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        minute = connection.execute(
            """SELECT close,volume,provider_total_volume FROM minute_bars
               WHERE symbol='AAA' AND trading_date=?""",
            (trading_date,),
        ).fetchone()
        quote = connection.execute(
            """SELECT event_time,last_price,last_price_at,total_volume
               FROM latest_quotes WHERE symbol='AAA' AND trading_date=?""",
            (trading_date,),
        ).fetchone()
    finally:
        connection.close()

    assert "last_price_at" in columns
    assert version == MARKET_SCHEMA_VERSION == "4"
    assert minute == (110, 10, 100)
    assert quote == ("09:20:10", 999, None, 100)


def test_startup_migrates_v3_shard_before_readonly_projection(
    tmp_path: Path,
) -> None:
    market_dir = tmp_path / "market"
    shard = market_dir / "ccc_market_2026.db"
    _legacy_v3_shard(shard, DAY)

    engine = CanonicalLiveEngine(
        market_store=CanonicalMarketStore(market_dir),
        engine_path=tmp_path / "engine.db",
        active_at=_after("09:20"),
    )

    assert engine.advance(_after("09:20")) == 1
    assert _state(engine)["last_price"] == 110
    _assert_v4_shard_preserved(shard, DAY)


def test_year_rollover_migrates_new_shard_before_readonly_projection(
    tmp_path: Path,
) -> None:
    market_dir = tmp_path / "market"
    rollover_day = "2027-01-04"
    rollover_at = datetime(2027, 1, 4, 9, 21, 3, tzinfo=VN_TZ)
    shard = market_dir / "ccc_market_2027.db"
    _legacy_v3_shard(shard, rollover_day)
    engine = CanonicalLiveEngine(
        market_store=CanonicalMarketStore(market_dir),
        engine_path=tmp_path / "engine.db",
        active_at=datetime(2026, 12, 31, 15, 1, tzinfo=VN_TZ),
    )

    assert engine.advance(rollover_at) == 1
    assert _state(engine)["trading_date"] == rollover_day
    assert _state(engine)["last_price"] == 110
    _assert_v4_shard_preserved(shard, rollover_day)


def test_startup_expires_old_state_but_preserves_today_baseline(
    tmp_path: Path,
) -> None:
    engine_path = tmp_path / "engine.db"
    with CanonicalEngineStore(engine_path) as store:
        store.replace_as_of(
            as_of_date=DAY,
            technical=(TechnicalBaseline("AAA", DAY, 90, 100, 10, 100, 200),),
            volume=(
                VolumeBaselinePoint("AAA", "09:14", DAY, 100, 10, 100, 10, 100, 10),
            ),
            current=(replace(_current_state(), trading_date="2026-09-24"),),
        )

    engine = CanonicalLiveEngine(
        market_store=CanonicalMarketStore(tmp_path / "market"),
        engine_path=engine_path,
        active_at=_after("09:14"),
    )

    assert engine.engine_store.current_row("AAA") is None
    assert engine.engine_store.load_technical("AAA", DAY) is not None
    assert engine.engine_store.load_volume_point("AAA", "09:14", DAY) is not None


def test_day_rollover_expires_previous_current_state(tmp_path: Path) -> None:
    engine = CanonicalLiveEngine(
        market_store=CanonicalMarketStore(tmp_path / "market"),
        engine_path=tmp_path / "engine.db",
        active_at=_after("09:14"),
    )
    engine.engine_store.upsert_current(_current_state())

    engine.advance(datetime(2026, 9, 26, 8, 0, tzinfo=VN_TZ))

    assert engine.engine_store.current_row("AAA") is None


def test_hook_is_lightweight_and_same_minute_events_write_once(tmp_path: Path) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.upsert_minute_bars([_minute("09:14", total=150)])
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("09:14"),
    )
    _baseline(engine, "09:14")
    calculations = 0
    original = engine._calculate

    def counted(*args, **kwargs):
        nonlocal calculations
        calculations += 1
        return original(*args, **kwargs)

    engine._calculate = counted  # type: ignore[method-assign]
    for _ in range(5):
        engine.mark_dirty(_event("09:14"), _result())
    assert calculations == 0
    assert engine.advance(_after("09:14")) == 1
    assert engine.advance(_after("09:14")) == 0
    assert calculations == 1
    assert engine.stats().state_writes == 1


def test_one_finalized_minute_projects_day_rvol_and_session_counts(
    tmp_path: Path,
) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.upsert_minute_bars([_minute("09:14", total=200)])
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("09:14"),
    )
    _baseline(
        engine, "09:14", day_sessions=10, sessions15=9, sessions30=8,
        denominator=100,
    )
    assert engine.advance(_after("09:14")) == 1
    state = _state(engine)
    assert state["minute"] == "09:14"
    assert state["day_rvol"] == pytest.approx(2)
    assert state["day_rvol_sessions_used"] == 10
    assert state["rvol15_sessions_used"] == 9
    assert state["rvol30_sessions_used"] == 8
    assert state["baseline_sessions_used"] == 10


def test_offline_rebuild_and_live_use_provider_cumulative_volume(
    tmp_path: Path,
) -> None:
    market_dir = tmp_path / "market"
    with CanonicalMarketStore(market_dir) as market:
        market.upsert_minute_bars([_minute("09:14", volume=10, total=250)])
    engine_path = tmp_path / "rebuilt-engine.db"
    rebuild_engine(
        market_db_dir=market_dir, engine_db=engine_path, as_of_date=DAY
    )
    connection = sqlite3.connect(engine_path)
    try:
        assert connection.execute(
            "SELECT cumulative_volume FROM current_state WHERE symbol='AAA'"
        ).fetchone()[0] == 250
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("target", "expected15", "expected30"),
    [
        ("09:13", None, None),
        ("09:14", 1.5, None),
        ("09:28", 1.5, None),
        ("09:29", 1.5, 3.0),
    ],
)
def test_rvol_first_valid_points_follow_market_grid(
    tmp_path: Path,
    target: str,
    expected15: float | None,
    expected30: float | None,
) -> None:
    market = CanonicalMarketStore(tmp_path / target.replace(":", ""))
    rows = []
    for value in range(30):
        minute = f"09:{value:02d}"
        if minute > target:
            break
        rows.append(_minute(minute, volume=10, total=(value + 1) * 10))
    market.upsert_minute_bars(rows)
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / f"engine-{target.replace(':', '')}.db",
        active_at=_after(target),
    )
    _baseline(engine, target)
    engine.advance(_after(target))
    state = _state(engine)
    if expected15 is None:
        assert state["rvol15"] is None
    else:
        assert state["rvol15"] == pytest.approx(expected15)
    if expected30 is None:
        assert state["rvol30"] is None
    else:
        assert state["rvol30"] == pytest.approx(expected30)


def test_pm_window_resets_and_never_bridges_lunch(tmp_path: Path) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    rows = [_minute("11:29", exchange="HOSE", volume=10_000, total=10_000)]
    rows.extend(
        _minute(f"13:{value:02d}", exchange="HOSE", volume=10, total=10_010 + value * 10)
        for value in range(15)
    )
    market.upsert_minute_bars(rows)
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("13:14"),
    )
    _baseline(engine, "13:13", "13:14", denominator=100)
    assert engine.advance(_after("13:13")) == 1
    assert _state(engine)["rvol15"] is None
    assert engine.advance(_after("13:14")) == 1
    assert _state(engine)["rvol15"] == pytest.approx(1.5)


@pytest.mark.parametrize(
    ("target", "anchor", "expected5", "expected15"),
    [
        ("09:20", "09:15", 10.0, None),
        ("09:20", "09:05", 10.0, 10.0),
        ("13:02", "12:57", None, None),
        ("13:05", "13:00", 10.0, None),
    ],
)
def test_price_windows_use_exact_same_segment_anchors(
    tmp_path: Path,
    target: str,
    anchor: str,
    expected5: float | None,
    expected15: float | None,
) -> None:
    folder = tmp_path / f"{target.replace(':', '')}-{anchor.replace(':', '')}"
    market = CanonicalMarketStore(folder)
    market.upsert_minute_bars(
        [
            _minute(anchor, close=100, volume=10, total=10),
            _minute(target, close=110, volume=10, total=20),
        ]
    )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=folder / "engine.db",
        active_at=_after(target),
    )
    _baseline(engine, target)
    engine.advance(_after(target))
    state = _state(engine)
    assert state["price5_pct"] == pytest.approx(expected5) if expected5 is not None else state["price5_pct"] is None
    assert state["price15_pct"] == pytest.approx(expected15) if expected15 is not None else state["price15_pct"] is None


def test_price5_forward_fills_anchor_without_synthetic_minute_bar(
    tmp_path: Path,
) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.upsert_minute_bars(
        [
            _minute("11:23", close=100, total=100),
            _minute("11:29", close=110, total=110),
        ]
    )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("11:29"),
    )
    _baseline(engine, "11:29")

    assert engine.advance(_after("11:29")) == 1
    assert _state(engine)["price5_pct"] == pytest.approx(10)
    rows = market.connection(2026).execute(
        "SELECT minute FROM minute_bars ORDER BY minute"
    ).fetchall()
    assert [row[0] for row in rows] == ["11:23", "11:29"]


def test_pm_price_state_starts_with_first_pm_trade_and_then_carries(
    tmp_path: Path,
) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.upsert_minute_bars(
        [
            _minute("11:29", close=100, total=100),
            _minute("13:00", close=None, total=100),
            _minute("13:01", close=None, total=100),
            _minute("13:02", close=110, total=110),
        ]
    )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("13:02"),
    )
    _baseline(engine, "13:02", "13:05", "13:07")

    assert engine.advance(_after("13:02")) == 1
    assert _state(engine)["price5_pct"] is None
    assert engine.advance(_after("13:05")) == 1
    assert _state(engine)["price5_pct"] is None
    assert engine.advance(_after("13:07")) == 1
    assert _state(engine)["price5_pct"] == pytest.approx(0)


def test_am_latest_quote_price_is_not_pm_price_state(tmp_path: Path) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.write_realtime_event(
        RealtimeMarketEvent(
            symbol="AAA", trading_date=DAY, event_at=_at("11:29", 10),
            minute="11:29", exchange="HNX", price=100, total_volume=100,
        ),
        observed_at=_after("11:29"),
    )
    market.write_realtime_event(
        RealtimeMarketEvent(
            symbol="AAA", trading_date=DAY, event_at=_at("13:01", 10),
            minute="13:01", exchange="HNX", price=None, total_volume=110,
        ),
        observed_at=_after("13:01"),
    )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("13:01"),
    )
    _baseline(engine, "13:01", "13:02")

    assert engine.advance(_after("13:01")) == 1
    assert _state(engine)["last_price"] is None
    quote = market.connection(2026).execute(
        """SELECT event_time,last_price,last_price_at FROM latest_quotes
           WHERE symbol='AAA'"""
    ).fetchone()
    assert tuple(quote) == ("13:01:10", 100, "11:29:10")

    market.write_realtime_event(
        RealtimeMarketEvent(
            symbol="AAA", trading_date=DAY, event_at=_at("13:02", 10),
            minute="13:02", exchange="HNX", price=110, total_volume=120,
        ),
        observed_at=_after("13:02"),
    )
    assert engine.advance(_after("13:02")) == 1
    assert _state(engine)["last_price"] == 110


def test_gap_breaks_price_carry_and_post_gap_trade_reestablishes_state(
    tmp_path: Path,
) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.upsert_minute_bars(
        [
            _minute("11:23", close=100, total=100),
            _minute("11:29", close=None, total=110),
        ]
    )
    market.record_data_gap(
        year=2026,
        trading_date=DAY,
        reason="STREAM_OUTAGE",
        source="SSI_STREAM",
        status="OPEN",
        symbol="AAA",
        minute_from="11:24",
        minute_to="11:26",
    )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("11:29"),
    )
    _baseline(engine, "11:29")

    assert engine.advance(_after("11:29")) == 1
    state = _state(engine)
    assert state["last_price"] is None
    assert state["price5_pct"] is None
    assert state["ma10"] == 100

    market.upsert_minute_bars([_minute("11:27", close=110, total=105)])
    engine.mark_dirty(_event("11:27"), _result())
    assert engine.advance(_after("11:29")) == 1
    state = _state(engine)
    assert state["last_price"] == 110
    assert state["price5_pct"] is None
    assert state["ma10"] == 100


def test_price_state_change_leaves_rvol_and_ma_formulas_unchanged(
    tmp_path: Path,
) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.upsert_minute_bars(
        [
            _minute(
                f"09:{value:02d}",
                close=100 if value == 0 else 110 if value == 29 else None,
                volume=10,
                total=(value + 1) * 10,
            )
            for value in range(30)
        ]
    )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("09:29"),
    )
    _baseline(engine, "09:29", ma10=100, ma200=100, denominator=100)

    assert engine.advance(_after("09:29")) == 1
    state = _state(engine)
    assert state["price5_pct"] == pytest.approx(10)
    assert state["day_rvol"] == pytest.approx(3)
    assert state["rvol15"] == pytest.approx(1.5)
    assert state["rvol30"] == pytest.approx(3)
    assert state["ma10"] == 100
    assert state["ma200"] == 100


def test_missing_metrics_are_independent(tmp_path: Path) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    rows = [
        _minute(f"09:{value:02d}", close=100 if value < 14 else 110,
                volume=10, total=(value + 1) * 10)
        for value in range(15)
    ]
    market.upsert_minute_bars(rows)
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("09:14"),
    )
    _baseline(engine, "09:14", ma10=100, ma200=None, denominator=100)
    engine.advance(_after("09:14"))
    state = _state(engine)
    assert state["ma10"] == 100 and state["distance_ma10_pct"] == pytest.approx(10)
    assert state["ma200"] is None and state["distance_ma200_pct"] is None
    assert state["day_rvol"] is not None and state["rvol15"] is not None
    assert state["price5_pct"] is not None

    engine.engine_store.connection.execute(
        "DELETE FROM volume_baseline_curve WHERE as_of_date=?", (DAY,)
    )
    engine.engine_store.connection.commit()
    engine.mark_dirty(_event("09:14"), _result())
    engine.advance(_after("09:14"))
    state = _state(engine)
    assert state["day_rvol"] is None and state["rvol15"] is None
    assert state["price5_pct"] is not None and state["ma10"] == 100


def test_baseline_date_mismatch_is_not_reused_and_no_baseline_is_fail_open(
    tmp_path: Path,
) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.upsert_minute_bars(
        [_minute("09:15", close=100, total=10), _minute("09:20", close=110, total=20)]
    )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("09:20"),
    )
    engine.engine_store.replace_as_of(
        as_of_date="2026-09-24",
        technical=(TechnicalBaseline("AAA", "2026-09-24", 90, 95, 10, 80, 200),),
        volume=(VolumeBaselinePoint("AAA", "09:20", "2026-09-24", 10, 10, 10, 10, 10, 10),),
        current=(),
    )
    assert engine.advance(_after("09:20")) == 1
    state = _state(engine)
    assert state["price5_pct"] == pytest.approx(10)
    assert state["day_rvol"] is None and state["ma10"] is None
    assert "NO_BASELINE" in json.loads(state["reason_codes_json"])


def test_no_baseline_for_today_does_not_crash_collector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_after("09:20")]
    monkeypatch.setattr("app.collector._now_vn", lambda: clock[0])
    market = CanonicalMarketStore(tmp_path / "market")
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=clock[0],
    )
    collector = QuoteCollector(
        {"AAA"}, None, started_at=_at("08:30"), canonical_store=market,
        post_commit_hook=engine.mark_dirty,
    )
    collector.on_message(
        {"Symbol": "AAA", "TradingDate": DAY, "Time": "09:20:00",
         "Market": "HNX", "TradingSession": "LO", "LastPrice": 110,
         "TotalVol": 100}
    )
    assert collector.stats.canonical_events_written == 1
    assert engine.advance(clock[0]) == 1
    state = _state(engine)
    assert state["quality_status"] == "PARTIAL"
    assert "NO_BASELINE" in json.loads(state["reason_codes_json"])


def test_late_correction_reprojects_without_rewinding_current_state(
    tmp_path: Path,
) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.upsert_minute_bars(
        [_minute("09:11", close=90, total=90), _minute("10:00", close=110, total=200)]
    )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("10:00"),
    )
    _baseline(engine, "10:00")
    assert engine.advance(_after("10:00")) == 1
    market.upsert_minute_bars([_minute("09:11", close=95, total=95)])
    engine.mark_dirty(_event("09:11"), _result())
    assert engine.advance(_after("10:00")) == 1
    state = _state(engine)
    assert state["minute"] == "10:00"
    assert state["last_price"] == 110


def test_dirty_generation_preserves_correction_arriving_during_projection(
    tmp_path: Path,
) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.upsert_minute_bars(
        [
            _minute("09:15", close=100, total=10),
            _minute("09:20", close=110, total=20),
        ]
    )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("09:20"),
    )
    _baseline(engine, "09:20")
    assert engine.advance(_after("09:20")) == 1
    assert _state(engine)["price5_pct"] == pytest.approx(10)

    engine.mark_dirty(_event("09:15"), _result())
    original_calculate = engine._calculate

    def calculate_then_correct(*args, **kwargs):
        stale_state = original_calculate(*args, **kwargs)
        market.upsert_minute_bars(
            [_minute("09:15", close=105, total=10)]
        )
        engine.mark_dirty(_event("09:15"), _result())
        return stale_state

    engine._calculate = calculate_then_correct  # type: ignore[method-assign]
    assert engine.advance(_after("09:20")) == 1
    assert _state(engine)["price5_pct"] == pytest.approx(10)
    assert engine.stats().dirty_symbols == 1

    engine._calculate = original_calculate  # type: ignore[method-assign]
    assert engine.advance(_after("09:20")) == 1
    state = _state(engine)
    assert state["minute"] == "09:20"
    assert state["price5_pct"] == pytest.approx((110 / 105 - 1) * 100)
    assert engine.stats().dirty_symbols == 0


def test_latest_quote_price_survives_volume_only_tick_and_late_correction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_at("09:11", 10)]
    monkeypatch.setattr("app.collector._now_vn", lambda: clock[0])
    market = CanonicalMarketStore(tmp_path / "market")
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=clock[0],
    )
    collector = QuoteCollector(
        {"AAA"}, None, started_at=_at("08:30"), canonical_store=market,
        post_commit_hook=engine.mark_dirty,
    )
    collector.on_message(
        {"Symbol": "AAA", "TradingDate": DAY, "Time": "09:11:10",
         "Market": "HNX", "TradingSession": "LO", "LastPrice": 90,
         "TotalVol": 100}
    )
    clock[0] = _at("10:00", 10)
    collector.on_message(
        {"Symbol": "AAA", "TradingDate": DAY, "Time": "10:00:10",
         "Market": "HNX", "TradingSession": "LO", "LastPrice": None,
         "TotalVol": 200}
    )
    projected_at = _after("10:00")
    collector.advance_time(projected_at)
    assert engine.advance(projected_at) == 1
    assert _state(engine)["last_price"] == 90

    clock[0] = projected_at
    collector.on_message(
        {"Symbol": "AAA", "TradingDate": DAY, "Time": "09:11:50",
         "Market": "HNX", "TradingSession": "LO", "LastPrice": 95,
         "TotalVol": 110}
    )
    assert engine.advance(projected_at) == 1

    connection = market.connection(2026)
    assert connection.execute(
        "SELECT close FROM minute_bars WHERE symbol='AAA' AND minute='09:11'"
    ).fetchone()[0] == 95
    latest = connection.execute(
        """SELECT event_time,last_price,last_price_at
           FROM latest_quotes WHERE symbol='AAA'"""
    ).fetchone()
    assert tuple(latest) == (
        "10:00:10",
        90,
        "09:11:10",
    )
    state = _state(engine)
    assert state["minute"] == "10:00"
    assert state["last_price"] == 90


def test_latest_quote_after_projected_minute_is_not_used(tmp_path: Path) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.write_realtime_event(
        RealtimeMarketEvent(
            symbol="AAA", trading_date=DAY, event_at=_at("10:00", 30),
            minute="10:00", exchange="HNX", price=100, total_volume=100,
        ),
        observed_at=_after("10:00"),
    )
    market.write_realtime_event(
        RealtimeMarketEvent(
            symbol="AAA", trading_date=DAY, event_at=_at("10:01", 10),
            minute="10:01", exchange="HNX", price=120, total_volume=110,
        ),
        observed_at=_at("10:01", 30),
    )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_at("10:01", 30),
    )

    assert engine.advance(_at("10:01", 30)) == 1
    assert _state(engine)["minute"] == "10:00"
    assert _state(engine)["last_price"] == 100


def test_restart_hydrates_today_and_silent_elapsed_minutes_need_no_fake_rows(
    tmp_path: Path,
) -> None:
    market_dir = tmp_path / "market"
    market = CanonicalMarketStore(market_dir)
    market.upsert_minute_bars([_minute("09:00", volume=10, total=10)])
    engine_path = tmp_path / "engine.db"
    with CanonicalEngineStore(engine_path) as store:
        store.replace_as_of(
            as_of_date=DAY,
            technical=(TechnicalBaseline("AAA", DAY, 99, 100, 10, 100, 200),),
            volume=(VolumeBaselinePoint("AAA", "09:14", DAY, 5, 10, 5, 10, 5, 10),),
            current=(),
        )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=engine_path,
        active_at=_after("09:14"),
    )
    assert engine.advance(_after("09:14")) == 1
    state = _state(engine)
    assert state["minute"] == "09:14"
    assert state["rvol15"] == pytest.approx(2)
    assert market.connection(2026).execute(
        "SELECT COUNT(*) FROM minute_bars"
    ).fetchone()[0] == 1
    assert engine.advance(_at("12:00")) == 1
    assert _state(engine)["minute"] == "11:29"


def test_explicit_gap_only_nulls_affected_rvol_metrics(tmp_path: Path) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.upsert_minute_bars(
        [_minute("09:00", close=100, total=10), _minute("09:14", close=110, total=150)]
    )
    market.record_data_gap(
        year=2026,
        trading_date=DAY,
        reason="STREAM_OUTAGE",
        source="SSI_STREAM",
        status="OPEN",
        symbol="AAA",
        minute_from="09:05",
        minute_to="09:06",
    )
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("09:14"),
    )
    _baseline(engine, "09:14")
    engine.advance(_after("09:14"))
    state = _state(engine)
    assert state["rvol15"] is None
    assert state["day_rvol"] == pytest.approx(1.5)
    assert state["ma10"] == 100
    assert "CURRENT_GAP" in json.loads(state["reason_codes_json"])


def test_projection_uses_readonly_reader_not_writer_lock(tmp_path: Path) -> None:
    market = CanonicalMarketStore(tmp_path / "market")
    market.upsert_minute_bars([_minute("09:14", total=150)])
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=_after("09:14"),
    )
    _baseline(engine, "09:14")

    class ForbiddenWriterLock:
        def __enter__(self):
            raise AssertionError("projector touched canonical writer lock")

        def __exit__(self, *_args):
            return None

    market._lock = ForbiddenWriterLock()  # type: ignore[assignment]

    assert engine.advance(_after("09:14")) == 1
    assert _state(engine)["minute"] == "09:14"


def test_engine_exception_keeps_canonical_commit_and_last_usable_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [_at("09:14", 10)]
    monkeypatch.setattr("app.collector._now_vn", lambda: clock[0])
    market = CanonicalMarketStore(tmp_path / "market")
    engine = CanonicalLiveEngine(
        market_store=market,
        engine_path=tmp_path / "engine.db",
        active_at=clock[0],
    )
    collector = QuoteCollector(
        {"AAA"}, None, started_at=_at("08:30"), canonical_store=market,
        post_commit_hook=engine.mark_dirty,
    )
    collector.on_message(
        {"Symbol": "AAA", "TradingDate": DAY, "Time": "09:14:10",
         "Market": "HNX", "TradingSession": "LO", "LastPrice": 100,
         "TotalVol": 100}
    )
    assert market.connection(2026).execute(
        "SELECT COUNT(*) FROM minute_bars"
    ).fetchone()[0] == 1
    original = engine.market_reader.read_live_day
    engine.market_reader.read_live_day = (  # type: ignore[method-assign]
        lambda *_args: (_ for _ in ()).throw(sqlite3.OperationalError("read failed"))
    )
    assert engine.advance(_after("09:14")) == 0
    assert engine.stats().calculation_errors == 1
    assert market.connection(2026).execute(
        "SELECT COUNT(*) FROM minute_bars"
    ).fetchone()[0] == 1
    engine.market_reader.read_live_day = original  # type: ignore[method-assign]


def test_main_engine_wrapper_is_fail_open() -> None:
    class Broken:
        def advance(self, _now: datetime) -> int:
            raise sqlite3.OperationalError("locked")

    assert _advance_canonical_engine(Broken(), _after("09:14")) == 0  # type: ignore[arg-type]


def _current_state() -> CurrentState:
    return CurrentState(
        symbol="AAA", exchange="HNX", trading_date=DAY, minute="09:14",
        last_price=100, cumulative_volume=100, day_rvol=1, rvol15=1,
        rvol30=None, price5_pct=0, price15_pct=None, ma10=100, ma200=100,
        distance_ma10_pct=0, distance_ma200_pct=0, baseline_sessions_used=10,
        day_rvol_sessions_used=10, rvol15_sessions_used=9,
        rvol30_sessions_used=8, quality_status="PARTIAL",
        reason_codes_json="[]",
    )


def test_engine_store_migrates_sessions_fields_and_is_cross_thread_safe(
    tmp_path: Path,
) -> None:
    path = tmp_path / "engine.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """CREATE TABLE current_state(
        symbol TEXT PRIMARY KEY, exchange TEXT, trading_date TEXT, minute TEXT,
        last_price REAL, cumulative_volume INTEGER, day_rvol REAL, rvol15 REAL,
        rvol30 REAL, price5_pct REAL, price15_pct REAL, ma10 REAL, ma200 REAL,
        distance_ma10_pct REAL, distance_ma200_pct REAL,
        baseline_sessions_used INTEGER, quality_status TEXT NOT NULL,
        reason_codes_json TEXT NOT NULL, updated_at TEXT NOT NULL);"""
    )
    connection.close()
    store = CanonicalEngineStore(path)
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            store.upsert_current(_current_state())
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    def reader() -> None:
        try:
            store.current_row("AAA")
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [Thread(target=writer), Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    row = store.current_row("AAA")
    assert errors == [] and row is not None
    assert store.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert store.connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert store.connection.execute("PRAGMA synchronous").fetchone()[0] == 1
    assert row["day_rvol_sessions_used"] == 10
    assert row["rvol15_sessions_used"] == 9
    assert row["rvol30_sessions_used"] == 8
