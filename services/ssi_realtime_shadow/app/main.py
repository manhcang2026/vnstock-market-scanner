from __future__ import annotations

import logging
import os
import signal
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

from .canonical_live_engine import CanonicalLiveEngine
from .canonical_market_store import CanonicalMarketStore
from .collector import QuoteCollector
from .market_session import VN_TZ, market_feed_stale
from .settings import Settings
from .storage import SQLiteStore
from .universe import load_universe

LOG = logging.getLogger("ssi_shadow")

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_RETIRED_LEGACY_FLAGS = ("VOLUME_ENGINE_ENABLED", "LIVE_STATE_ENABLED")


def _reconnect_delay(attempt: int, *, maximum: int = 60) -> int:
    """Bound retry delay without ever producing a terminal retry state."""
    return min(maximum, 2 ** min(max(0, int(attempt)), 6))


@dataclass
class _ReconnectBackoff:
    failed_attempts: int = 0
    next_attempt_at: float = 0.0

    def ready(self, now: float) -> bool:
        return now >= self.next_attempt_at

    def failed(self, now: float) -> int:
        self.failed_attempts += 1
        delay = _reconnect_delay(self.failed_attempts - 1)
        self.next_attempt_at = now + delay
        return delay

    def succeeded(self) -> int:
        attempts = self.failed_attempts + 1
        self.failed_attempts = 0
        self.next_attempt_at = 0.0
        return attempts


