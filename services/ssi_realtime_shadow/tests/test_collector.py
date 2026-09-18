import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app.collector import QuoteCollector, _extract_payloads
from app.market_session import VN_TZ
from app.realtime_volume import VolumeEvent
from app.storage import SQLiteStore


def market_event(**overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "Symbol": "HPG",
        "Market": "HOSE",
        "TradingDate": "14/09/2026",
        "Time": "09:00:10",
        "LastPrice": 27000,
        "TotalVol": 1000,
    }
    event.update(overrides)
    return event


def started_at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 9, 14, hour, minute, second, tzinfo=VN_TZ)


def official_x_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "RType": "X",
        "TradingDate": "14/09/2026",
        "Time": "10:30:00",
        "Symbol": "HPG",
        "LastPrice": 27000,
        "TotalVol": 123456,
        "Exchange": "HOSE",
    }
    payload.update(overrides)
    return payload


def test_extracts_official_ssi_content_json_string() -> None:
    inner = official_x_payload()
    outer = {"DataType": "X", "Content": json.dumps(inner)}

    assert list(_extract_payloads(outer)) == [inner]


def test_extracts_official_ssi_content_dict() -> None:
    inner = official_x_payload(Symbol="SHS", Exchange="HNX")

    assert list(_extract_payloads({"DataType": "X", "Content": inner})) == [inner]


def test_extracts_lowercase_content_envelope() -> None:
    inner = official_x_payload(Symbol="VGI", Exchange="UPCOM")

    assert list(_extract_payloads({"DataType": "X", "content": inner})) == [inner]


def test_extracts_x_trade_content_list_wrapper() -> None:
    payloads = [
        official_x_payload(Symbol="HPG"),
        official_x_payload(Symbol="SHS", Exchange="HNX"),
    ]
    outer = {
        "DataType": "X-TRADE",
        "Content": [json.dumps(payloads[0]), payloads[1]],
    }

    assert list(_extract_payloads(outer)) == payloads


def test_malformed_content_does_not_crash() -> None:
    assert list(_extract_payloads({"DataType": "X", "Content": "{broken"})) == []


def test_direct_symbol_payload_still_extracts_unchanged() -> None:
    payload = official_x_payload()

    assert list(_extract_payloads(payload)) == [payload]


@pytest.mark.parametrize("key", ["data", "payload", "message"])
def test_legacy_envelopes_still_extract(key: str) -> None:
    payload = official_x_payload()

    assert list(_extract_payloads({key: json.dumps(payload)})) == [payload]


