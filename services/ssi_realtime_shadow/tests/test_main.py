from __future__ import annotations

import logging
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.main import (
    VolumeShadowQALogger,
    _advance_volume_shadow,
    _start_postgres_shadow,
    _stop_postgres_shadow,
    _start_volume_shadow,
    _volume_event_handler,
)
from app.realtime_volume import VolumeEvent
from tests.test_realtime_volume import _at, _event


def _settings(tmp_path: Path, *, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        volume_engine_enabled=enabled,
        volume_baseline_path=tmp_path / "baseline.db",
        volume_shadow_symbols=("HPG", "SHS", "VGI"),
    )


def _postgres_settings(*, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        postgres_shadow_enabled=enabled,
        postgres_shadow_dsn="postgresql://test",
        postgres_shadow_flush_seconds=1,
        postgres_shadow_batch_size=500,
        postgres_shadow_queue_size=10_000,
    )


def test_postgres_shadow_disabled_does_not_construct_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_writer(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("writer must not be constructed")

    monkeypatch.setattr("app.main.PostgresShadowWriter", unexpected_writer)

    assert _start_postgres_shadow(_postgres_settings(enabled=False)) is None


def test_postgres_shadow_initialization_failure_is_fail_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_writer(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("bad configuration")

    monkeypatch.setattr("app.main.PostgresShadowWriter", broken_writer)

    assert _start_postgres_shadow(_postgres_settings(enabled=True)) is None


def test_postgres_shadow_shutdown_failure_is_fail_open() -> None:
    class BrokenWriter:
        def stop(self) -> None:
            raise RuntimeError("shutdown failed")

    _stop_postgres_shadow(BrokenWriter())


def _snapshot(
    symbol: str = "HPG",
    *,
    as_of: str = "09:30",
    trusted: bool = True,
    quality: str = "TRUSTED",
    reasons: tuple[str, ...] = ("OK",),
) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        trading_date="2026-09-14",
        as_of_minute=as_of,
        cumulative_volume=1_000,
        day_rvol=1.25,
        volume_15=150,
        rvol_15=1.5,
        volume_30=250,
        rvol_30=1.1,
        opening_rvol=None,
        baseline_sessions_used=10,
        active_sessions_used=8,
        metrics_trusted=trusted,
        quality_status=quality,
        reasons=reasons,
    )


def test_shadow_disabled_never_loads_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def unexpected_load(_path: Path) -> object:
        raise AssertionError("baseline loader must not run")

    monkeypatch.setattr("app.main.RealtimeVolumeEngine", unexpected_load)
    with caplog.at_level(logging.INFO, logger="ssi_shadow"):
        engine = _start_volume_shadow(_settings(tmp_path, enabled=False))

    assert engine is None
    assert caplog.text.count("CCC V2 volume shadow disabled") == 1


def test_baseline_load_failure_disables_shadow_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken_load(_path: Path) -> object:
        raise RuntimeError("corrupt baseline")

    monkeypatch.setattr("app.main.RealtimeVolumeEngine", broken_load)
    with caplog.at_level(logging.ERROR, logger="ssi_shadow"):
        engine = _start_volume_shadow(_settings(tmp_path, enabled=True))

    assert engine is None
    assert "continuing V1 collector" in caplog.text
    assert "corrupt baseline" in caplog.text


def test_successful_shadow_start_logs_loaded_baseline_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    baseline_path = (tmp_path / "baseline.db").resolve()
    baseline = SimpleNamespace(
        source_path=baseline_path,
        schema_version=2,
        lookback=10,
        coverage=range(800),
        points=range(193_533),
    )
    fake_engine = SimpleNamespace(baseline=baseline)
    monkeypatch.setattr(
        "app.main.RealtimeVolumeEngine", lambda _path: fake_engine
    )

    with caplog.at_level(logging.INFO, logger="ssi_shadow"):
        engine = _start_volume_shadow(_settings(tmp_path, enabled=True))

    assert engine is fake_engine
    assert "CCC V2 volume shadow enabled:" in caplog.text
    assert "schema=2" in caplog.text
    assert "lookback=10" in caplog.text
    assert "coverage=800" in caplog.text
    assert "points=193533" in caplog.text
    assert "qa_symbols=HPG,SHS,VGI" in caplog.text


def test_volume_handler_passes_canonical_event_to_engine_and_counts_log() -> None:
    received: list[VolumeEvent] = []
    snapshot = _snapshot()
    engine = SimpleNamespace(
        on_event=lambda event: received.append(event) or snapshot
    )
    qa_logger = SimpleNamespace(log_if_changed=lambda value: value is snapshot)
    logged: list[bool] = []
    handler = _volume_event_handler(
        engine,
        qa_logger,
        lambda: logged.append(True),
        engine_lock=threading.Lock(),
    )
    event = _event("HPG", "HOSE", "09:30", 10)

    handler(event)

    assert received == [event]
    assert logged == [True]


def test_advance_time_runs_without_any_ssi_event_and_counts_changed_snapshot() -> None:
    calls: list[object] = []
    snapshot = _snapshot()
    engine = SimpleNamespace(
        advance_time=lambda now: calls.append(now) or {"HPG": snapshot}
    )
    qa_logger = SimpleNamespace(log_if_changed=lambda value: value is snapshot)
    stats = SimpleNamespace(
        volume_shadow_snapshots=0, volume_shadow_advance_errors=0
    )
    collector = SimpleNamespace(stats=stats)
    now = _at("09:31")

    _advance_volume_shadow(
        engine,
        qa_logger,
        collector,
        now,
        engine_lock=threading.Lock(),
    )

    assert calls == [now]
    assert stats.volume_shadow_snapshots == 1
    assert stats.volume_shadow_advance_errors == 0


def test_advance_time_exception_isolated_and_counted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken_advance(_now: object) -> object:
        raise RuntimeError("advance boom")

    engine = SimpleNamespace(advance_time=broken_advance)
    qa_logger = SimpleNamespace(log_if_changed=lambda _value: False)
    stats = SimpleNamespace(
        volume_shadow_snapshots=0, volume_shadow_advance_errors=0
    )
    collector = SimpleNamespace(stats=stats)

    with caplog.at_level(logging.ERROR, logger="ssi_shadow"):
        _advance_volume_shadow(
            engine,
            qa_logger,
            collector,
            _at("09:31"),
            engine_lock=threading.Lock(),
        )

    assert stats.volume_shadow_advance_errors == 1
    assert stats.volume_shadow_snapshots == 0
    assert "advance_time failed" in caplog.text
    assert "advance boom" in caplog.text


def test_event_and_timer_volume_engine_mutations_are_serialized() -> None:
    event_entered = threading.Event()
    release_event = threading.Event()
    advance_entered = threading.Event()
    second_lock_attempted = threading.Event()
    snapshot = _snapshot()

    class ObservedLock:
        def __init__(self) -> None:
            self._lock = threading.Lock()
            self._attempt_lock = threading.Lock()
            self._attempts = 0

        def __enter__(self) -> object:
            with self._attempt_lock:
                self._attempts += 1
                if self._attempts == 2:
                    second_lock_attempted.set()
            self._lock.acquire()
            return self

        def __exit__(self, *_args: object) -> None:
            self._lock.release()

    class BlockingEngine:
        def on_event(self, _event: VolumeEvent) -> object:
            event_entered.set()
            assert release_event.wait(1)
            return snapshot

        def advance_time(self, _now: object) -> dict[str, object]:
            advance_entered.set()
            return {}

    engine = BlockingEngine()
    lock = ObservedLock()
    qa_logger = SimpleNamespace(log_if_changed=lambda _value: False)
    collector = SimpleNamespace(
        stats=SimpleNamespace(
            volume_shadow_snapshots=0, volume_shadow_advance_errors=0
        )
    )
    handler = _volume_event_handler(
        engine, qa_logger, lambda: None, engine_lock=lock
    )
    callback = threading.Thread(
        target=handler, args=(_event("HPG", "HOSE", "09:30", 10),)
    )
    callback.start()
    assert event_entered.wait(1)

    timer = threading.Thread(
        target=_advance_volume_shadow,
        args=(engine, qa_logger, collector, _at("09:31")),
        kwargs={"engine_lock": lock},
    )
    timer.start()
    assert second_lock_attempted.wait(1)
    assert not advance_entered.is_set()

    release_event.set()
    callback.join(1)
    timer.join(1)
    assert not callback.is_alive()
    assert not timer.is_alive()
    assert advance_entered.is_set()


def test_qa_logger_only_logs_configured_symbols_once_per_same_state(
    caplog: pytest.LogCaptureFixture,
) -> None:
    qa_logger = VolumeShadowQALogger(("HPG",))
    hpg = _snapshot("HPG")
    shs = _snapshot("SHS")

    with caplog.at_level(logging.INFO, logger="ssi_shadow"):
        assert not qa_logger.log_if_changed(shs)
        assert qa_logger.log_if_changed(hpg)
        assert not qa_logger.log_if_changed(hpg)

    messages = [record.message for record in caplog.records if "VOLUME_SHADOW" in record.message]
    assert len(messages) == 1
    assert "symbol=HPG" in messages[0]
    assert "as_of=09:30" in messages[0]
    assert "trusted=true" in messages[0]
    assert "reasons=OK" in messages[0]
    assert "symbol=SHS" not in caplog.text


def test_qa_logger_logs_trust_change_in_same_as_of_minute(
    caplog: pytest.LogCaptureFixture,
) -> None:
    qa_logger = VolumeShadowQALogger(("HPG",))
    trusted = _snapshot()
    tainted = _snapshot(
        trusted=False,
        quality="GAP",
        reasons=("CURRENT_GAP", "NON_TRUSTED_QUALITY"),
    )

    with caplog.at_level(logging.INFO, logger="ssi_shadow"):
        assert qa_logger.log_if_changed(trusted)
        assert qa_logger.log_if_changed(tainted)
        assert not qa_logger.log_if_changed(tainted)

    messages = [record.message for record in caplog.records if "VOLUME_SHADOW" in record.message]
    assert len(messages) == 2
    assert "trusted=false" in messages[-1]
    assert "quality=GAP" in messages[-1]
    assert "reasons=CURRENT_GAP,NON_TRUSTED_QUALITY" in messages[-1]
