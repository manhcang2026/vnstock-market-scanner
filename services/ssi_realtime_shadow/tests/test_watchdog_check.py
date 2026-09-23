from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app.market_session import VN_TZ
from app.watchdog_check import HEARTBEAT_KEY, check_heartbeat, main


def _at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 9, 24, hour, minute, second, tzinfo=VN_TZ)


def _database(path: Path, heartbeat: str | None) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE collector_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO collector_meta VALUES (?, ?, ?)",
            ("sentinel", "preserve", _at(9, 0).isoformat()),
        )
        if heartbeat is not None:
            connection.execute(
                "INSERT INTO collector_meta VALUES (?, ?, ?)",
                (HEARTBEAT_KEY, heartbeat, heartbeat),
            )
        connection.commit()
    finally:
        connection.close()


def test_recent_valid_heartbeat_exits_healthy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "hot.db"
    _database(database, datetime.now(VN_TZ).isoformat())

    result = main(
        ["--database", str(database), "--max-age-seconds", "90"]
    )

    assert result == 0
    assert capsys.readouterr().out.startswith("WATCHDOG_HEALTHY ")


def test_stale_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    database = tmp_path / "hot.db"
    _database(database, _at(9, 0).isoformat())

    healthy, diagnostic = check_heartbeat(
        database,
        max_age_seconds=90,
        now=_at(9, 1, 31),
    )

    assert not healthy
    assert "reason=heartbeat_stale" in diagnostic


def test_missing_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    database = tmp_path / "hot.db"
    _database(database, None)

    healthy, diagnostic = check_heartbeat(
        database,
        max_age_seconds=90,
        now=_at(9, 0),
    )

    assert not healthy
    assert diagnostic == "WATCHDOG_UNHEALTHY reason=heartbeat_missing"


def test_malformed_or_naive_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    for index, value in enumerate(("not-a-time", "2026-09-24T09:00:00")):
        database = tmp_path / f"hot-{index}.db"
        _database(database, value)

        healthy, diagnostic = check_heartbeat(
            database,
            max_age_seconds=90,
            now=_at(9, 0),
        )

        assert not healthy
        assert diagnostic == "WATCHDOG_UNHEALTHY reason=heartbeat_malformed"


@pytest.mark.parametrize("kind", ("missing", "corrupt"))
def test_missing_or_unreadable_database_is_unhealthy(
    tmp_path: Path,
    kind: str,
) -> None:
    database = tmp_path / "hot.db"
    if kind == "corrupt":
        database.write_bytes(b"not a sqlite database")

    healthy, diagnostic = check_heartbeat(
        database,
        max_age_seconds=90,
        now=_at(9, 0),
    )

    assert not healthy
    assert "reason=database_unreadable" in diagnostic


def test_read_only_check_does_not_modify_collector_meta(tmp_path: Path) -> None:
    database = tmp_path / "hot.db"
    heartbeat = _at(9, 0).isoformat()
    _database(database, heartbeat)
    before = _meta_rows(database)

    healthy, _diagnostic = check_heartbeat(
        database,
        max_age_seconds=90,
        now=_at(9, 0, 30),
    )

    assert healthy
    assert _meta_rows(database) == before


def _meta_rows(database: Path) -> list[tuple[str, str, str]]:
    connection = sqlite3.connect(database)
    try:
        return connection.execute(
            "SELECT key, value, updated_at FROM collector_meta ORDER BY key"
        ).fetchall()
    finally:
        connection.close()
