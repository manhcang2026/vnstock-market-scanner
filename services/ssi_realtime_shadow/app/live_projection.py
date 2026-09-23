from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .market_session import VN_TZ
from .realtime_volume import VolumeEvent, VolumeSnapshot

LOG = logging.getLogger(__name__)


class LiveProjectionTarget(Protocol):
    def handle_snapshot(
        self,
        snapshot: VolumeSnapshot,
        *,
        event: VolumeEvent | None = None,
        observed_at: datetime | None = None,
    ) -> bool: ...


@dataclass(frozen=True)
class _ProjectionWork:
    snapshot: VolumeSnapshot
    event: VolumeEvent | None
    observed_at: datetime | None


class LiveProjectionWorker:
    """Run live-state projection off the SSI callback with bounded coalescing."""

    def __init__(
        self,
        target: LiveProjectionTarget,
        *,
        max_pending: int = 1024,
        thread_name: str = "ccc-live-projection",
    ) -> None:
        if max_pending < 1:
            raise ValueError("max_pending must be positive")
        self._target = target
        self._max_pending = max_pending
        self._thread_name = thread_name
        self._condition = threading.Condition()
        self._pending: OrderedDict[str, _ProjectionWork] = OrderedDict()
        self._thread: threading.Thread | None = None
        self._accepting = False
        self._stop_requested = False
        self._offered = 0
        self._coalesced = 0
        self._dropped = 0
        self._processed = 0
        self._errors = 0
        self._last_success_at: str | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                return
            if self._stop_requested:
                raise RuntimeError("live projection worker cannot be restarted")
            thread = threading.Thread(
                target=self._run,
                name=self._thread_name,
                daemon=True,
            )
            self._thread = thread
            self._accepting = True
            try:
                thread.start()
            except BaseException:
                self._accepting = False
                self._thread = None
                raise

    def offer(
        self,
        snapshot: VolumeSnapshot,
        *,
        event: VolumeEvent | None = None,
        observed_at: datetime | None = None,
    ) -> bool:
        symbol = str(snapshot.symbol or "").strip().upper()
        if not symbol:
            raise ValueError("projection snapshot symbol is required")
        work = _ProjectionWork(snapshot, event, observed_at)
        with self._condition:
            self._offered += 1
            if not self._accepting or self._stop_requested:
                self._dropped += 1
                return False
            if symbol in self._pending:
                self._pending[symbol] = work
                self._pending.move_to_end(symbol)
                self._coalesced += 1
                self._condition.notify()
                return True
            if len(self._pending) >= self._max_pending:
                self._dropped += 1
                return False
            self._pending[symbol] = work
            self._condition.notify()
            return True

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._stop_requested:
                    self._condition.wait()
                if self._stop_requested:
                    return
                _, work = self._pending.popitem(last=False)
            try:
                self._target.handle_snapshot(
                    work.snapshot,
                    event=work.event,
                    observed_at=work.observed_at,
                )
            except Exception as exc:
                with self._condition:
                    self._errors += 1
                    self._last_error = f"{type(exc).__name__}:{exc}"
                LOG.exception(
                    "Live projection worker failed; continuing: symbol=%s",
                    getattr(work.snapshot, "symbol", "?"),
                )
            else:
                with self._condition:
                    self._processed += 1
                    self._last_success_at = datetime.now(VN_TZ).isoformat()

    def stop(self, *, timeout: float = 2.0) -> bool:
        with self._condition:
            self._accepting = False
            self._stop_requested = True
            self._dropped += len(self._pending)
            self._pending.clear()
            thread = self._thread
            self._condition.notify_all()
        if thread is None:
            return True
        thread.join(max(0.0, timeout))
        return not thread.is_alive()

    def health(self) -> dict[str, object]:
        with self._condition:
            thread = self._thread
            running = bool(thread is not None and thread.is_alive())
            return {
                "live_projection_enabled": True,
                "live_projection_started": thread is not None,
                "live_projection_running": running,
                "live_projection_healthy": running and self._accepting,
                "live_projection_offered": self._offered,
                "live_projection_coalesced": self._coalesced,
                "live_projection_dropped": self._dropped,
                "live_projection_processed": self._processed,
                "live_projection_errors": self._errors,
                "live_projection_pending": len(self._pending),
                "live_projection_max_pending": self._max_pending,
                "live_projection_last_success_at": self._last_success_at,
                "live_projection_last_error": self._last_error,
            }


__all__ = ["LiveProjectionWorker"]
