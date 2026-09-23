from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest

from app.market_session import VN_TZ
from app.ssi_stream_runtime import CanonicalProgress, SSIStreamSupervisor


def _at(hour: int, minute: int, *, day: int = 14, second: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, second, tzinfo=VN_TZ)


@dataclass
class _Progress:
    accepted_events: int = 0
    last_canonical_write_at: datetime | None = None

    def snapshot(self) -> CanonicalProgress:
        return CanonicalProgress(
            self.accepted_events, self.last_canonical_write_at
        )


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def set(self, value: datetime) -> None:
        self.now = value


class _FakeTransport:
    def __init__(self, *, fail_stop: bool) -> None:
        self.fail_stop = fail_stop
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1
        if self.fail_stop:
            raise RuntimeError("transport stop failed")


class _FakeConnection:
    def __init__(
        self,
        stream: "_FakeStream",
        *,
        fail_close: bool,
        fail_stop: bool,
    ) -> None:
        self.stream = stream
        self.fail_close = fail_close
        self.close_calls = 0
        # Match SSI FCData 2.2.2 Connection's name-mangled transport field.
        self._Connection__transport = _FakeTransport(fail_stop=fail_stop)

    def close(self) -> None:
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError("close failed")
        self.stream.on_close()


class _FakeStream:
    def __init__(
        self,
        *,
        on_close: Any,
        on_open: Any,
        fail_close: bool = False,
        fail_stop: bool = False,
        invoke_on_open: bool = True,
    ) -> None:
        self.on_close = on_close
        self.on_open = on_open
        self.invoke_on_open = invoke_on_open
        self.connection = _FakeConnection(
            self,
            fail_close=fail_close,
            fail_stop=fail_stop,
        )
        self.on_message: Any = None
        self.on_error: Any = None
        self.channel: str | None = None
        self.started = False

    def start(self, on_message: Any, on_error: Any, channel: str) -> None:
        self.on_message = on_message
        self.on_error = on_error
        self.channel = channel
        self.started = True
        if self.invoke_on_open:
            self.on_open()

    def emit_message(self, message: object) -> None:
        self.on_message(message)

    def emit_error(self, error: object | None = None) -> None:
        self.on_error(error or RuntimeError("socket error"))

    def emit_close(self) -> None:
        self.on_close()


class _FakeSDK:
    def __init__(
        self,
        *,
        fail_close_indexes: set[int] | None = None,
        fail_stop_indexes: set[int] | None = None,
        invoke_on_open: bool = True,
    ) -> None:
        self.clients: list[object] = []
        self.streams: list[_FakeStream] = []
        self.fail_close_indexes = fail_close_indexes or set()
        self.fail_stop_indexes = fail_stop_indexes or set()
        self.invoke_on_open = invoke_on_open

    def client_factory(self, _config: object) -> object:
        client = object()
        self.clients.append(client)
        return client

    def stream_factory(
        self,
        _config: object,
        _client: object,
        *,
        on_close: Any,
        on_open: Any,
    ) -> _FakeStream:
        index = len(self.streams)
        stream = _FakeStream(
            on_close=on_close,
            on_open=on_open,
            fail_close=index in self.fail_close_indexes,
            fail_stop=index in self.fail_stop_indexes,
            invoke_on_open=self.invoke_on_open,
        )
        self.streams.append(stream)
        return stream


def _supervisor(
    *,
    now: datetime | None = None,
    max_attempts: int = 3,
    backoff: float = 0,
    progress_timeout: float = 60,
    sdk: _FakeSDK | None = None,
    accept_provider_messages: bool = False,
):
    clock = _Clock(now or _at(9, 0))
    progress = _Progress()
    fake_sdk = sdk or _FakeSDK()
    messages: list[object] = []

    def on_message(message: object) -> None:
        messages.append(message)
        if accept_provider_messages:
            progress.accepted_events += 1
            progress.last_canonical_write_at = clock.now

    supervisor = SSIStreamSupervisor(
        config=object(),
        channel="X:ALL",
        on_message=on_message,
        progress_provider=progress.snapshot,
        client_factory=fake_sdk.client_factory,
        stream_factory=fake_sdk.stream_factory,
        reconnect_max_attempts=max_attempts,
        reconnect_backoff_seconds=backoff,
        reconnect_progress_timeout_seconds=progress_timeout,
        clock=clock,
    )
    return supervisor, clock, progress, fake_sdk, messages


