from __future__ import annotations

import sqlite3

import pytest

from app.market_storage_schema import STORAGE_SCHEMA_VERSION, ensure_market_storage_schema


AT = "2026-09-18T10:30:00+07:00"


def legacy_v2_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE engine_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    connection.executemany(
        "INSERT INTO engine_meta VALUES (?,?,?)",
        (("market_data_contract", "2", AT), ("storage_schema", "2", AT)),
    )
    connection.execute(
        """
        CREATE TABLE stock_state_current (
            symbol TEXT PRIMARY KEY, exchange TEXT NOT NULL, trading_date TEXT NOT NULL,
            last_price REAL,
            session_type TEXT NOT NULL,
            ma10 REAL, ma200 REAL,
            ma10_sessions INTEGER NOT NULL, ma200_sessions INTEGER NOT NULL,
            distance_ma10_pct REAL, distance_ma200_pct REAL,
            above_ma10 INTEGER, above_ma200 INTEGER,
            baseline_sessions_used INTEGER NOT NULL,
            baseline_target_sessions INTEGER NOT NULL,
            baseline_coverage_pct REAL NOT NULL,
            signal_state TEXT NOT NULL, signal_level INTEGER NOT NULL,
            signal_summary_vi TEXT NOT NULL, signal_at TEXT,
            previous_signal_state TEXT, state_changed_at TEXT,
            engine_version TEXT NOT NULL CHECK (
                engine_version GLOB '[0-9]*.[0-9]*.[0-9]*'
                AND engine_version NOT GLOB '*[^0-9.]*'
            ),
            config_version TEXT NOT NULL,
            feed_status TEXT NOT NULL, quality_status TEXT NOT NULL,
            metrics_trusted INTEGER NOT NULL, event_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO stock_state_current (
            symbol,exchange,trading_date,last_price,session_type,
            ma10,ma200,ma10_sessions,ma200_sessions,
            distance_ma10_pct,distance_ma200_pct,above_ma10,above_ma200,
            baseline_sessions_used,baseline_target_sessions,baseline_coverage_pct,
            signal_state,signal_level,signal_summary_vi,signal_at,
            previous_signal_state,state_changed_at,engine_version,config_version,
            feed_status,quality_status,metrics_trusted,event_at,updated_at
        ) VALUES (
            'FPT','HOSE','2026-09-18',74300,'AM_CONTINUOUS',
            NULL,NULL,0,0,NULL,NULL,NULL,NULL,10,10,100,
            'NORMAL',0,'Bình thường',NULL,NULL,NULL,'2.0.0','legacy',
            'LIVE','TRUSTED',1,?,?
        )
        """,
        (AT, AT),
    )
    connection.execute(
        """
        CREATE TABLE signal_events (
            event_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, exchange TEXT NOT NULL,
            trading_date TEXT NOT NULL, detected_at TEXT NOT NULL,
            previous_state TEXT, signal_state TEXT NOT NULL, signal_level INTEGER NOT NULL,
            price_at_signal REAL, change_pct_at_signal REAL, session_type TEXT NOT NULL,
            engine_version TEXT NOT NULL CHECK (engine_version NOT GLOB '*[^0-9.]*'),
            config_version TEXT NOT NULL, quality_status TEXT NOT NULL,
            metrics_trusted INTEGER NOT NULL
        )
        """
    )
    event_id = "11111111-1111-4111-8111-111111111111"
    connection.execute(
        "INSERT INTO signal_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, "FPT", "HOSE", "2026-09-18", AT, None, "NORMAL", 0,
         74300, 0.0, "AM_CONTINUOUS", "2.0.0", "legacy", "TRUSTED", 1),
    )
    connection.execute(
        """
        CREATE TABLE signal_event_features (
            signal_event_id TEXT PRIMARY KEY, engine_version TEXT NOT NULL,
            config_version TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(signal_event_id) REFERENCES signal_events(event_id)
        )
        """
    )
    connection.execute(
        "INSERT INTO signal_event_features VALUES (?,?,?,?)",
        (event_id, "2.0.0", "legacy", AT),
    )
    connection.commit()
    return connection


def test_v2_to_signal01_migration_is_additive_and_preserves_rows() -> None:
    connection = legacy_v2_connection()
    ensure_market_storage_schema(connection, applied_at=AT)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(stock_state_current)")}
    assert {
        "signal_direction", "reason_codes_json", "ato_volume", "ato_rvol",
        "ato_baseline_sessions_used", "ato_baseline_quality", "atc_volume",
        "atc_rvol", "atc_baseline_sessions_used", "atc_baseline_quality",
        "atc_price_impact_pct",
    } <= columns
    row = connection.execute(
        "SELECT symbol,last_price,engine_version,signal_direction,reason_codes_json "
        "FROM stock_state_current"
    ).fetchone()
    assert row == ("FPT", 74300, "2.0.0", "NEUTRAL", "[]")
    assert dict(connection.execute("SELECT key,value FROM engine_meta"))["storage_schema"] == str(STORAGE_SCHEMA_VERSION)

    connection.execute("UPDATE stock_state_current SET engine_version='2.0.0-beta'")
    connection.execute("UPDATE stock_state_current SET engine_version='2.0.0'")
    for malformed in ("v2", "2.0", "2.a.0", "2.0.0-"):
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE stock_state_current SET engine_version=? WHERE symbol='FPT'",
                (malformed,),
            )
    assert connection.execute("SELECT COUNT(*) FROM stock_state_current").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM signal_events").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM signal_event_features").fetchone()[0] == 1
    connection.execute("UPDATE signal_events SET engine_version='2.0.0-beta'")
    connection.execute("UPDATE signal_event_features SET engine_version='2.0.0-beta'")
    connection.close()
