from __future__ import annotations

import importlib
import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable, Protocol


LOG = logging.getLogger(__name__)
SOURCE = "SSI_FASTCONNECT"


@dataclass(frozen=True, slots=True)
class LiveQuoteShadow:
    symbol: str
    exchange: str
    trading_date: str
    last_price: float | None
    cumulative_volume: int | None
    provider_session: str | None
    event_time: datetime
    provider_time: datetime | None
    quality_status: str
    source_meta: dict[str, object]
    updated_at: datetime
    source: str = SOURCE


@dataclass(frozen=True, slots=True)
class MinuteBarShadow:
    symbol: str
    exchange: str
    trading_date: str
    minute_of_day: str
    minute_start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    provider_total_volume: int | None
    provider_session: str | None
    provider_time: datetime | None
    quality_status: str
    is_partial: bool
    updated_at: datetime
    source_meta: dict[str, object]
    is_final: bool = False
    source: str = SOURCE


@dataclass(frozen=True, slots=True)
class AuctionSessionShadow:
    symbol: str
    exchange: str
    trading_date: str
    auction_type: str
    provider_session: str | None
    pre_auction_price: float | None
    auction_price: float | None
    provider_total_volume_start: int | None
    provider_total_volume_end: int | None
    auction_volume: int | None
    quality_status: str
    event_count: int
    first_event_at: datetime | None
    last_event_at: datetime | None
    finalized: bool
    updated_at: datetime
    source_meta: dict[str, object]
    source: str = SOURCE


class PostgresShadowSink(Protocol):
    def offer_live_quote(self, row: LiveQuoteShadow) -> bool: ...

    def offer_minute_bar(self, row: MinuteBarShadow) -> bool: ...

    def offer_auction(self, row: AuctionSessionShadow) -> bool: ...

    def health(self) -> dict[str, object]: ...


@dataclass(slots=True)
class _Stats:
    offered: int = 0
    coalesced: int = 0
    dropped_overflow: int = 0
    written: int = 0
    batches: int = 0
    write_errors: int = 0
    connect_errors: int = 0
    retries: int = 0
    last_error: str | None = None
    last_success_at: str | None = None


_LIVE_QUOTE_SQL = """
INSERT INTO market.live_quotes (
    symbol, exchange, trading_date, last_price, cumulative_volume,
    provider_session, event_time, provider_time, source, quality_status,
    source_meta, updated_at
) VALUES (
    %(symbol)s, %(exchange)s, %(trading_date)s, %(last_price)s,
    %(cumulative_volume)s, %(provider_session)s, %(event_time)s,
    %(provider_time)s, %(source)s, %(quality_status)s,
    %(source_meta)s::jsonb, %(updated_at)s
)
ON CONFLICT (symbol) DO UPDATE SET
    exchange = EXCLUDED.exchange,
    trading_date = EXCLUDED.trading_date,
    last_price = EXCLUDED.last_price,
    cumulative_volume = EXCLUDED.cumulative_volume,
    provider_session = EXCLUDED.provider_session,
    event_time = EXCLUDED.event_time,
    provider_time = EXCLUDED.provider_time,
    source = EXCLUDED.source,
    quality_status = EXCLUDED.quality_status,
    source_meta = EXCLUDED.source_meta,
    updated_at = EXCLUDED.updated_at
WHERE market.live_quotes.event_time IS NULL
   OR EXCLUDED.event_time >= market.live_quotes.event_time
"""


