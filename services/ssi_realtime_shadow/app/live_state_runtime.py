"""Live CCC V2 current-state orchestration over the canonical SSI collector.

This module deliberately does not prove the active day against DailyOhlc.  The
immutable exact-10 baseline is the historical proof; the active-day trust gate
is the canonical :class:`VolumeSnapshot` produced from the live stream.
"""

from __future__ import annotations

import logging
import math
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .auction_history import Exact10Result, read_atc_exact10, read_ato_exact10
from .daily_ma import MAResult, calculate_moving_averages_from_db
from .market_session import VN_TZ, classify_market_session, normalize_exchange
from .market_storage_schema import ensure_market_storage_schema
from .price_momentum import MinutePrice, calculate_price_momentum
from .realtime_volume import RealtimeVolumeEngine, VolumeEvent, VolumeSnapshot
from .signal_auction import AuctionSignalMetrics, build_auction_signal_metrics
from .signal_config import SignalConfig, load_signal_config
from .stock_state_current import (
    LatestQuote,
    project_stock_state,
    upsert_stock_state_current,
)
from .storage import SQLiteStore
from .volume_baseline import COVERAGE_PROOF, load_candidate_market_sessions


LOG = logging.getLogger(__name__)
EXPECTED_BASELINE_SCHEMA = 2
EXPECTED_LOOKBACK = 10


@dataclass(frozen=True, slots=True)
class HydrationReport:
    trading_date: str
    rows_seen: int
    rows_hydrated: int
    symbols_hydrated: int
    rows_rejected: int
    cumulative_by_symbol: dict[str, int]


def _local(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=VN_TZ)
    return moment.astimezone(VN_TZ)


def hydrate_realtime_volume_from_store(
    engine: RealtimeVolumeEngine,
    store: SQLiteStore,
    *,
    active_at: datetime,
) -> HydrationReport:
    """Replay only the active local date, preserving stored quality evidence."""
    now = _local(active_at)
    trading_date = now.date().isoformat()
    rows = store.get_volume_hydration_rows(trading_date)
    hydrated = 0
    rejected = 0
    symbols: set[str] = set()
    for row in rows:
        try:
            minute = str(row["minute"])
            if minute > now.strftime("%H:%M"):
                raise ValueError("stored minute is in the future")
            event_at = datetime.combine(
                date.fromisoformat(trading_date),
                datetime.strptime(minute, "%H:%M").time(),
                tzinfo=VN_TZ,
            )
            event = VolumeEvent(
                symbol=str(row["symbol"]),
                exchange=normalize_exchange(str(row["exchange"] or "")),
                trading_date=trading_date,
                event_time=event_at,
                minute=minute,
                volume_delta=max(0, int(row["volume"])),
                total_volume=(
                    int(row["last_total_volume"])
                    if row["last_total_volume"] is not None
                    else None
                ),
                quality_status=str(row["quality_status"] or "LEGACY_UNVERIFIED"),
                is_partial=bool(row["is_partial"]),
                has_gap=bool(row["has_gap"]),
                data_source=str(row["data_source"] or "SSI_STREAM"),
            )
            engine.on_event(event)
            hydrated += 1
            symbols.add(event.symbol)
        except (KeyError, TypeError, ValueError):
            rejected += 1
            LOG.exception(
                "Rejected unsafe live volume hydration row: symbol=%s date=%s minute=%s",
                row.get("symbol"),
                trading_date,
                row.get("minute"),
            )
    engine.advance_time(now)
    cumulative = {
        symbol: snapshot.cumulative_volume
        for symbol, snapshot in engine.get_all_snapshots().items()
        if snapshot.trading_date == trading_date
    }
    return HydrationReport(
        trading_date=trading_date,
        rows_seen=len(rows),
        rows_hydrated=hydrated,
        symbols_hydrated=len(symbols),
        rows_rejected=rejected,
        cumulative_by_symbol=cumulative,
    )


