from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .market_session import VN_TZ, market_feed_stale

LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CanonicalProgress:
    accepted_events: int
    last_canonical_write_at: datetime | None


def _local(moment: datetime | None) -> datetime:
    if moment is None:
        return datetime.now(VN_TZ)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=VN_TZ)
    return moment.astimezone(VN_TZ)


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _best_effort_close_stream(
    stream: object | None,
    *,
    logger: logging.Logger,
    reason: str,
) -> None:
    """Close one SSI stream, including the FCData 2.2.2 transport mismatch.

    FCData 2.2.2 ``Connection.close()`` calls ``transport.close()``, but its
    WebsocketTransport implements ``stop()`` instead.  Keep the private-name
    compatibility workaround isolated here until the SDK fixes its public API.
    """
    if stream is None:
        return
    connection = getattr(stream, "connection", None)
    close = getattr(connection, "close", None)
    if callable(close):
        try:
            close()
            return
        except Exception as exc:
            logger.warning(
                "SSI public connection close failed; trying transport stop: "
                "reason=%s error_type=%s",
                reason,
                type(exc).__name__,
            )

    transport = getattr(connection, "_Connection__transport", None)
    stop = getattr(transport, "stop", None)
    if not callable(stop):
        logger.warning(
            "SSI stream close unavailable; continuing fail-open: reason=%s",
            reason,
        )
        return
    try:
        stop()
    except Exception as exc:
        logger.warning(
            "SSI transport stop failed; continuing fail-open: "
            "reason=%s error_type=%s",
            reason,
            type(exc).__name__,
        )


