from __future__ import annotations

import csv
import inspect
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.auction_salvage_import import import_salvage
from app.canonical_market_store import (
    AuctionSession,
    CanonicalMarketStore,
    DailyBar,
    MinuteBar,
)
from app.clean_rest_bootstrap import (
    normalize_daily_row,
    normalize_minute_row,
    run_bootstrap,
)
from app import rebuild_engine as rebuild_module
from app.rebuild_engine import MarketShardReader, exact_price_change, rebuild_engine
from app.ssi_historical import SSINoDataFound


def _minute_raw(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Symbol": "AAA",
        "TradingDate": "24/09/2026",
        "Time": "09:15:00",
        "Market": "HOSE",
        "Open": 10,
        "High": 11,
        "Low": 9,
        "Close": 10.5,
        "Volume": 100,
        "Value": 1050,
    }
    row.update(changes)
    return row


def _count(path: Path, table: str) -> int:
    connection = sqlite3.connect(path)
    try:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("changes", "expected_price", "expected_volume"),
    [
        ({}, 10.5, 100),
        ({"Volume": None}, 10.5, None),
        ({"Open": None, "High": None, "Low": None, "Close": None}, None, 100),
        ({"High": None}, 10.5, 100),
    ],
)
def test_minute_rows_persist_independent_nullable_fields(
    tmp_path: Path,
    changes: dict[str, object],
    expected_price: float | None,
    expected_volume: int | None,
) -> None:
    row = normalize_minute_row(_minute_raw(**changes), symbol_hint="AAA")
    assert row is not None
    with CanonicalMarketStore(tmp_path) as store:
        assert store.upsert_minute_bars([row]) == 1
        saved = store.connection(2026).execute("SELECT * FROM minute_bars").fetchone()
        assert saved["close"] == expected_price
        assert saved["volume"] == expected_volume
        assert saved["quality_status"] == ("TRUSTED" if not changes else "PARTIAL")


def test_inconsistent_ohlc_is_preserved_and_labeled_partial(tmp_path: Path) -> None:
    row = normalize_minute_row(
        _minute_raw(Open=12, High=11, Low=9, Close=10), symbol_hint="AAA"
    )
    assert row is not None and row.open == 12 and row.high == 11
    assert row.quality_status == "PARTIAL"
    with CanonicalMarketStore(tmp_path) as store:
        store.upsert_minute_bars([row])
        saved = store.connection(2026).execute(
            "SELECT open,high FROM minute_bars"
        ).fetchone()
        assert tuple(saved) == (12, 11)


def test_partial_daily_row_persists(tmp_path: Path) -> None:
    row = normalize_daily_row(
        {"Symbol": "AAA", "TradingDate": "24/09/2026", "Close": 10},
        symbol_hint="AAA",
        exchange_hint="HOSE",
    )
    assert row is not None and row.quality_status == "PARTIAL"
    with CanonicalMarketStore(tmp_path) as store:
        store.upsert_daily_bars([row])
    assert _count(tmp_path / "ccc_market_2026.db", "daily_bars") == 1


def test_bootstrap_continues_no_data_and_failure_and_routes_years(tmp_path: Path) -> None:
    class Fetcher:
        calls: list[str] = []

        def fetch_intraday_ohlc(self, symbol, from_date, to_date, resolution=1):
            self.calls.append(f"{symbol}:{from_date.year}")
            if symbol == "BAD":
                raise RuntimeError("boom")
            if symbol == "NONE":
                raise SSINoDataFound("NoDataFound")
            return [
                _minute_raw(
                    Symbol=symbol,
                    TradingDate=f"24/09/{from_date.year}",
                )
            ]

        def fetch_daily_ohlc(self, symbol, from_date, to_date):
            raise NotImplementedError

    fetcher = Fetcher()
    with CanonicalMarketStore(tmp_path) as store:
        summary = run_bootstrap(
            mode="minute",
            store=store,
            client=fetcher,
            symbols=["GOOD", "BAD", "NONE"],
            exchange_map={symbol: "HOSE" for symbol in ("GOOD", "BAD", "NONE")},
            from_date=date(2025, 1, 1),
            to_date=date(2026, 9, 24),
        )
    assert summary.requested == 6
    assert summary.completed == 2 and summary.no_data == 2 and summary.failed == 2
    assert _count(tmp_path / "ccc_market_2025.db", "minute_bars") == 1
    assert _count(tmp_path / "ccc_market_2026.db", "minute_bars") == 1
    assert _count(tmp_path / "ccc_market_2025.db", "data_gaps") == 1
    assert _count(tmp_path / "ccc_market_2026.db", "data_gaps") == 1
    assert _count(tmp_path / "ccc_market_2025.db", "rest_session_status") == 1
    assert _count(tmp_path / "ccc_market_2026.db", "rest_session_status") == 1


