from __future__ import annotations

import logging
import signal
import threading
import time
from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace
from typing import ContextManager

from .collector import QuoteCollector
from .live_projection import LiveProjectionWorker
from .live_state_runtime import LiveStateRuntime
from .market_session import VN_TZ
from .postgres_shadow import PostgresShadowWriter
from .realtime_volume import RealtimeVolumeEngine, VolumeEvent, VolumeSnapshot
from .settings import Settings
from .ssi_stream_runtime import CanonicalProgress, SSIStreamSupervisor
from .storage import SQLiteStore
from .universe import load_universe

LOG = logging.getLogger("ssi_shadow")
MAIN_LOOP_HEARTBEAT_KEY = "main_loop_heartbeat_at"
MAIN_LOOP_HEARTBEAT_INTERVAL_SECONDS = 10.0


def _refresh_main_loop_heartbeat(
    store: SQLiteStore,
    now: datetime,
    *,
    monotonic_now: float,
    last_refresh_monotonic: float | None,
) -> float:
    """Commit liveness evidence produced only by the operational main loop."""
    if (
        last_refresh_monotonic is not None
        and monotonic_now - last_refresh_monotonic
        < MAIN_LOOP_HEARTBEAT_INTERVAL_SECONDS
    ):
        return last_refresh_monotonic
    local_now = (
        now.replace(tzinfo=VN_TZ)
        if now.tzinfo is None
        else now.astimezone(VN_TZ)
    )
    timestamp = local_now.isoformat()
    store.set_meta(MAIN_LOOP_HEARTBEAT_KEY, timestamp, timestamp)
    store.commit()
    return monotonic_now


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


def _start_postgres_shadow(settings: Settings) -> PostgresShadowWriter | None:
    if not settings.postgres_shadow_enabled:
        LOG.info("PostgreSQL shadow writer disabled")
        return None
    try:
        writer = PostgresShadowWriter(
            settings.postgres_shadow_dsn,
            flush_seconds=settings.postgres_shadow_flush_seconds,
            batch_size=settings.postgres_shadow_batch_size,
            queue_size=settings.postgres_shadow_queue_size,
        )
        writer.start()
    except Exception:
        LOG.exception(
            "PostgreSQL shadow writer failed to initialize; continuing SQLite runtime"
        )
        return None
    LOG.info(
        "PostgreSQL shadow writer enabled: flush_seconds=%s batch_size=%s "
        "queue_size=%s",
        settings.postgres_shadow_flush_seconds,
        settings.postgres_shadow_batch_size,
        settings.postgres_shadow_queue_size,
    )
    return writer


def _stop_postgres_shadow(writer: PostgresShadowWriter | None) -> None:
    if writer is None:
        return
    try:
        writer.stop()
    except Exception:
        LOG.exception(
            "PostgreSQL shadow shutdown failed; continuing normal shutdown"
        )


def _volume_event_handler(
    engine: RealtimeVolumeEngine,
    qa_logger: VolumeShadowQALogger,
    on_snapshot_logged: Callable[[], None],
    *,
    engine_lock: ContextManager[object],
) -> Callable[[VolumeEvent], VolumeSnapshot]:
    def handle(event: VolumeEvent) -> VolumeSnapshot:
        with engine_lock:
            snapshot = engine.on_event(event)
        if qa_logger.log_if_changed(snapshot):
            on_snapshot_logged()
        return snapshot

    return handle