def test_collector_accepts_official_x_all_wrapper_and_emits_volume_event(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    received: list[VolumeEvent] = []
    collector = QuoteCollector(
        {"HPG"},
        store,
        started_at=started_at(8, 30),
        volume_event_handler=received.append,
    )
    inner = official_x_payload()

    collector.on_message(
        {"DataType": "X", "Content": json.dumps(inner, separators=(",", ":"))}
    )

    bar = store._conn.execute(
        "SELECT symbol, minute, volume FROM minute_bars"
    ).fetchone()
    quote = store._conn.execute(
        "SELECT symbol, event_time, total_volume FROM latest_quotes"
    ).fetchone()
    assert collector.stats.received_messages == 1
    assert collector.stats.accepted_events == 1
    assert bar["symbol"] == "HPG"
    assert bar["minute"] == "10:30"
    assert bar["volume"] == 123456
    assert quote["symbol"] == "HPG"
    assert quote["event_time"] == "10:30:00"
    assert quote["total_volume"] == 123456
    assert len(received) == 1
    assert received[0].symbol == "HPG"
    assert received[0].volume_delta == 123456
    assert collector.stats.volume_shadow_events == 1
    store.close()


def test_minute_volume_uses_cumulative_delta(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    store = SQLiteStore(db, commit_every_events=1, commit_every_seconds=1)
    collector = QuoteCollector({"HPG"}, store)

    collector.on_message(
        {"Symbol": "HPG", "TradingDate": "11/09/2026", "Time": "09:00:10", "LastPrice": 27000, "TotalVol": 1000}
    )
    collector.on_message(
        {"Symbol": "HPG", "TradingDate": "11/09/2026", "Time": "09:00:20", "LastPrice": 27100, "TotalVol": 1200}
    )
    collector.on_message(
        {"Symbol": "HPG", "TradingDate": "11/09/2026", "Time": "09:00:40", "LastPrice": 26900, "TotalVol": 1250}
    )
    collector.on_message(
        {"Symbol": "HPG", "TradingDate": "11/09/2026", "Time": "09:01:05", "LastPrice": 27200, "TotalVol": 1500}
    )
    store.commit()

    rows = store._conn.execute(
        "SELECT minute, open, high, low, close, volume, last_total_volume, is_partial FROM minute_bars ORDER BY minute"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["minute"] == "09:00"
    assert rows[0]["open"] == 27000
    assert rows[0]["high"] == 27100
    assert rows[0]["low"] == 26900
    assert rows[0]["close"] == 26900
    assert rows[0]["volume"] == 250
    assert rows[0]["last_total_volume"] == 1250
    assert rows[0]["is_partial"] == 1

    assert rows[1]["minute"] == "09:01"
    assert rows[1]["volume"] == 250
    assert rows[1]["is_partial"] == 0
    store.close()


def test_outside_universe_is_ignored(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store)
    collector.on_message(
        {"Symbol": "VN30F1M", "TradingDate": "11/09/2026", "Time": "09:00:10", "LastPrice": 1800, "TotalVol": 10}
    )
    store.commit()
    count = store._conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0]
    assert count == 0
    assert collector.stats.ignored_outside_universe == 1
    store.close()


@pytest.mark.parametrize(
    "provider_date",
    ["14092026", "14/09/2026", "14-09-2026", "2026-09-14", "2026/09/14"],
)
def test_supported_trading_date_formats(
    tmp_path: Path, provider_date: str
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    collector.on_message(market_event(TradingDate=provider_date))

    row = store._conn.execute(
        "SELECT trading_date FROM latest_quotes WHERE symbol = 'HPG'"
    ).fetchone()
    assert row["trading_date"] == "2026-09-14"
    store.close()


def test_malformed_nonempty_trading_date_is_rejected(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store)

    with caplog.at_level(logging.WARNING):
        collector.on_message(market_event(TradingDate="2026-99-99"))

    assert store._conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0] == 0
    assert collector.stats.ignored_malformed_trading_date == 1
    assert "malformed TradingDate" in caplog.text
    store.close()


def test_missing_trading_date_uses_current_local_date(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store)
    expected_date = datetime.now(VN_TZ).date().isoformat()
    event = market_event()
    event.pop("TradingDate")
    collector.on_message(event)

    row = store._conn.execute(
        "SELECT trading_date FROM latest_quotes WHERE symbol = 'HPG'"
    ).fetchone()
    assert row["trading_date"] == expected_date
    store.close()


@pytest.mark.parametrize(
    ("field", "provider_market", "expected"),
    [
        ("Market", "UPCOM", "UPCOM"),
        ("MarketId", "HNX", "HNX"),
        ("Exchange", "HSX", "HOSE"),
    ],
)
def test_provider_market_is_normalized_by_priority_fields(
    tmp_path: Path, field: str, provider_market: str, expected: str
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    event = market_event(TradingSession=" lo ", TradingStatus=" raw ")
    event.pop("Market")
    event[field] = provider_market
    collector.on_message(event)

    quote = store._conn.execute(
        "SELECT exchange, trading_session, trading_status FROM latest_quotes"
    ).fetchone()
    bar = store._conn.execute("SELECT exchange FROM minute_bars").fetchone()
    assert quote["exchange"] == expected
    assert bar["exchange"] == expected
    assert quote["trading_session"] == "LO"
    assert quote["trading_status"] == " raw "
    store.close()


def test_market_field_has_priority_over_market_id_and_exchange(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    collector.on_message(
        market_event(Market="UPCOM", MarketId="HNX", Exchange="HSX")
    )

    exchange = store._conn.execute(
        "SELECT exchange FROM latest_quotes WHERE symbol = 'HPG'"
    ).fetchone()[0]
    assert exchange == "UPCOM"
    store.close()


def test_derivative_market_is_rejected_from_equity_storage(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"VN30F1M"}, store)
    collector.on_message(market_event(Symbol="VN30F1M", Market="DER"))

    assert store._conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0] == 0
    assert store._conn.execute("SELECT COUNT(*) FROM latest_quotes").fetchone()[0] == 0
    assert collector.stats.ignored_non_equity_market == 1
    store.close()


def test_explicit_unknown_market_is_rejected(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store)
    collector.on_message(market_event(Market="UNKNOWN"))

    assert store._conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0] == 0
    assert collector.stats.ignored_unknown_market == 1
    store.close()


def test_missing_market_is_accepted_only_as_untrusted_compatibility_data(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    first = market_event(Time="09:00:10", TotalVol=1000)
    first.pop("Market")
    second = market_event(Time="09:01:10", TotalVol=1200)
    second.pop("Market")
    collector.on_message(first)
    collector.on_message(second)

    row = store._conn.execute(
        """
        SELECT exchange, volume, is_partial, quality_status
        FROM minute_bars
        WHERE minute = '09:01'
        """
    ).fetchone()
    assert row["exchange"] is None
    assert row["volume"] == 200
    assert row["is_partial"] == 0
    assert row["quality_status"] == "UNKNOWN_MARKET"
    store.close()


def test_missing_total_volume_marks_minute_untrusted(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    event = market_event()
    event.pop("TotalVol")
    collector.on_message(event)

    row = store._conn.execute(
        "SELECT volume, last_total_volume, is_partial, quality_status FROM minute_bars"
    ).fetchone()
    assert row["volume"] == 0
    assert row["last_total_volume"] is None
    assert row["is_partial"] == 1
    assert row["quality_status"] == "MISSING_TOTAL_VOLUME"
    store.close()


def test_first_total_volume_seeds_from_zero_when_started_before_open(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    collector.on_message(market_event(TotalVol=1000))

    row = store._conn.execute(
        "SELECT volume, is_partial, quality_status FROM minute_bars"
    ).fetchone()
    assert row["volume"] == 1000
    assert row["is_partial"] == 0
    assert row["quality_status"] == "TRUSTED"
    store.close()


def test_first_total_volume_is_baseline_when_started_mid_session(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store, started_at=started_at(10, 30))
    collector.on_message(
        market_event(Time="10:30:10", TotalVol=5_000_000)
    )

    row = store._conn.execute(
        "SELECT volume, last_total_volume, is_partial, quality_status FROM minute_bars"
    ).fetchone()
    assert row["volume"] == 0
    assert row["last_total_volume"] == 5_000_000
    assert row["is_partial"] == 1
    assert row["quality_status"] == "PARTIAL"
    store.close()


def test_first_afternoon_total_is_not_seeded_even_after_preopen_start(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    collector.on_message(market_event(Time="13:00:10", TotalVol=5_000_000))

    row = store._conn.execute(
        "SELECT volume, is_partial, quality_status FROM minute_bars"
    ).fetchone()
    assert row["volume"] == 0
    assert row["is_partial"] == 1
    assert row["quality_status"] == "PARTIAL"
    store.close()


def test_restart_in_same_minute_continues_cumulative_delta(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    store = SQLiteStore(db, commit_every_events=1)
    first = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    first.on_message(market_event(Time="10:01:10", TotalVol=1000))
    store.close()

    store = SQLiteStore(db, commit_every_events=1)
    restarted = QuoteCollector({"HPG"}, store, started_at=started_at(10, 1, 20))
    restarted.on_message(market_event(Time="10:01:30", TotalVol=1200))

    row = store._conn.execute(
        "SELECT volume, last_total_volume, has_gap, quality_status FROM minute_bars"
    ).fetchone()
    assert row["volume"] == 1200
    assert row["last_total_volume"] == 1200
    assert row["has_gap"] == 0
    assert row["quality_status"] == "TRUSTED"
    store.close()


def test_cross_minute_restart_records_gap_without_volume_spike(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    store = SQLiteStore(db, commit_every_events=1)
    first = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    first.on_message(market_event(Time="10:01:10", TotalVol=1_000_000))
    store.close()

    store = SQLiteStore(db, commit_every_events=1)
    restarted = QuoteCollector({"HPG"}, store, started_at=started_at(10, 6))
    restarted.on_message(market_event(Time="10:06:05", TotalVol=1_500_000))
    restarted.on_message(market_event(Time="10:06:20", TotalVol=1_510_000))

    row = store._conn.execute(
        """
        SELECT volume, last_total_volume, is_partial, quality_status,
               has_gap, gap_from, gap_to
        FROM minute_bars
        WHERE minute = '10:06'
        """
    ).fetchone()
    assert row["volume"] == 10_000
    assert row["last_total_volume"] == 1_510_000
    assert row["is_partial"] == 1
    assert row["quality_status"] == "GAP"
    assert row["has_gap"] == 1
    assert row["gap_from"] == "2026-09-14T10:01:10+07:00"
    assert row["gap_to"] == "2026-09-14T10:06:05+07:00"
    store.close()


def test_cumulative_volume_regression_preserves_last_good_baseline(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    collector.on_message(market_event(Time="09:00:10", TotalVol=1000))
    collector.on_message(market_event(Time="09:00:20", TotalVol=1200))
    with caplog.at_level(logging.WARNING):
        collector.on_message(market_event(Time="09:00:30", TotalVol=1100))
    collector.on_message(market_event(Time="09:00:40", TotalVol=1250))

    row = store._conn.execute(
        """
        SELECT volume, last_total_volume, is_partial, quality_status
        FROM minute_bars
        """
    ).fetchone()
    latest_total = store._conn.execute(
        "SELECT total_volume FROM latest_quotes WHERE symbol = 'HPG'"
    ).fetchone()[0]
    assert row["volume"] == 1250
    assert row["last_total_volume"] == 1250
    assert row["is_partial"] == 1
    assert row["quality_status"] == "VOLUME_REGRESSION"
    assert latest_total == 1250
    assert "Cumulative volume moved backwards" in caplog.text
    store.close()


def test_existing_database_is_migrated_without_rebuilding_data(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE minute_bars (
            trading_date TEXT NOT NULL,
            minute TEXT NOT NULL,
            symbol TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume INTEGER NOT NULL DEFAULT 0,
            last_total_volume INTEGER,
            event_count INTEGER NOT NULL DEFAULT 0,
            is_partial INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (trading_date, minute, symbol)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO minute_bars VALUES (
            '2026-09-11', '09:00', 'HPG', 27, 28, 26, 27.5,
            1000, 1000, 3, 0, '2026-09-11T09:00:30+07:00'
        )
        """
    )
    conn.commit()
    conn.close()

    store = SQLiteStore(db)
    columns = {
        row["name"]
        for row in store._conn.execute("PRAGMA table_info(minute_bars)").fetchall()
    }
    row = store._conn.execute(
        "SELECT symbol, volume, quality_status, has_gap FROM minute_bars"
    ).fetchone()
    indexes = {
        row["name"]
        for row in store._conn.execute("PRAGMA index_list(minute_bars)").fetchall()
    }
    assert {
        "exchange",
        "quality_status",
        "has_gap",
        "gap_from",
        "gap_to",
        "data_source",
        "provider_time",
    } <= columns
    assert row["symbol"] == "HPG"
    assert row["volume"] == 1000
    assert row["quality_status"] == "LEGACY_UNVERIFIED"
    assert row["has_gap"] == 0
    assert store._conn.execute(
        "SELECT data_source FROM minute_bars"
    ).fetchone()[0] == "SSI_STREAM"
    assert "idx_minute_bars_pending_gaps" in indexes
    store.close()

    reopened = SQLiteStore(db)
    assert reopened._conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0] == 1
    reopened.close()


def test_volume_callback_receives_exact_post_accounting_canonical_event(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=100)
    received: list[VolumeEvent] = []

    def handler(event: VolumeEvent) -> None:
        assert store._conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0] == 1
        assert store._conn.execute("SELECT COUNT(*) FROM latest_quotes").fetchone()[0] == 1
        received.append(event)

    collector = QuoteCollector(
        {"HPG"},
        store,
        started_at=started_at(8, 30),
        volume_event_handler=handler,
    )
    collector.on_message(
        market_event(
            Market="HSX",
            Time="09:00:10",
            TotalVol=1_000,
            TradingSession=" ato ",
        )
    )

    assert len(received) == 1
    event = received[0]
    assert event.symbol == "HPG"
    assert event.exchange == "HOSE"
    assert event.trading_date == "2026-09-14"
    assert event.event_time == started_at(9, 0, 10)
    assert event.minute == "09:00"
    assert event.volume_delta == 1_000
    assert event.total_volume == 1_000
    assert event.provider_total_volume == 1_000
    assert event.provider_session == "ATO"
    assert event.data_source == "SSI_STREAM"
    assert event.quality_status == "TRUSTED"
    assert not event.is_partial
    assert not event.has_gap
    assert collector.stats.volume_shadow_events == 1
    assert collector.stats.volume_shadow_event_errors == 0
    store.close()


def test_collector_persists_isolated_provider_session_auction_projection(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    collector.on_message(
        market_event(Time="09:00:10", TotalVol=100, TradingSession="ATO")
    )
    collector.on_message(
        market_event(Time="09:16:10", TotalVol=150, TradingSession="LO")
    )
    collector.on_message(
        market_event(Time="14:29:10", TotalVol=1_000, TradingSession="LO")
    )
    collector.on_message(
        market_event(Time="14:30:10", TotalVol=1_250, TradingSession="ATC")
    )
    collector.on_message(
        market_event(Time="14:46:10", TotalVol=1_250, TradingSession="C")
    )

    rows = store._conn.execute(
        """
        SELECT auction_type,provider_session,auction_volume,finalized,
               quality_status FROM auction_session_buckets ORDER BY auction_type
        """
    ).fetchall()
    minute_pk = [
        row["name"]
        for row in store._conn.execute("PRAGMA table_info(minute_bars)")
        if row["pk"]
    ]
    assert [tuple(row) for row in rows] == [
        ("CLOSE_AUCTION", "ATC", 250, 1, "TRUSTED"),
        ("OPEN_AUCTION", "ATO", 100, 1, "TRUSTED"),
    ]
    assert minute_pk == ["trading_date", "minute", "symbol"]
    assert store._conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='signal_events'"
    ).fetchone()[0] == 0
    store.close()


def test_reopened_store_and_collector_hydrate_lo_state_before_atc(
    tmp_path: Path,
) -> None:
    path = tmp_path / "restart-before-atc.db"
    store = SQLiteStore(path, commit_every_events=1)
    first = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    first.on_message(
        market_event(Time="09:00:10", TotalVol=0, TradingSession="ATO")
    )
    first.on_message(
        market_event(
            Time="14:29:00",
            TotalVol=6_980_600,
            LastPrice=73_900,
            TradingSession="LO",
        )
    )
    store.close()

    reopened = SQLiteStore(path, commit_every_events=1)
    resumed = QuoteCollector(
        {"HPG"}, reopened, started_at=started_at(14, 44)
    )
    resumed.on_message(
        market_event(
            Time="14:45:00",
            TotalVol=15_500_700,
            LastPrice=71_700,
            TradingSession="ATC",
        )
    )
    closing = {
        bucket.auction_type: bucket
        for bucket in reopened.get_auction_buckets("HPG", "2026-09-14")
    }["CLOSE_AUCTION"]

    assert closing.start_total_volume == 6_980_600
    assert closing.auction_volume == 8_520_100
    assert closing.pre_auction_price == 73_900
    assert closing.auction_price == 71_700
    reopened.close()


def test_reopened_collector_continues_existing_atc_bucket_without_double_count(
    tmp_path: Path,
) -> None:
    path = tmp_path / "restart-during-atc.db"
    store = SQLiteStore(path, commit_every_events=1)
    first = QuoteCollector({"HPG"}, store, started_at=started_at(8, 30))
    first.on_message(
        market_event(Time="09:00:10", TotalVol=0, TradingSession="ATO")
    )
    first.on_message(
        market_event(
            Time="14:29:00",
            TotalVol=6_980_600,
            LastPrice=73_900,
            TradingSession="LO",
        )
    )
    first.on_message(
        market_event(
            Time="14:30:00",
            TotalVol=10_000_000,
            LastPrice=72_500,
            TradingSession="ATC",
        )
    )
    store.close()

    reopened = SQLiteStore(path, commit_every_events=1)
    resumed = QuoteCollector(
        {"HPG"}, reopened, started_at=started_at(14, 39)
    )
    resumed.on_message(
        market_event(
            Time="14:40:00",
            TotalVol=15_500_700,
            LastPrice=71_700,
            TradingSession="ATC",
        )
    )
    closing = {
        bucket.auction_type: bucket
        for bucket in reopened.get_auction_buckets("HPG", "2026-09-14")
    }["CLOSE_AUCTION"]

    assert closing.start_total_volume == 6_980_600
    assert closing.auction_volume == 8_520_100
    assert closing.event_count == 2
    assert closing.pre_auction_price == 73_900
    assert closing.auction_price == 71_700
    reopened.close()


def test_none_volume_callback_preserves_collector_behavior(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    collector = QuoteCollector(
        {"HPG"}, store, started_at=started_at(8, 30), volume_event_handler=None
    )

    collector.on_message(market_event())

    assert collector.stats.accepted_events == 1
    assert collector.stats.volume_shadow_events == 0
    assert collector.stats.volume_shadow_event_errors == 0
    assert store._conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0] == 1
    store.close()


def test_volume_callback_exception_is_isolated_after_audit_writes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)

    def broken_handler(_event: VolumeEvent) -> None:
        raise RuntimeError("shadow boom")

    collector = QuoteCollector(
        {"HPG"},
        store,
        started_at=started_at(8, 30),
        volume_event_handler=broken_handler,
    )
    with caplog.at_level(logging.ERROR):
        collector.on_message(market_event())

    assert collector.stats.accepted_events == 1
    assert collector.stats.volume_shadow_events == 1
    assert collector.stats.volume_shadow_event_errors == 1
    assert store._conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0] == 1
    assert store._conn.execute("SELECT COUNT(*) FROM latest_quotes").fetchone()[0] == 1
    assert "symbol=HPG minute=09:00" in caplog.text
    assert "shadow boom" in caplog.text
    store.close()


def test_volume_event_construction_failure_is_also_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)

    def broken_event(**_kwargs: object) -> VolumeEvent:
        raise ValueError("contract boom")

    monkeypatch.setattr("app.collector.VolumeEvent", broken_event)
    collector = QuoteCollector(
        {"HPG"},
        store,
        started_at=started_at(8, 30),
        volume_event_handler=lambda _event: None,
    )

    collector.on_message(market_event())

    assert collector.stats.accepted_events == 1
    assert collector.stats.volume_shadow_events == 1
    assert collector.stats.volume_shadow_event_errors == 1
    assert store._conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0] == 1
    store.close()


@pytest.mark.parametrize("market", ["UNKNOWN", None])
def test_unknown_or_missing_exchange_does_not_emit_volume_event(
    tmp_path: Path, market: str | None
) -> None:
    store = SQLiteStore(tmp_path / "test.db", commit_every_events=1)
    received: list[VolumeEvent] = []
    collector = QuoteCollector(
        {"HPG"}, store, volume_event_handler=received.append
    )
    event = market_event(Market=market)
    collector.on_message(event)

    assert received == []
    assert collector.stats.volume_shadow_events == 0
    store.close()