def test_completed_skips_and_failed_retries_only_when_requested(tmp_path: Path) -> None:
    class Fetcher:
        calls = 0

        def fetch_intraday_ohlc(self, symbol, from_date, to_date, resolution=1):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary")
            return [_minute_raw(Symbol=symbol)]

        def fetch_daily_ohlc(self, symbol, from_date, to_date):
            raise NotImplementedError

    fetcher = Fetcher()
    kwargs = dict(
        mode="minute",
        client=fetcher,
        symbols=["AAA"],
        exchange_map={"AAA": "HOSE"},
        from_date=date(2026, 9, 24),
        to_date=date(2026, 9, 24),
    )
    with CanonicalMarketStore(tmp_path) as store:
        assert run_bootstrap(store=store, **kwargs).failed == 1
        assert run_bootstrap(store=store, **kwargs).failed == 1
        assert fetcher.calls == 1
        assert run_bootstrap(store=store, retry_failed=True, **kwargs).completed == 1
        assert run_bootstrap(store=store, retry_failed=True, **kwargs).completed == 1
        assert fetcher.calls == 2


@pytest.mark.parametrize(
    "row",
    [
        AuctionSession("AAA", "2026-09-24", "ATC", auction_price=None, auction_volume=5),
        AuctionSession("BBB", "2026-09-24", "ATC", auction_price=10, auction_volume=None),
    ],
)
def test_auction_nullable_price_or_volume_persists(
    tmp_path: Path, row: AuctionSession
) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        store.upsert_auction_sessions([row])
    assert _count(tmp_path / "ccc_market_2026.db", "auction_sessions") == 1


def test_salvage_imports_expected_1110_and_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "salvage.tsv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("symbol", "trading_date", "auction_type", "auction_price", "auction_volume"),
            delimiter="\t",
        )
        writer.writeheader()
        for index in range(551):
            writer.writerow(
                {"symbol": f"A{index:04d}", "trading_date": "22/09/2026", "auction_type": "CLOSE_AUCTION", "auction_price": "", "auction_volume": index}
            )
        for index in range(559):
            writer.writerow(
                {"symbol": f"B{index:04d}", "trading_date": "24/09/2026", "auction_type": "ATC", "auction_price": 10, "auction_volume": ""}
            )
    with CanonicalMarketStore(tmp_path) as store:
        expected = {"2026-09-22": 551, "2026-09-24": 559}
        assert import_salvage(
            source, store=store, expected_rows=1110, expected_atc_by_date=expected
        ) == 1110
        assert import_salvage(
            source, store=store, expected_rows=1110, expected_atc_by_date=expected
        ) == 1110
    assert _count(tmp_path / "ccc_market_2026.db", "auction_sessions") == 1110


