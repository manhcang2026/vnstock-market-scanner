from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable

from .market_session import (
    VN_TZ,
    market_day_feed_start,
    market_feed_expected,
    market_feed_window_start,
    normalize_exchange,
)
from .normalization import parse_trading_date
from .realtime_volume import VolumeEvent
from .storage import SQLiteStore

LOG = logging.getLogger(__name__)
_NON_EQUITY_MARKETS = {"DER"}


def _first(mapping: dict[str, Any], *names: str) -> Any:
    lowered = {str(k).lower(): v for k, v in mapping.items()}
    for name in names:
        if name in mapping:
            return mapping[name]
        value = lowered.get(name.lower())
        if value is not None:
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any, fallback: datetime) -> tuple[str, str]:
    if not value:
        return fallback.strftime("%H:%M:%S"), fallback.strftime("%H:%M")
    text = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M:%S.%f", "%H%M%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%H:%M:%S"), parsed.strftime("%H:%M")
        except ValueError:
            pass
    return fallback.strftime("%H:%M:%S"), fallback.strftime("%H:%M")


def _first_non_empty(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = _first(mapping, name)
        if value is not None and str(value).strip():
            return value
    return None


def _provider_market(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    raw_market = _first_non_empty(payload, "Market", "MarketId", "Exchange")
    if raw_market is None:
        return None, None
    provider_value = str(raw_market).strip().upper()
    if provider_value in _NON_EQUITY_MARKETS:
        return None, "NON_EQUITY"
    try:
        return normalize_exchange(provider_value), None
    except ValueError:
        return None, "UNKNOWN"


def _event_datetime(trading_date: str, event_time: str) -> datetime:
    return datetime.fromisoformat(f"{trading_date}T{event_time}").replace(tzinfo=VN_TZ)


def _stored_event_datetime(
    trading_date: str, event_time: str | None
) -> datetime | None:
    if not event_time:
        return None
    try:
        return _event_datetime(trading_date, event_time)
    except ValueError:
        return None


def _as_local(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=VN_TZ)
    return moment.astimezone(VN_TZ)


def _extract_payloads(message: Any) -> Iterable[dict[str, Any]]:
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            return []

    if isinstance(message, list):
        out: list[dict[str, Any]] = []
        for item in message:
            out.extend(_extract_payloads(item))
        return out

    if not isinstance(message, dict):
        return []

    if _first(message, "Symbol"):
        return [message]

    for key in (
        "Content",
        "content",
        "data",
        "Data",
        "payload",
        "Payload",
        "message",
        "Message",
    ):
        nested = message.get(key)
        if nested is not None:
            payloads = list(_extract_payloads(nested))
            if payloads:
                return payloads
    return []


@dataclass
class CollectorStats:
    received_messages: int = 0
    accepted_events: int = 0
    ignored_outside_universe: int = 0
    ignored_without_price: int = 0
    ignored_malformed_trading_date: int = 0
    ignored_non_equity_market: int = 0
    ignored_unknown_market: int = 0
    volume_shadow_events: int = 0
    volume_shadow_event_errors: int = 0
    volume_shadow_advance_errors: int = 0
    volume_shadow_snapshots: int = 0


class QuoteCollector:
    def __init__(
        self,
        universe: set[str],
        store: SQLiteStore,
        *,
        started_at: datetime | None = None,
        volume_event_handler: Callable[[VolumeEvent], object] | None = None,
    ) -> None:
        self.universe = universe
        self.store = store
        self.started_at = _as_local(started_at or datetime.now(VN_TZ))
        self.stats = CollectorStats()
        self._prev_total: dict[tuple[str, str], int] = {}
        self._initialized_keys: set[tuple[str, str]] = set()
        self.last_event_at: datetime | None = None
        self.volume_event_handler = volume_event_handler

    def _can_seed_from_zero(self, event_at: datetime, exchange: str | None) -> bool:
        if exchange is None or not market_feed_expected(event_at, exchange):
            return False
        day_start = market_day_feed_start(event_at, exchange)
        window_start = market_feed_window_start(event_at, exchange)
        return (
            day_start is not None
            and window_start == day_start
            and self.started_at <= day_start
        )

    def on_message(self, message: Any) -> None:
        self.stats.received_messages += 1
        now = datetime.now(VN_TZ)
        payloads = list(_extract_payloads(message))
        if not payloads:
            return

        for payload in payloads:
            symbol = str(_first(payload, "Symbol") or "").strip().upper()
            if not symbol:
                continue
            if symbol not in self.universe:
                self.stats.ignored_outside_universe += 1
                continue

            exchange, market_error = _provider_market(payload)
            if market_error == "NON_EQUITY":
                self.stats.ignored_non_equity_market += 1
                LOG.warning("Ignoring non-equity SSI market for %s", symbol)
                continue
            if market_error == "UNKNOWN":
                self.stats.ignored_unknown_market += 1
                LOG.warning(
                    "Ignoring SSI payload for %s: unsupported market %r",
                    symbol,
                    _first_non_empty(payload, "Market", "MarketId", "Exchange"),
                )
                continue

            raw_trading_date = _first(payload, "TradingDate")
            trading_date = parse_trading_date(raw_trading_date, fallback=now.date())
            if trading_date is None:
                self.stats.ignored_malformed_trading_date += 1
                LOG.warning(
                    "Ignoring SSI payload for %s: malformed TradingDate=%r",
                    symbol,
                    raw_trading_date,
                )
                continue

            event_time, minute = _parse_time(_first(payload, "Time"), now)
            event_at = _event_datetime(trading_date, event_time)
            last_price = _to_float(_first(payload, "LastPrice", "Close"))
            total_volume = _to_int(_first(payload, "TotalVol", "TotalVolume"))

            if last_price is None or last_price <= 0:
                self.stats.ignored_without_price += 1
                continue

            key = (symbol, trading_date)
            first_event_in_process = key not in self._initialized_keys
            persisted = (
                self.store.get_latest_quote_state(symbol, trading_date)
                if first_event_in_process
                else None
            )
            self._initialized_keys.add(key)
            previous_total = (
                persisted.total_volume
                if persisted is not None
                else self._prev_total.get(key)
            )
            if previous_total is not None:
                self._prev_total.setdefault(key, previous_total)
            if exchange is None and persisted is not None and persisted.exchange:
                try:
                    exchange = normalize_exchange(persisted.exchange)
                except ValueError:
                    pass

            volume_delta = 0
            is_partial = False
            has_gap = False
            gap_from: str | None = None
            gap_to: str | None = None
            quality_status = "TRUSTED" if exchange is not None else "UNKNOWN_MARKET"

            if persisted is not None:
                persisted_at = _stored_event_datetime(
                    trading_date, persisted.event_time
                )
                same_minute = (
                    persisted_at is not None
                    and persisted_at.strftime("%H:%M") == minute
                )
                if not same_minute:
                    has_gap = True
                    is_partial = True
                    quality_status = "GAP"
                    gap_from = (
                        persisted_at.isoformat()
                        if persisted_at is not None
                        else persisted.updated_at
                    )
                    gap_to = event_at.isoformat()

            if total_volume is None:
                is_partial = True
                if not has_gap:
                    quality_status = "MISSING_TOTAL_VOLUME"
            elif previous_total is None:
                if self._can_seed_from_zero(event_at, exchange):
                    volume_delta = total_volume
                else:
                    is_partial = True
                    if not has_gap:
                        quality_status = "PARTIAL"
                self._prev_total[key] = total_volume
            elif total_volume >= previous_total:
                if not has_gap:
                    volume_delta = total_volume - previous_total
                self._prev_total[key] = total_volume
            else:
                LOG.warning(
                    "Cumulative volume moved backwards for %s on %s: %s -> %s",
                    symbol,
                    trading_date,
                    previous_total,
                    total_volume,
                )
                is_partial = True
                if not has_gap:
                    quality_status = "VOLUME_REGRESSION"

            effective_total_volume = self._prev_total.get(key, previous_total)
            updated_at = now.isoformat()

            self.store.upsert_minute_bar(
                trading_date=trading_date,
                minute=minute,
                symbol=symbol,
                price=last_price,
                volume_delta=volume_delta,
                total_volume=effective_total_volume,
                is_partial=is_partial,
                exchange=exchange,
                quality_status=quality_status,
                has_gap=has_gap,
                gap_from=gap_from,
                gap_to=gap_to,
                updated_at=updated_at,
            )

            self.store.upsert_latest_quote(
                {
                    "symbol": symbol,
                    "trading_date": trading_date,
                    "event_time": event_time,
                    "last_price": last_price,
                    "total_volume": effective_total_volume,
                    "ref_price": _to_float(_first(payload, "RefPrice")),
                    "open": _to_float(_first(payload, "Open")),
                    "high": _to_float(_first(payload, "High")),
                    "low": _to_float(_first(payload, "Low")),
                    "close": _to_float(_first(payload, "Close")),
                    "bid_price1": _to_float(_first(payload, "BidPrice1")),
                    "bid_vol1": _to_int(_first(payload, "BidVol1")),
                    "ask_price1": _to_float(_first(payload, "AskPrice1")),
                    "ask_vol1": _to_int(_first(payload, "AskVol1")),
                    "change": _to_float(_first(payload, "Change")),
                    "ratio_change": _to_float(_first(payload, "RatioChange")),
                    "exchange": exchange,
                    "trading_session": str(
                        _first(payload, "TradingSession") or ""
                    ).strip().upper(),
                    "trading_status": str(_first(payload, "TradingStatus") or ""),
                    "updated_at": updated_at,
                }
            )
            self.stats.accepted_events += 1
            self.last_event_at = now
            if exchange is not None and self.volume_event_handler is not None:
                self.stats.volume_shadow_events += 1
                try:
                    volume_event = VolumeEvent(
                        symbol=symbol,
                        exchange=exchange,
                        trading_date=trading_date,
                        event_time=event_at,
                        minute=minute,
                        volume_delta=volume_delta,
                        total_volume=effective_total_volume,
                        quality_status=quality_status,
                        is_partial=is_partial,
                        has_gap=has_gap,
                    )
                    self.volume_event_handler(volume_event)
                except Exception:
                    self.stats.volume_shadow_event_errors += 1
                    LOG.exception(
                        "CCC V2 volume shadow event failed: symbol=%s minute=%s",
                        symbol,
                        minute,
                    )

    def snapshot_stats(self) -> dict[str, int]:
        return {
            "received_messages": self.stats.received_messages,
            "accepted_events": self.stats.accepted_events,
            "ignored_outside_universe": self.stats.ignored_outside_universe,
            "ignored_without_price": self.stats.ignored_without_price,
            "ignored_malformed_trading_date": self.stats.ignored_malformed_trading_date,
            "ignored_non_equity_market": self.stats.ignored_non_equity_market,
            "ignored_unknown_market": self.stats.ignored_unknown_market,
            "volume_shadow_events": self.stats.volume_shadow_events,
            "volume_shadow_event_errors": self.stats.volume_shadow_event_errors,
            "volume_shadow_advance_errors": self.stats.volume_shadow_advance_errors,
            "volume_shadow_snapshots": self.stats.volume_shadow_snapshots,
        }
