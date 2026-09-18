from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from app.market_storage_schema import (
    ARCHIVE_STORAGE_SCHEMA_VERSION,
    MARKET_DATA_CONTRACT_VERSION,
    STORAGE_SCHEMA_VERSION,
    SchemaVersionError,
    canonical_timestamp,
    ensure_5m_archive_schema,
    ensure_market_storage_schema,
)


APPLIED_AT = "2026-09-18T10:30:00+07:00"
EVENT_ID_1 = "123e4567-e89b-42d3-a456-426614174000"
EVENT_ID_2 = "123e4567-e89b-42d3-b456-426614174001"
EVENT_ID_3 = "123e4567-e89b-42d3-8456-426614174002"
MARKET_TABLES = {
    "daily_bars",
    "stock_state_current",
    "signal_events",
    "signal_event_features",
    "market_index_current",
    "universe_cache",
    "trading_calendar",
    "auction_session_history",
    "engine_meta",
}
MARKET_INDEXES = {
    "idx_daily_bars_date_exchange",
    "idx_stock_state_signal",
    "idx_stock_state_exchange_updated",
    "idx_stock_state_updated",
    "idx_signal_events_symbol_detected",
    "idx_signal_events_detected",
    "idx_signal_events_journal",
    "idx_signal_events_idempotency",
    "idx_universe_cache_active_exchange",
    "idx_trading_calendar_exchange_day",
    "idx_auction_history_date_type",
}


@pytest.fixture
def connection() -> sqlite3.Connection:
    database = sqlite3.connect(":memory:")
    try:
        ensure_market_storage_schema(database, applied_at=APPLIED_AT)
        yield database
    finally:
        database.close()


@pytest.fixture
def archive_connection() -> sqlite3.Connection:
    database = sqlite3.connect(":memory:")
    try:
        ensure_5m_archive_schema(database)
        yield database
    finally:
        database.close()


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _insert_stock_state(
    connection: sqlite3.Connection,
    *,
    symbol: str = "HPG",
    session_type: str = "AM_CONTINUOUS",
    signal_level: int = 0,
    feed_status: str = "LIVE",
    quality_status: str = "DEGRADED",
) -> None:
    connection.execute(
        """
        INSERT INTO stock_state_current (
            symbol, exchange, trading_date, session_type,
            ma10_sessions, ma200_sessions,
            baseline_sessions_used, baseline_target_sessions,
            baseline_coverage_pct, signal_state, signal_level,
            signal_summary_vi, engine_version, config_version,
            feed_status, quality_status, metrics_trusted,
            event_at, updated_at
        ) VALUES (?, 'HOSE', '2026-09-18', ?, 0, 0, 0, 10, 0,
                  'NORMAL', ?, 'Bình thường', '2.0.0', 'cfg-20260918-001',
                  ?, ?, 0, ?, ?)
        """,
        (
            symbol,
            session_type,
            signal_level,
            feed_status,
            quality_status,
            APPLIED_AT,
            APPLIED_AT,
        ),
    )