def _seed_engine_market(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        store.upsert_daily_bars(
            [
                DailyBar("AAA", f"2026-09-{day:02d}", exchange="HNX", close=float(day))
                for day in range(1, 25)
            ]
        )
        for day, volume in ((22, 10), (23, 30), (24, 40)):
            store.upsert_minute_bars(
                [
                    MinuteBar(
                        "AAA", f"2026-09-{day:02d}", "09:00", exchange="HNX",
                        close=100 + day, volume=volume, quality_status="TRUSTED"
                    )
                ]
            )
            store.mark_fetch_status(
                mode="minute", symbol="AAA", from_date=f"2026-09-{day:02d}",
                to_date=f"2026-09-{day:02d}", resolution=1, year=2026,
                status="COMPLETED", rows_received=1, rows_written=1
            )
            store.mark_rest_sessions_completed(
                mode="minute",
                symbol="AAA",
                resolution=1,
                rows_by_date={f"2026-09-{day:02d}": 1},
            )


def test_engine_insufficient_ma_and_fewer_than_10_volume_sessions(tmp_path: Path) -> None:
    _seed_engine_market(tmp_path)
    engine = tmp_path / "ccc_engine.db"
    symbols, failures = rebuild_engine(
        market_db_dir=tmp_path, engine_db=engine, as_of_date="2026-09-24"
    )
    assert (symbols, failures) == (1, 0)
    connection = sqlite3.connect(engine)
    connection.row_factory = sqlite3.Row
    try:
        technical = connection.execute("SELECT * FROM technical_baseline").fetchone()
        point = connection.execute(
            "SELECT * FROM volume_baseline_curve WHERE minute='09:00'"
        ).fetchone()
        assert technical["ma10"] == pytest.approx(18.5)
        assert technical["ma10_sessions"] == 10
        assert technical["ma200"] is None and technical["ma200_sessions"] == 23
        assert point["day_sessions_used"] == 2
        assert point["avg_cumulative_volume"] == 20
    finally:
        connection.close()


def _read_technical(tmp_path: Path, as_of: str) -> sqlite3.Row:
    engine = tmp_path / "technical-engine.db"
    rebuild_engine(market_db_dir=tmp_path, engine_db=engine, as_of_date=as_of)
    connection = sqlite3.connect(engine)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute("SELECT * FROM technical_baseline").fetchone()
        assert row is not None
        return row
    finally:
        connection.close()


def test_previous_close_does_not_substitute_older_valid_session(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        store.upsert_daily_bars(
            [
                DailyBar("AAA", "2026-09-22", exchange="HOSE", close=71.5),
                DailyBar("AAA", "2026-09-23", exchange="HOSE", close=None),
            ]
        )
    technical = _read_technical(tmp_path, "2026-09-24")
    assert technical["previous_close"] is None
    assert technical["ma10_sessions"] == 1


def test_ma200_scans_past_unusable_close_in_newest_200_rows(tmp_path: Path) -> None:
    first = date(2025, 1, 1)
    rows = [
        DailyBar(
            "AAA",
            (first + timedelta(days=index)).isoformat(),
            exchange="HOSE",
            close=None if index == 200 else float(index + 1),
        )
        for index in range(201)
    ]
    with CanonicalMarketStore(tmp_path) as store:
        store.upsert_daily_bars(rows)
    technical = _read_technical(tmp_path, (first + timedelta(days=201)).isoformat())
    assert technical["previous_close"] is None
    assert technical["ma200_sessions"] == 200
    assert technical["ma200"] == pytest.approx(100.5)


def test_ma200_remains_null_with_only_199_usable_closes(tmp_path: Path) -> None:
    first = date(2025, 1, 1)
    with CanonicalMarketStore(tmp_path) as store:
        store.upsert_daily_bars(
            [
                DailyBar(
                    "AAA",
                    (first + timedelta(days=index)).isoformat(),
                    exchange="HOSE",
                    close=float(index + 1),
                )
                for index in range(199)
            ]
        )
    technical = _read_technical(tmp_path, (first + timedelta(days=199)).isoformat())
    assert technical["ma200"] is None
    assert technical["ma200_sessions"] == 199


@pytest.mark.parametrize(
    ("minute", "window", "price", "expected"),
    [
        ("13:02", 5, 110, None),
        ("13:05", 5, 110, 10),
        ("13:10", 15, 120, None),
        ("13:15", 15, 120, 20),
    ],
)
def test_price_windows_require_exact_same_segment_clock_anchor(
    minute: str, window: int, price: float, expected: float | None
) -> None:
    result = exact_price_change(
        exchange="HNX",
        trading_date="2026-09-24",
        current_minute=minute,
        current_price=price,
        closes={"11:27": 1, "12:57": 2, "13:00": 100},
        window=window,
    )
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_missing_exact_price_anchor_returns_null() -> None:
    assert exact_price_change(
        exchange="HNX",
        trading_date="2026-09-24",
        current_minute="09:20",
        current_price=110,
        closes={"09:14": 100},
        window=5,
    ) is None


def test_broad_job_checkpoint_does_not_prove_unobserved_session(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        store.upsert_daily_bars(
            [DailyBar("AAA", "2026-01-05", exchange="HOSE", close=10)]
        )
        store.upsert_minute_bars(
            [MinuteBar("AAA", "2026-01-05", "09:16", exchange="HOSE", volume=10)]
        )
        store.mark_fetch_status(
            mode="minute",
            symbol="AAA",
            from_date="2026-01-01",
            to_date="2026-12-31",
            resolution=1,
            year=2026,
            status="COMPLETED",
            rows_received=1,
            rows_written=1,
        )
    with MarketShardReader(tmp_path) as reader:
        snapshot = reader.load_symbol("AAA", "2026-01-06")
        assert snapshot.load_completed_session("2026-01-05") is None


def test_sparse_zero_requires_daily_and_exact_session_proof(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        store.upsert_daily_bars(
            [DailyBar("AAA", "2026-01-05", exchange="HOSE", close=10)]
        )
        store.upsert_minute_bars(
            [MinuteBar("AAA", "2026-01-05", "09:16", exchange="HOSE", volume=10)]
        )
    rebuild_engine(
        market_db_dir=tmp_path,
        engine_db=tmp_path / "engine-no-proof.db",
        as_of_date="2026-01-06",
    )
    connection = sqlite3.connect(tmp_path / "engine-no-proof.db")
    try:
        no_proof = connection.execute(
            """SELECT avg_cumulative_volume,day_sessions_used
               FROM volume_baseline_curve
               WHERE symbol='AAA' AND minute='09:15'"""
        ).fetchone()
        assert no_proof == (None, 0)
    finally:
        connection.close()

    with CanonicalMarketStore(tmp_path) as store:
        store.mark_rest_sessions_completed(
            mode="minute",
            symbol="AAA",
            resolution=1,
            rows_by_date={"2026-01-05": 1},
        )
    rebuild_engine(
        market_db_dir=tmp_path,
        engine_db=tmp_path / "engine-proof.db",
        as_of_date="2026-01-06",
    )
    connection = sqlite3.connect(tmp_path / "engine-proof.db")
    try:
        proven = connection.execute(
            """SELECT avg_cumulative_volume,day_sessions_used
               FROM volume_baseline_curve
               WHERE symbol='AAA' AND minute='09:15'"""
        ).fetchone()
        assert proven == (0.0, 1)
    finally:
        connection.close()
    assert _count(tmp_path / "ccc_market_2026.db", "minute_bars") == 1


def test_rvol_grid_readiness_and_pm_window_reset(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        store.upsert_daily_bars(
            [DailyBar("AAA", "2026-09-23", exchange="HOSE", close=10)]
        )
        store.upsert_minute_bars(
            [
                MinuteBar(
                    "AAA", "2026-09-23", "11:29", exchange="HOSE", volume=900
                )
            ]
        )
        store.mark_rest_sessions_completed(
            mode="minute",
            symbol="AAA",
            resolution=1,
            rows_by_date={"2026-09-23": 1},
        )
    rebuild_engine(
        market_db_dir=tmp_path,
        engine_db=tmp_path / "ccc_engine.db",
        as_of_date="2026-09-24",
    )
    connection = sqlite3.connect(tmp_path / "ccc_engine.db")
    connection.row_factory = sqlite3.Row
    try:
        rows = {
            row["minute"]: row
            for row in connection.execute(
                """SELECT minute,avg_volume_15,rvol15_sessions_used,
                          avg_volume_30,rvol30_sessions_used
                   FROM volume_baseline_curve WHERE symbol='AAA'
                     AND minute IN ('09:29','09:30','09:44','09:45','13:13','13:14','13:29')"""
            )
        }
        assert rows["09:29"]["rvol15_sessions_used"] == 0
        assert rows["09:30"]["rvol15_sessions_used"] == 1
        assert rows["09:44"]["rvol30_sessions_used"] == 0
        assert rows["09:45"]["rvol30_sessions_used"] == 1
        assert rows["13:13"]["rvol15_sessions_used"] == 0
        assert rows["13:14"]["avg_volume_15"] == 0
        assert rows["13:29"]["avg_volume_30"] == 0
    finally:
        connection.close()


def test_bad_recent_session_is_skipped_and_older_session_fills_ten(tmp_path: Path) -> None:
    with CanonicalMarketStore(tmp_path) as store:
        store.upsert_daily_bars(
            [
                DailyBar("AAA", f"2026-09-{day:02d}", exchange="HOSE", close=10)
                for day in range(1, 12)
            ]
        )
        store.upsert_minute_bars(
            [
                MinuteBar(
                    "AAA",
                    f"2026-09-{day:02d}",
                    "09:15",
                    exchange="HOSE",
                    volume=None if day == 11 else day,
                )
                for day in range(1, 12)
            ]
        )
        store.mark_rest_sessions_completed(
            mode="minute",
            symbol="AAA",
            resolution=1,
            rows_by_date={f"2026-09-{day:02d}": 1 for day in range(1, 12)},
        )
    rebuild_engine(
        market_db_dir=tmp_path,
        engine_db=tmp_path / "ccc_engine.db",
        as_of_date="2026-09-12",
    )
    connection = sqlite3.connect(tmp_path / "ccc_engine.db")
    connection.row_factory = sqlite3.Row
    try:
        point = connection.execute(
            """SELECT avg_cumulative_volume,day_sessions_used
               FROM volume_baseline_curve
               WHERE symbol='AAA' AND minute='09:15'"""
        ).fetchone()
        assert point["day_sessions_used"] == 10
        assert point["avg_cumulative_volume"] == pytest.approx(5.5)
    finally:
        connection.close()


def test_rebuild_source_has_no_global_unbounded_minute_materialization() -> None:
    source = inspect.getsource(rebuild_module)
    assert "SELECT * FROM minute_bars" not in source
    assert "WHERE symbol=? AND trading_date=?" in source


def test_calculation_failure_cannot_mutate_canonical_market(tmp_path: Path) -> None:
    _seed_engine_market(tmp_path)
    market = tmp_path / "ccc_market_2026.db"
    before = (_count(market, "daily_bars"), _count(market, "minute_bars"))

    def fail(*_args, **_kwargs):
        raise RuntimeError("calculation failed")

    symbols, failures = rebuild_engine(
        market_db_dir=tmp_path,
        engine_db=tmp_path / "ccc_engine.db",
        as_of_date="2026-09-24",
        calculator=fail,
    )
    after = (_count(market, "daily_bars"), _count(market, "minute_bars"))
    assert (symbols, failures) == (1, 1)
    assert after == before