def _make_healthy(
    supervisor: SSIStreamSupervisor,
    progress: _Progress,
    now: datetime,
) -> None:
    supervisor.start(now=now)
    progress.accepted_events += 1
    progress.last_canonical_write_at = now
    supervisor.tick(now, stale_after_seconds=180)
    assert supervisor.state == "HEALTHY"


def test_active_session_stale_feed_requests_recovery_with_new_grace() -> None:
    supervisor, clock, _progress, sdk, _messages = _supervisor()
    supervisor.start(now=clock.now)

    stale_at = _at(9, 3, second=1)
    clock.set(stale_at)
    supervisor.tick(stale_at, stale_after_seconds=180)

    assert supervisor.state == "RECOVERING"
    assert supervisor.fatal_error is None
    supervisor.tick(stale_at, stale_after_seconds=180)
    assert len(sdk.streams) == 2
    assert supervisor.state == "AWAITING_PROGRESS"
    supervisor.tick(stale_at + timedelta(seconds=1), stale_after_seconds=180)
    assert supervisor.state == "AWAITING_PROGRESS"


def test_each_reconnect_uses_fresh_client_and_stream() -> None:
    supervisor, clock, progress, sdk, _messages = _supervisor()
    _make_healthy(supervisor, progress, clock.now)
    first_stream = sdk.streams[0]
    first_client = sdk.clients[0]

    first_stream.emit_error()
    supervisor.tick(clock.now, stale_after_seconds=180)

    assert len(sdk.streams) == 2
    assert sdk.streams[1] is not first_stream
    assert sdk.clients[1] is not first_client
    assert first_stream.connection.close_calls == 1


def test_late_previous_generation_callbacks_and_messages_are_ignored() -> None:
    supervisor, clock, progress, sdk, messages = _supervisor()
    _make_healthy(supervisor, progress, clock.now)
    old_stream = sdk.streams[0]
    old_stream.emit_error()
    supervisor.tick(clock.now, stale_after_seconds=180)
    current_generation = supervisor.generation
    current_state = supervisor.state

    old_stream.emit_message({"old": True})
    old_stream.emit_error(RuntimeError("late"))
    old_stream.emit_close()

    assert messages == []
    assert supervisor.generation == current_generation
    assert supervisor.state == current_state


def test_socket_open_without_canonical_progress_does_not_recover() -> None:
    supervisor, clock, progress, sdk, _messages = _supervisor()
    _make_healthy(supervisor, progress, clock.now)
    sdk.streams[0].emit_error()
    supervisor.tick(clock.now, stale_after_seconds=180)

    assert supervisor.state == "AWAITING_PROGRESS"
    health = supervisor.health()
    assert health["ssi_stream_last_recovered_at"] is None
    assert health["ssi_stream_consecutive_failures"] == 0


