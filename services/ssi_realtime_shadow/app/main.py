from __future__ import annotations

import logging
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

from .canonical_live_engine import CanonicalLiveEngine
from .canonical_market_store import CanonicalMarketStore
from .collector import QuoteCollector
from .live_state_runtime import LiveStateRuntime
from .market_session import VN_TZ, market_feed_stale
from .realtime_volume import RealtimeVolumeEngine, VolumeEvent, VolumeSnapshot
from .settings import Settings
from .storage import SQLiteStore
from .universe import load_universe

LOG = logging.getLogger("ssi_shadow")


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


class VolumeShadowQALogger:
    def __init__(
        self,
        symbols: tuple[str, ...],
        *,
        logger: logging.Logger = LOG,
    ) -> None:
        self.symbols = frozenset(symbols)
        self.logger = logger
        self._last_signatures: dict[str, tuple[object, ...]] = {}

    def log_if_changed(self, snapshot: VolumeSnapshot) -> bool:
        if snapshot.symbol not in self.symbols:
            return False
        signature = (
            snapshot.trading_date,
            snapshot.as_of_minute,
            snapshot.metrics_trusted,
            snapshot.quality_status,
            snapshot.reasons,
        )
        if self._last_signatures.get(snapshot.symbol) == signature:
            return False
        self._last_signatures[snapshot.symbol] = signature
        self.logger.info(
            "VOLUME_SHADOW symbol=%s date=%s as_of=%s cum=%s "
            "day_rvol=%s vol15=%s rvol15=%s vol30=%s rvol30=%s "
            "opening_rvol=%s sessions=%s active_sessions=%s trusted=%s "
            "quality=%s reasons=%s",
            snapshot.symbol,
            snapshot.trading_date,
            snapshot.as_of_minute or "null",
            snapshot.cumulative_volume,
            _log_value(snapshot.day_rvol),
            _log_value(snapshot.volume_15),
            _log_value(snapshot.rvol_15),
            _log_value(snapshot.volume_30),
            _log_value(snapshot.rvol_30),
            _log_value(snapshot.opening_rvol),
            snapshot.baseline_sessions_used,
            snapshot.active_sessions_used,
            str(snapshot.metrics_trusted).lower(),
            snapshot.quality_status,
            ",".join(snapshot.reasons),
        )
        return True


def _log_value(value: object | None) -> str:
    return "null" if value is None else str(value)


def _start_volume_shadow(settings: Settings) -> RealtimeVolumeEngine | None:
    if not settings.volume_engine_enabled:
        LOG.info("CCC V2 volume shadow disabled")
        return None
    try:
        engine = RealtimeVolumeEngine(settings.volume_baseline_path)
    except Exception:
        LOG.exception(
            "CCC V2 volume shadow failed to start; continuing V1 collector: "
            "baseline=%s",
            settings.volume_baseline_path,
        )
        return None
    baseline = engine.baseline
    LOG.info(
        "CCC V2 volume shadow enabled: baseline=%s schema=%s lookback=%s "
        "coverage=%s points=%s qa_symbols=%s",
        baseline.source_path,
        baseline.schema_version,
        baseline.lookback,
        len(baseline.coverage),
        len(baseline.points),
        ",".join(settings.volume_shadow_symbols),
    )
    return engine


def _volume_event_handler(
    engine: RealtimeVolumeEngine,
    qa_logger: VolumeShadowQALogger,
    on_snapshot_logged: Callable[[], None],
    live_runtime: LiveStateRuntime | None = None,
) -> Callable[[VolumeEvent], None]:
    def handle(event: VolumeEvent) -> None:
        snapshot = engine.on_event(event)
        if qa_logger.log_if_changed(snapshot):
            on_snapshot_logged()
        if live_runtime is not None:
            live_runtime.handle_snapshot(snapshot, event=event)

    return handle