def _finite(value: object, *, required: bool = False) -> float | None:
    if value in (None, ""):
        if required:
            raise ValueError("required quote price is missing")
        return None
    parsed = float(value)
    if not math.isfinite(parsed) or (required and parsed <= 0):
        raise ValueError("quote price must be positive and finite")
    return parsed


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed < 0:
        raise ValueError("quote integer must not be negative")
    return parsed


def _quote_event_at(trading_date: str, raw: object) -> datetime:
    value = str(raw or "").strip()
    for pattern in ("%H:%M:%S", "%H:%M:%S.%f", "%H:%M"):
        try:
            parsed = datetime.strptime(value, pattern).time()
            return datetime.combine(date.fromisoformat(trading_date), parsed, tzinfo=VN_TZ)
        except ValueError:
            pass
    parsed_at = datetime.fromisoformat(value)
    return _local(parsed_at)


def _latest_quote(row: dict[str, Any]) -> LatestQuote:
    trading_date = str(row.get("trading_date") or "")
    event_at = _quote_event_at(trading_date, row.get("event_time"))
    price = _finite(row.get("last_price"), required=True)
    assert price is not None
    return LatestQuote(
        symbol=str(row.get("symbol") or "").strip().upper(),
        exchange=normalize_exchange(str(row.get("exchange") or "")),
        trading_date=trading_date,
        event_at=event_at,
        updated_at=str(row.get("updated_at") or event_at.isoformat()),
        last_price=price,
        total_volume=_optional_int(row.get("total_volume")),
        ref_price=_finite(row.get("ref_price")),
        open_price=_finite(row.get("open")),
        high_price=_finite(row.get("high")),
        low_price=_finite(row.get("low")),
        bid_price1=_finite(row.get("bid_price1")),
        bid_volume1=_optional_int(row.get("bid_vol1")),
        ask_price1=_finite(row.get("ask_price1")),
        ask_volume1=_optional_int(row.get("ask_vol1")),
        change_value=_finite(row.get("change")),
        change_pct=_finite(row.get("ratio_change")),
    )