def _insert_signal_event(
    connection: sqlite3.Connection,
    event_id: str,
    detected_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO signal_events (
            event_id, symbol, exchange, trading_date, detected_at,
            previous_state, signal_state, signal_level,
            price_at_signal, change_pct_at_signal, session_type,
            engine_version, config_version, quality_status, metrics_trusted
        ) VALUES (?, 'HPG', 'HOSE', '2026-09-18', ?, 'NORMAL',
                  'FLOW_APPEARING', 1, 28000, 1.82, 'AM_CONTINUOUS',
                  '2.0.0', 'cfg-20260918-001', 'TRUSTED', 1)
        """,
        (event_id, detected_at),
    )


def test_empty_database_initializes_required_market_schema() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        ensure_market_storage_schema(connection, applied_at=APPLIED_AT)
        assert MARKET_TABLES <= _table_names(connection)
        assert "bars_5m_archive" not in _table_names(connection)
        versions = dict(
            connection.execute(
                "SELECT key, value FROM engine_meta ORDER BY key"
            ).fetchall()
        )
        assert versions["market_data_contract"] == str(
            MARKET_DATA_CONTRACT_VERSION
        )
        assert versions["storage_schema"] == str(STORAGE_SCHEMA_VERSION)
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()


def test_empty_archive_database_initializes_only_archive_schema() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        ensure_5m_archive_schema(connection)
        assert _table_names(connection) == {"bars_5m_archive"}
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            ARCHIVE_STORAGE_SCHEMA_VERSION
        )
    finally:
        connection.close()


def test_initialization_is_idempotent_and_preserves_metadata(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        "INSERT INTO engine_meta(key, value, updated_at) VALUES ('owner', 'ccc', ?)",
        (APPLIED_AT,),
    )
    connection.commit()
    before = connection.execute(
        "SELECT key, value, updated_at FROM engine_meta ORDER BY key"
    ).fetchall()

    ensure_market_storage_schema(
        connection,
        applied_at="2026-09-18T11:30:00+07:00",
    )

    after = connection.execute(
        "SELECT key, value, updated_at FROM engine_meta ORDER BY key"
    ).fetchall()
    assert after == before


def test_archive_initialization_is_idempotent(
    archive_connection: sqlite3.Connection,
) -> None:
    before = archive_connection.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'bars_5m_archive'"
    ).fetchone()
    ensure_5m_archive_schema(archive_connection)
    after = archive_connection.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'bars_5m_archive'"
    ).fetchone()
    assert after == before
    assert archive_connection.execute("PRAGMA user_version").fetchone()[0] == 1


def test_existing_reused_tables_and_rows_are_preserved() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE minute_bars (sentinel TEXT PRIMARY KEY, payload TEXT)"
        )
        connection.execute(
            "CREATE TABLE latest_quotes (symbol TEXT PRIMARY KEY, payload TEXT)"
        )
        connection.execute(
            "INSERT INTO minute_bars VALUES ('keep', 'minute')"
        )
        connection.execute(
            "INSERT INTO latest_quotes VALUES ('HPG', 'quote')"
        )
        connection.commit()

        ensure_market_storage_schema(connection, applied_at=APPLIED_AT)

        assert connection.execute("SELECT * FROM minute_bars").fetchall() == [
            ("keep", "minute")
        ]
        assert connection.execute("SELECT * FROM latest_quotes").fetchall() == [
            ("HPG", "quote")
        ]
        minute_columns = [
            row[1] for row in connection.execute("PRAGMA table_info(minute_bars)")
        ]
        assert minute_columns == ["sentinel", "payload"]
    finally:
        connection.close()


def test_daily_primary_key(connection: sqlite3.Connection) -> None:
    daily = (
        "HPG",
        "2026-09-18",
        "HOSE",
        28000,
        28500,
        27900,
        28300,
        1000000,
        None,
        "SSI",
        "TRUSTED",
        APPLIED_AT,
    )
    connection.execute(
        "INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        daily,
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            daily,
        )



def test_five_minute_primary_key(
    archive_connection: sqlite3.Connection,
) -> None:
    bar_5m = (
        "HPG",
        "HOSE",
        "2026-09-18",
        "09:20",
        28000,
        28200,
        27900,
        28100,
        10000,
        None,
        "TRUSTED",
        "SSI_1M_AGG",
        APPLIED_AT,
    )
    archive_connection.execute(
        "INSERT INTO bars_5m_archive VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        bar_5m,
    )
    with pytest.raises(sqlite3.IntegrityError):
        archive_connection.execute(
            "INSERT INTO bars_5m_archive VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            bar_5m,
        )


def test_stock_state_has_one_row_per_symbol_and_accepts_null_metrics(
    connection: sqlite3.Connection,
) -> None:
    _insert_stock_state(connection)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_stock_state(connection)

    nullable_metrics = (
        "ma10",
        "ma200",
        "distance_ma10_pct",
        "distance_ma200_pct",
        "day_rvol",
        "rvol15",
        "rvol30",
        "opening_rvol",
        "price5_pct",
        "price15_pct",
    )
    row = connection.execute(
        f"SELECT {', '.join(nullable_metrics)} "
        "FROM stock_state_current WHERE symbol = 'HPG'"
    ).fetchone()
    assert row == (None,) * len(nullable_metrics)

    defaults = {
        str(row[1]): row[4]
        for row in connection.execute("PRAGMA table_info(stock_state_current)")
    }
    assert all(defaults[column] is None for column in nullable_metrics)


def test_ma_coverage_contract_is_enforced(connection: sqlite3.Connection) -> None:
    _insert_stock_state(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE stock_state_current SET ma10_sessions = 9, ma10 = 28000 "
            "WHERE symbol = 'HPG'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE stock_state_current SET ma200_sessions = 200, ma200 = NULL "
            "WHERE symbol = 'HPG'"
        )


def test_signal_events_allow_multiple_events_per_symbol(
    connection: sqlite3.Connection,
) -> None:
    _insert_signal_event(connection, EVENT_ID_1, "2026-09-18T09:30:00+07:00")
    _insert_signal_event(connection, EVENT_ID_2, "2026-09-18T10:15:00+07:00")
    assert connection.execute(
        "SELECT COUNT(*) FROM signal_events WHERE symbol = 'HPG'"
    ).fetchone()[0] == 2


def test_watching_is_accepted_in_current_and_event_state_checks(
    connection: sqlite3.Connection,
) -> None:
    _insert_stock_state(connection)
    connection.execute(
        "UPDATE stock_state_current "
        "SET signal_state = 'WATCHING', previous_signal_state = 'WATCHING' "
        "WHERE symbol = 'HPG'"
    )
    connection.execute(
        """
        INSERT INTO signal_events (
            event_id, symbol, exchange, trading_date, detected_at,
            previous_state, signal_state, signal_level,
            price_at_signal, change_pct_at_signal, session_type,
            engine_version, config_version, quality_status, metrics_trusted
        ) VALUES (?, 'SSI', 'HOSE', '2026-09-18', ?, 'NORMAL',
                  'WATCHING', 0, 28000, 0.5, 'AM_CONTINUOUS',
                  '2.0.0', 'cfg-20260918-001', 'TRUSTED', 1)
        """,
        (EVENT_ID_3, "2026-09-18T09:20:00+07:00"),
    )
    assert connection.execute(
        "SELECT signal_state, previous_signal_state FROM stock_state_current"
    ).fetchone() == ("WATCHING", "WATCHING")
    assert connection.execute(
        "SELECT previous_state, signal_state FROM signal_events "
        "WHERE event_id = ?",
        (EVENT_ID_3,),
    ).fetchone() == ("NORMAL", "WATCHING")


def test_signal_event_features_enforce_one_to_one_foreign_key(
    connection: sqlite3.Connection,
) -> None:
    _insert_signal_event(connection, EVENT_ID_1, "2026-09-18T09:30:00+07:00")
    connection.execute(
        """
        INSERT INTO signal_event_features (
            signal_event_id, day_rvol_at_signal, engine_version,
            config_version, created_at
        ) VALUES (?, NULL, '2.0.0', 'cfg-20260918-001', ?)
        """,
        (EVENT_ID_1, APPLIED_AT),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO signal_event_features (
                signal_event_id, engine_version, config_version, created_at
            ) VALUES (?, '2.0.0', 'cfg-20260918-001', ?)
            """,
            (EVENT_ID_3, APPLIED_AT),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO signal_event_features (
                signal_event_id, engine_version, config_version, created_at
            ) VALUES (?, '2.0.0', 'cfg-20260918-001', ?)
            """,
            (EVENT_ID_1, APPLIED_AT),
        )


def test_signal_event_requires_uuid4_text_and_semantic_idempotency(
    connection: sqlite3.Connection,
) -> None:
    _insert_signal_event(connection, EVENT_ID_1, "2026-09-18T09:30:00+07:00")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_signal_event(connection, "not-a-uuid", "2026-09-18T10:00:00+07:00")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_signal_event(connection, EVENT_ID_2, "2026-09-18T09:30:00+07:00")

    event_column = next(
        row
        for row in connection.execute("PRAGMA table_info(signal_events)")
        if row[1] == "event_id"
    )
    assert event_column[2] == "TEXT"
    assert event_column[5] == 1


def test_engine_and_config_version_constraints(
    connection: sqlite3.Connection,
) -> None:
    _insert_stock_state(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE stock_state_current SET engine_version = 'v2' "
            "WHERE symbol = 'HPG'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE stock_state_current SET config_version = '' "
            "WHERE symbol = 'HPG'"
        )


def test_universe_cache_is_minimal_and_enforces_active_flag(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        """
        INSERT INTO universe_cache (
            symbol, exchange, active, source_updated_at, synced_at
        ) VALUES ('HPG', 'HOSE', 1, NULL, ?)
        """,
        (APPLIED_AT,),
    )
    assert connection.execute(
        "SELECT symbol, exchange, active, source_updated_at FROM universe_cache"
    ).fetchone() == ("HPG", "HOSE", 1, None)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO universe_cache VALUES ('SSI', 'HOSE', 2, NULL, ?)",
            (APPLIED_AT,),
        )


def test_trading_calendar_key_and_boolean_contract(
    connection: sqlite3.Connection,
) -> None:
    row = ("2026-09-18", "HOSE", 1, "SSI_ACTUAL", "ACTUAL_COMPLETED", APPLIED_AT)
    connection.execute(
        "INSERT INTO trading_calendar VALUES (?, ?, ?, ?, ?, ?)", row
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO trading_calendar VALUES (?, ?, ?, ?, ?, ?)", row
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO trading_calendar VALUES "
            "('2026-09-19', 'HOSE', 2, 'TEST', 'EXPECTED', ?)",
            (APPLIED_AT,),
        )


@pytest.mark.parametrize(
    ("column", "value"),
    (
        ("session_type", "C"),
        ("signal_level", 5),
        ("feed_status", "DELAYED"),
        ("quality_status", "PARTIAL"),
    ),
)
def test_stock_state_enum_and_range_constraints(
    connection: sqlite3.Connection,
    column: str,
    value: object,
) -> None:
    _insert_stock_state(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            f"UPDATE stock_state_current SET {column} = ? WHERE symbol = 'HPG'",
            (value,),
        )


def test_expected_market_indexes_exist(connection: sqlite3.Connection) -> None:
    indexes = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    assert MARKET_INDEXES <= indexes


def test_expected_archive_index_exists(
    archive_connection: sqlite3.Connection,
) -> None:
    indexes = {
        str(row[0])
        for row in archive_connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    assert "idx_bars_5m_archive_date_time" in indexes


def test_timestamp_normalization_requires_timezone() -> None:
    assert canonical_timestamp("2026-09-18T03:30:00Z") == APPLIED_AT
    assert canonical_timestamp(
        datetime(2026, 9, 18, 3, 30, tzinfo=timezone.utc)
    ) == APPLIED_AT
    with pytest.raises(ValueError, match="timezone"):
        canonical_timestamp("2026-09-18T10:30:00")


def test_newer_schema_version_is_rejected() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE engine_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
            "updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO engine_meta VALUES ('storage_schema', '99', ?)",
            (APPLIED_AT,),
        )
        connection.commit()
        with pytest.raises(SchemaVersionError, match="newer"):
            ensure_market_storage_schema(connection, applied_at=APPLIED_AT)
    finally:
        connection.close()
