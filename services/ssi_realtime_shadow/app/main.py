from __future__ import annotations

import logging
import signal
import threading
import time
from datetime import datetime, time as dtime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from .collector import QuoteCollector
from .settings import Settings
from .storage import SQLiteStore
from .universe import load_universe

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
LOG = logging.getLogger("ssi_shadow")


def _market_should_be_streaming(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.time()
    morning = dtime(8, 45) <= t <= dtime(11, 35)
    afternoon = dtime(12, 55) <= t <= dtime(15, 5)
    return morning or afternoon


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

    universe = load_universe(settings)
    store = SQLiteStore(
        settings.database_path,
        commit_every_events=settings.commit_every_events,
        commit_every_seconds=settings.commit_every_seconds,
    )
    collector = QuoteCollector(universe, store)
    stop_event = threading.Event()
    stream_error = threading.Event()

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

        started_at = datetime.now(VN_TZ)
        store.set_meta("started_at", started_at.isoformat(), started_at.isoformat())
        store.set_meta("channel", settings.ssi_channel, started_at.isoformat())
        store.set_meta("universe_size", str(len(universe)), started_at.isoformat())
        store.commit()

        LOG.info(
            "Starting SSI shadow collector: channel=%s universe=%s db=%s",
            settings.ssi_channel,
            len(universe),
            settings.database_path,
        )
        stream.start(collector.on_message, on_error, settings.ssi_channel)

        last_stats_log = time.monotonic()
        while not stop_event.wait(1):
            if stream_error.is_set():
                raise RuntimeError("SSI stream reported an error; process will exit for restart")

            now = datetime.now(VN_TZ)
            if (
                _market_should_be_streaming(now)
                and collector.last_event_at is not None
                and (now - collector.last_event_at).total_seconds() > settings.stale_stream_seconds
            ):
                raise RuntimeError(
                    f"SSI stream stale for more than {settings.stale_stream_seconds}s during market session"
                )

            if time.monotonic() - last_stats_log >= 60:
                stats = collector.snapshot_stats()
                LOG.info("collector stats: %s", stats)
                store.set_meta("last_stats", str(stats), now.isoformat())
                store.commit()
                last_stats_log = time.monotonic()

        return 0
    finally:
        now = datetime.now(VN_TZ).isoformat()
        try:
            store.set_meta("stopped_at", now, now)
            store.commit()
        finally:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
