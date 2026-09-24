from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from app import legacy_ssi_history_import as import_module
from app.canonical_market_store import CanonicalMarketStore, MinuteBar
from app.legacy_ssi_history_import import import_legacy_history


LEGACY_SCHEMA = """
CREATE TABLE minute_bars (
    trading_date TEXT NOT NULL,
    minute TEXT NOT NULL,
    symbol TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    last_total_volume INTEGER,
    event_count INTEGER,
    is_partial INTEGER,
    exchange TEXT,
    quality_status TEXT NOT NULL,
    has_gap INTEGER,
    gap_from TEXT,
    gap_to TEXT,
    data_source TEXT NOT NULL,
    provider_time TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trading_date, minute, symbol)
);
CREATE TABLE historical_bootstrap_checkpoints (
    symbol TEXT NOT NULL,
    from_date TEXT NOT NULL,
    to_date TEXT NOT NULL,
    resolution INTEGER NOT NULL,
    status TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT NOT NULL,
    completed_at TEXT,
    error TEXT,
    PRIMARY KEY (symbol, from_date, to_date, resolution)
);
"""


def _create_legacy(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(LEGACY_SCHEMA)
    return connection


def _insert_minute(
    connection: sqlite3.Connection,
    *,
    symbol: str = "AAA",
    trading_date: str = "2026-01-05",
    minute: str = "09:15",
    open_price: float | None = 10,
    total_volume: int | None = 1234,
    source: str = "SSI_REST",
    quality: str = "TRUSTED",
) -> None:
    connection.execute(
        """INSERT INTO minute_bars(
               trading_date, minute, symbol, open, high, low, close, volume,
               last_total_volume, event_count, is_partial, exchange,
               quality_status, has_gap, gap_from, gap_to, data_source,
               provider_time, updated_at
           ) VALUES(?,?,?,?,?,?,?,?,?,7,0,'HOSE',?,0,NULL,NULL,?,?,?)""",
        (
            trading_date,
            minute,
            symbol,
            open_price,
            11,
            9,
            10.5,
            100,
            total_volume,
            quality,
            source,
            f"{minute}:42",
            "2026-01-05T02:16:00+00:00",
        ),
    )


def _insert_checkpoint(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    status: str,
    from_date: str = "2026-01-01",
    to_date: str = "2026-01-31",
) -> None:
    connection.execute(
        """INSERT INTO historical_bootstrap_checkpoints(
               symbol,from_date,to_date,resolution,status,row_count,
               attempt_count,last_attempt_at,completed_at,error
           ) VALUES(?,?,?,1,?,1,1,'2026-01-31T00:00:00Z',NULL,NULL)""",
        (symbol, from_date, to_date, status),
    )


def _read_one(path: Path, sql: str) -> sqlite3.Row:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(sql).fetchone()
        assert row is not None
        return row
    finally:
        connection.close()


def test_legacy_minute_maps_values_and_leaves_new_fields_null(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    legacy = _create_legacy(source)
    _insert_minute(legacy)
    _insert_checkpoint(legacy, symbol="AAA", status="COMPLETED")
    legacy.commit()
    legacy.close()

    summary = import_legacy_history(source, db_dir=tmp_path / "canonical")

    assert summary.rows_read == 1
    assert summary.rows_upserted == 1
    assert summary.dates == 1
    assert summary.symbols == 1
    row = _read_one(
        tmp_path / "canonical" / "ccc_market_2026.db",
        "SELECT * FROM minute_bars",
    )
    assert row["symbol"] == "AAA"
    assert row["trading_date"] == "2026-01-05"
    assert row["minute"] == "09:15"
    assert row["exchange"] == "HOSE"
    assert tuple(row[name] for name in ("open", "high", "low", "close")) == (
        10,
        11,
        9,
        10.5,
    )
    assert row["volume"] == 100
    assert row["provider_total_volume"] == 1234
    assert row["provider_time"] == "09:15:42"
    assert row["source"] == "SSI_REST"
    assert row["quality_status"] == "TRUSTED"
    assert row["is_finalized"] == 1
    assert row["value"] is None
    assert row["provider_session"] is None
    assert row["first_event_at"] is None
    assert row["last_event_at"] is None


def test_import_reruns_never_overwrite_canonical_minute_or_session_proof(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.db"
    legacy = _create_legacy(source)
    _insert_minute(legacy, open_price=None, total_volume=None)
    _insert_checkpoint(legacy, symbol="AAA", status="COMPLETED")
    legacy.commit()
    legacy.close()
    target_dir = tmp_path / "canonical"
    with CanonicalMarketStore(target_dir) as store:
        store.upsert_minute_bars(
            [
                MinuteBar(
                    "AAA",
                    "2026-01-05",
                    "09:15",
                    open=99,
                    high=101,
                    low=98,
                    close=100,
                    volume=999,
                    value=5000,
                    provider_total_volume=999,
                    provider_session="CONTINUOUS",
                    provider_time="fresh-provider-time",
                    first_event_at="first",
                    last_event_at="last",
                    source="SSI_REST_REPAIR",
                    quality_status="FRESH_TRUSTED",
                    is_finalized=0,
                    updated_at="2026-09-25T01:02:03+00:00",
                )
            ]
        )
        store.mark_rest_sessions_completed(
            mode="minute",
            symbol="AAA",
            resolution=1,
            rows_by_date={"2026-01-05": 777},
        )

    first = import_legacy_history(source, db_dir=target_dir)
    second = import_legacy_history(source, db_dir=target_dir)
    third = import_legacy_history(source, db_dir=target_dir)

    assert first.rows_upserted == second.rows_upserted == third.rows_upserted == 0
    row = _read_one(
        target_dir / "ccc_market_2026.db",
        "SELECT *, (SELECT COUNT(*) FROM minute_bars) AS total FROM minute_bars",
    )
    assert row["total"] == 1
    assert row["open"] == 99
    assert row["high"] == 101
    assert row["low"] == 98
    assert row["close"] == 100
    assert row["volume"] == 999
    assert row["provider_total_volume"] == 999
    assert row["value"] == 5000
    assert row["provider_session"] == "CONTINUOUS"
    assert row["provider_time"] == "fresh-provider-time"
    assert row["first_event_at"] == "first"
    assert row["last_event_at"] == "last"
    assert row["source"] == "SSI_REST_REPAIR"
    assert row["quality_status"] == "FRESH_TRUSTED"
    assert row["is_finalized"] == 0
    assert row["updated_at"] == "2026-09-25T01:02:03+00:00"
    proof = _read_one(
        target_dir / "ccc_market_2026.db",
        "SELECT *, (SELECT COUNT(*) FROM rest_session_status) AS total "
        "FROM rest_session_status",
    )
    assert proof["total"] == 1
    assert proof["rows_received"] == 777


def test_only_completed_ranges_create_observed_per_date_proof(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.db"
    legacy = _create_legacy(source)
    _insert_minute(legacy, symbol="GOOD", trading_date="2026-01-05")
    _insert_minute(legacy, symbol="FAILED", trading_date="2026-01-05")
    _insert_minute(legacy, symbol="EMPTY", trading_date="2026-01-05")
    _insert_checkpoint(legacy, symbol="GOOD", status="COMPLETED")
    _insert_checkpoint(legacy, symbol="FAILED", status="FAILED")
    _insert_checkpoint(legacy, symbol="EMPTY", status="NO_DATA")
    legacy.commit()
    legacy.close()

    summary = import_legacy_history(source, db_dir=tmp_path / "canonical")

    market = tmp_path / "canonical" / "ccc_market_2026.db"
    connection = sqlite3.connect(market)
    connection.row_factory = sqlite3.Row
    try:
        raw_symbols = {
            row[0] for row in connection.execute("SELECT symbol FROM minute_bars")
        }
        proofs = connection.execute(
            "SELECT * FROM rest_session_status ORDER BY symbol"
        ).fetchall()
    finally:
        connection.close()
    assert raw_symbols == {"GOOD", "FAILED", "EMPTY"}
    assert summary.session_proofs_upserted == 1
    assert len(proofs) == 1
    assert proofs[0]["symbol"] == "GOOD"
    assert proofs[0]["trading_date"] == "2026-01-05"
    assert proofs[0]["mode"] == "minute"
    assert proofs[0]["resolution"] == 1
    assert proofs[0]["status"] == "COMPLETED"
    assert proofs[0]["rows_received"] == 1


def test_completed_range_does_not_create_unobserved_date_proof(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    legacy = _create_legacy(source)
    _insert_minute(legacy, symbol="AAA", trading_date="2026-01-05")
    _insert_checkpoint(
        legacy,
        symbol="AAA",
        status="COMPLETED",
        from_date="2026-01-01",
        to_date="2026-01-31",
    )
    legacy.commit()
    legacy.close()

    import_legacy_history(source, db_dir=tmp_path / "canonical")

    market = tmp_path / "canonical" / "ccc_market_2026.db"
    connection = sqlite3.connect(market)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM rest_session_status WHERE trading_date='2026-01-06'"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_import_uses_sql_and_fetchmany_bounded_batches(tmp_path: Path) -> None:
    source_text = inspect.getsource(import_module)
    assert "date_cursor.fetchmany(batch_size)" in source_text
    assert "INSERT INTO minute_bars" in source_text
    assert "FROM legacy.minute_bars" in source_text
    assert ".fetchall(" not in source_text

    source = tmp_path / "legacy.db"
    legacy = _create_legacy(source)
    for day in range(1, 6):
        _insert_minute(legacy, trading_date=f"2026-01-{day:02d}")
    _insert_checkpoint(legacy, symbol="AAA", status="COMPLETED")
    legacy.commit()
    legacy.close()
    progress: list[str] = []

    summary = import_legacy_history(
        source,
        db_dir=tmp_path / "canonical",
        batch_size=2,
        output=progress.append,
    )

    assert summary.rows_read == 5
    assert len(progress) == 3


def test_session_proof_failure_cannot_roll_back_raw_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "legacy.db"
    legacy = _create_legacy(source)
    _insert_minute(legacy)
    _insert_checkpoint(legacy, symbol="AAA", status="COMPLETED")
    legacy.commit()
    legacy.close()
    target_dir = tmp_path / "canonical"
    monkeypatch.setattr(
        import_module,
        "IMPORT_SESSION_PROOFS_SQL",
        "INSERT INTO table_that_does_not_exist VALUES (1)",
    )

    with pytest.raises(sqlite3.OperationalError):
        import_legacy_history(source, db_dir=target_dir)

    row = _read_one(
        target_dir / "ccc_market_2026.db",
        "SELECT COUNT(*) AS total FROM minute_bars",
    )
    assert row["total"] == 1
