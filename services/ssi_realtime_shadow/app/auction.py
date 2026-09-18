from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Iterable, Sequence

from .market_session import VN_TZ, normalize_exchange


OPEN_AUCTION = "OPEN_AUCTION"
CLOSE_AUCTION = "CLOSE_AUCTION"
SUPPORTED_PROVIDER_SESSIONS = frozenset(
    {"ATO", "LO", "ATC", "PT", "C", "BREAK", "HALT"}
)
SUPPORTED_SSI_SOURCES = frozenset({"SSI_STREAM", "SSI_REST"})


@dataclass(frozen=True, slots=True)
class AuctionEvent:
    symbol: str
    exchange: str
    trading_date: str
    event_at: datetime
    price: float
    total_volume: int | None
    provider_session: str
    data_source: str = "SSI_STREAM"
    quality_status: str = "TRUSTED"
    is_partial: bool = False
    has_gap: bool = False

    def __post_init__(self) -> None:
        symbol = str(self.symbol or "").strip().upper()
        if not symbol:
            raise ValueError("AuctionEvent symbol is required")
        object.__setattr__(self, "symbol", symbol)
        exchange = normalize_exchange(self.exchange)
        object.__setattr__(self, "exchange", exchange)
        parsed_date = date.fromisoformat(self.trading_date)
        if parsed_date.isoformat() != self.trading_date:
            raise ValueError("AuctionEvent trading_date must be canonical")
        event_at = self.event_at
        if event_at.tzinfo is None:
            event_at = event_at.replace(tzinfo=VN_TZ)
        else:
            event_at = event_at.astimezone(VN_TZ)
        if event_at.date() != parsed_date:
            raise ValueError("AuctionEvent date does not match event_at")
        object.__setattr__(self, "event_at", event_at)
        price = float(self.price)
        if price <= 0:
            raise ValueError("AuctionEvent price must be positive")
        object.__setattr__(self, "price", price)
        if self.total_volume is not None:
            if (
                isinstance(self.total_volume, bool)
                or not isinstance(self.total_volume, int)
                or self.total_volume < 0
            ):
                raise ValueError("AuctionEvent total_volume must be non-negative")
        object.__setattr__(
            self, "provider_session", str(self.provider_session or "").strip().upper()
        )
        object.__setattr__(
            self, "data_source", str(self.data_source or "").strip().upper()
        )
        object.__setattr__(
            self, "quality_status", str(self.quality_status or "").strip().upper()
        )


@dataclass(frozen=True, slots=True)
class AuctionSessionBucket:
    symbol: str
    trading_date: str
    exchange: str
    auction_type: str
    provider_session: str
    auction_price: float | None
    pre_auction_price: float | None
    auction_volume: int
    start_total_volume: int
    end_total_volume: int
    event_count: int
    out_of_order_events: int
    first_event_at: str | None
    last_event_at: str | None
    quality_status: str
    finalized: bool
    data_source: str
    updated_at: str

    def to_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AuctionAccumulatorResult:
    delta: int
    high_watermark: int
    anomaly: str | None
    auction_type: str | None
    updated_buckets: tuple[AuctionSessionBucket, ...]


@dataclass(slots=True)
class _MutableBucket:
    symbol: str
    trading_date: str
    exchange: str
    auction_type: str
    provider_session: str
    auction_price: float | None
    pre_auction_price: float | None
    auction_volume: int
    start_total_volume: int
    end_total_volume: int
    event_count: int = 0
    out_of_order_events: int = 0
    first_event_at: str | None = None
    last_event_at: str | None = None
    failures: set[str] = field(default_factory=set)
    finalized: bool = False
    data_sources: set[str] = field(default_factory=set)

    def snapshot(self, updated_at: str) -> AuctionSessionBucket:
        return AuctionSessionBucket(
            symbol=self.symbol,
            trading_date=self.trading_date,
            exchange=self.exchange,
            auction_type=self.auction_type,
            provider_session=self.provider_session,
            auction_price=self.auction_price,
            pre_auction_price=self.pre_auction_price,
            auction_volume=self.auction_volume,
            start_total_volume=self.start_total_volume,
            end_total_volume=self.end_total_volume,
            event_count=self.event_count,
            out_of_order_events=self.out_of_order_events,
            first_event_at=self.first_event_at,
            last_event_at=self.last_event_at,
            quality_status="DEGRADED" if self.failures else "TRUSTED",
            finalized=self.finalized,
            data_source=(
                next(iter(self.data_sources))
                if len(self.data_sources) == 1
                else "SSI_MIXED"
            ),
            updated_at=updated_at,
        )


