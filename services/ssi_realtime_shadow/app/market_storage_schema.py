"""Additive SQLite schema foundation for the CCC V2 market-data contract.

This module deliberately has no runtime wiring and never opens a database path.
Callers must opt in by passing an explicit SQLite connection.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo


MARKET_DATA_CONTRACT_VERSION = 2
STORAGE_SCHEMA_VERSION = 3
ARCHIVE_STORAGE_SCHEMA_VERSION = 1
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class SchemaVersionError(RuntimeError):
    """Raised when a database version is invalid or newer than this code."""


_ENGINE_META_SQL = """
CREATE TABLE IF NOT EXISTS engine_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


_MARKET_V1_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS daily_bars (
        symbol TEXT NOT NULL,
        trading_date TEXT NOT NULL,
        exchange TEXT NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        volume INTEGER NOT NULL CHECK (volume >= 0),
        value REAL CHECK (value IS NULL OR value >= 0),
        source TEXT NOT NULL,
        quality_status TEXT NOT NULL CHECK (
            quality_status IN ('TRUSTED', 'DEGRADED', 'UNAVAILABLE')
        ),
        finalized_at TEXT NOT NULL,
        PRIMARY KEY (symbol, trading_date),
        CHECK (symbol = UPPER(symbol) AND length(symbol) BETWEEN 2 AND 12),
        CHECK (high >= low AND open BETWEEN low AND high AND close BETWEEN low AND high)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_daily_bars_date_exchange
        ON daily_bars(trading_date, exchange, symbol)
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_state_current (
        symbol TEXT PRIMARY KEY,
        exchange TEXT NOT NULL,
        trading_date TEXT NOT NULL,

        last_price REAL,
        ref_price REAL,
        ceiling_price REAL,
        floor_price REAL,
        open_price REAL,
        high_price REAL,
        low_price REAL,
        change_value REAL,
        change_pct REAL,
        total_volume INTEGER CHECK (total_volume IS NULL OR total_volume >= 0),
        total_value REAL CHECK (total_value IS NULL OR total_value >= 0),
        bid_price1 REAL,
        bid_volume1 INTEGER CHECK (bid_volume1 IS NULL OR bid_volume1 >= 0),
        ask_price1 REAL,
        ask_volume1 INTEGER CHECK (ask_volume1 IS NULL OR ask_volume1 >= 0),

        session_type TEXT NOT NULL CHECK (
            session_type IN (
                'OPEN_AUCTION', 'AM_CONTINUOUS', 'LUNCH_BREAK',
                'PM_CONTINUOUS', 'CLOSE_AUCTION', 'POST_TRADING', 'CLOSED'
            )
        ),
        session_id TEXT,
        session_started_at TEXT,
        session_ends_at TEXT,
        elapsed_valid_minutes INTEGER CHECK (
            elapsed_valid_minutes IS NULL OR elapsed_valid_minutes >= 0
        ),

        ma10 REAL,
        ma200 REAL,
        ma10_sessions INTEGER NOT NULL CHECK (ma10_sessions BETWEEN 0 AND 10),
        ma200_sessions INTEGER NOT NULL CHECK (ma200_sessions BETWEEN 0 AND 200),
        distance_ma10_pct REAL,
        distance_ma200_pct REAL,
        above_ma10 INTEGER CHECK (above_ma10 IS NULL OR above_ma10 IN (0, 1)),
        above_ma200 INTEGER CHECK (above_ma200 IS NULL OR above_ma200 IN (0, 1)),

        cumulative_volume INTEGER CHECK (
            cumulative_volume IS NULL OR cumulative_volume >= 0
        ),
        day_rvol REAL CHECK (day_rvol IS NULL OR day_rvol >= 0),
        volume_15 INTEGER CHECK (volume_15 IS NULL OR volume_15 >= 0),
        avg_volume_15 REAL CHECK (avg_volume_15 IS NULL OR avg_volume_15 >= 0),
        rvol15 REAL CHECK (rvol15 IS NULL OR rvol15 >= 0),
        volume_30 INTEGER CHECK (volume_30 IS NULL OR volume_30 >= 0),
        avg_volume_30 REAL CHECK (avg_volume_30 IS NULL OR avg_volume_30 >= 0),
        rvol30 REAL CHECK (rvol30 IS NULL OR rvol30 >= 0),
        opening_volume INTEGER CHECK (opening_volume IS NULL OR opening_volume >= 0),
        avg_opening_volume REAL CHECK (
            avg_opening_volume IS NULL OR avg_opening_volume >= 0
        ),
        opening_rvol REAL CHECK (opening_rvol IS NULL OR opening_rvol >= 0),
        baseline_sessions_used INTEGER NOT NULL CHECK (
            baseline_sessions_used BETWEEN 0 AND 10
        ),
        baseline_target_sessions INTEGER NOT NULL CHECK (
            baseline_target_sessions = 10
        ),
        baseline_coverage_pct REAL NOT NULL CHECK (
            baseline_coverage_pct BETWEEN 0 AND 100
        ),

        price5_pct REAL,
        price15_pct REAL,
        breakout_state TEXT,
        trigger_price REAL,
        trigger_at TEXT,

        signal_state TEXT NOT NULL CHECK (
            signal_state IN (
                'NORMAL', 'WATCHING', 'FLOW_APPEARING', 'FLOW_PRICE_CONFIRMED',
                'MOMENTUM_MAINTAINED', 'MOMENTUM_WEAKENING', 'SELLING_PRESSURE'
            )
        ),
        signal_level INTEGER NOT NULL CHECK (signal_level BETWEEN 0 AND 4),
        signal_direction TEXT NOT NULL DEFAULT 'NEUTRAL' CHECK (
            signal_direction IN ('NEUTRAL', 'BULLISH', 'BEARISH')
        ),
        reason_codes_json TEXT NOT NULL DEFAULT '[]' CHECK (
            json_valid(reason_codes_json) AND json_type(reason_codes_json) = 'array'
        ),
        signal_summary_vi TEXT NOT NULL,
        signal_at TEXT,
        previous_signal_state TEXT CHECK (
            previous_signal_state IS NULL OR previous_signal_state IN (
                'NORMAL', 'WATCHING', 'FLOW_APPEARING', 'FLOW_PRICE_CONFIRMED',
                'MOMENTUM_MAINTAINED', 'MOMENTUM_WEAKENING', 'SELLING_PRESSURE'
            )
        ),
        state_changed_at TEXT,
        engine_version TEXT NOT NULL CHECK (
            engine_version GLOB '[0-9]*.[0-9]*.[0-9]*'
            AND (
                (engine_version NOT GLOB '*[^0-9.]*'
                 AND length(engine_version)-length(replace(engine_version,'.',''))=2)
                OR
                (instr(engine_version, '-') > 0
                 AND substr(engine_version, 1, instr(engine_version, '-')-1)
                     NOT GLOB '*[^0-9.]*'
                 AND length(substr(engine_version,1,instr(engine_version,'-')-1))
                     - length(replace(substr(engine_version,1,instr(engine_version,'-')-1),'.',''))=2
                 AND substr(engine_version, instr(engine_version, '-')+1) <> ''
                 AND substr(engine_version, instr(engine_version, '-')+1)
                     NOT GLOB '*[^0-9A-Za-z.-]*')
            )
        ),
        config_version TEXT NOT NULL CHECK (length(trim(config_version)) > 0),

        ato_volume INTEGER CHECK (ato_volume IS NULL OR ato_volume >= 0),
        ato_avg_volume_10 REAL CHECK (
            ato_avg_volume_10 IS NULL OR ato_avg_volume_10 >= 0
        ),
        ato_rvol REAL CHECK (ato_rvol IS NULL OR ato_rvol >= 0),
        ato_baseline_sessions_used INTEGER NOT NULL DEFAULT 0 CHECK (
            ato_baseline_sessions_used BETWEEN 0 AND 10
        ),
        ato_baseline_quality TEXT NOT NULL DEFAULT 'UNAVAILABLE' CHECK (
            ato_baseline_quality IN ('PROVEN','MIXED','INFERRED_BOUNDARY','UNAVAILABLE')
        ),
        atc_volume INTEGER CHECK (atc_volume IS NULL OR atc_volume >= 0),
        atc_avg_volume_10 REAL CHECK (
            atc_avg_volume_10 IS NULL OR atc_avg_volume_10 >= 0
        ),
        atc_rvol REAL CHECK (atc_rvol IS NULL OR atc_rvol >= 0),
        atc_baseline_sessions_used INTEGER NOT NULL DEFAULT 0 CHECK (
            atc_baseline_sessions_used BETWEEN 0 AND 10
        ),
        atc_baseline_quality TEXT NOT NULL DEFAULT 'UNAVAILABLE' CHECK (
            atc_baseline_quality IN ('PROVEN','MIXED','INFERRED_BOUNDARY','UNAVAILABLE')
        ),
        atc_price_impact_pct REAL,

        feed_status TEXT NOT NULL CHECK (
            feed_status IN ('LIVE', 'STALE', 'DISCONNECTED', 'EXPECTED_IDLE')
        ),
        quality_status TEXT NOT NULL CHECK (
            quality_status IN ('TRUSTED', 'DEGRADED', 'UNAVAILABLE')
        ),
        metrics_trusted INTEGER NOT NULL CHECK (metrics_trusted IN (0, 1)),
        event_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,

        CHECK (symbol = UPPER(symbol) AND length(symbol) BETWEEN 2 AND 12),
        CHECK (
            (ma10_sessions = 10 AND ma10 IS NOT NULL)
            OR (ma10_sessions < 10 AND ma10 IS NULL)
        ),
        CHECK (
            (ma200_sessions = 200 AND ma200 IS NOT NULL)
            OR (ma200_sessions < 200 AND ma200 IS NULL)
        ),
        CHECK (
            ma10 IS NOT NULL
            OR (distance_ma10_pct IS NULL AND above_ma10 IS NULL)
        ),
        CHECK (
            ma200 IS NOT NULL
            OR (distance_ma200_pct IS NULL AND above_ma200 IS NULL)
        )
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_stock_state_signal
        ON stock_state_current(signal_state, signal_level DESC, signal_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_stock_state_exchange_updated
        ON stock_state_current(exchange, updated_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_stock_state_updated
        ON stock_state_current(updated_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS signal_events (
        event_id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        exchange TEXT NOT NULL,
        trading_date TEXT NOT NULL,
        detected_at TEXT NOT NULL,
        previous_state TEXT CHECK (
            previous_state IS NULL OR previous_state IN (
                'NORMAL', 'WATCHING', 'FLOW_APPEARING', 'FLOW_PRICE_CONFIRMED',
                'MOMENTUM_MAINTAINED', 'MOMENTUM_WEAKENING', 'SELLING_PRESSURE'
            )
        ),
        signal_state TEXT NOT NULL CHECK (
            signal_state IN (
                'NORMAL', 'WATCHING', 'FLOW_APPEARING', 'FLOW_PRICE_CONFIRMED',
                'MOMENTUM_MAINTAINED', 'MOMENTUM_WEAKENING', 'SELLING_PRESSURE'
            )
        ),
        signal_level INTEGER NOT NULL CHECK (signal_level BETWEEN 0 AND 4),
        price_at_signal REAL,
        change_pct_at_signal REAL,
        session_type TEXT NOT NULL CHECK (
            session_type IN (
                'OPEN_AUCTION', 'AM_CONTINUOUS', 'LUNCH_BREAK',
                'PM_CONTINUOUS', 'CLOSE_AUCTION', 'POST_TRADING', 'CLOSED'
            )
        ),
        engine_version TEXT NOT NULL CHECK (
            engine_version GLOB '[0-9]*.[0-9]*.[0-9]*'
            AND (
                (engine_version NOT GLOB '*[^0-9.]*'
                 AND length(engine_version)-length(replace(engine_version,'.',''))=2)
                OR
                (instr(engine_version, '-') > 0
                 AND substr(engine_version, 1, instr(engine_version, '-')-1)
                     NOT GLOB '*[^0-9.]*'
                 AND length(substr(engine_version,1,instr(engine_version,'-')-1))
                     - length(replace(substr(engine_version,1,instr(engine_version,'-')-1),'.',''))=2
                 AND substr(engine_version, instr(engine_version, '-')+1) <> ''
                 AND substr(engine_version, instr(engine_version, '-')+1)
                     NOT GLOB '*[^0-9A-Za-z.-]*')
            )
        ),
        config_version TEXT NOT NULL CHECK (length(trim(config_version)) > 0),
        quality_status TEXT NOT NULL CHECK (
            quality_status IN ('TRUSTED', 'DEGRADED', 'UNAVAILABLE')
        ),
        metrics_trusted INTEGER NOT NULL CHECK (metrics_trusted IN (0, 1)),

        close_price REAL,
        close_change_from_signal_pct REAL,
        max_price_after_signal REAL,
        max_gain_after_signal_pct REAL,
        min_price_after_signal REAL,
        max_drawdown_after_signal_pct REAL,
        outcome_30m_pct REAL,
        outcome_eod_pct REAL,
        outcome_t1_pct REAL,
        outcome_t3_pct REAL,

        CHECK (symbol = UPPER(symbol) AND length(symbol) BETWEEN 2 AND 12),
        CHECK (
            length(event_id) = 36
            AND substr(event_id, 9, 1) = '-'
            AND substr(event_id, 14, 1) = '-'
            AND substr(event_id, 15, 1) = '4'
            AND substr(event_id, 19, 1) = '-'
            AND substr(event_id, 20, 1) GLOB '[89ab]'
            AND substr(event_id, 24, 1) = '-'
            AND event_id = lower(event_id)
            AND replace(event_id, '-', '') NOT GLOB '*[^0-9a-f]*'
        )
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_signal_events_symbol_detected
        ON signal_events(symbol, detected_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_signal_events_detected
        ON signal_events(detected_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_signal_events_journal
        ON signal_events(trading_date, signal_state, detected_at DESC)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_events_idempotency
        ON signal_events(
            symbol, detected_at, signal_state, engine_version, config_version
        )
    """,
    """
    CREATE TABLE IF NOT EXISTS signal_event_features (
        signal_event_id TEXT PRIMARY KEY,
        day_rvol_at_signal REAL CHECK (
            day_rvol_at_signal IS NULL OR day_rvol_at_signal >= 0
        ),
        rvol15_at_signal REAL CHECK (
            rvol15_at_signal IS NULL OR rvol15_at_signal >= 0
        ),
        rvol30_at_signal REAL CHECK (
            rvol30_at_signal IS NULL OR rvol30_at_signal >= 0
        ),
        price5_at_signal REAL,
        price15_at_signal REAL,
        ma10_at_signal REAL,
        ma200_at_signal REAL,
        distance_ma10_at_signal REAL,
        distance_ma200_at_signal REAL,
        baseline_sessions_used INTEGER CHECK (
            baseline_sessions_used IS NULL
            OR baseline_sessions_used BETWEEN 0 AND 10
        ),
        breakout_state TEXT,
        internal_reason_code TEXT,
        engine_version TEXT NOT NULL CHECK (
            engine_version GLOB '[0-9]*.[0-9]*.[0-9]*'
            AND (
                (engine_version NOT GLOB '*[^0-9.]*'
                 AND length(engine_version)-length(replace(engine_version,'.',''))=2)
                OR
                (instr(engine_version, '-') > 0
                 AND substr(engine_version, 1, instr(engine_version, '-')-1)
                     NOT GLOB '*[^0-9.]*'
                 AND length(substr(engine_version,1,instr(engine_version,'-')-1))
                     - length(replace(substr(engine_version,1,instr(engine_version,'-')-1),'.',''))=2
                 AND substr(engine_version, instr(engine_version, '-')+1) <> ''
                 AND substr(engine_version, instr(engine_version, '-')+1)
                     NOT GLOB '*[^0-9A-Za-z.-]*')
            )
        ),
        config_version TEXT NOT NULL CHECK (length(trim(config_version)) > 0),
        created_at TEXT NOT NULL,
        FOREIGN KEY (signal_event_id)
            REFERENCES signal_events(event_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS market_index_current (
        index_code TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        last_value REAL,
        reference_value REAL,
        change_value REAL,
        change_pct REAL,
        session_type TEXT NOT NULL CHECK (
            session_type IN (
                'OPEN_AUCTION', 'AM_CONTINUOUS', 'LUNCH_BREAK',
                'PM_CONTINUOUS', 'CLOSE_AUCTION', 'POST_TRADING', 'CLOSED'
            )
        ),
        source TEXT NOT NULL,
        event_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        feed_status TEXT NOT NULL CHECK (
            feed_status IN ('LIVE', 'STALE', 'DISCONNECTED', 'EXPECTED_IDLE')
        ),
        quality_status TEXT NOT NULL CHECK (
            quality_status IN ('TRUSTED', 'DEGRADED', 'UNAVAILABLE')
        ),
        CHECK (index_code = UPPER(index_code) AND length(index_code) >= 2)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS universe_cache (
        symbol TEXT PRIMARY KEY,
        exchange TEXT NOT NULL CHECK (exchange IN ('HOSE', 'HNX', 'UPCOM')),
        active INTEGER NOT NULL CHECK (active IN (0, 1)),
        source_updated_at TEXT,
        synced_at TEXT NOT NULL,
        CHECK (symbol = UPPER(symbol) AND length(symbol) BETWEEN 2 AND 12)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_universe_cache_active_exchange
        ON universe_cache(active, exchange, symbol)
    """,
    """
    CREATE TABLE IF NOT EXISTS trading_calendar (
        trading_date TEXT NOT NULL,
        exchange TEXT NOT NULL CHECK (exchange IN ('HOSE', 'HNX', 'UPCOM')),
        is_trading_day INTEGER NOT NULL CHECK (is_trading_day IN (0, 1)),
        source TEXT NOT NULL CHECK (length(trim(source)) > 0),
        status TEXT NOT NULL CHECK (length(trim(status)) > 0),
        updated_at TEXT NOT NULL,
        PRIMARY KEY (trading_date, exchange)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_trading_calendar_exchange_day
        ON trading_calendar(exchange, is_trading_day, trading_date)
    """,
)


_MARKET_V2_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS auction_session_history (
        symbol TEXT NOT NULL,
        trading_date TEXT NOT NULL,
        exchange TEXT NOT NULL CHECK (exchange IN ('HOSE', 'HNX', 'UPCOM')),
        auction_type TEXT NOT NULL CHECK (
            auction_type IN ('OPEN_AUCTION', 'CLOSE_AUCTION')
        ),
        auction_price REAL NOT NULL CHECK (auction_price > 0),
        pre_auction_price REAL CHECK (
            pre_auction_price IS NULL OR pre_auction_price > 0
        ),
        auction_volume INTEGER NOT NULL CHECK (auction_volume >= 0),
        provider_session TEXT,
        source TEXT NOT NULL CHECK (source IN ('SSI_REST', 'SSI_STREAM')),
        quality TEXT NOT NULL CHECK (
            quality IN ('PROVEN', 'INFERRED_BOUNDARY')
        ),
        proof_code TEXT,
        finalized INTEGER NOT NULL CHECK (finalized = 1),
        previous_source TEXT CHECK (
            previous_source IS NULL OR previous_source IN ('SSI_REST', 'SSI_STREAM')
        ),
        previous_quality TEXT CHECK (
            previous_quality IS NULL
            OR previous_quality IN ('PROVEN', 'INFERRED_BOUNDARY')
        ),
        previous_proof_code TEXT,
        superseded_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (symbol, trading_date, auction_type),
        CHECK (symbol = UPPER(symbol) AND length(symbol) BETWEEN 2 AND 12),
        CHECK (
            (quality = 'INFERRED_BOUNDARY'
             AND source = 'SSI_REST'
             AND proof_code = 'CROSS_PROVIDER_BOUNDARY_CONFIRMED_V1')
            OR
            (quality = 'PROVEN' AND source = 'SSI_STREAM')
        ),
        CHECK (
            (previous_quality IS NULL
             AND previous_source IS NULL
             AND previous_proof_code IS NULL
             AND superseded_at IS NULL)
            OR
            (quality = 'PROVEN'
             AND previous_quality = 'INFERRED_BOUNDARY'
             AND previous_source = 'SSI_REST'
             AND superseded_at IS NOT NULL)
        )
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auction_history_date_type
        ON auction_session_history(trading_date, auction_type, exchange, symbol)
    """,
)


def _apply_market_v3(connection: sqlite3.Connection) -> None:
    """Add SIGNAL-01 fields and prerelease validation while preserving rows."""
    def table_exists(name: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None

    def copy_common(source: str, target: str) -> None:
        source_columns = [
            str(row[1]) for row in connection.execute(f"PRAGMA table_info({source})")
        ]
        target_columns = {
            str(row[1]) for row in connection.execute(f"PRAGMA table_info({target})")
        }
        names = ", ".join(name for name in source_columns if name in target_columns)
        connection.execute(f"INSERT INTO {target} ({names}) SELECT {names} FROM {source}")

    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(stock_state_current)")
    }
    if "signal_direction" not in columns:
        old_name = "stock_state_current_v2_migration"
        connection.execute(f"ALTER TABLE stock_state_current RENAME TO {old_name}")
        connection.execute(_MARKET_V1_STATEMENTS[2])
        copy_common(old_name, "stock_state_current")
        connection.execute(
            "UPDATE stock_state_current SET signal_direction = CASE "
            "WHEN signal_state IN ('FLOW_APPEARING','FLOW_PRICE_CONFIRMED','MOMENTUM_MAINTAINED') THEN 'BULLISH' "
            "WHEN signal_state='SELLING_PRESSURE' THEN 'BEARISH' ELSE 'NEUTRAL' END"
        )
        connection.execute(f"DROP TABLE {old_name}")
        for statement in _MARKET_V1_STATEMENTS[3:6]:
            connection.execute(statement)

    if table_exists("signal_events"):
        has_features = table_exists("signal_event_features")
        if has_features:
            connection.execute(
                "ALTER TABLE signal_event_features RENAME TO signal_event_features_v2_migration"
            )
        connection.execute("ALTER TABLE signal_events RENAME TO signal_events_v2_migration")
        connection.execute(_MARKET_V1_STATEMENTS[6])
        copy_common("signal_events_v2_migration", "signal_events")
        if has_features:
            connection.execute(_MARKET_V1_STATEMENTS[11])
            copy_common("signal_event_features_v2_migration", "signal_event_features")
            connection.execute("DROP TABLE signal_event_features_v2_migration")
        connection.execute("DROP TABLE signal_events_v2_migration")
        for statement in _MARKET_V1_STATEMENTS[7:11]:
            connection.execute(statement)


_ARCHIVE_V1_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS bars_5m_archive (
        symbol TEXT NOT NULL,
        exchange TEXT NOT NULL,
        trading_date TEXT NOT NULL,
        bar_time TEXT NOT NULL,
        open REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        close REAL NOT NULL,
        volume INTEGER NOT NULL CHECK (volume >= 0),
        value REAL CHECK (value IS NULL OR value >= 0),
        quality_status TEXT NOT NULL CHECK (
            quality_status IN ('TRUSTED', 'DEGRADED', 'UNAVAILABLE')
        ),
        source TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (symbol, trading_date, bar_time),
        CHECK (symbol = UPPER(symbol) AND length(symbol) BETWEEN 2 AND 12),
        CHECK (high >= low AND open BETWEEN low AND high AND close BETWEEN low AND high)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bars_5m_archive_date_time
        ON bars_5m_archive(trading_date, bar_time, exchange, symbol)
    """,
)


def canonical_timestamp(value: str | datetime | None = None) -> str:
    """Return an ISO-8601 timestamp normalized to Asia/Ho_Chi_Minh.

    Naive datetimes are rejected because the contract never infers a timezone.
    """
    if value is None:
        moment = datetime.now(VN_TZ)
    elif isinstance(value, datetime):
        moment = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            moment = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("timestamp must be ISO 8601 with timezone") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return moment.astimezone(VN_TZ).isoformat(timespec="seconds")


def _read_version(connection: sqlite3.Connection, key: str) -> int | None:
    row = connection.execute(
        "SELECT value FROM engine_meta WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return None
    try:
        value = int(row[0])
    except (TypeError, ValueError) as exc:
        raise SchemaVersionError(f"Invalid {key} version: {row[0]!r}") from exc
    if value < 0:
        raise SchemaVersionError(f"Invalid {key} version: {value}")
    return value


def _advance_version(
    connection: sqlite3.Connection,
    *,
    key: str,
    current: int | None,
    target: int,
    updated_at: str,
) -> None:
    if current is None:
        connection.execute(
            "INSERT INTO engine_meta(key, value, updated_at) VALUES (?, ?, ?)",
            (key, str(target), updated_at),
        )
    elif current < target:
        connection.execute(
            "UPDATE engine_meta SET value = ?, updated_at = ? WHERE key = ?",
            (str(target), updated_at, key),
        )


def ensure_market_storage_schema(
    connection: sqlite3.Connection,
    *,
    applied_at: str | datetime | None = None,
) -> None:
    """Apply the additive versioned storage schema to an explicit SQLite connection.

    The caller must invoke this outside an active transaction. Existing compatible
    tables and rows are left untouched. A database newer than this module is
    rejected rather than silently downgraded.
    """
    if connection.in_transaction:
        raise RuntimeError("ensure_market_storage_schema requires no active transaction")

    connection.execute("PRAGMA foreign_keys = ON")
    if int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) != 1:
        raise RuntimeError("SQLite foreign key enforcement could not be enabled")

    timestamp = canonical_timestamp(applied_at)
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(_ENGINE_META_SQL)
        current_contract = _read_version(connection, "market_data_contract")
        current_schema = _read_version(connection, "storage_schema")
        if (
            current_contract is not None
            and current_contract > MARKET_DATA_CONTRACT_VERSION
        ):
            raise SchemaVersionError(
                "Database market-data contract is newer than this code: "
                f"{current_contract} > {MARKET_DATA_CONTRACT_VERSION}"
            )
        if current_schema is not None and current_schema > STORAGE_SCHEMA_VERSION:
            raise SchemaVersionError(
                "Database storage schema is newer than this code: "
                f"{current_schema} > {STORAGE_SCHEMA_VERSION}"
            )

        if current_schema is None or current_schema < 1:
            for statement in _MARKET_V1_STATEMENTS:
                connection.execute(statement)
        if current_schema is None or current_schema < 2:
            for statement in _MARKET_V2_STATEMENTS:
                connection.execute(statement)
        if current_schema is not None and current_schema < 3:
            _apply_market_v3(connection)

        _advance_version(
            connection,
            key="market_data_contract",
            current=current_contract,
            target=MARKET_DATA_CONTRACT_VERSION,
            updated_at=timestamp,
        )
        _advance_version(
            connection,
            key="storage_schema",
            current=current_schema,
            target=STORAGE_SCHEMA_VERSION,
            updated_at=timestamp,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def ensure_5m_archive_schema(connection: sqlite3.Connection) -> None:
    """Apply the isolated 5-minute archive schema to an explicit connection.

    The archive database intentionally contains no application metadata table.
    Its schema version is held in SQLite ``PRAGMA user_version``.
    """
    if connection.in_transaction:
        raise RuntimeError("ensure_5m_archive_schema requires no active transaction")

    current_schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_schema > ARCHIVE_STORAGE_SCHEMA_VERSION:
        raise SchemaVersionError(
            "5-minute archive schema is newer than this code: "
            f"{current_schema} > {ARCHIVE_STORAGE_SCHEMA_VERSION}"
        )

    connection.execute("BEGIN IMMEDIATE")
    try:
        if current_schema < 1:
            for statement in _ARCHIVE_V1_STATEMENTS:
                connection.execute(statement)
        connection.execute(
            f"PRAGMA user_version = {ARCHIVE_STORAGE_SCHEMA_VERSION}"
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
