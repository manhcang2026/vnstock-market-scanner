from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.auction import (
    CLOSE_AUCTION,
    OPEN_AUCTION,
    AuctionEvent,
    AuctionHistorySession,
    AuctionSessionAccumulator,
    calculate_auction_features,
)
from app.market_session import VN_TZ


TRADING_DATE = "2026-09-18"


def _event(
    provider_session: str,
    total_volume: int | None,
    *,
    minute: str,
    price: float = 100,
    quality_status: str = "TRUSTED",
    is_partial: bool = False,
    has_gap: bool = False,
    data_source: str = "SSI_STREAM",
) -> AuctionEvent:
    return AuctionEvent(
        symbol="FPT",
        exchange="HOSE",
        trading_date=TRADING_DATE,
        event_at=datetime.fromisoformat(f"{TRADING_DATE}T{minute}:00").replace(
            tzinfo=VN_TZ
        ),
        price=price,
        total_volume=total_volume,
        provider_session=provider_session,
        quality_status=quality_status,
        is_partial=is_partial,
        has_gap=has_gap,
        data_source=data_source,
    )


def _finalized_buckets():
    accumulator = AuctionSessionAccumulator()
    accumulator.on_event(_event("ATO", 100, minute="09:00", price=101))
    accumulator.on_event(_event("LO", 150, minute="09:16", price=102))
    accumulator.on_event(_event("LO", 1_000, minute="14:29", price=103))
    accumulator.on_event(_event("ATC", 1_250, minute="14:30", price=99))
    accumulator.on_event(_event("C", 1_250, minute="14:46", price=99))
    return (
        accumulator.get_bucket("FPT", TRADING_DATE, OPEN_AUCTION),
        accumulator.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION),
    )


def _dates(count: int = 11) -> list[str]:
    values: list[str] = []
    current = date(2026, 9, 1)
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def test_ato_and_atc_deltas_are_assigned_only_to_provider_auction_session() -> None:
    accumulator = AuctionSessionAccumulator()
    opening = accumulator.on_event(_event("ATO", 100, minute="10:00"))
    lo = accumulator.on_event(_event("LO", 180, minute="10:01"))
    closing = accumulator.on_event(_event("ATC", 250, minute="10:02"))

    assert opening.auction_type == OPEN_AUCTION
    assert opening.delta == 100
    assert lo.auction_type is None
    assert closing.auction_type == CLOSE_AUCTION
    assert closing.delta == 70
    assert accumulator.get_bucket("FPT", TRADING_DATE, OPEN_AUCTION).auction_volume == 100
    assert accumulator.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION).auction_volume == 70


def test_lo_volume_and_boundary_timestamps_never_imply_auction() -> None:
    accumulator = AuctionSessionAccumulator()
    at_open_boundary = accumulator.on_event(
        _event("LO", 100, minute="09:15", price=74_500)
    )
    at_close_boundary = accumulator.on_event(
        _event("LO", 200, minute="14:45", price=73_900)
    )

    assert at_open_boundary.auction_type is None
    assert at_close_boundary.auction_type is None
    assert accumulator.get_bucket("FPT", TRADING_DATE, OPEN_AUCTION) is None
    assert accumulator.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION) is None


def test_regression_is_zero_delta_and_never_lowers_high_watermark() -> None:
    accumulator = AuctionSessionAccumulator()
    accumulator.on_event(_event("ATO", 100, minute="09:00"))
    regression = accumulator.on_event(
        _event(
            "ATO",
            90,
            minute="09:01",
            quality_status="VOLUME_REGRESSION",
            is_partial=True,
        )
    )
    recovered = accumulator.on_event(_event("ATO", 120, minute="09:02"))
    accumulator.on_event(_event("LO", 120, minute="09:16"))
    bucket = accumulator.get_bucket("FPT", TRADING_DATE, OPEN_AUCTION)

    assert regression.delta == 0
    assert regression.high_watermark == 100
    assert regression.anomaly == "OUT_OF_ORDER_REGRESSION"
    assert recovered.delta == 20
    assert bucket.auction_volume == 120
    assert bucket.out_of_order_events == 1
    assert bucket.quality_status == "DEGRADED"
    assert bucket.finalized


