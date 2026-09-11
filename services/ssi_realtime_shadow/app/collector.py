from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .storage import SQLiteStore

LOG = logging.getLogger(__name__)
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


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


def _parse_date(value: Any, fallback: date) -> str:
    if not value:
        return fallback.isoformat()
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return fallback.isoformat()


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

    for key in ("data", "Data", "payload", "Payload", "message", "Message"):
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


class QuoteCollector:
    def __init__(self, universe: set[str], store: SQLiteStore) -> None:
        self.universe = universe
        self.store = store
        self.stats = CollectorStats()
        self._prev_total: dict[tuple[str, str], int] = {}
        self._first_minute: dict[tuple[str, str], str] = {}
        self.last_event_at: datetime | None = None

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

            trading_date = _parse_date(_first(payload, "TradingDate"), now.date())
            event_time, minute = _parse_time(_first(payload, "Time"), now)
            last_price = _to_float(_first(payload, "LastPrice", "Close"))
            total_volume = _to_int(_first(payload, "TotalVol", "TotalVolume"))

            if last_price is None or last_price <= 0:
                self.stats.ignored_without_price += 1
                continue

            key = (symbol, trading_date)
            previous_total = self._prev_total.get(key)
            if previous_total is None:
                previous_total = self.store.get_last_total(symbol, trading_date)

            if total_volume is None or previous_total is None:
                volume_delta = 0
            elif total_volume >= previous_total:
                volume_delta = total_volume - previous_total
            else:
                LOG.warning(
                    "Cumulative volume moved backwards for %s on %s: %s -> %s",
                    symbol,
                    trading_date,
                    previous_total,
                    total_volume,
                )
                volume_delta = 0

            if total_volume is not None:
                self._prev_total[key] = total_volume

            first_minute = self._first_minute.setdefault(key, minute)
            is_partial = minute == first_minute
            updated_at = now.isoformat()

            self.store.upsert_minute_bar(
                trading_date=trading_date,
                minute=minute,
                symbol=symbol,
                price=last_price,
                volume_delta=volume_delta,
                total_volume=total_volume,
                is_partial=is_partial,
                updated_at=updated_at,
            )

            self.store.upsert_latest_quote(
                {
                    "symbol": symbol,
                    "trading_date": trading_date,
                    "event_time": event_time,
                    "last_price": last_price,
                    "total_volume": total_volume,
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
                    "exchange": str(_first(payload, "Exchange", "MarketId") or ""),
                    "trading_session": str(_first(payload, "TradingSession") or ""),
                    "trading_status": str(_first(payload, "TradingStatus") or ""),
                    "updated_at": updated_at,
                }
            )
            self.stats.accepted_events += 1
            self.last_event_at = now

    def snapshot_stats(self) -> dict[str, int]:
        return {
            "received_messages": self.stats.received_messages,
            "accepted_events": self.stats.accepted_events,
            "ignored_outside_universe": self.stats.ignored_outside_universe,
            "ignored_without_price": self.stats.ignored_without_price,
        }