def _advance_volume_shadow(
    engine: RealtimeVolumeEngine,
    qa_logger: VolumeShadowQALogger,
    collector: QuoteCollector,
    now: datetime,
    live_runtime: LiveStateRuntime | None = None,
) -> None:
    try:
        changed = engine.advance_time(now)
        for snapshot in changed.values():
            if qa_logger.log_if_changed(snapshot):
                collector.stats.volume_shadow_snapshots += 1
            if live_runtime is not None:
                live_runtime.handle_snapshot(snapshot, observed_at=now)
    except Exception:
        collector.stats.volume_shadow_advance_errors += 1
        LOG.exception("CCC V2 volume shadow advance_time failed")


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
    volume_engine = _start_volume_shadow(settings)
    volume_qa_logger = (
        VolumeShadowQALogger(settings.volume_shadow_symbols)
        if volume_engine is not None
        else None
    )
    started_at = datetime.now(VN_TZ)
    canonical_engine: CanonicalLiveEngine | None = None
    if settings.canonical_engine_enabled:
        try:
            canonical_engine = CanonicalLiveEngine(
                market_store=canonical_store,
                engine_path=settings.canonical_engine_path,
                active_at=started_at,
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
    live_runtime: LiveStateRuntime | None = None
    if settings.live_state_enabled and volume_engine is not None:
        try:
            live_runtime = LiveStateRuntime(
                volume_engine=volume_engine,
                hot_store=store,
                market_db_path=settings.market_v2_database_path,
                history_db_path=settings.ssi_history_path,
                active_at=started_at,
            )
            LOG.info("CCC V2 live state initialized: %s", live_runtime.health())
        except Exception:
            LOG.exception(
                "CCC V2 live state initialization failed; raw collection will continue"
            )
    elif settings.live_state_enabled:
        LOG.error(
            "CCC V2 live state unavailable because volume engine did not initialize"
        )

    def live_health() -> dict[str, object]:
        if live_runtime is not None:
            values = live_runtime.health()
        else:
            values = {
                "live_state_enabled": settings.live_state_enabled,
                "live_state_initialized": False,
                "live_state_updates": 0,
                "live_state_errors": int(settings.live_state_enabled),
                "live_state_last_update_at": None,
                "live_state_trading_date": started_at.date().isoformat(),
                "live_state_baseline_as_of_date": (
                    volume_engine.baseline.as_of_date
                    if volume_engine is not None
                    else None
                ),
                "live_state_baseline_ready": False,
                "live_state_market_db_path": str(settings.market_v2_database_path),
                "live_state_history_available": settings.ssi_history_path.is_file(),
            }
        canonical_stats = canonical_engine.stats() if canonical_engine else None
        values.update(
            {
                "canonical_engine_enabled": settings.canonical_engine_enabled,
                "canonical_engine_initialized": canonical_engine is not None,
                "canonical_engine_writes": (
                    canonical_stats.state_writes if canonical_stats else 0
                ),
                "canonical_engine_errors": (
                    canonical_stats.calculation_errors
                    if canonical_stats
                    else int(settings.canonical_engine_enabled)
                ),
            }
        )
        return values

    # Universe loading remains after all local live-state hydration so the stream
    # cannot start before the runtime is ready.
    try:
        universe = load_universe(settings)
    except Exception:
        if canonical_engine is not None:
            canonical_engine.close()
        if live_runtime is not None:
            live_runtime.close()
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

        collector: QuoteCollector

        def snapshot_logged() -> None:
            collector.stats.volume_shadow_snapshots += 1

        volume_handler = (
            _volume_event_handler(
                volume_engine,
                volume_qa_logger,
                snapshot_logged,
                live_runtime=live_runtime,
            )
            if volume_engine is not None and volume_qa_logger is not None
            else None
        )
        collector = QuoteCollector(
            universe,
            store,
            started_at=started_at,
            volume_event_handler=volume_handler,
            extra_stats_provider=live_health,
            canonical_store=canonical_store,
            post_commit_hook=(
                canonical_engine.mark_dirty if canonical_engine is not None else None
            ),
        )
        store.set_meta("started_at", started_at.isoformat(), started_at.isoformat())
        store.set_meta("channel", settings.ssi_channel, started_at.isoformat())
        store.set_meta("universe_size", str(len(universe)), started_at.isoformat())
        for key, value in live_health().items():
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
            if volume_engine is not None and volume_qa_logger is not None:
                _advance_volume_shadow(
                    volume_engine,
                    volume_qa_logger,
                    collector,
                    now,
                    live_runtime=live_runtime,
                )
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
                if live_runtime is not None:
                    for key, value in live_runtime.health().items():
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
                if live_runtime is not None:
                    live_runtime.close()
            finally:
                try:
                    canonical_store.close()
                finally:
                    store.close()


if __name__ == "__main__":
    raise SystemExit(main())