def _advance_volume_shadow(
    engine: RealtimeVolumeEngine,
    qa_logger: VolumeShadowQALogger,
    collector: QuoteCollector,
    now: datetime,
    *,
    engine_lock: ContextManager[object],
    projection_worker: LiveProjectionWorker | None = None,
) -> None:
    try:
        with engine_lock:
            changed = engine.advance_time(now)
            for snapshot in changed.values():
                if qa_logger.log_if_changed(snapshot):
                    collector.stats.volume_shadow_snapshots += 1
                if projection_worker is not None:
                    projection_worker.offer(snapshot, observed_at=now)
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
    stop_event = threading.Event()
    volume_engine = _start_volume_shadow(settings)
    volume_qa_logger = (
        VolumeShadowQALogger(settings.volume_shadow_symbols)
        if volume_engine is not None
        else None
    )
    started_at = datetime.now(VN_TZ)
    live_runtime: LiveStateRuntime | None = None
    projection_worker: LiveProjectionWorker | None = None
    collector: QuoteCollector | None = None
    stream_supervisor: SSIStreamSupervisor | None = None
    # One guard orders callback on_event and timer advance_time mutations.  The
    # collector retains it through its post-transaction projection offer.
    engine_lock = threading.RLock()
    postgres_shadow = _start_postgres_shadow(settings)
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
            projection_worker = LiveProjectionWorker(live_runtime)
            projection_worker.start()
            LOG.info(
                "CCC V2 live projection worker initialized: %s",
                projection_worker.health(),
            )
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
            return live_runtime.health()
        return {
            "live_state_enabled": settings.live_state_enabled,
            "live_state_initialized": False,
            "live_state_updates": 0,
            "live_state_errors": int(settings.live_state_enabled),
            "live_state_last_update_at": None,
            "live_state_trading_date": started_at.date().isoformat(),
            "live_state_baseline_as_of_date": (
                volume_engine.baseline.as_of_date if volume_engine is not None else None
            ),
            "live_state_baseline_ready": False,
            "live_state_market_db_path": str(settings.market_v2_database_path),
            "live_state_history_available": settings.ssi_history_path.is_file(),
        }

    def runtime_health() -> dict[str, object]:
        values = live_health()
        if projection_worker is not None:
            values.update(projection_worker.health())
        else:
            values.update(
                {
                    "live_projection_enabled": settings.live_state_enabled,
                    "live_projection_started": False,
                    "live_projection_running": False,
                    "live_projection_healthy": not settings.live_state_enabled,
                    "live_projection_offered": 0,
                    "live_projection_coalesced": 0,
                    "live_projection_dropped": 0,
                    "live_projection_processed": 0,
                    "live_projection_errors": int(settings.live_state_enabled),
                    "live_projection_pending": 0,
                    "live_projection_max_pending": 0,
                    "live_projection_last_success_at": None,
                    "live_projection_last_error": None,
                }
            )
        if stream_supervisor is not None:
            values.update(stream_supervisor.health())
        else:
            values.update(
                {
                    "ssi_stream_state": "DISCONNECTED",
                    "ssi_stream_generation": 0,
                    "ssi_stream_reconnects_total": 0,
                    "ssi_stream_consecutive_failures": 0,
                    "ssi_stream_last_open_at": None,
                    "ssi_stream_last_close_at": None,
                    "ssi_stream_last_error_at": None,
                    "ssi_stream_last_recovery_reason": None,
                    "ssi_stream_last_recovered_at": None,
                }
            )
        values["ssi_last_provider_message_at"] = (
            collector.last_provider_message_at.isoformat()
            if collector is not None
            and collector.last_provider_message_at is not None
            else None
        )
        values["ssi_last_canonical_write_at"] = (
            collector.last_canonical_write_at.isoformat()
            if collector is not None
            and collector.last_canonical_write_at is not None
            else None
        )
        if postgres_shadow is not None:
            values.update(postgres_shadow.health())
        else:
            values.update(
                {
                    "postgres_shadow_enabled": settings.postgres_shadow_enabled,
                    "postgres_shadow_started": False,
                    "postgres_shadow_healthy": not settings.postgres_shadow_enabled,
                    "postgres_shadow_connected": False,
                    "postgres_shadow_accepting": False,
                    "postgres_shadow_pending": 0,
                }
            )
        return values

    # Universe loading remains after all local live-state hydration so the stream
    # cannot start before the runtime is ready.
    try:
        universe = load_universe(settings)
    except Exception:
        _stop_postgres_shadow(postgres_shadow)
        projection_stopped = (
            projection_worker.stop() if projection_worker is not None else True
        )
        if live_runtime is not None and projection_stopped:
            live_runtime.close()
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
        def snapshot_logged() -> None:
            assert collector is not None
            collector.stats.volume_shadow_snapshots += 1

        volume_handler = (
            _volume_event_handler(
                volume_engine,
                volume_qa_logger,
                snapshot_logged,
                engine_lock=engine_lock,
            )
            if volume_engine is not None and volume_qa_logger is not None
            else None
        )
        collector = QuoteCollector(
            universe,
            store,
            started_at=started_at,
            volume_event_handler=volume_handler,
            volume_snapshot_handler=(
                lambda snapshot, event: projection_worker.offer(
                    snapshot, event=event
                )
                if projection_worker is not None
                else False
            ),
            volume_engine_lock=engine_lock,
            extra_stats_provider=runtime_health,
            postgres_shadow_sink=postgres_shadow,
        )
        stream_supervisor = SSIStreamSupervisor(
            config=cfg,
            channel=settings.ssi_channel,
            on_message=collector.on_message,
            progress_provider=lambda: CanonicalProgress(
                accepted_events=collector.stats.accepted_events,
                last_canonical_write_at=collector.last_canonical_write_at,
            ),
            client_factory=MarketDataClient,
            stream_factory=MarketDataStream,
            reconnect_max_attempts=settings.ssi_reconnect_max_attempts,
            reconnect_backoff_seconds=(
                settings.ssi_reconnect_backoff_seconds
            ),
            reconnect_progress_timeout_seconds=(
                settings.ssi_reconnect_progress_timeout_seconds
            ),
        )
        store.set_meta("started_at", started_at.isoformat(), started_at.isoformat())
        store.set_meta("channel", settings.ssi_channel, started_at.isoformat())
        store.set_meta("universe_size", str(len(universe)), started_at.isoformat())

        LOG.info(
            "Starting SSI shadow collector: channel=%s universe=%s db=%s",
            settings.ssi_channel,
            len(universe),
            settings.database_path,
        )
        stream_supervisor.start()
        heartbeat_monotonic = _refresh_main_loop_heartbeat(
            store,
            started_at,
            monotonic_now=time.monotonic(),
            last_refresh_monotonic=None,
        )
        for key, value in runtime_health().items():
            store.set_meta(key, str(value), started_at.isoformat())
        store.commit()

        last_stats_log = time.monotonic()
        while not stop_event.wait(1):
            now = datetime.now(VN_TZ)
            loop_monotonic = time.monotonic()
            heartbeat_monotonic = _refresh_main_loop_heartbeat(
                store,
                now,
                monotonic_now=loop_monotonic,
                last_refresh_monotonic=heartbeat_monotonic,
            )
            stream_supervisor.tick(
                now, stale_after_seconds=settings.stale_stream_seconds
            )
            stream_supervisor.raise_if_fatal()
            if volume_engine is not None and volume_qa_logger is not None:
                _advance_volume_shadow(
                    volume_engine,
                    volume_qa_logger,
                    collector,
                    now,
                    engine_lock=engine_lock,
                    projection_worker=projection_worker,
                )

            if time.monotonic() - last_stats_log >= 60:
                stats = collector.snapshot_stats()
                LOG.info("collector stats: %s", stats)
                store.set_meta("last_stats", str(stats), now.isoformat())
                for key, value in runtime_health().items():
                    store.set_meta(key, str(value), now.isoformat())
                store.commit()
                last_stats_log = time.monotonic()

        return 0
    finally:
        if stream_supervisor is not None:
            stream_supervisor.stop()
        now = datetime.now(VN_TZ).isoformat()
        try:
            store.set_meta("stopped_at", now, now)
            store.commit()
        finally:
            try:
                _stop_postgres_shadow(postgres_shadow)
            finally:
                try:
                    projection_stopped = (
                        projection_worker.stop()
                        if projection_worker is not None
                        else True
                    )
                    if live_runtime is not None and projection_stopped:
                        live_runtime.close()
                    elif live_runtime is not None:
                        LOG.error(
                            "Live projection worker did not stop before timeout; "
                            "skipping live-state close during process shutdown"
                        )
                finally:
                    store.close()


if __name__ == "__main__":
    raise SystemExit(main())