@dataclass(slots=True)
class _DayState:
    symbol: str
    trading_date: str
    exchange: str
    high_watermark: int = 0
    last_continuous_price: float | None = None
    buckets: dict[str, _MutableBucket] = field(default_factory=dict)
    failures: set[str] = field(default_factory=set)


def auction_type_for_provider_session(provider_session: str) -> str | None:
    session = str(provider_session or "").strip().upper()
    if session == "ATO":
        return OPEN_AUCTION
    if session == "ATC":
        return CLOSE_AUCTION
    return None


class AuctionSessionAccumulator:
    """Pure SSI cumulative-volume projection split by provider session."""

    def __init__(self) -> None:
        self._states: dict[tuple[str, str], _DayState] = {}

    def on_event(self, event: AuctionEvent) -> AuctionAccumulatorResult:
        key = (event.symbol, event.trading_date)
        state = self._states.get(key)
        if state is None:
            state = _DayState(event.symbol, event.trading_date, event.exchange)
            self._states[key] = state
        elif state.exchange != event.exchange:
            raise ValueError("AuctionEvent exchange changed within trading day")

        updated: list[AuctionSessionBucket] = []
        auction_type = auction_type_for_provider_session(event.provider_session)
        anomaly: str | None = None
        previous_high = state.high_watermark
        delta = 0
        if event.total_volume is None:
            anomaly = "MISSING_TOTAL_VOLUME"
        elif event.total_volume > state.high_watermark:
            delta = event.total_volume - state.high_watermark
            state.high_watermark = event.total_volume
        elif event.total_volume == state.high_watermark:
            anomaly = "DUPLICATE_TOTAL_VOLUME"
        else:
            anomaly = "OUT_OF_ORDER_REGRESSION"

        if event.total_volume is None:
            state.failures.add("MISSING_TOTAL_VOLUME")
        if event.has_gap:
            state.failures.add("GAP")
        if event.is_partial and anomaly != "OUT_OF_ORDER_REGRESSION":
            state.failures.add("PARTIAL")
        if event.quality_status not in {"TRUSTED", "VOLUME_REGRESSION"}:
            state.failures.add("NON_TRUSTED_QUALITY")
        if event.data_source not in SUPPORTED_SSI_SOURCES:
            state.failures.add("UNSUPPORTED_SOURCE")
        if event.provider_session not in SUPPORTED_PROVIDER_SESSIONS:
            state.failures.add("UNSUPPORTED_SESSION")
            if anomaly is None:
                anomaly = "UNSUPPORTED_SESSION"

        if event.provider_session == "LO":
            state.last_continuous_price = event.price

        if auction_type is None:
            for bucket_type, bucket in state.buckets.items():
                if not bucket.finalized and (
                    bucket_type == OPEN_AUCTION
                    or event.provider_session not in {"ATC"}
                ):
                    bucket.finalized = True
                    updated.append(bucket.snapshot(event.event_at.isoformat()))
            return AuctionAccumulatorResult(
                delta, state.high_watermark, anomaly, None, tuple(updated)
            )

        bucket = state.buckets.get(auction_type)
        if bucket is None:
            bucket = _MutableBucket(
                symbol=event.symbol,
                trading_date=event.trading_date,
                exchange=event.exchange,
                auction_type=auction_type,
                provider_session=event.provider_session,
                auction_price=None,
                pre_auction_price=state.last_continuous_price,
                auction_volume=0,
                start_total_volume=previous_high,
                end_total_volume=previous_high,
                failures=set(state.failures),
            )
            state.buckets[auction_type] = bucket
        bucket.event_count += 1
        bucket.auction_price = event.price
        bucket.auction_volume += delta
        bucket.end_total_volume = state.high_watermark
        event_at = event.event_at.isoformat()
        bucket.first_event_at = bucket.first_event_at or event_at
        bucket.last_event_at = event_at
        bucket.data_sources.add(event.data_source)
        if anomaly == "OUT_OF_ORDER_REGRESSION":
            bucket.out_of_order_events += 1
        bucket.failures.update(state.failures)
        updated.append(bucket.snapshot(event_at))
        return AuctionAccumulatorResult(
            delta, state.high_watermark, anomaly, auction_type, tuple(updated)
        )

    def get_bucket(
        self, symbol: str, trading_date: str, auction_type: str
    ) -> AuctionSessionBucket | None:
        state = self._states.get((symbol.strip().upper(), trading_date))
        if state is None or auction_type not in state.buckets:
            return None
        return state.buckets[auction_type].snapshot(
            state.buckets[auction_type].last_event_at or ""
        )