def test_start_return_and_provider_traffic_do_not_depend_on_on_open() -> None:
    sdk = _FakeSDK(invoke_on_open=False)
    supervisor, clock, progress, sdk, messages = _supervisor(sdk=sdk)

    supervisor.start(now=clock.now)

    assert supervisor.state == "AWAITING_PROGRESS"
    assert supervisor.health()["ssi_stream_last_open_at"] is None

    progress.accepted_events += 1
    progress.last_canonical_write_at = clock.now
    supervisor.tick(clock.now, stale_after_seconds=180)
    assert supervisor.state == "HEALTHY"

    sdk.streams[0].emit_error()
    supervisor.tick(clock.now, stale_after_seconds=180)
    assert supervisor.state == "AWAITING_PROGRESS"
    assert supervisor.health()["ssi_stream_last_open_at"] is None

    sdk.streams[1].emit_message({"TradingDate": "2025-01-01"})

    assert messages == [{"TradingDate": "2025-01-01"}]
    assert supervisor.state == "AWAITING_PROGRESS"
    assert (
        supervisor.health()["ssi_stream_last_open_at"]
        == clock.now.isoformat()
    )

    progress.accepted_events += 1
    progress.last_canonical_write_at = clock.now
    supervisor.tick(clock.now, stale_after_seconds=180)

    assert supervisor.state == "HEALTHY"
    assert (
        supervisor.health()["ssi_stream_last_recovered_at"]
        == clock.now.isoformat()
    )


def test_canonical_progress_recovers_and_resets_failures_not_lifetime_count() -> None:
    supervisor, clock, progress, sdk, _messages = _supervisor()
    _make_healthy(supervisor, progress, clock.now)
    sdk.streams[0].emit_error()
    supervisor.tick(clock.now, stale_after_seconds=180)
    sdk.streams[1].emit_error()
    assert supervisor.health()["ssi_stream_consecutive_failures"] == 1
    supervisor.tick(clock.now, stale_after_seconds=180)
    assert supervisor.state == "AWAITING_PROGRESS"
    assert supervisor.health()["ssi_stream_consecutive_failures"] == 1

    progress.accepted_events += 1
    progress.last_canonical_write_at = clock.now
    supervisor.tick(clock.now, stale_after_seconds=180)

    health = supervisor.health()
    assert supervisor.state == "HEALTHY"
    assert health["ssi_stream_consecutive_failures"] == 0
    assert health["ssi_stream_reconnects_total"] == 2
    assert health["ssi_stream_last_recovered_at"] == clock.now.isoformat()


def test_callback_canonical_progress_marks_recovery_healthy_immediately() -> None:
    supervisor, clock, progress, sdk, _messages = _supervisor(
        accept_provider_messages=True
    )
    _make_healthy(supervisor, progress, clock.now)
    sdk.streams[0].emit_error()
    supervisor.tick(clock.now, stale_after_seconds=180)

    sdk.streams[1].emit_message({"TradingDate": "2026-09-14"})

    assert supervisor.state == "HEALTHY"
    health = supervisor.health()
    assert health["ssi_stream_consecutive_failures"] == 0
    assert health["ssi_stream_reconnects_total"] == 1
    assert health["ssi_stream_last_recovered_at"] == clock.now.isoformat()


def test_later_outage_after_recovery_starts_a_new_recovery_episode() -> None:
    supervisor, clock, progress, sdk, _messages = _supervisor(
        progress_timeout=60,
        accept_provider_messages=True,
    )
    _make_healthy(supervisor, progress, clock.now)

    sdk.streams[0].emit_error()
    supervisor.tick(clock.now, stale_after_seconds=180)
    first_recovery_stream = sdk.streams[1]
    first_recovery_stream.emit_message({"TradingDate": "2026-09-14"})

    assert supervisor.state == "HEALTHY"
    first_health = supervisor.health()
    assert first_health["ssi_stream_consecutive_failures"] == 0
    assert first_health["ssi_stream_reconnects_total"] == 1

    first_recovery_stream.emit_error(RuntimeError("second outage"))

    assert supervisor.state == "RECOVERING"
    assert supervisor.health()["ssi_stream_consecutive_failures"] == 0

    supervisor.tick(clock.now, stale_after_seconds=180)
    assert supervisor.state == "AWAITING_PROGRESS"
    assert len(sdk.streams) == 3

    timeout_at = clock.now + timedelta(seconds=61)
    supervisor.tick(timeout_at, stale_after_seconds=180)

    health = supervisor.health()
    assert supervisor.state == "RECOVERING"
    assert health["ssi_stream_consecutive_failures"] == 1
    assert health["ssi_stream_reconnects_total"] == 2