_MINUTE_BAR_SQL = """
INSERT INTO market.minute_bars_1m (
    symbol, exchange, trading_date, minute_of_day, minute_start,
    open, high, low, close, volume, provider_total_volume,
    provider_session, provider_time, source, quality_status,
    is_partial, is_final, source_meta, updated_at
) VALUES (
    %(symbol)s, %(exchange)s, %(trading_date)s, %(minute_of_day)s,
    %(minute_start)s, %(open)s, %(high)s, %(low)s, %(close)s,
    %(volume)s, %(provider_total_volume)s, %(provider_session)s,
    %(provider_time)s, %(source)s, %(quality_status)s,
    %(is_partial)s, %(is_final)s, %(source_meta)s::jsonb, %(updated_at)s
)
ON CONFLICT (symbol, trading_date, minute_of_day) DO UPDATE SET
    exchange = EXCLUDED.exchange,
    minute_start = EXCLUDED.minute_start,
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume,
    provider_total_volume = EXCLUDED.provider_total_volume,
    provider_session = EXCLUDED.provider_session,
    provider_time = EXCLUDED.provider_time,
    source = EXCLUDED.source,
    quality_status = EXCLUDED.quality_status,
    is_partial = EXCLUDED.is_partial,
    is_final = EXCLUDED.is_final,
    source_meta = EXCLUDED.source_meta,
    updated_at = EXCLUDED.updated_at
WHERE market.minute_bars_1m.is_final = false
  AND (
      market.minute_bars_1m.provider_time IS NULL
      OR (
          EXCLUDED.provider_time IS NOT NULL
          AND EXCLUDED.provider_time >= market.minute_bars_1m.provider_time
      )
  )
"""


_AUCTION_SQL = """
INSERT INTO market.auction_sessions (
    symbol, exchange, trading_date, auction_type, provider_session,
    pre_auction_price, auction_price, provider_total_volume_start,
    provider_total_volume_end, auction_volume, quality_status, event_count,
    first_event_at, last_event_at, finalized, source, source_meta, updated_at
) VALUES (
    %(symbol)s, %(exchange)s, %(trading_date)s, %(auction_type)s,
    %(provider_session)s, %(pre_auction_price)s, %(auction_price)s,
    %(provider_total_volume_start)s, %(provider_total_volume_end)s,
    %(auction_volume)s, %(quality_status)s, %(event_count)s,
    %(first_event_at)s, %(last_event_at)s, %(finalized)s, %(source)s,
    %(source_meta)s::jsonb, %(updated_at)s
)
ON CONFLICT (symbol, trading_date, auction_type) DO UPDATE SET
    exchange = EXCLUDED.exchange,
    provider_session = EXCLUDED.provider_session,
    pre_auction_price = EXCLUDED.pre_auction_price,
    auction_price = EXCLUDED.auction_price,
    provider_total_volume_start = EXCLUDED.provider_total_volume_start,
    provider_total_volume_end = EXCLUDED.provider_total_volume_end,
    auction_volume = EXCLUDED.auction_volume,
    quality_status = EXCLUDED.quality_status,
    event_count = EXCLUDED.event_count,
    first_event_at = EXCLUDED.first_event_at,
    last_event_at = EXCLUDED.last_event_at,
    finalized = market.auction_sessions.finalized OR EXCLUDED.finalized,
    source = EXCLUDED.source,
    source_meta = EXCLUDED.source_meta,
    updated_at = EXCLUDED.updated_at
WHERE market.auction_sessions.last_event_at IS NULL
   OR (
       EXCLUDED.last_event_at IS NOT NULL
       AND EXCLUDED.last_event_at >= market.auction_sessions.last_event_at
   )
"""


_SQL_BY_KIND = {
    "quote": _LIVE_QUOTE_SQL,
    "minute": _MINUTE_BAR_SQL,
    "auction": _AUCTION_SQL,
}