def test_hydration_before_atc_uses_persisted_lo_watermark_and_price() -> None:
    accumulator = AuctionSessionAccumulator()
    accumulator.hydrate(
        symbol="FPT",
        trading_date=TRADING_DATE,
        exchange="HOSE",
        high_watermark=6_980_600,
        last_continuous_price=73_900,
        last_structural_event_at=datetime.fromisoformat(
            f"{TRADING_DATE}T14:29:00+07:00"
        ),
    )
    result = accumulator.on_event(
        _event("ATC", 15_500_700, minute="14:45", price=71_700)
    )
    bucket = accumulator.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION)

    assert result.delta == 8_520_100
    assert bucket.auction_volume == 8_520_100
    assert bucket.start_total_volume == 6_980_600
    assert bucket.pre_auction_price == 73_900


def test_hydration_before_ato_keeps_explicit_provider_session_proof() -> None:
    accumulator = AuctionSessionAccumulator()
    accumulator.hydrate(
        symbol="FPT",
        trading_date=TRADING_DATE,
        exchange="HOSE",
        high_watermark=0,
        last_continuous_price=None,
        last_structural_event_at=None,
    )
    result = accumulator.on_event(
        _event("ATO", 100, minute="09:00", price=101)
    )
    bucket = accumulator.get_bucket("FPT", TRADING_DATE, OPEN_AUCTION)

    assert result.auction_type == OPEN_AUCTION
    assert bucket.provider_session == "ATO"
    assert bucket.auction_volume == 100
    assert bucket.quality_status == "TRUSTED"


def test_hydration_during_atc_preserves_bucket_and_appends_only_new_delta() -> None:
    before_restart = AuctionSessionAccumulator()
    before_restart.on_event(_event("LO", 6_980_600, minute="14:29", price=73_900))
    before_restart.on_event(_event("ATC", 10_000_000, minute="14:30", price=72_500))
    persisted = before_restart.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION)

    resumed = AuctionSessionAccumulator()
    resumed.hydrate(
        symbol="FPT",
        trading_date=TRADING_DATE,
        exchange="HOSE",
        high_watermark=10_000_000,
        last_continuous_price=None,
        last_structural_event_at=datetime.fromisoformat(
            f"{TRADING_DATE}T14:30:00+07:00"
        ),
        buckets=(persisted,),
    )
    result = resumed.on_event(
        _event("ATC", 15_500_700, minute="14:40", price=71_700)
    )
    bucket = resumed.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION)

    assert result.delta == 5_500_700
    assert bucket.auction_volume == 8_520_100
    assert bucket.pre_auction_price == 73_900


def test_stale_or_regressing_events_cannot_mutate_canonical_price_or_session() -> None:
    accumulator = AuctionSessionAccumulator()
    accumulator.on_event(_event("LO", 1_000, minute="14:29", price=103))
    accumulator.on_event(_event("ATC", 1_200, minute="14:31", price=101))
    stale = accumulator.on_event(_event("ATC", 1_100, minute="14:30", price=99))
    stale_lo = accumulator.on_event(_event("LO", 900, minute="14:30", price=90))
    before_finalize = accumulator.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION)

    assert stale.delta == 0
    assert stale.anomaly == "OUT_OF_ORDER_EVENT"
    assert stale_lo.delta == 0
    assert before_finalize.auction_volume == 200
    assert before_finalize.auction_price == 101
    assert before_finalize.pre_auction_price == 103
    assert before_finalize.last_event_at == f"{TRADING_DATE}T14:31:00+07:00"
    assert before_finalize.out_of_order_events == 1
    assert not before_finalize.finalized

    duplicate_transition = accumulator.on_event(
        _event("C", 1_200, minute="14:32", price=101)
    )
    finalized = accumulator.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION)
    assert duplicate_transition.delta == 0
    assert duplicate_transition.anomaly == "DUPLICATE_TOTAL_VOLUME"
    assert finalized.auction_volume == 200
    assert finalized.finalized


