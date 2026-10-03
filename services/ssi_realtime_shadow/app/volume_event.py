"""Normalized SSI volume event contract shared by collector consumers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .market_session import VN_TZ, normalize_exchange


class BaselineValidationError(ValueError):
    """Raised when a derived volume baseline cannot be trusted."""


@dataclass(frozen=True, slots=True)
class VolumeEvent:
    """Canonical volume event produced after SSI collector normalization."""

    symbol: str
    exchange: str
    trading_date: str
    event_time: datetime
    minute: str
    volume_delta: int
    total_volume: int | None
    quality_status: str
    is_partial: bool = False
    has_gap: bool = False
    provider_session: str = ""
    provider_total_volume: int | None = None
    data_source: str = "SSI_STREAM"

    def __post_init__(self) -> None:
        symbol = str(self.symbol or "").strip().upper()
        if not symbol:
            raise ValueError("VolumeEvent symbol is required")
        object.__setattr__(self, "symbol", symbol)

        exchange_text = str(self.exchange or "").strip().upper()
        canonical_exchange = normalize_exchange(exchange_text)
        if exchange_text != canonical_exchange:
            raise ValueError(
                f"VolumeEvent exchange must be canonical: {self.exchange!r}"
            )
        object.__setattr__(self, "exchange", canonical_exchange)

        trading_date = _valid_iso_date(self.trading_date, "VolumeEvent trading_date")
        object.__setattr__(self, "trading_date", trading_date)
        minute = _valid_minute(self.minute, "VolumeEvent minute")
        object.__setattr__(self, "minute", minute)

        if not isinstance(self.event_time, datetime):
            raise ValueError("VolumeEvent event_time must be a datetime")
        local_event_time = _as_local(self.event_time)
        if local_event_time.date().isoformat() != trading_date:
            raise ValueError("VolumeEvent event_time date does not match trading_date")
        if local_event_time.strftime("%H:%M") != minute:
            raise ValueError("VolumeEvent event_time does not match minute")
        object.__setattr__(self, "event_time", local_event_time)

        if isinstance(self.volume_delta, bool) or not isinstance(self.volume_delta, int):
            raise ValueError("VolumeEvent volume_delta must be an integer")
        if self.volume_delta < 0:
            raise ValueError("VolumeEvent volume_delta must not be negative")
        if self.total_volume is not None:
            if isinstance(self.total_volume, bool) or not isinstance(
                self.total_volume, int
            ):
                raise ValueError("VolumeEvent total_volume must be an integer or None")
            if self.total_volume < 0:
                raise ValueError("VolumeEvent total_volume must not be negative")
        if self.provider_total_volume is not None:
            if isinstance(self.provider_total_volume, bool) or not isinstance(
                self.provider_total_volume, int
            ):
                raise ValueError(
                    "VolumeEvent provider_total_volume must be an integer or None"
                )
            if self.provider_total_volume < 0:
                raise ValueError(
                    "VolumeEvent provider_total_volume must not be negative"
                )

        quality_status = str(self.quality_status or "").strip().upper()
        if not quality_status:
            raise ValueError("VolumeEvent quality_status is required")
        object.__setattr__(self, "quality_status", quality_status)
        object.__setattr__(
            self,
            "provider_session",
            str(self.provider_session or "").strip().upper(),
        )
        object.__setattr__(
            self, "data_source", str(self.data_source or "").strip().upper()
        )


def _as_local(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=VN_TZ)
    return moment.astimezone(VN_TZ)


def _valid_iso_date(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}") from exc
    if parsed.isoformat() != text:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}")
    return text


def _valid_minute(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError as exc:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}") from exc
    if parsed.strftime("%H:%M") != text:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}")
    return text