class PostgresShadowWriter:
    """Fail-open, bounded PostgreSQL observer for canonical SQLite state."""

    def __init__(
        self,
        dsn: str,
        *,
        flush_seconds: float = 1.0,
        batch_size: int = 500,
        queue_size: int = 10_000,
        connect_timeout_seconds: int = 5,
        statement_timeout_ms: int = 5_000,
        connection_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not str(dsn or "").strip():
            raise ValueError("PostgreSQL shadow DSN is required")
        if flush_seconds <= 0 or batch_size <= 0 or queue_size <= 0:
            raise ValueError("PostgreSQL shadow queue settings must be positive")
        self._dsn = dsn
        self._flush_seconds = float(flush_seconds)
        self._batch_size = int(batch_size)
        self._queue_size = int(queue_size)
        self._connect_timeout_seconds = max(1, int(connect_timeout_seconds))
        self._statement_timeout_ms = max(1, int(statement_timeout_ms))
        self._connection_factory = connection_factory
        self._condition = threading.Condition()
        self._pending: OrderedDict[tuple[object, ...], tuple[str, object]] = (
            OrderedDict()
        )
        self._stats = _Stats()
        self._accepting = True
        self._stopping = False
        self._stop_deadline: float | None = None
        self._started = False
        self._healthy = True
        self._connected = False
        self._thread = threading.Thread(
            target=self._run,
            name="postgres-shadow-writer",
            daemon=True,
        )

    def start(self) -> None:
        with self._condition:
            if self._started:
                return
            self._started = True
            self._thread.start()

    def offer_live_quote(self, row: LiveQuoteShadow) -> bool:
        return self._offer(("quote", row.symbol), "quote", row)

    def offer_minute_bar(self, row: MinuteBarShadow) -> bool:
        return self._offer(
            ("minute", row.symbol, row.trading_date, row.minute_of_day),
            "minute",
            row,
        )

    def offer_auction(self, row: AuctionSessionShadow) -> bool:
        return self._offer(
            ("auction", row.symbol, row.trading_date, row.auction_type),
            "auction",
            row,
        )

    def _offer(
        self, key: tuple[object, ...], kind: str, row: object
    ) -> bool:
        with self._condition:
            if not self._accepting:
                return False
            self._stats.offered += 1
            if key in self._pending:
                self._pending[key] = (kind, row)
                self._pending.move_to_end(key)
                self._stats.coalesced += 1
                self._condition.notify()
                return True
            if len(self._pending) >= self._queue_size:
                self._stats.dropped_overflow += 1
                if (
                    self._stats.dropped_overflow == 1
                    or self._stats.dropped_overflow % 1_000 == 0
                ):
                    LOG.warning(
                        "PostgreSQL shadow buffer full; dropping %s key=%s "
                        "capacity=%s total_dropped=%s",
                        kind,
                        key[1:],
                        self._queue_size,
                        self._stats.dropped_overflow,
                    )
                return False
            self._pending[key] = (kind, row)
            self._condition.notify()
            return True

    def health(self) -> dict[str, object]:
        with self._condition:
            return {
                "postgres_shadow_enabled": True,
                "postgres_shadow_started": self._started,
                "postgres_shadow_healthy": self._healthy,
                "postgres_shadow_connected": self._connected,
                "postgres_shadow_accepting": self._accepting,
                "postgres_shadow_pending": len(self._pending),
                "postgres_shadow_offered": self._stats.offered,
                "postgres_shadow_coalesced": self._stats.coalesced,
                "postgres_shadow_dropped_overflow": (
                    self._stats.dropped_overflow
                ),
                "postgres_shadow_written": self._stats.written,
                "postgres_shadow_batches": self._stats.batches,
                "postgres_shadow_write_errors": self._stats.write_errors,
                "postgres_shadow_connect_errors": self._stats.connect_errors,
                "postgres_shadow_retries": self._stats.retries,
                "postgres_shadow_last_error": self._stats.last_error,
                "postgres_shadow_last_success_at": self._stats.last_success_at,
            }

    def stop(self, timeout: float = 3.0) -> dict[str, object]:
        bounded_timeout = max(0.0, float(timeout))
        with self._condition:
            self._accepting = False
            self._stopping = True
            self._stop_deadline = time.monotonic() + bounded_timeout
            self._condition.notify_all()
        if self._started:
            self._thread.join(timeout=bounded_timeout)
        health = self.health()
        if self._thread.is_alive() or health["postgres_shadow_pending"]:
            LOG.warning(
                "PostgreSQL shadow stopped with unresolved work: pending=%s "
                "worker_alive=%s",
                health["postgres_shadow_pending"],
                self._thread.is_alive(),
            )
        return health

    def _connect(self) -> Any:
        factory = self._connection_factory
        if factory is None:
            psycopg = importlib.import_module("psycopg")
            factory = psycopg.connect
        return factory(
            self._dsn,
            connect_timeout=self._connect_timeout_seconds,
            autocommit=False,
            options=f"-c statement_timeout={self._statement_timeout_ms}",
        )

    def _take_batch(self) -> list[tuple[tuple[object, ...], str, object]]:
        with self._condition:
            while not self._pending and not self._stopping:
                self._condition.wait(self._flush_seconds)
            if not self._pending:
                return []
            flush_at = time.monotonic() + self._flush_seconds
            while (
                not self._stopping
                and len(self._pending) < self._batch_size
                and time.monotonic() < flush_at
            ):
                self._condition.wait(flush_at - time.monotonic())
            items: list[tuple[tuple[object, ...], str, object]] = []
            while self._pending and len(items) < self._batch_size:
                key, (kind, row) = self._pending.popitem(last=False)
                items.append((key, kind, row))
            return items

    def _requeue(
        self, items: list[tuple[tuple[object, ...], str, object]]
    ) -> None:
        with self._condition:
            for key, kind, row in items:
                if key in self._pending:
                    continue
                if len(self._pending) >= self._queue_size:
                    self._stats.dropped_overflow += 1
                    continue
                self._pending[key] = (kind, row)
                self._stats.retries += 1
            self._condition.notify_all()

    @staticmethod
    def _params(row: object) -> dict[str, object]:
        values = asdict(row)  # type: ignore[arg-type]
        values["source_meta"] = json.dumps(
            values.get("source_meta") or {}, separators=(",", ":")
        )
        return values

    def _write_batch(
        self,
        connection: Any,
        items: list[tuple[tuple[object, ...], str, object]],
    ) -> None:
        grouped: dict[str, list[dict[str, object]]] = {
            "quote": [],
            "minute": [],
            "auction": [],
        }
        for _key, kind, row in items:
            grouped[kind].append(self._params(row))
        with connection.cursor() as cursor:
            for kind, rows in grouped.items():
                if rows:
                    cursor.executemany(_SQL_BY_KIND[kind], rows)
        connection.commit()

    def _should_stop(self) -> bool:
        with self._condition:
            if not self._stopping:
                return False
            if not self._pending:
                return True
            return bool(
                self._stop_deadline is not None
                and time.monotonic() >= self._stop_deadline
            )

    def _run(self) -> None:
        connection: Any | None = None
        backoff_seconds = 0.25
        try:
            while not self._should_stop():
                batch = self._take_batch()
                if not batch:
                    continue
                try:
                    if connection is None:
                        connection = self._connect()
                        with self._condition:
                            self._connected = True
                    self._write_batch(connection, batch)
                except Exception as exc:
                    with self._condition:
                        if connection is None:
                            self._stats.connect_errors += 1
                        else:
                            self._stats.write_errors += 1
                        self._healthy = False
                        self._connected = False
                        self._stats.last_error = str(exc)[:1000]
                    LOG.exception("PostgreSQL shadow batch failed; will retry")
                    if connection is not None:
                        try:
                            connection.close()
                        except Exception:
                            LOG.exception("PostgreSQL shadow connection close failed")
                    connection = None
                    self._requeue(batch)
                    with self._condition:
                        wait_seconds = backoff_seconds
                        if self._stop_deadline is not None:
                            wait_seconds = min(
                                wait_seconds,
                                max(0.0, self._stop_deadline - time.monotonic()),
                            )
                        if wait_seconds > 0:
                            self._condition.wait(wait_seconds)
                    backoff_seconds = min(backoff_seconds * 2, 5.0)
                    continue
                with self._condition:
                    self._stats.written += len(batch)
                    self._stats.batches += 1
                    self._stats.last_success_at = datetime.now().astimezone().isoformat()
                    self._stats.last_error = None
                    self._healthy = True
                backoff_seconds = 0.25
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    LOG.exception("PostgreSQL shadow final connection close failed")
            with self._condition:
                self._connected = False