def _best_effort_stream_cleanup(stream: object) -> None:
    stop = getattr(stream, "stop", None)
    if callable(stop):
        try:
            stop()
            return
        except Exception:
            LOG.exception("Old SSI stream stop failed; continuing reconnect")
    close = getattr(stream, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            LOG.exception("Old SSI stream close failed; continuing reconnect")


def _start_replacement_stream(
    old_stream: object,
    stream_factory: Callable[[], object],
    on_message: Callable[[object], None],
    on_error: Callable[[object], None],
    channel: str,
) -> object:
    _best_effort_stream_cleanup(old_stream)
    replacement = stream_factory()
    replacement.start(on_message, on_error, channel)  # type: ignore[attr-defined]
    return replacement


def _advance_minute_finalization(collector: QuoteCollector, now: datetime) -> int:
    try:
        return collector.advance_time(now)
    except Exception:
        LOG.exception("Canonical minute finalization failed; will retry")
        return 0


def _advance_canonical_engine(
    engine: CanonicalLiveEngine | None, now: datetime
) -> int:
    if engine is None:
        return 0
    try:
        return engine.advance(now)
    except Exception:
        LOG.exception("Canonical live-engine advance failed; collector continues")
        return 0


def _retired_flag_enabled(name: str, environ: Mapping[str, str]) -> bool:
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return False
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise RuntimeError(f"Invalid boolean environment variable {name}: {raw!r}")


def validate_collector_startup(
    settings: Settings, *, environ: Mapping[str, str] | None = None
) -> None:
    """Fail closed on retired V2 flags and missing canonical production flags."""
    source = os.environ if environ is None else environ
    for name in _RETIRED_LEGACY_FLAGS:
        if _retired_flag_enabled(name, source):
            raise RuntimeError(f"LEGACY_V2_RUNTIME_RETIRED: {name}=true")
    if not settings.canonical_engine_enabled:
        raise RuntimeError(
            "CANONICAL_COLLECTOR_CONFIGURATION_REQUIRED: "
            "CANONICAL_ENGINE_ENABLED=true"
        )
    if not settings.canonical_signal_enabled:
        raise RuntimeError(
            "CANONICAL_COLLECTOR_CONFIGURATION_REQUIRED: "
            "CANONICAL_SIGNAL_ENABLED=true"
        )


def runtime_health(
    settings: Settings, engine: CanonicalLiveEngine | None
) -> dict[str, object]:
    canonical_stats = engine.stats() if engine is not None else None
    return {
        "canonical_engine_enabled": settings.canonical_engine_enabled,
        "canonical_engine_initialized": engine is not None,
        "canonical_engine_writes": (
            canonical_stats.state_writes if canonical_stats else 0
        ),
        "canonical_engine_errors": (
            canonical_stats.calculation_errors if canonical_stats else 1
        ),
        "canonical_signal_enabled": settings.canonical_signal_enabled,
        "canonical_signal_initialized": (
            canonical_stats.canonical_signal_initialized
            if canonical_stats
            else False
        ),
        "canonical_signal_writes": (
            canonical_stats.canonical_signal_writes if canonical_stats else 0
        ),
        "canonical_signal_events": (
            canonical_stats.canonical_signal_events if canonical_stats else 0
        ),
        "canonical_signal_errors": (
            canonical_stats.canonical_signal_errors if canonical_stats else 1
        ),
    }


def _ssi_config(settings: Settings) -> SimpleNamespace:
    # SSI legacy FCData client expects a config module/object with these exact names.
    return SimpleNamespace(
        auth_type=settings.ssi_auth_type,
        consumerID=settings.ssi_consumer_id,
        consumerSecret=settings.ssi_consumer_secret,
        url=settings.ssi_url,
        stream_url=settings.ssi_stream_url,
    )


def main() -> int:
    settings = Settings.from_env()
    validate_collector_startup(settings)
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    store = SQLiteStore(
        settings.database_path,
        commit_every_events=settings.commit_every_events,
        commit_every_seconds=settings.commit_every_seconds,
    )
    canonical_store = CanonicalMarketStore(settings.canonical_market_dir)
    stop_event = threading.Event()
    stream_error = threading.Event()
    started_at = datetime.now(VN_TZ)
    canonical_engine: CanonicalLiveEngine | None = None
    try:
        canonical_engine = CanonicalLiveEngine(
            market_store=canonical_store,
            engine_path=settings.canonical_engine_path,
            active_at=started_at,
            signal_enabled=settings.canonical_signal_enabled,
        )
        LOG.info(
            "Canonical live engine initialized: path=%s stats=%s",
            settings.canonical_engine_path,
            canonical_engine.stats(),
        )
    except Exception:
        LOG.exception(
            "Canonical live engine initialization failed; raw collection continues"
        )

    def current_runtime_health() -> dict[str, object]:
        return runtime_health(settings, canonical_engine)

    # Universe loading remains after local canonical-engine initialization so
    # the stream cannot start before the runtime is ready.
    try:
        universe = load_universe(settings)
    except Exception:
        if canonical_engine is not None:
            canonical_engine.close()
        canonical_store.close()
        store.close()
        raise

    def shutdown(signum: int, _frame: object) -> None:
        LOG.info("Received signal %s; shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        try:
            from ssi_fc_data.fc_md_client import MarketDataClient
            from ssi_fc_data.fc_md_stream import MarketDataStream
        except ImportError as exc:
            raise RuntimeError(
                "SSI FCData SDK is not installed. Install the official "
                "ssi_fc_data-2.2.2.tar.gz first."
            ) from exc

        cfg = _ssi_config(settings)
        stream = MarketDataStream(cfg, MarketDataClient(cfg))

        def on_error(error: object) -> None:
            LOG.error("SSI stream error: %s", error)
            stream_error.set()

        collector = QuoteCollector(
            universe,
            store,
            started_at=started_at,
            extra_stats_provider=current_runtime_health,
            canonical_store=canonical_store,
            post_commit_hook=(
                canonical_engine.mark_dirty if canonical_engine is not None else None
            ),
        )
        store.set_meta("started_at", started_at.isoformat(), started_at.isoformat())
        store.set_meta("channel", settings.ssi_channel, started_at.isoformat())
        store.set_meta("universe_size", str(len(universe)), started_at.isoformat())
        for key, value in current_runtime_health().items():
            store.set_meta(key, str(value), started_at.isoformat())
        store.commit()

        LOG.info(
            "Starting SSI collector: channel=%s universe=%s canonical_dir=%s projection_db=%s",
            settings.ssi_channel,
            len(universe),
            settings.canonical_market_dir,
            settings.database_path,
        )
        reconnect_backoff = _ReconnectBackoff()
        stale_anchor = started_at
        try:
            stream.start(collector.on_message, on_error, settings.ssi_channel)
        except Exception:
            LOG.exception("Initial SSI stream connection failed; retrying")
            stream_error.set()

        last_stats_log = time.monotonic()
        stale_logged = False
        while not stop_event.wait(1):
            if stream_error.is_set():
                monotonic_now = time.monotonic()
                if reconnect_backoff.ready(monotonic_now):
                    try:
                        stream = _start_replacement_stream(
                            stream,
                            lambda: MarketDataStream(cfg, MarketDataClient(cfg)),
                            collector.on_message,
                            on_error,
                            settings.ssi_channel,
                        )
                    except Exception:
                        delay = reconnect_backoff.failed(monotonic_now)
                        LOG.exception(
                            "SSI reconnect attempt %s failed; retrying in %ss",
                            reconnect_backoff.failed_attempts,
                            delay,
                        )
                    else:
                        attempts = reconnect_backoff.succeeded()
                        stream_error.clear()
                        stale_anchor = datetime.now(VN_TZ)
                        stale_logged = False
                        LOG.info(
                            "SSI stream reconnected after %s attempt(s)",
                            attempts,
                        )

            now = datetime.now(VN_TZ)
            _advance_minute_finalization(collector, now)
            _advance_canonical_engine(canonical_engine, now)
            feed_is_stale = market_feed_stale(
                now,
                collector_started_at=stale_anchor,
                last_accepted_event_at=collector.last_event_at,
                stale_after_seconds=settings.stale_stream_seconds,
            )
            if feed_is_stale:
                if not stale_logged:
                    LOG.warning(
                        "SSI feed has no accepted event for more than %ss; "
                        "requesting in-process reconnect",
                        settings.stale_stream_seconds,
                    )
                    stale_logged = True
                if not stream_error.is_set():
                    stream_error.set()
            else:
                stale_logged = False

            if time.monotonic() - last_stats_log >= 60:
                stats = collector.snapshot_stats()
                LOG.info("collector stats: %s", stats)
                store.set_meta("last_stats", str(stats), now.isoformat())
                for key, value in current_runtime_health().items():
                    store.set_meta(key, str(value), now.isoformat())
                store.commit()
                last_stats_log = time.monotonic()

        return 0
    finally:
        now = datetime.now(VN_TZ).isoformat()
        try:
            store.set_meta("stopped_at", now, now)
            store.commit()
        finally:
            try:
                if canonical_engine is not None:
                    canonical_engine.close()
            finally:
                try:
                    canonical_store.close()
                finally:
                    store.close()


if __name__ == "__main__":
    raise SystemExit(main())
