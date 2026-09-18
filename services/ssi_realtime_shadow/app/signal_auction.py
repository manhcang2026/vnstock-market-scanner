"""Canonical auction metrics adapter for SIGNAL-01."""

from __future__ import annotations

from dataclasses import dataclass

from .auction import AuctionSessionBucket
from .auction_history import Exact10Result


@dataclass(frozen=True, slots=True)
class AuctionSignalMetrics:
    ato_volume: int | None = None
    ato_avg_volume_10: float | None = None
    ato_rvol: float | None = None
    ato_baseline_sessions_used: int = 0
    ato_baseline_quality: str = "UNAVAILABLE"
    ato_gap_pct: float | None = None
    atc_volume: int | None = None
    atc_avg_volume_10: float | None = None
    atc_rvol: float | None = None
    atc_baseline_sessions_used: int = 0
    atc_baseline_quality: str = "UNAVAILABLE"
    atc_price_impact_pct: float | None = None
    atc_volume_share_pct: float | None = None


def _pct(current: float | None, reference: float | None) -> float | None:
    if current is None or reference is None or reference <= 0:
        return None
    return (current / reference - 1.0) * 100.0


def _canonical_bucket(
    bucket: AuctionSessionBucket | None, *, auction_type: str, provider_session: str
) -> AuctionSessionBucket | None:
    if bucket is None:
        return None
    if (
        bucket.auction_type != auction_type
        or bucket.provider_session != provider_session
        or bucket.data_source != "SSI_STREAM"
        or bucket.quality_status != "TRUSTED"
    ):
        return None
    return bucket


def build_auction_signal_metrics(
    *,
    ato_history: Exact10Result | None = None,
    atc_history: Exact10Result | None = None,
    ato_bucket: AuctionSessionBucket | None = None,
    atc_bucket: AuctionSessionBucket | None = None,
    ref_price: float | None = None,
    total_day_volume: int | None = None,
) -> AuctionSignalMetrics:
    """Consume exact-10 readers and live session buckets without inference."""
    ato = _canonical_bucket(
        ato_bucket, auction_type="OPEN_AUCTION", provider_session="ATO"
    )
    atc = _canonical_bucket(
        atc_bucket, auction_type="CLOSE_AUCTION", provider_session="ATC"
    )
    ato_usable = bool(
        ato_history
        and ato_history.baseline_usable
        and ato_history.sessions_used == 10
        and ato_history.proven_sessions == 10
        and ato_history.baseline_quality == "PROVEN"
    )
    atc_usable = bool(
        atc_history
        and atc_history.baseline_usable
        and atc_history.sessions_used == 10
        and atc_history.baseline_quality in {"PROVEN", "MIXED", "INFERRED_BOUNDARY"}
    )
    ato_avg = ato_history.avg_closing_auction_volume if ato_usable else None
    atc_avg = atc_history.avg_closing_auction_volume if atc_usable else None
    ato_volume = ato.auction_volume if ato is not None else None
    atc_volume = atc.auction_volume if atc is not None else None
    return AuctionSignalMetrics(
        ato_volume=ato_volume,
        ato_avg_volume_10=ato_avg,
        ato_rvol=(ato_volume / ato_avg if ato_volume is not None and ato_avg and ato_avg > 0 else None),
        ato_baseline_sessions_used=ato_history.sessions_used if ato_history else 0,
        ato_baseline_quality=ato_history.baseline_quality if ato_usable else "UNAVAILABLE",
        ato_gap_pct=_pct(ato.auction_price if ato else None, ref_price),
        atc_volume=atc_volume,
        atc_avg_volume_10=atc_avg,
        atc_rvol=(atc_volume / atc_avg if atc_volume is not None and atc_avg and atc_avg > 0 else None),
        atc_baseline_sessions_used=atc_history.sessions_used if atc_history else 0,
        atc_baseline_quality=atc_history.baseline_quality if atc_usable else "UNAVAILABLE",
        atc_price_impact_pct=_pct(
            atc.auction_price if atc else None,
            atc.pre_auction_price if atc else None,
        ),
        atc_volume_share_pct=(
            atc_volume / total_day_volume * 100.0
            if atc_volume is not None and total_day_volume is not None and total_day_volume > 0
            else None
        ),
    )