class LiveStateRuntime:
    """Serialize live projection, cache immutable daily inputs, and persist safely."""

    def __init__(
        self,
        *,
        volume_engine: RealtimeVolumeEngine,
        hot_store: SQLiteStore,
        market_db_path: Path,
        history_db_path: Path,
        active_at: datetime | None = None,
        signal_config: SignalConfig | None = None,
        hydrate_volume: bool = True,
    ) -> None:
        self.volume_engine = volume_engine
        self.hot_store = hot_store
        self.market_db_path = Path(market_db_path)
        self.history_db_path = Path(history_db_path)
        self._lock = threading.RLock()
        self._closed = False
        self._active_date = _local(active_at or datetime.now(VN_TZ)).date().isoformat()
        self._ma_cache: dict[tuple[str, str], MAResult] = {}
        self._auction_cache: dict[
            tuple[str, str], tuple[Exact10Result | None, Exact10Result | None]
        ] = {}
        self._candidate_dates_trading_date: str | None = None
        self._candidate_dates: tuple[str, ...] = ()
        self._previous_state: dict[tuple[str, str], str | None] = {}
        self._last_projection: dict[str, tuple[str, str, str]] = {}
        self._minute_prices: dict[str, dict[str, MinutePrice]] = {}
        self.live_state_updates = 0
        self.live_state_errors = 0
        self.live_state_last_update_at: str | None = None
        self.last_error: str | None = None
        self.health_errors: list[str] = []

        self.baseline_ready = False
        self._record_baseline_health(self._active_date)

        market_resolved = self.market_db_path.resolve()
        protected_sources = {
            self.hot_store.path.resolve(),
            self.history_db_path.resolve(),
            self.volume_engine.baseline.source_path.resolve(),
        }
        if market_resolved in protected_sources:
            raise ValueError("market DB must be separate from hot/history/baseline DBs")

        self.market_db_path.parent.mkdir(parents=True, exist_ok=True)
        market = sqlite3.connect(self.market_db_path, check_same_thread=False)
        try:
            market.row_factory = sqlite3.Row
            market.execute("PRAGMA busy_timeout=5000")
            market.execute("PRAGMA journal_mode=WAL")
            market.execute("PRAGMA synchronous=NORMAL")
            ensure_market_storage_schema(market)
        except Exception:
            market.close()
            raise
        self._market = market
        try:
            self.signal_config = signal_config or load_signal_config()
        except Exception:
            self._market.close()
            self._closed = True
            raise

        self._history: sqlite3.Connection | None = None
        try:
            if self.history_db_path.is_file():
                self._history = sqlite3.connect(
                    f"{self.history_db_path.resolve().as_uri()}?mode=ro", uri=True
                )
                self._history.row_factory = sqlite3.Row
                self._history.execute("PRAGMA query_only=ON")
                self._history.execute("SELECT 1 FROM minute_bars LIMIT 1")
            else:
                self.health_errors.append(
                    "AUCTION_HISTORY_UNAVAILABLE:FileNotFoundError"
                )
                self.live_state_errors += 1
        except sqlite3.Error as exc:
            if self._history is not None:
                self._history.close()
            self._history = None
            self.health_errors.append(
                f"AUCTION_HISTORY_UNAVAILABLE:{type(exc).__name__}"
            )
            self.live_state_errors += 1

        try:
            hydration_at = _local(active_at or datetime.now(VN_TZ))
            self.hydration_report = (
                hydrate_realtime_volume_from_store(
                    self.volume_engine, self.hot_store, active_at=hydration_at
                )
                if hydrate_volume
                else HydrationReport(self._active_date, 0, 0, 0, 0, {})
            )
            if self.hydration_report.rows_rejected:
                self.health_errors.append(
                    "HYDRATION_REJECTED_ROWS:"
                    f"{self.hydration_report.rows_rejected}"
                )
                self.live_state_errors += self.hydration_report.rows_rejected
            self._hydrate_price_cache(self._active_date)
        except Exception:
            if self._history is not None:
                self._history.close()
                self._history = None
            self._market.close()
            self._closed = True
            raise

    @property
    def history_available(self) -> bool:
        return self._history is not None

    def _hydrate_price_cache(self, trading_date: str) -> None:
        self._minute_prices = {
            symbol: {point.minute: point for point in points}
            for symbol, points in self.hot_store.get_day_minute_prices(
                trading_date
            ).items()
        }

    def _record_baseline_health(self, trading_date: str) -> None:
        baseline = self.volume_engine.baseline
        self.baseline_ready = bool(
            baseline.schema_version == EXPECTED_BASELINE_SCHEMA
            and baseline.lookback == EXPECTED_LOOKBACK
            and baseline.coverage_proof == COVERAGE_PROOF
            and baseline.as_of_date == trading_date
        )
        prefix = "BASELINE_NOT_READY:"
        previous = next(
            (item for item in self.health_errors if item.startswith(prefix)),
            None,
        )
        self.health_errors = [
            item for item in self.health_errors if not item.startswith(prefix)
        ]
        if not self.baseline_ready:
            message = (
                "BASELINE_NOT_READY: expected schema=2 lookback=10 "
                f"coverage={COVERAGE_PROOF} as_of={trading_date}; got "
                f"schema={baseline.schema_version} lookback={baseline.lookback} "
                f"coverage={baseline.coverage_proof} as_of={baseline.as_of_date}"
            )
            self.health_errors.append(message)
            if previous != message:
                self.live_state_errors += 1

    def _roll_date(self, trading_date: str) -> None:
        if trading_date == self._active_date:
            return
        self._active_date = trading_date
        self._ma_cache.clear()
        self._auction_cache.clear()
        self._candidate_dates_trading_date = None
        self._candidate_dates = ()
        self._previous_state.clear()
        self._last_projection.clear()
        self._hydrate_price_cache(trading_date)
        self._record_baseline_health(trading_date)

    def _moving_averages(self, symbol: str, trading_date: str) -> MAResult:
        key = (trading_date, symbol)
        value = self._ma_cache.get(key)
        if value is None:
            value = calculate_moving_averages_from_db(
                self._market, symbol=symbol, as_of_date=trading_date
            )
            self._ma_cache[key] = value
        return value

    def _auction_history(
        self, symbol: str, trading_date: str
    ) -> tuple[Exact10Result | None, Exact10Result | None]:
        key = (trading_date, symbol)
        if key in self._auction_cache:
            return self._auction_cache[key]
        result: tuple[Exact10Result | None, Exact10Result | None] = (None, None)
        if self._history is not None:
            try:
                if self._candidate_dates_trading_date != trading_date:
                    self._candidate_dates = tuple(
                        load_candidate_market_sessions(
                            self._history,
                            self._market,
                            as_of_date=trading_date,
                            lookback=EXPECTED_LOOKBACK,
                        )
                    )
                    self._candidate_dates_trading_date = trading_date
                result = (
                    read_ato_exact10(
                        self._market,
                        self._history,
                        self._market,
                        symbol=symbol,
                        as_of_date=trading_date,
                        candidate_dates=self._candidate_dates,
                    ),
                    read_atc_exact10(
                        self._market,
                        self._history,
                        self._market,
                        symbol=symbol,
                        as_of_date=trading_date,
                        candidate_dates=self._candidate_dates,
                    ),
                )
            except (sqlite3.Error, TypeError, ValueError) as exc:
                self.last_error = f"AUCTION_HISTORY_UNAVAILABLE:{type(exc).__name__}"
                self.live_state_errors += 1
                LOG.warning(
                    "Auction history unavailable for %s/%s: %s",
                    symbol,
                    trading_date,
                    exc,
                )
        self._auction_cache[key] = result
        return result

    def _auction_metrics(self, quote: LatestQuote) -> AuctionSignalMetrics:
        ato_history, atc_history = self._auction_history(
            quote.symbol, quote.trading_date
        )
        buckets = {
            item.auction_type: item
            for item in self.hot_store.get_auction_buckets(
                quote.symbol, quote.trading_date
            )
        }
        return build_auction_signal_metrics(
            ato_history=ato_history,
            atc_history=atc_history,
            ato_bucket=buckets.get("OPEN_AUCTION"),
            atc_bucket=buckets.get("CLOSE_AUCTION"),
            ref_price=quote.ref_price,
            total_day_volume=quote.total_volume,
        )

    def _previous(self, symbol: str, trading_date: str) -> str | None:
        key = (trading_date, symbol)
        if key not in self._previous_state:
            row = self._market.execute(
                "SELECT trading_date, signal_state FROM stock_state_current WHERE symbol=?",
                (symbol,),
            ).fetchone()
            self._previous_state[key] = (
                str(row["signal_state"])
                if row is not None and str(row["trading_date"]) == trading_date
                else None
            )
        return self._previous_state[key]

    def _update_price(self, event: VolumeEvent | None) -> None:
        if event is None:
            return
        point = self.hot_store.get_minute_price(
            event.symbol, event.trading_date, event.minute
        )
        if point is not None:
            self._minute_prices.setdefault(event.symbol, {})[event.minute] = point

    def handle_snapshot(
        self,
        snapshot: VolumeSnapshot,
        *,
        event: VolumeEvent | None = None,
        observed_at: datetime | None = None,
        force: bool = False,
    ) -> bool:
        """Project at most once per symbol/clock minute and isolate failures."""
        try:
            with self._lock:
                if self._closed:
                    return False
                self._roll_date(snapshot.trading_date)
                self._update_price(event)
                if event is not None:
                    effective_at = _local(event.event_time)
                    session = classify_market_session(event.exchange, effective_at)
                    cadence = (
                        snapshot.trading_date,
                        effective_at.strftime("%H:%M"),
                        session.session_type.value,
                    )
                    if (
                        not force
                        and self._last_projection.get(snapshot.symbol) == cadence
                    ):
                        return False
                quote_row = self.hot_store.get_latest_quote(
                    snapshot.symbol, snapshot.trading_date
                )
                if quote_row is None:
                    return False
                quote = _latest_quote(quote_row)
                effective_at = (
                    _local(observed_at or quote.event_at)
                    if event is None
                    else effective_at
                )
                if effective_at.date().isoformat() != snapshot.trading_date:
                    return False
                if event is None:
                    session = classify_market_session(quote.exchange, effective_at)
                    cadence = (
                        snapshot.trading_date,
                        effective_at.strftime("%H:%M"),
                        session.session_type.value,
                    )
                if not force and self._last_projection.get(snapshot.symbol) == cadence:
                    return False
                momentum = calculate_price_momentum(
                    exchange=quote.exchange,
                    selected_at=effective_at,
                    current_price=quote.last_price,
                    minute_prices=self._minute_prices.get(snapshot.symbol, {}).values(),
                )
                coverage = self.volume_engine.baseline.coverage.get(snapshot.symbol)
                baseline_proven = bool(
                    self.baseline_ready
                    and coverage is not None
                    and coverage.baseline_sessions_used == EXPECTED_LOOKBACK
                    and coverage.active_sessions_used == EXPECTED_LOOKBACK
                )
                projection = project_stock_state(
                    quote=quote,
                    session=session,
                    volume=snapshot,
                    moving_averages=self._moving_averages(
                        snapshot.symbol, snapshot.trading_date
                    ),
                    price_momentum=momentum,
                    baseline_coverage_proven=baseline_proven,
                    auction=self._auction_metrics(quote),
                    previous_signal_state=self._previous(
                        snapshot.symbol, snapshot.trading_date
                    ),
                    signal_config=self.signal_config,
                    feed_status=(
                        "LIVE"
                        if session.is_continuous or session.is_auction
                        else "EXPECTED_IDLE"
                    ),
                )
                self._market.execute("BEGIN IMMEDIATE")
                try:
                    upsert_stock_state_current(self._market, projection)
                    self._market.commit()
                except Exception:
                    self._market.rollback()
                    raise
                self._previous_state[(snapshot.trading_date, snapshot.symbol)] = str(
                    projection["signal_state"]
                )
                self._last_projection[snapshot.symbol] = cadence
                self.live_state_updates += 1
                self.live_state_last_update_at = datetime.now(VN_TZ).isoformat()
                return True
        except Exception as exc:
            self.live_state_errors += 1
            self.last_error = f"{type(exc).__name__}:{exc}"
            LOG.exception(
                "Live state projection failed: symbol=%s date=%s",
                getattr(snapshot, "symbol", "?"),
                getattr(snapshot, "trading_date", "?"),
            )
            return False

    def health(self) -> dict[str, Any]:
        baseline = self.volume_engine.baseline
        return {
            "live_state_enabled": True,
            "live_state_initialized": not self._closed,
            "live_state_updates": self.live_state_updates,
            "live_state_errors": self.live_state_errors,
            "live_state_last_update_at": self.live_state_last_update_at,
            "live_state_trading_date": self._active_date,
            "live_state_baseline_as_of_date": baseline.as_of_date,
            "live_state_baseline_ready": self.baseline_ready,
            "live_state_market_db_path": str(self.market_db_path),
            "live_state_history_available": self.history_available,
            "live_state_health_errors": tuple(self.health_errors),
            "live_state_last_error": self.last_error,
        }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._history is not None:
                self._history.close()
                self._history = None
            self._market.commit()
            self._market.close()
            self._closed = True


__all__ = [
    "HydrationReport",
    "LiveStateRuntime",
    "hydrate_realtime_volume_from_store",
]
