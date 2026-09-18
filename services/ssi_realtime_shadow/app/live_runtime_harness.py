"""Deterministic no-network harness for the production live-state wiring."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from .collector import QuoteCollector
from .live_state_runtime import LiveStateRuntime
from .realtime_volume import RealtimeVolumeEngine, VolumeEvent
from .state_contract import list_current_states
from .storage import SQLiteStore


class LiveRuntimeHarness:
    """Drive collector -> volume engine -> live runtime with fixture messages.

    The harness intentionally uses ``QuoteCollector.on_message`` so fixture data
    follows the same normalization and hot-storage path as the SSI callback.
    It performs no network calls and never writes outside caller-supplied DBs.
    """

    def __init__(
        self,
        *,
        universe: set[str],
        store: SQLiteStore,
        volume_engine: RealtimeVolumeEngine,
        live_runtime: LiveStateRuntime,
        started_at: datetime,
    ) -> None:
        self.volume_engine = volume_engine
        self.live_runtime = live_runtime
        self.volume_engine_calls = 0

        def handle(event: VolumeEvent) -> None:
            self.volume_engine_calls += 1
            snapshot = self.volume_engine.on_event(event)
            self.live_runtime.handle_snapshot(snapshot, event=event)

        self.collector = QuoteCollector(
            universe,
            store,
            started_at=started_at,
            volume_event_handler=handle,
            extra_stats_provider=live_runtime.health,
        )

    def feed(self, message: Any) -> None:
        self.collector.on_message(message)

    def advance(self, now: datetime) -> int:
        changed = self.volume_engine.advance_time(now)
        return sum(
            self.live_runtime.handle_snapshot(snapshot, observed_at=now)
            for snapshot in changed.values()
        )

    def serialized_states(self) -> list[dict[str, Any]]:
        connection = sqlite3.connect(self.live_runtime.market_db_path)
        try:
            return list_current_states(
                connection, config=self.live_runtime.signal_config
            )
        finally:
            connection.close()


__all__ = ["LiveRuntimeHarness"]
