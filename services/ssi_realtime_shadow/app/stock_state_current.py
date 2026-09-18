"""Reusable projection and upsert for the canonical V2 current stock state."""

from __future__ import annotations

import math
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .daily_ma import MAResult
from .market_session import MarketSession, normalize_exchange
from .market_storage_schema import canonical_timestamp
from .price_momentum import PriceMomentum
from .realtime_volume import VolumeSnapshot
from .signal_auction import AuctionSignalMetrics
from .signal_config import SignalConfig, load_signal_config
from .signal_engine import TechnicalState, classify_signal


_DEFAULT_CONFIG = load_signal_config()
ENGINE_VERSION = _DEFAULT_CONFIG.engine_version
CONFIG_VERSION = _DEFAULT_CONFIG.config_version
BASELINE_TARGET_SESSIONS = 10
SIGNAL_SUMMARY_VI = _DEFAULT_CONFIG.states["NORMAL"].summary_vi


@dataclass(frozen=True, slots=True)
class LatestQuote:
    symbol: str
    exchange: str
    trading_date: str
    event_at: datetime
    updated_at: str
    last_price: float
    total_volume: int | None = None
    ref_price: float | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    bid_price1: float | None = None
    bid_volume1: int | None = None
    ask_price1: float | None = None
    ask_volume1: int | None = None
    change_value: float | None = None
    change_pct: float | None = None


_STATE_COLUMNS = (
    "symbol", "exchange", "trading_date",
    "last_price", "ref_price", "ceiling_price", "floor_price",
    "open_price", "high_price", "low_price", "change_value", "change_pct",
    "total_volume", "total_value", "bid_price1", "bid_volume1",
    "ask_price1", "ask_volume1",
    "session_type", "session_id", "session_started_at", "session_ends_at",
    "elapsed_valid_minutes",
    "ma10", "ma200", "ma10_sessions", "ma200_sessions",
    "distance_ma10_pct", "distance_ma200_pct", "above_ma10", "above_ma200",
    "cumulative_volume", "day_rvol", "volume_15", "avg_volume_15", "rvol15",
    "volume_30", "avg_volume_30", "rvol30", "opening_volume",
    "avg_opening_volume", "opening_rvol", "baseline_sessions_used",
    "baseline_target_sessions", "baseline_coverage_pct",
    "price5_pct", "price15_pct", "breakout_state", "trigger_price", "trigger_at",
    "signal_state", "signal_level", "signal_direction", "reason_codes_json",
    "signal_summary_vi", "signal_at",
    "previous_signal_state", "state_changed_at", "engine_version", "config_version",
    "ato_volume", "ato_avg_volume_10", "ato_rvol",
    "ato_baseline_sessions_used", "ato_baseline_quality",
    "atc_volume", "atc_avg_volume_10", "atc_rvol",
    "atc_baseline_sessions_used", "atc_baseline_quality", "atc_price_impact_pct",
    "feed_status", "quality_status", "metrics_trusted", "event_at", "updated_at",
)


def _distance(price: float, average: float | None) -> float | None:
    if average is None or average <= 0:
        return None
    return (price / average - 1.0) * 100.0


def _above(price: float, average: float | None) -> int | None:
    return None if average is None else int(price > average)


def _volume_is_trusted(
    snapshot: VolumeSnapshot | None, *, baseline_coverage_proven: bool
) -> bool:
    if snapshot is None or not baseline_coverage_proven:
        return False
    untrusted_reasons = {
        "CURRENT_GAP",
        "CURRENT_PARTIAL",
        "NON_TRUSTED_QUALITY",
        "NO_BASELINE",
        "INSUFFICIENT_HISTORY",
    }
    return (
        snapshot.metrics_trusted
        and snapshot.quality_status == "TRUSTED"
        and snapshot.baseline_sessions_used >= BASELINE_TARGET_SESSIONS
        and snapshot.active_sessions_used >= snapshot.baseline_sessions_used
        and not untrusted_reasons.intersection(snapshot.reasons)
    )


