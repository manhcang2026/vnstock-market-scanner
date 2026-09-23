from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.collector import QuoteCollector
from app.live_projection import LiveProjectionWorker
from app.storage import SQLiteStore
from tests.test_collector import market_event, started_at


def _snapshot(symbol: str, marker: int = 0) -> SimpleNamespace:
    return SimpleNamespace(symbol=symbol, marker=marker)


@pytest.fixture(autouse=True)
def _fixed_collector_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.collector._now_vn", lambda: started_at(9, 0))


def test_projection_runs_only_after_collector_live_transaction_exits(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "outside-transaction.db", commit_every_events=1)
    projected = threading.Event()

    class Target:
        def handle_snapshot(self, _snapshot: object, **_kwargs: object) -> bool:
            assert not store._live_event_transaction
            projected.set()
            return True

    worker = LiveProjectionWorker(Target())
    worker.start()
    collector = QuoteCollector(
        {"HPG"},
        store,
        started_at=started_at(8, 30),
        volume_event_handler=lambda _event: _snapshot("HPG"),
        volume_snapshot_handler=(
            lambda snapshot, event: worker.offer(snapshot, event=event)
        ),
    )

    collector.on_message(market_event())

    assert projected.wait(1)
    assert collector.stats.accepted_events == 1
    assert worker.stop(timeout=1)
    store.close()


def test_blocked_projection_does_not_block_canonical_collector_write(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "blocked-projection.db", commit_every_events=1)
    projection_entered = threading.Event()
    release_projection = threading.Event()

    class Target:
        def handle_snapshot(self, _snapshot: object, **_kwargs: object) -> bool:
            projection_entered.set()
            assert release_projection.wait(2)
            return True

    worker = LiveProjectionWorker(Target())
    worker.start()
    collector = QuoteCollector(
        {"HPG"},
        store,
        started_at=started_at(8, 30),
        volume_event_handler=lambda _event: _snapshot("HPG"),
        volume_snapshot_handler=(
            lambda snapshot, event: worker.offer(snapshot, event=event)
        ),
    )
    collector.on_message(market_event(Time="09:00:10", TotalVol=1_000))
    assert projection_entered.wait(1)

    collected = threading.Event()

    def collect_next() -> None:
        collector.on_message(market_event(Time="09:00:20", TotalVol=1_100))
        collected.set()

    callback = threading.Thread(target=collect_next)
    callback.start()
    assert collected.wait(1)
    assert collector.stats.accepted_events == 2
    assert store.get_latest_quote("HPG", "2026-09-14")["event_time"] == "09:00:20"

    release_projection.set()
    callback.join(1)
    assert worker.stop(timeout=1)
    store.close()


def test_worker_survives_individual_projection_exception() -> None:
    second_processed = threading.Event()

    class Target:
        def __init__(self) -> None:
            self.calls = 0

        def handle_snapshot(self, _snapshot: object, **_kwargs: object) -> bool:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("projection boom")
            second_processed.set()
            return True

    target = Target()
    worker = LiveProjectionWorker(target)
    worker.start()
    assert worker.offer(_snapshot("HPG"))
    assert worker.offer(_snapshot("SHS"))

    assert second_processed.wait(1)
    health = worker.health()
    assert health["live_projection_errors"] == 1
    assert health["live_projection_processed"] == 1
    assert health["live_projection_healthy"] is True
    assert worker.stop(timeout=1)


def test_worker_queue_is_bounded_and_coalesces_latest_per_symbol() -> None:
    first_entered = threading.Event()
    release_first = threading.Event()
    processed: list[tuple[str, int]] = []
    all_processed = threading.Event()

    class Target:
        def handle_snapshot(self, snapshot: object, **_kwargs: object) -> bool:
            if snapshot.symbol == "AAA":
                first_entered.set()
                assert release_first.wait(2)
            processed.append((snapshot.symbol, snapshot.marker))
            if len(processed) == 3:
                all_processed.set()
            return True

    worker = LiveProjectionWorker(Target(), max_pending=2)
    worker.start()
    assert worker.offer(_snapshot("AAA"))
    assert first_entered.wait(1)
    assert worker.offer(_snapshot("BBB", 1))
    assert worker.offer(_snapshot("BBB", 2))
    assert worker.offer(_snapshot("CCC"))
    assert not worker.offer(_snapshot("DDD"))

    health = worker.health()
    assert health["live_projection_pending"] == 2
    assert health["live_projection_max_pending"] == 2
    assert health["live_projection_coalesced"] == 1
    assert health["live_projection_dropped"] == 1

    release_first.set()
    assert all_processed.wait(1)
    assert ("BBB", 2) in processed
    assert ("BBB", 1) not in processed
    assert worker.stop(timeout=1)


def test_saturated_worker_does_not_reject_canonical_collector_write(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "saturated-projection.db", commit_every_events=1)
    first_entered = threading.Event()
    release_first = threading.Event()

    class Target:
        def handle_snapshot(self, snapshot: object, **_kwargs: object) -> bool:
            if snapshot.symbol == "AAA":
                first_entered.set()
                assert release_first.wait(2)
            return True

    worker = LiveProjectionWorker(Target(), max_pending=1)
    worker.start()
    assert worker.offer(_snapshot("AAA"))
    assert first_entered.wait(1)
    assert worker.offer(_snapshot("BBB"))
    collector = QuoteCollector(
        {"HPG"},
        store,
        started_at=started_at(8, 30),
        volume_event_handler=lambda _event: _snapshot("HPG"),
        volume_snapshot_handler=(
            lambda snapshot, event: worker.offer(snapshot, event=event)
        ),
    )

    collector.on_message(market_event())

    assert collector.stats.accepted_events == 1
    assert store.get_latest_quote("HPG", "2026-09-14") is not None
    assert worker.health()["live_projection_dropped"] == 1
    release_first.set()
    assert worker.stop(timeout=1)
    store.close()


def test_worker_stop_is_bounded_when_projection_is_blocked() -> None:
    projection_entered = threading.Event()
    release_projection = threading.Event()

    class Target:
        def handle_snapshot(self, _snapshot: object, **_kwargs: object) -> bool:
            projection_entered.set()
            assert release_projection.wait(2)
            return True

    worker = LiveProjectionWorker(Target())
    worker.start()
    assert worker.offer(_snapshot("HPG"))
    assert projection_entered.wait(1)

    started = time.monotonic()
    assert not worker.stop(timeout=0.01)
    assert time.monotonic() - started < 0.5

    release_projection.set()
    assert worker.stop(timeout=1)
