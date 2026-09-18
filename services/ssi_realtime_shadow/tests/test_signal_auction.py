from __future__ import annotations

from dataclasses import replace

import pytest

from app.auction import AuctionSessionBucket
from app.auction_history import Exact10Result
from app.signal_auction import build_auction_signal_metrics


def history(*, sessions: int, proven: int, inferred: int, quality: str, average: float | None) -> Exact10Result:
    dates = tuple(f"2026-09-{day:02d}" for day in range(1, 11))
    return Exact10Result(
        symbol="FPT", as_of_date="2026-09-18", candidate_dates=dates,
        sessions_used=sessions, proven_sessions=proven, inferred_sessions=inferred,
        missing_sessions=() if sessions == 10 else dates[sessions:],
        avg_closing_auction_volume=average,
        baseline_usable=sessions == 10,
        baseline_quality=quality,
    )


def bucket(auction_type: str, session: str, *, price: float = 102, pre: float | None = 100) -> AuctionSessionBucket:
    return AuctionSessionBucket(
        symbol="FPT", trading_date="2026-09-18", exchange="HOSE",
        auction_type=auction_type, provider_session=session,
        auction_price=price, pre_auction_price=pre, auction_volume=1_000,
        start_total_volume=10_000, end_total_volume=11_000, event_count=1,
        out_of_order_events=0, first_event_at="2026-09-18T09:00:00+07:00",
        last_event_at="2026-09-18T09:01:00+07:00", quality_status="TRUSTED",
        finalized=False, data_source="SSI_STREAM", updated_at="2026-09-18T09:01:00+07:00",
    )


@pytest.mark.parametrize("sessions", (0, 1, 9))
def test_ato_incomplete_history_never_calculates_average_or_rvol(sessions: int) -> None:
    result = build_auction_signal_metrics(
        ato_history=history(sessions=sessions, proven=sessions, inferred=0, quality="UNAVAILABLE", average=None),
        ato_bucket=bucket("OPEN_AUCTION", "ATO"), ref_price=100,
    )
    assert result.ato_baseline_sessions_used == sessions
    assert result.ato_avg_volume_10 is None
    assert result.ato_rvol is None
    assert result.ato_baseline_quality == "UNAVAILABLE"


def test_ato_requires_ten_proven_and_canonical_ssi_stream_session() -> None:
    exact = history(sessions=10, proven=10, inferred=0, quality="PROVEN", average=400)
    result = build_auction_signal_metrics(
        ato_history=exact, ato_bucket=bucket("OPEN_AUCTION", "ATO"), ref_price=100,
    )
    assert result.ato_avg_volume_10 == 400
    assert result.ato_rvol == 2.5
    assert result.ato_gap_pct == pytest.approx(2.0)
    rejected = build_auction_signal_metrics(
        ato_history=exact,
        ato_bucket=replace(bucket("OPEN_AUCTION", "ATO"), provider_session="LO"),
        ref_price=100,
    )
    assert rejected.ato_volume is None
    assert rejected.ato_rvol is None


def test_inferred_historical_ato_is_rejected() -> None:
    inferred = history(sessions=10, proven=0, inferred=10, quality="INFERRED_BOUNDARY", average=400)
    result = build_auction_signal_metrics(
        ato_history=inferred, ato_bucket=bucket("OPEN_AUCTION", "ATO"), ref_price=100,
    )
    assert result.ato_avg_volume_10 is None
    assert result.ato_rvol is None


@pytest.mark.parametrize(
    ("quality", "proven", "inferred"),
    (("INFERRED_BOUNDARY", 0, 10), ("MIXED", 5, 5), ("PROVEN", 10, 0)),
)
def test_atc_accepts_all_locked_exact10_qualities(quality: str, proven: int, inferred: int) -> None:
    result = build_auction_signal_metrics(
        atc_history=history(sessions=10, proven=proven, inferred=inferred, quality=quality, average=500),
        atc_bucket=bucket("CLOSE_AUCTION", "ATC", price=98, pre=100),
        total_day_volume=5_000,
    )
    assert result.atc_baseline_quality == quality
    assert result.atc_avg_volume_10 == 500
    assert result.atc_rvol == 2.0
    assert result.atc_price_impact_pct == pytest.approx(-2.0)
    assert result.atc_volume_share_pct == 20.0


def test_atc_price_impact_positive_negative_and_missing_preauction() -> None:
    exact = history(sessions=10, proven=10, inferred=0, quality="PROVEN", average=500)
    positive = build_auction_signal_metrics(
        atc_history=exact, atc_bucket=bucket("CLOSE_AUCTION", "ATC", price=101, pre=100)
    )
    negative = build_auction_signal_metrics(
        atc_history=exact, atc_bucket=bucket("CLOSE_AUCTION", "ATC", price=99, pre=100)
    )
    missing = build_auction_signal_metrics(
        atc_history=exact, atc_bucket=bucket("CLOSE_AUCTION", "ATC", price=99, pre=None)
    )
    assert positive.atc_price_impact_pct == pytest.approx(1.0)
    assert negative.atc_price_impact_pct == pytest.approx(-1.0)
    assert missing.atc_price_impact_pct is None


def test_non_session_aware_current_atc_is_not_canonical() -> None:
    exact = history(sessions=10, proven=10, inferred=0, quality="PROVEN", average=500)
    result = build_auction_signal_metrics(
        atc_history=exact,
        atc_bucket=replace(bucket("CLOSE_AUCTION", "ATC"), data_source="SSI_REST"),
    )
    assert result.atc_volume is None
    assert result.atc_rvol is None


def test_0915_clock_without_provider_ato_evidence_is_not_canonical_ato() -> None:
    exact = history(sessions=10, proven=10, inferred=0, quality="PROVEN", average=400)
    result = build_auction_signal_metrics(ato_history=exact, ato_bucket=None, ref_price=100)
    assert result.ato_volume is None
    assert result.ato_rvol is None


def test_continuous_0915_bar_cannot_substitute_for_ato_bucket() -> None:
    exact = history(sessions=10, proven=10, inferred=0, quality="PROVEN", average=400)
    continuous = replace(
        bucket("OPEN_AUCTION", "ATO"),
        provider_session="LO",
        first_event_at="2026-09-18T09:15:00+07:00",
        last_event_at="2026-09-18T09:15:00+07:00",
    )
    result = build_auction_signal_metrics(
        ato_history=exact, ato_bucket=continuous, ref_price=100
    )
    assert result.ato_volume is None
    assert result.ato_rvol is None
