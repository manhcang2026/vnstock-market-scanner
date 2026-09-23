from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime
from typing import Any

from app.market_session import VN_TZ
from app.postgres_shadow import (
    _AUCTION_SQL,
    _MINUTE_BAR_SQL,
    MinuteBarShadow,
    PostgresShadowWriter,
    SOURCE,
)


def _minute(close: float = 27_000) -> MinuteBarShadow:
    event_at = datetime(2026, 9, 14, 9, 0, 10, tzinfo=VN_TZ)
    return MinuteBarShadow(
        symbol="HPG",
        exchange="HOSE",
        trading_date="2026-09-14",
        minute_of_day="09:00",
        minute_start=event_at.replace(second=0),
        open=27_000,
        high=max(27_000, close),
        low=min(27_000, close),
        close=close,
        volume=1_000,
        provider_total_volume=1_000,
        provider_session="ATO",
        provider_time=event_at,
        quality_status="TRUSTED",
        is_partial=False,
        source_meta={"local_source": "SSI_STREAM"},
        updated_at=event_at,
    )


class _Cursor:
    def __init__(self, connection: "_Connection") -> None:
        self.connection = connection

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object) -> None:
        self.connection.calls.append((sql, params))

    def executemany(self, sql: str, rows: list[dict[str, object]]) -> None:
        self.connection.calls.append((sql, rows))
        if self.connection.fail_writes:
            raise RuntimeError("database unavailable")


class _Connection:
    def __init__(self, *, fail_writes: bool = False) -> None:
        self.fail_writes = fail_writes
        self.calls: list[tuple[str, object]] = []
        self.commits = 0
        self.closed = False

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


def _wait_until(predicate: Any, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached before timeout")


def _normalized_sql(sql: str) -> str:
    return " ".join(sql.split())


def test_bounded_buffer_coalesces_hot_keys_and_drops_new_overflow() -> None:
    writer = PostgresShadowWriter("postgresql://test", queue_size=1)

    assert writer.offer_minute_bar(_minute(27_000))
    assert writer.offer_minute_bar(_minute(27_100))
    second_symbol = replace(_minute(27_200), symbol="SHS")
    assert not writer.offer_minute_bar(second_symbol)

    health = writer.health()
    assert health["postgres_shadow_pending"] == 1
    assert health["postgres_shadow_coalesced"] == 1
    assert health["postgres_shadow_dropped_overflow"] == 1


def test_minute_upsert_is_complete_idempotent_snapshot() -> None:
    connection = _Connection()
    writer = PostgresShadowWriter("postgresql://test")
    row = _minute()

    writer._write_batch(  # noqa: SLF001 - focused SQL contract test
        connection, [(('minute', 'HPG', '2026-09-14', '09:00'), 'minute', row)]
    )

    sql, rows = connection.calls[-1]
    assert "ON CONFLICT (symbol, trading_date, minute_of_day)" in sql
    assert "volume = EXCLUDED.volume" in sql
    assert rows[0]["volume"] == 1_000
    assert rows[0]["source"] == SOURCE
    assert connection.commits == 1


def test_fastconnect_minute_upsert_cannot_overwrite_finalized_history() -> None:
    sql = _normalized_sql(_MINUTE_BAR_SQL)

    assert "WHERE market.minute_bars_1m.is_final = false AND (" in sql


def test_minute_stale_guard_rejects_null_over_non_null_provider_time() -> None:
    sql = _normalized_sql(_MINUTE_BAR_SQL)

    assert (
        "market.minute_bars_1m.provider_time IS NULL OR ( "
        "EXCLUDED.provider_time IS NOT NULL AND EXCLUDED.provider_time >= "
        "market.minute_bars_1m.provider_time )"
    ) in sql


def test_auction_finalization_is_monotonic() -> None:
    sql = _normalized_sql(_AUCTION_SQL)

    assert (
        "finalized = market.auction_sessions.finalized OR EXCLUDED.finalized"
    ) in sql


def test_auction_stale_guard_rejects_null_over_non_null_last_event() -> None:
    sql = _normalized_sql(_AUCTION_SQL)

    assert (
        "market.auction_sessions.last_event_at IS NULL OR ( "
        "EXCLUDED.last_event_at IS NOT NULL AND EXCLUDED.last_event_at >= "
        "market.auction_sessions.last_event_at )"
    ) in sql


def test_worker_reconnects_after_write_failure_and_marks_recovery() -> None:
    connections = [_Connection(fail_writes=True), _Connection()]

    def factory(*_args: object, **_kwargs: object) -> _Connection:
        return connections.pop(0)

    writer = PostgresShadowWriter(
        "postgresql://test",
        flush_seconds=0.01,
        connection_factory=factory,
    )
    writer.start()
    writer.offer_minute_bar(_minute())

    _wait_until(lambda: writer.health()["postgres_shadow_written"] == 1)
    health = writer.stop(timeout=0.5)

    assert health["postgres_shadow_write_errors"] == 1
    assert health["postgres_shadow_retries"] == 1
    assert health["postgres_shadow_healthy"] is True
    assert health["postgres_shadow_written"] == 1


def test_shutdown_is_bounded_when_connection_keeps_failing() -> None:
    def broken_factory(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("offline")

    writer = PostgresShadowWriter(
        "postgresql://test",
        flush_seconds=0.01,
        connection_factory=broken_factory,
    )
    writer.start()
    writer.offer_minute_bar(_minute())
    started = time.monotonic()

    health = writer.stop(timeout=0.05)

    assert time.monotonic() - started < 0.3
    assert health["postgres_shadow_connect_errors"] >= 1
    assert health["postgres_shadow_pending"] == 1