def project_stock_state(
    *,
    quote: LatestQuote,
    session: MarketSession,
    volume: VolumeSnapshot | None,
    moving_averages: MAResult,
    price_momentum: PriceMomentum,
    baseline_coverage_proven: bool = False,
    auction: AuctionSignalMetrics | None = None,
    previous_signal_state: str | None = None,
    signal_config: SignalConfig | None = None,
    recent_high_retreat_pct: float | None = None,
    feed_status: str = "EXPECTED_IDLE",
) -> dict[str, Any]:
    """Combine existing engines into one conservative current-state row."""
    symbol = str(quote.symbol or "").strip().upper()
    exchange = normalize_exchange(quote.exchange)
    price = float(quote.last_price)
    if not symbol or not math.isfinite(price) or price <= 0:
        raise ValueError("quote requires a symbol and positive finite last_price")
    if quote.trading_date != session.trading_date.isoformat():
        raise ValueError("quote and market session trading dates differ")
    if session.exchange != exchange:
        raise ValueError("quote and market session exchanges differ")
    if moving_averages.symbol != symbol:
        raise ValueError("quote and moving-average symbols differ")
    if moving_averages.as_of_date != quote.trading_date:
        raise ValueError("moving-average cutoff must equal the state trading date")
    if volume is not None and (
        volume.symbol != symbol
        or volume.exchange != exchange
        or volume.trading_date != quote.trading_date
    ):
        raise ValueError("volume snapshot identity differs from quote")

    baseline_used = volume.baseline_sessions_used if volume is not None else 0
    if not 0 <= baseline_used <= BASELINE_TARGET_SESSIONS:
        raise ValueError("baseline_sessions_used must be between 0 and 10")
    trusted = _volume_is_trusted(
        volume, baseline_coverage_proven=baseline_coverage_proven
    )
    quality_status = (
        "TRUSTED" if trusted else "UNAVAILABLE" if volume is None or baseline_used == 0 else "DEGRADED"
    )

    config = signal_config or _DEFAULT_CONFIG
    auction = auction or AuctionSignalMetrics()
    signal_metrics_trusted = trusted
    if session.session_type.value == "OPEN_AUCTION":
        signal_metrics_trusted = bool(
            auction.ato_rvol is not None
            and auction.ato_baseline_sessions_used == config.exact_previous_sessions
            and auction.ato_baseline_quality == "PROVEN"
        )
    elif session.session_type.value == "CLOSE_AUCTION":
        signal_metrics_trusted = bool(
            auction.atc_rvol is not None
            and auction.atc_baseline_sessions_used == config.exact_previous_sessions
            and auction.atc_baseline_quality in {"PROVEN", "MIXED", "INFERRED_BOUNDARY"}
        )
    if signal_metrics_trusted:
        quality_status = "TRUSTED"
    technical = TechnicalState(
        session_type=session.session_type.value,
        last_price=price,
        day_rvol=volume.day_rvol if volume else None,
        rvol15=volume.rvol_15 if volume else None,
        rvol30=volume.rvol_30 if volume else None,
        price5_pct=price_momentum.price5_pct,
        price15_pct=price_momentum.price15_pct,
        ma10=moving_averages.ma10,
        ma200=moving_averages.ma200,
        distance_ma10_pct=_distance(price, moving_averages.ma10),
        distance_ma200_pct=_distance(price, moving_averages.ma200),
        recent_high_retreat_pct=recent_high_retreat_pct,
        ato_rvol=auction.ato_rvol,
        ato_gap_pct=auction.ato_gap_pct,
        ato_baseline_sessions_used=auction.ato_baseline_sessions_used,
        ato_baseline_quality=auction.ato_baseline_quality,
        atc_rvol=auction.atc_rvol,
        atc_volume_share_pct=auction.atc_volume_share_pct,
        atc_price_impact_pct=auction.atc_price_impact_pct,
        atc_baseline_sessions_used=auction.atc_baseline_sessions_used,
        atc_baseline_quality=auction.atc_baseline_quality,
        baseline_sessions_used=baseline_used,
        metrics_trusted=signal_metrics_trusted,
    )
    decision = classify_signal(technical, previous_signal_state, config)

    values: dict[str, Any] = {
        "symbol": symbol,
        "exchange": exchange,
        "trading_date": quote.trading_date,
        "last_price": price,
        "ref_price": quote.ref_price,
        "ceiling_price": None,
        "floor_price": None,
        "open_price": quote.open_price,
        "high_price": quote.high_price,
        "low_price": quote.low_price,
        "change_value": quote.change_value,
        "change_pct": quote.change_pct,
        "total_volume": quote.total_volume,
        "total_value": None,
        "bid_price1": quote.bid_price1,
        "bid_volume1": quote.bid_volume1,
        "ask_price1": quote.ask_price1,
        "ask_volume1": quote.ask_volume1,
        "session_type": session.session_type.value,
        "session_id": session.session_id,
        "session_started_at": canonical_timestamp(session.session_start) if session.session_start else None,
        "session_ends_at": canonical_timestamp(session.session_end) if session.session_end else None,
        "elapsed_valid_minutes": session.elapsed_valid_trading_minutes,
        "ma10": moving_averages.ma10,
        "ma200": moving_averages.ma200,
        "ma10_sessions": moving_averages.ma10_sessions,
        "ma200_sessions": moving_averages.ma200_sessions,
        "distance_ma10_pct": _distance(price, moving_averages.ma10),
        "distance_ma200_pct": _distance(price, moving_averages.ma200),
        "above_ma10": _above(price, moving_averages.ma10),
        "above_ma200": _above(price, moving_averages.ma200),
        "cumulative_volume": volume.cumulative_volume if volume else None,
        "day_rvol": volume.day_rvol if volume else None,
        "volume_15": volume.volume_15 if volume else None,
        "avg_volume_15": volume.avg_volume_15 if volume else None,
        "rvol15": volume.rvol_15 if volume else None,
        "volume_30": volume.volume_30 if volume else None,
        "avg_volume_30": volume.avg_volume_30 if volume else None,
        "rvol30": volume.rvol_30 if volume else None,
        "opening_volume": volume.opening_volume if volume else None,
        "avg_opening_volume": volume.avg_opening_volume if volume else None,
        "opening_rvol": volume.opening_rvol if volume else None,
        "baseline_sessions_used": baseline_used,
        "baseline_target_sessions": BASELINE_TARGET_SESSIONS,
        "baseline_coverage_pct": baseline_used * 100.0 / BASELINE_TARGET_SESSIONS,
        "price5_pct": price_momentum.price5_pct,
        "price15_pct": price_momentum.price15_pct,
        "breakout_state": None,
        "trigger_price": None,
        "trigger_at": None,
        "signal_state": decision.signal_state,
        "signal_level": decision.signal_level,
        "signal_direction": decision.signal_direction,
        "reason_codes_json": json.dumps(
            list(decision.reason_codes), ensure_ascii=False, separators=(",", ":")
        ),
        "signal_summary_vi": decision.signal_summary_vi,
        "signal_at": None,
        "previous_signal_state": previous_signal_state,
        "state_changed_at": None,
        "engine_version": config.engine_version,
        "config_version": config.config_version,
        "ato_volume": auction.ato_volume,
        "ato_avg_volume_10": auction.ato_avg_volume_10,
        "ato_rvol": auction.ato_rvol,
        "ato_baseline_sessions_used": auction.ato_baseline_sessions_used,
        "ato_baseline_quality": auction.ato_baseline_quality,
        "atc_volume": auction.atc_volume,
        "atc_avg_volume_10": auction.atc_avg_volume_10,
        "atc_rvol": auction.atc_rvol,
        "atc_baseline_sessions_used": auction.atc_baseline_sessions_used,
        "atc_baseline_quality": auction.atc_baseline_quality,
        "atc_price_impact_pct": auction.atc_price_impact_pct,
        "feed_status": feed_status,
        "quality_status": quality_status,
        "metrics_trusted": int(signal_metrics_trusted),
        "event_at": canonical_timestamp(quote.event_at),
        "updated_at": canonical_timestamp(quote.updated_at),
    }
    return values