def test_regressing_lo_cannot_replace_valid_preclose_before_atc() -> None:
    accumulator = AuctionSessionAccumulator()
    accumulator.on_event(_event("LO", 1_000, minute="14:29", price=103))
    regression = accumulator.on_event(
        _event(
            "LO",
            900,
            minute="14:30",
            price=90,
            quality_status="VOLUME_REGRESSION",
            is_partial=True,
        )
    )
    accumulator.on_event(_event("ATC", 1_200, minute="14:31", price=101))
    bucket = accumulator.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION)

    assert regression.delta == 0
    assert regression.anomaly == "OUT_OF_ORDER_REGRESSION"
    assert bucket.pre_auction_price == 103
    assert bucket.auction_volume == 200


def test_rejected_ordinary_event_does_not_poison_later_atc() -> None:
    accumulator = AuctionSessionAccumulator()
    accumulator.on_event(_event("LO", 1_000, minute="14:29", price=103))
    rejected = accumulator.on_event(
        _event(
            "LO",
            900,
            minute="14:30",
            price=90,
            quality_status="VOLUME_REGRESSION",
            is_partial=True,
        )
    )
    accumulator.on_event(_event("ATC", 1_200, minute="14:31", price=101))
    bucket = accumulator.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION)

    assert rejected.anomaly == "OUT_OF_ORDER_REGRESSION"
    assert bucket.quality_status == "TRUSTED"
    assert bucket.pre_auction_price == 103


def test_first_actual_auction_regression_creates_degraded_diagnostic_bucket() -> None:
    accumulator = AuctionSessionAccumulator()
    accumulator.on_event(_event("LO", 1_000, minute="14:29", price=103))

    rejected = accumulator.on_event(
        _event(
            "ATC",
            900,
            minute="14:30",
            price=90,
            quality_status="VOLUME_REGRESSION",
            is_partial=True,
        )
    )
    bucket = accumulator.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION)

    assert rejected.anomaly == "OUT_OF_ORDER_REGRESSION"
    assert bucket.quality_status == "DEGRADED"
    assert bucket.auction_price is None
    assert bucket.auction_volume == 0
    assert bucket.out_of_order_events == 1


def test_duplicate_total_volume_adds_zero() -> None:
    accumulator = AuctionSessionAccumulator()
    accumulator.on_event(_event("ATC", 1_000, minute="14:30"))
    duplicate = accumulator.on_event(_event("ATC", 1_000, minute="14:31"))

    assert duplicate.delta == 0
    assert duplicate.high_watermark == 1_000
    assert duplicate.anomaly == "DUPLICATE_TOTAL_VOLUME"


def test_unsupported_provider_session_is_a_quality_failure() -> None:
    accumulator = AuctionSessionAccumulator()
    unsupported = accumulator.on_event(_event("UNKNOWN", 10, minute="09:00"))
    accumulator.on_event(_event("ATO", 20, minute="09:01"))
    bucket = accumulator.get_bucket("FPT", TRADING_DATE, OPEN_AUCTION)

    assert unsupported.auction_type is None
    assert unsupported.anomaly == "UNSUPPORTED_SESSION"
    assert bucket.quality_status == "TRUSTED"


@pytest.mark.parametrize(
    "options",
    [
        {"total_volume": None},
        {"total_volume": 100, "has_gap": True},
        {"total_volume": 100, "is_partial": True},
        {"total_volume": 100, "data_source": "LEGACY_UNVERIFIED"},
    ],
)
def test_unresolved_volume_quality_failures_degrade_auction(options: dict) -> None:
    accumulator = AuctionSessionAccumulator()
    total_volume = options["total_volume"]
    event_options = {
        key: value for key, value in options.items() if key != "total_volume"
    }
    result = accumulator.on_event(
        _event("ATO", total_volume, minute="09:00", **event_options)
    )
    bucket = accumulator.get_bucket("FPT", TRADING_DATE, OPEN_AUCTION)

    assert result.delta >= 0
    assert bucket.quality_status == "DEGRADED"
    if total_volume is None:
        assert result.anomaly == "MISSING_TOTAL_VOLUME"