@pytest.mark.parametrize("signal", ("error", "close"))
def test_unexpected_error_or_close_requests_controlled_recovery(
    signal: str,
) -> None:
    supervisor, clock, progress, sdk, _messages = _supervisor()
    _make_healthy(supervisor, progress, clock.now)

    if signal == "error":
        sdk.streams[0].emit_error()
    else:
        sdk.streams[0].emit_close()

    assert supervisor.state == "RECOVERING"
    assert supervisor.fatal_error is None


def test_intentional_close_does_not_recurse_and_shutdown_never_reconnects() -> None:
    supervisor, clock, progress, sdk, _messages = _supervisor()
    _make_healthy(supervisor, progress, clock.now)
    old_stream = sdk.streams[0]
    old_stream.emit_error()
    assert supervisor.state == "RECOVERING"
    old_stream.emit_close()
    assert supervisor.state == "RECOVERING"

    supervisor.tick(clock.now, stale_after_seconds=180)
    replacement = sdk.streams[1]
    supervisor.stop(now=clock.now)
    replacement.emit_close()
    supervisor.tick(clock.now + timedelta(minutes=10), stale_after_seconds=1)

    assert supervisor.state == "STOPPED"
    assert len(sdk.streams) == 2


def test_broken_public_close_falls_back_to_transport_stop() -> None:
    sdk = _FakeSDK(fail_close_indexes={0})
    supervisor, clock, progress, sdk, messages = _supervisor(sdk=sdk)
    _make_healthy(supervisor, progress, clock.now)
    old_stream = sdk.streams[0]

    old_stream.emit_error()
    supervisor.tick(clock.now, stale_after_seconds=180)

    assert supervisor.state == "AWAITING_PROGRESS"
    assert len(sdk.streams) == 2
    assert old_stream.connection.close_calls == 1
    assert old_stream.connection._Connection__transport.stop_calls == 1

    old_stream.emit_message({"old": True})
    old_stream.emit_error(RuntimeError("late"))
    assert messages == []
    assert supervisor.state == "AWAITING_PROGRESS"


def test_both_close_methods_failing_is_fail_open_for_replacement() -> None:
    sdk = _FakeSDK(fail_close_indexes={0}, fail_stop_indexes={0})
    supervisor, clock, progress, sdk, _messages = _supervisor(sdk=sdk)
    _make_healthy(supervisor, progress, clock.now)

    sdk.streams[0].emit_error()
    supervisor.tick(clock.now, stale_after_seconds=180)

    assert supervisor.state == "AWAITING_PROGRESS"
    assert len(sdk.streams) == 2
    assert sdk.streams[0].connection.close_calls == 1
    assert sdk.streams[0].connection._Connection__transport.stop_calls == 1


def test_healthy_feed_keeps_normal_stale_grace() -> None:
    supervisor, clock, progress, _sdk, _messages = _supervisor()
    _make_healthy(supervisor, progress, clock.now)

    supervisor.tick(
        clock.now + timedelta(seconds=180), stale_after_seconds=180
    )
    assert supervisor.state == "HEALTHY"

    supervisor.tick(
        clock.now + timedelta(seconds=181), stale_after_seconds=180
    )
    assert supervisor.state == "RECOVERING"


def test_recovery_generation_uses_shorter_canonical_progress_timeout() -> None:
    supervisor, clock, progress, sdk, _messages = _supervisor(
        progress_timeout=60
    )
    _make_healthy(supervisor, progress, clock.now)
    sdk.streams[0].emit_error()
    supervisor.tick(clock.now, stale_after_seconds=180)

    supervisor.tick(
        clock.now + timedelta(seconds=60), stale_after_seconds=180
    )
    assert supervisor.state == "AWAITING_PROGRESS"

    supervisor.tick(
        clock.now + timedelta(seconds=61), stale_after_seconds=180
    )
    assert supervisor.state == "RECOVERING"
    assert supervisor.health()["ssi_stream_consecutive_failures"] == 1