def upsert_stock_state_current(
    connection: sqlite3.Connection, values: dict[str, Any]
) -> None:
    """Upsert one projected row without committing or writing signal history."""
    missing = set(_STATE_COLUMNS) - values.keys()
    if missing:
        raise ValueError(f"stock-state projection is missing columns: {sorted(missing)}")
    projected = dict(values)
    existing = connection.execute(
        "SELECT trading_date, signal_state, previous_signal_state, "
        "state_changed_at, signal_at "
        "FROM stock_state_current WHERE symbol = ?",
        (projected["symbol"],),
    ).fetchone()
    if existing is not None and existing[0] != projected["trading_date"]:
        existing = None
    event_at = projected["event_at"]
    current = projected["signal_state"]
    if existing is None:
        projected["previous_signal_state"] = None
        projected["state_changed_at"] = event_at if current != "NORMAL" else None
        projected["signal_at"] = event_at if current != "NORMAL" else None
    elif existing[1] != current:
        projected["previous_signal_state"] = existing[1]
        projected["state_changed_at"] = event_at
        projected["signal_at"] = event_at if current != "NORMAL" else None
    else:
        projected["previous_signal_state"] = existing[2]
        projected["state_changed_at"] = existing[3]
        projected["signal_at"] = existing[4]
    assignments = ", ".join(
        f"{column}=excluded.{column}" for column in _STATE_COLUMNS if column != "symbol"
    )
    connection.execute(
        f"""
        INSERT INTO stock_state_current ({', '.join(_STATE_COLUMNS)})
        VALUES ({', '.join('?' for _ in _STATE_COLUMNS)})
        ON CONFLICT(symbol) DO UPDATE SET {assignments}
        """,
        tuple(projected[column] for column in _STATE_COLUMNS),
    )