def test_auction_rvol_domains_use_only_their_own_prior_sessions() -> None:
    opening, closing = _finalized_buckets()
    dates = _dates(10)
    history = [
        AuctionHistorySession(item, 50, 500, True, True) for item in dates
    ]
    features = calculate_auction_features(
        trading_date=TRADING_DATE,
        opening_bucket=opening,
        closing_bucket=closing,
        ref_price=100,
        last_continuous_price=103,
        total_day_volume=1_250,
        history=history,
        candidate_sessions=dates,
    )

    assert features.opening_auction_rvol == 2
    assert features.closing_auction_rvol == 0.5
    assert features.opening_trusted
    assert features.closing_trusted


def test_exact_previous_ten_does_not_replace_bad_session_with_older_11th() -> None:
    opening, closing = _finalized_buckets()
    dates = _dates(11)
    bad_date = dates[-5]
    history = [
        AuctionHistorySession(
            item,
            50,
            100,
            item != bad_date,
            item != bad_date,
        )
        for item in dates
    ]
    features = calculate_auction_features(
        trading_date=TRADING_DATE,
        opening_bucket=opening,
        closing_bucket=closing,
        ref_price=100,
        last_continuous_price=103,
        total_day_volume=1_250,
        history=history,
        candidate_sessions=dates,
    )

    assert features.opening_history_sessions_used == 9
    assert features.closing_history_sessions_used == 9
    assert not features.opening_trusted
    assert not features.closing_trusted


def test_fewer_than_ten_can_calculate_but_remains_untrusted() -> None:
    opening, closing = _finalized_buckets()
    dates = _dates(9)
    history = [AuctionHistorySession(item, 50, 100, True, True) for item in dates]
    features = calculate_auction_features(
        trading_date=TRADING_DATE,
        opening_bucket=opening,
        closing_bucket=closing,
        ref_price=100,
        last_continuous_price=103,
        total_day_volume=1_250,
        history=history,
        candidate_sessions=dates,
    )

    assert features.opening_auction_rvol == 2
    assert features.closing_auction_rvol == 2.5
    assert not features.opening_trusted
    assert not features.closing_trusted


def test_zero_auction_history_denominator_returns_null() -> None:
    opening, closing = _finalized_buckets()
    dates = _dates(10)
    history = [AuctionHistorySession(item, 0, 0, True, True) for item in dates]
    features = calculate_auction_features(
        trading_date=TRADING_DATE,
        opening_bucket=opening,
        closing_bucket=closing,
        ref_price=100,
        last_continuous_price=103,
        total_day_volume=1_250,
        history=history,
        candidate_sessions=dates,
    )

    assert features.opening_auction_rvol is None
    assert features.closing_auction_rvol is None


def test_fpt_observed_boundary_shape_is_a_negative_impact_semantic_fixture() -> None:
    accumulator = AuctionSessionAccumulator()
    # The observed 09:15 boundary bar is deliberately classified LO, not ATO.
    accumulator.on_event(_event("LO", 1_376_000, minute="09:15", price=74_600))
    accumulator.on_event(_event("LO", 6_980_600, minute="14:29", price=73_900))
    accumulator.on_event(_event("LO", 6_980_600, minute="14:44", price=73_900))
    # Synthetic ATC classification exercises semantics; raw historical
    # TradingSession events for 2026-09-18 are not available as evidence.
    accumulator.on_event(_event("ATC", 15_500_700, minute="14:45", price=71_700))
    accumulator.on_event(_event("C", 15_500_700, minute="14:46", price=71_700))
    closing = accumulator.get_bucket("FPT", TRADING_DATE, CLOSE_AUCTION)
    features = calculate_auction_features(
        trading_date=TRADING_DATE,
        opening_bucket=None,
        closing_bucket=closing,
        ref_price=74_500,
        last_continuous_price=73_900,
        total_day_volume=15_500_700,
        history=(),
        candidate_sessions=(),
    )

    assert features.preclose_price == 73_900
    assert features.closing_auction_price == 71_700
    assert features.closing_auction_volume == 8_520_100
    assert closing.start_total_volume == 6_980_600
    assert closing.end_total_volume == 15_500_700
    assert features.closing_price_impact_pct == pytest.approx(-2.976996, rel=1e-6)
    assert features.closing_volume_share_pct == pytest.approx(54.9659, rel=1e-5)
    assert features.closing_selling_pressure_eligible
    assert not features.positive_flow_inferred