def test_recovery_progress_timeout_pauses_during_lunch() -> None:
    lunch_edge = _at(11, 29)
    supervisor, _clock, progress, sdk, _messages = _supervisor(
        now=lunch_edge,
        progress_timeout=60,
    )
    _make_healthy(supervisor, progress, lunch_edge)
    sdk.streams[0].emit_error()
    supervisor.tick(lunch_edge, stale_after_seconds=180)

    supervisor.tick(_at(12, 30), stale_after_seconds=180)

    assert supervisor.state == "AWAITING_PROGRESS"
    assert supervisor.health()["ssi_stream_consecutive_failures"] == 0


def test_canonical_progress_wins_at_recovery_timeout_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor, clock, progress, sdk, _messages = _supervisor(
        progress_timeout=60,
        accept_provider_messages=True,
    )
    _make_healthy(supervisor, progress, clock.now)
    sdk.streams[0].emit_error()
    supervisor.tick(clock.now, stale_after_seconds=180)
    recovery_generation = supervisor.generation
    recovery_stream = sdk.streams[1]
    boundary = clock.now + timedelta(seconds=61)
    clock.set(boundary)

    def accept_during_timeout_evaluation(*_args: object, **_kwargs: object) -> bool:
        recovery_stream.emit_message({"TradingDate": "2026-09-14"})
        return True

    monkeypatch.setattr(
        "app.ssi_stream_runtime.market_feed_stale",
        accept_during_timeout_evaluation,
    )

    supervisor.tick(boundary, stale_after_seconds=180)

    assert supervisor.state == "HEALTHY"
    assert supervisor.generation == recovery_generation
    assert recovery_stream.connection.close_calls == 0
    health = supervisor.health()
    assert health["ssi_stream_consecutive_failures"] == 0
    assert health["ssi_stream_reconnects_total"] == 1


def test_recovery_attempt_exhaustion_becomes_fatal() -> None:
    supervisor, clock, progress, sdk, _messages = _supervisor(max_attempts=3)
    _make_healthy(supervisor, progress, clock.now)
    sdk.streams[0].emit_error()

    for index in range(1, 4):
        supervisor.tick(clock.now, stale_after_seconds=180)
        sdk.streams[index].emit_error()

    assert supervisor.state == "FATAL"
    assert supervisor.fatal_error is not None
    with pytest.raises(RuntimeError, match="recovery exhausted"):
        supervisor.raise_if_fatal()
    health = supervisor.health()
    assert health["ssi_stream_consecutive_failures"] == 3
    assert health["ssi_stream_reconnects_total"] == 3


def test_three_recovery_progress_timeouts_become_fatal() -> None:
    supervisor, clock, progress, sdk, _messages = _supervisor(
        max_attempts=3,
        progress_timeout=60,
    )
    _make_healthy(supervisor, progress, clock.now)
    sdk.streams[0].emit_error()

    moment = clock.now
    for index in range(1, 4):
        supervisor.tick(moment, stale_after_seconds=180)
        assert len(sdk.streams) == index + 1
        moment += timedelta(seconds=61)
        supervisor.tick(moment, stale_after_seconds=180)

    assert supervisor.state == "FATAL"
    assert supervisor.health()["ssi_stream_consecutive_failures"] == 3
    assert supervisor.health()["ssi_stream_reconnects_total"] == 3


@pytest.mark.parametrize(
    "moment",
    (_at(12, 0), _at(10, 0, day=19), _at(15, 0)),
)
def test_no_stale_reconnect_during_lunch_weekend_or_closed(
    moment: datetime,
) -> None:
    supervisor, _clock, _progress, sdk, _messages = _supervisor(now=moment)
    supervisor.start(now=moment)

    supervisor.tick(moment + timedelta(minutes=30), stale_after_seconds=1)

    assert supervisor.state == "AWAITING_PROGRESS"
    assert len(sdk.streams) == 1