@dataclass(frozen=True, slots=True)
class AuctionHistorySession:
    trading_date: str
    opening_volume: int | None
    closing_volume: int | None
    opening_proven: bool
    closing_proven: bool


@dataclass(frozen=True, slots=True)
class AuctionFeatures:
    opening_auction_price: float | None
    opening_auction_volume: int | None
    opening_auction_rvol: float | None
    opening_gap_pct: float | None
    preclose_price: float | None
    closing_auction_price: float | None
    closing_auction_volume: int | None
    closing_auction_rvol: float | None
    closing_volume_share_pct: float | None
    closing_price_impact_pct: float | None
    opening_history_sessions_used: int
    closing_history_sessions_used: int
    opening_trusted: bool
    closing_trusted: bool
    closing_selling_pressure_eligible: bool
    positive_flow_inferred: bool


def _ratio(numerator: int | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _pct(current: float | None, reference: float | None) -> float | None:
    if current is None or reference is None or reference <= 0:
        return None
    return (current / reference - 1.0) * 100.0


def calculate_auction_features(
    *,
    trading_date: str,
    opening_bucket: AuctionSessionBucket | None,
    closing_bucket: AuctionSessionBucket | None,
    ref_price: float | None,
    last_continuous_price: float | None,
    total_day_volume: int | None,
    history: Iterable[AuctionHistorySession],
    candidate_sessions: Sequence[str],
    lookback: int = 10,
) -> AuctionFeatures:
    if lookback < 1:
        raise ValueError("lookback must be positive")
    candidates = sorted(
        {value for value in candidate_sessions if value < trading_date}
    )[-lookback:]
    by_date = {item.trading_date: item for item in history}
    opening_values = [
        item.opening_volume
        for value in candidates
        if (item := by_date.get(value)) is not None
        and item.opening_proven
        and item.opening_volume is not None
    ]
    closing_values = [
        item.closing_volume
        for value in candidates
        if (item := by_date.get(value)) is not None
        and item.closing_proven
        and item.closing_volume is not None
    ]
    opening_average = (
        sum(opening_values) / len(opening_values) if opening_values else None
    )
    closing_average = (
        sum(closing_values) / len(closing_values) if closing_values else None
    )
    opening_volume = opening_bucket.auction_volume if opening_bucket else None
    closing_volume = closing_bucket.auction_volume if closing_bucket else None
    closing_share = (
        closing_volume / total_day_volume * 100.0
        if closing_volume is not None
        and total_day_volume is not None
        and total_day_volume > 0
        else None
    )
    preclose_price = (
        closing_bucket.pre_auction_price
        if closing_bucket and closing_bucket.pre_auction_price is not None
        else last_continuous_price
    )
    closing_impact = _pct(
        closing_bucket.auction_price if closing_bucket else None,
        preclose_price,
    )
    exact_window = len(candidates) == lookback
    opening_current_valid = bool(
        opening_bucket
        and opening_bucket.finalized
        and opening_bucket.quality_status == "TRUSTED"
    )
    closing_current_valid = bool(
        closing_bucket
        and closing_bucket.finalized
        and closing_bucket.quality_status == "TRUSTED"
    )
    return AuctionFeatures(
        opening_auction_price=opening_bucket.auction_price if opening_bucket else None,
        opening_auction_volume=opening_volume,
        opening_auction_rvol=_ratio(opening_volume, opening_average),
        opening_gap_pct=_pct(
            opening_bucket.auction_price if opening_bucket else None, ref_price
        ),
        preclose_price=preclose_price,
        closing_auction_price=closing_bucket.auction_price if closing_bucket else None,
        closing_auction_volume=closing_volume,
        closing_auction_rvol=_ratio(closing_volume, closing_average),
        closing_volume_share_pct=closing_share,
        closing_price_impact_pct=closing_impact,
        opening_history_sessions_used=len(opening_values),
        closing_history_sessions_used=len(closing_values),
        opening_trusted=opening_current_valid
        and exact_window
        and len(opening_values) == lookback,
        closing_trusted=closing_current_valid
        and exact_window
        and len(closing_values) == lookback,
        closing_selling_pressure_eligible=bool(
            closing_current_valid
            and closing_volume is not None
            and closing_volume > 0
            and closing_impact is not None
            and closing_impact < 0
        ),
        positive_flow_inferred=False,
    )