class SSIStreamSupervisor:
    """Own fresh SSI stream generations and bounded in-process recovery."""

    def __init__(
        self,
        *,
        config: object,
        channel: str,
        on_message: Callable[[object], None],
        progress_provider: Callable[[], CanonicalProgress],
        client_factory: Callable[[object], object],
        stream_factory: Callable[..., object],
        reconnect_max_attempts: int = 3,
        reconnect_backoff_seconds: float = 5.0,
        reconnect_progress_timeout_seconds: float = 60.0,
        clock: Callable[[], datetime] | None = None,
        logger: logging.Logger = LOG,
    ) -> None:
        if reconnect_max_attempts < 1:
            raise ValueError("reconnect_max_attempts must be at least 1")
        if reconnect_backoff_seconds < 0:
            raise ValueError("reconnect_backoff_seconds must not be negative")
        if reconnect_progress_timeout_seconds < 1:
            raise ValueError(
                "reconnect_progress_timeout_seconds must be at least 1"
            )
        self.config = config
        self.channel = channel
        self._on_message = on_message
        self._progress_provider = progress_provider
        self._client_factory = client_factory
        self._stream_factory = stream_factory
        self._max_attempts = reconnect_max_attempts
        self._backoff_seconds = reconnect_backoff_seconds
        self._progress_timeout_seconds = reconnect_progress_timeout_seconds
        self._clock = clock or (lambda: datetime.now(VN_TZ))
        self._logger = logger
        self._lock = threading.RLock()

        self._state = "DISCONNECTED"
        self._generation = 0
        self._stream: object | None = None
        self._intentional_generation: int | None = None
        self._generation_started_at: datetime | None = None
        self._accepted_at_generation_start = 0
        self._generation_is_recovery = False
        self._recovery_active = False
        self._recovery_attempts = 0
        self._next_attempt_at: datetime | None = None
        self._shutdown = False
        self._fatal_error: str | None = None

        self._reconnects_total = 0
        self._consecutive_failures = 0
        self._last_open_at: datetime | None = None
        self._last_open_generation: int | None = None
        self._last_close_at: datetime | None = None
        self._last_error_at: datetime | None = None
        self._last_recovery_reason: str | None = None
        self._last_recovered_at: datetime | None = None

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    @property
    def fatal_error(self) -> str | None:
        with self._lock:
            return self._fatal_error

    @property
    def feed_health_anchor(self) -> datetime:
        with self._lock:
            return self._generation_started_at or _local(self._clock())

    def start(self, *, now: datetime | None = None) -> None:
        moment = _local(now or self._clock())
        with self._lock:
            if self._shutdown:
                return
            if self._state != "DISCONNECTED":
                raise RuntimeError("SSI stream supervisor already started")
        self._connect(moment, recovery=False)

    def raise_if_fatal(self) -> None:
        error = self.fatal_error
        if error is not None:
            raise RuntimeError(error)

    def tick(self, now: datetime, *, stale_after_seconds: int) -> None:
        moment = _local(now)
        self._observe_canonical_progress(moment)

        should_connect = False
        with self._lock:
            if (
                not self._shutdown
                and self._state == "RECOVERING"
                and self._next_attempt_at is not None
                and moment >= self._next_attempt_at
            ):
                should_connect = True
        if should_connect:
            self._connect(moment, recovery=True)
            self._observe_canonical_progress(moment)

        with self._lock:
            monitor_stale = self._state in {
                "CONNECTING",
                "AWAITING_PROGRESS",
                "HEALTHY",
            }
            generation = self._generation
            anchor = self._generation_started_at
            recovery_generation = (
                self._generation_is_recovery and self._recovery_active
            )
        progress = self._progress_provider()
        timeout_seconds = (
            self._progress_timeout_seconds
            if recovery_generation
            else stale_after_seconds
        )
        last_progress_at = (
            None if recovery_generation else progress.last_canonical_write_at
        )
        if (
            monitor_stale
            and anchor is not None
            and market_feed_stale(
                moment,
                collector_started_at=anchor,
                last_accepted_event_at=last_progress_at,
                stale_after_seconds=timeout_seconds,
            )
        ):
            self._logger.warning(
                "SSI_STREAM_STALE generation=%s recovery=%s "
                "timeout_seconds=%s last_canonical_write_at=%s",
                self.generation,
                recovery_generation,
                timeout_seconds,
                _timestamp(progress.last_canonical_write_at),
            )
            reason = (
                "RECOVERY_PROGRESS_TIMEOUT"
                if recovery_generation
                else "STALE_FEED"
            )
            if recovery_generation:
                self._current_recovery_generation_timed_out(
                    reason,
                    moment,
                    expected_generation=generation,
                )
            else:
                self._current_generation_failed(reason, moment)

    def stop(self, *, now: datetime | None = None) -> None:
        moment = _local(now or self._clock())
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            self._state = "STOPPED"
            stream = self._retire_current_locked(moment)
        _best_effort_close_stream(
            stream, logger=self._logger, reason="SHUTDOWN"
        )

    def _connect(self, moment: datetime, *, recovery: bool) -> None:
        with self._lock:
            if self._shutdown or self._state == "FATAL":
                return
            if recovery and self._recovery_attempts >= self._max_attempts:
                self._mark_fatal_locked("RECOVERY_ATTEMPTS_EXHAUSTED", moment)
                return
            self._generation += 1
            generation = self._generation
            self._generation_is_recovery = recovery
            self._intentional_generation = None
            self._generation_started_at = moment
            progress = self._progress_provider()
            self._accepted_at_generation_start = progress.accepted_events
            self._state = "CONNECTING"
            if recovery:
                self._recovery_attempts += 1
                self._reconnects_total += 1

        def on_open(*_args: object) -> None:
            opened_at = _local(self._clock())
            with self._lock:
                if not self._callback_is_current_locked(generation):
                    return
                self._last_open_at = opened_at
                self._last_open_generation = generation
            self._logger.info("SSI_STREAM_OPEN generation=%s", generation)

        def on_close(*_args: object) -> None:
            closed_at = _local(self._clock())
            with self._lock:
                if generation != self._generation or self._shutdown:
                    return
                self._last_close_at = closed_at
                if self._intentional_generation == generation:
                    return
            self._current_generation_failed("UNEXPECTED_CLOSE", closed_at)

        def on_error(error: object) -> None:
            failed_at = _local(self._clock())
            with self._lock:
                if not self._callback_is_current_locked(generation):
                    return
                self._last_error_at = failed_at
            self._current_generation_failed(
                f"STREAM_ERROR:{type(error).__name__}", failed_at
            )

        def on_generation_message(message: object) -> None:
            # Retiring a generation waits for an in-flight callback to finish;
            # after retirement, late messages cannot reach the collector.
            with self._lock:
                if not self._callback_is_current_locked(generation):
                    return
                if self._last_open_generation != generation:
                    self._last_open_at = _local(self._clock())
                    self._last_open_generation = generation
                    self._logger.info(
                        "SSI_STREAM_OPEN generation=%s evidence=provider_message",
                        generation,
                    )
                self._on_message(message)
                self._observe_canonical_progress_locked(
                    _local(self._clock())
                )

        stream: object | None = None
        try:
            client = self._client_factory(self.config)
            stream = self._stream_factory(
                self.config,
                client,
                on_close=on_close,
                on_open=on_open,
            )
            with self._lock:
                if self._shutdown or generation != self._generation:
                    self._intentional_generation = generation
                    should_close = True
                else:
                    self._stream = stream
                    should_close = False
                    stream.start(  # type: ignore[attr-defined]
                        on_generation_message, on_error, self.channel
                    )
                    if (
                        self._callback_is_current_locked(generation)
                        and self._state == "CONNECTING"
                    ):
                        self._state = "AWAITING_PROGRESS"
            if should_close:
                _best_effort_close_stream(
                    stream,
                    logger=self._logger,
                    reason="SUPERSEDED_BEFORE_START",
                )
                return
        except Exception as exc:
            self._connection_start_failed(generation, exc, moment, stream)

    def _observe_canonical_progress(self, moment: datetime) -> None:
        with self._lock:
            self._observe_canonical_progress_locked(moment)

    def _observe_canonical_progress_locked(self, moment: datetime) -> bool:
        progress = self._progress_provider()
        if self._state not in {"CONNECTING", "AWAITING_PROGRESS", "HEALTHY"}:
            return False
        if progress.accepted_events <= self._accepted_at_generation_start:
            return False
        recovered = self._recovery_active
        if recovered:
            self._last_recovered_at = moment
            self._recovery_active = False
            self._generation_is_recovery = False
            self._recovery_attempts = 0
            self._consecutive_failures = 0
        self._state = "HEALTHY"
        if recovered:
            self._logger.info(
                "SSI_STREAM_RECOVERED generation=%s accepted_events=%s",
                self._generation,
                progress.accepted_events,
            )
        return True

    def _connection_start_failed(
        self,
        generation: int,
        error: Exception,
        moment: datetime,
        stream: object | None,
    ) -> None:
        with self._lock:
            if generation != self._generation or self._shutdown:
                return
            if (
                self._intentional_generation == generation
                and self._state in {"RECOVERING", "FATAL", "STOPPED"}
            ):
                return
            self._last_error_at = moment
            if self._stream is stream:
                self._stream = None
            self._intentional_generation = generation
            if self._generation_is_recovery:
                self._fail_recovery_attempt_locked(
                    f"CONNECT_FAILED:{type(error).__name__}", moment
                )
            else:
                self._begin_recovery_locked(
                    f"INITIAL_CONNECT_FAILED:{type(error).__name__}", moment
                )
        _best_effort_close_stream(
            stream, logger=self._logger, reason="CONNECT_FAILED"
        )

    def _current_generation_failed(self, reason: str, moment: datetime) -> None:
        with self._lock:
            if self._shutdown or self._state in {"RECOVERING", "FATAL", "STOPPED"}:
                return
            stream = self._retire_current_locked(moment)
            if self._generation_is_recovery:
                self._fail_recovery_attempt_locked(reason, moment)
            else:
                self._begin_recovery_locked(reason, moment)
        _best_effort_close_stream(
            stream, logger=self._logger, reason=reason
        )

    def _current_recovery_generation_timed_out(
        self,
        reason: str,
        moment: datetime,
        *,
        expected_generation: int,
    ) -> None:
        with self._lock:
            if (
                self._shutdown
                or self._generation != expected_generation
                or self._state in {"RECOVERING", "FATAL", "STOPPED"}
            ):
                return
            # A callback may commit canonical data after timeout evaluation but
            # before retirement.  Recovery wins while this generation is current.
            if self._observe_canonical_progress_locked(moment):
                return
            stream = self._retire_current_locked(moment)
            self._fail_recovery_attempt_locked(reason, moment)
        _best_effort_close_stream(
            stream, logger=self._logger, reason=reason
        )

    def _begin_recovery_locked(self, reason: str, moment: datetime) -> None:
        self._recovery_active = True
        self._recovery_attempts = 0
        self._last_recovery_reason = reason
        self._state = "RECOVERING"
        self._next_attempt_at = moment + timedelta(seconds=self._backoff_seconds)
        self._logger.warning(
            "SSI_STREAM_RECOVERING generation=%s reason=%s",
            self._generation,
            reason,
        )

    def _fail_recovery_attempt_locked(self, reason: str, moment: datetime) -> None:
        self._consecutive_failures += 1
        self._last_recovery_reason = reason
        self._logger.warning(
            "SSI_STREAM_RECONNECT_FAILED generation=%s attempt=%s/%s reason=%s",
            self._generation,
            self._recovery_attempts,
            self._max_attempts,
            reason,
        )
        if self._recovery_attempts >= self._max_attempts:
            self._mark_fatal_locked("RECOVERY_ATTEMPTS_EXHAUSTED", moment)
            return
        self._state = "RECOVERING"
        self._next_attempt_at = moment + timedelta(seconds=self._backoff_seconds)

    def _mark_fatal_locked(self, reason: str, moment: datetime) -> None:
        self._state = "FATAL"
        self._last_recovery_reason = reason
        self._fatal_error = (
            f"SSI stream recovery exhausted after {self._max_attempts} attempts"
        )
        self._next_attempt_at = None
        self._logger.error(
            "SSI_STREAM_FATAL generation=%s failures=%s reason=%s at=%s",
            self._generation,
            self._consecutive_failures,
            reason,
            moment.isoformat(),
        )

    def _retire_current_locked(self, moment: datetime) -> object | None:
        stream = self._stream
        self._stream = None
        self._intentional_generation = self._generation
        self._last_close_at = moment
        return stream

    def _callback_is_current_locked(self, generation: int) -> bool:
        return bool(
            not self._shutdown
            and generation == self._generation
            and self._intentional_generation != generation
            and self._state not in {"RECOVERING", "FATAL", "STOPPED"}
        )

    def health(self) -> dict[str, object]:
        with self._lock:
            return {
                "ssi_stream_state": self._state,
                "ssi_stream_generation": self._generation,
                "ssi_stream_reconnects_total": self._reconnects_total,
                "ssi_stream_consecutive_failures": self._consecutive_failures,
                "ssi_stream_last_open_at": _timestamp(self._last_open_at),
                "ssi_stream_last_close_at": _timestamp(self._last_close_at),
                "ssi_stream_last_error_at": _timestamp(self._last_error_at),
                "ssi_stream_last_recovery_reason": self._last_recovery_reason,
                "ssi_stream_last_recovered_at": _timestamp(
                    self._last_recovered_at
                ),
            }


__all__ = ["CanonicalProgress", "SSIStreamSupervisor"]
