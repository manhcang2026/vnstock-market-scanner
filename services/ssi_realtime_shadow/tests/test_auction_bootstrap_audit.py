from __future__ import annotations

from app.auction_bootstrap_audit import (
    DISAGREEMENT,
    INFERRED_BOUNDARY,
    SINGLE_SOURCE,
    STRONG_AGREEMENT,
    UNAVAILABLE,
    WEAK_AGREEMENT,
    audit_provider_session,
    compare_provider_rows,
    recommend_domain,
    reconcile_daily_volume,
)


DATE = "2026-09-17"


def _bar(minute: str, price: float, volume: int, **prices: float) -> dict:
    return {
        "time": f"{DATE} {minute}:00",
        "open": prices.get("open", price),
        "high": prices.get("high", price),
        "low": prices.get("low", price),
        "close": prices.get("close", price),
        "volume": volume,
    }


def _session(provider: str = "KBS", *, opening_mixed: bool = False, closing: bool = True):
    bars = [
        _bar("09:15", 100, 100, high=101 if opening_mixed else 100),
        _bar("09:16", 101, 20),
        _bar("14:29", 102, 300),
    ]
    if closing:
        bars.append(_bar("14:45", 103, 580))
    return audit_provider_session(
        provider=provider,
        symbol="FPT",
        trading_date=DATE,
        minute_bars=bars,
        daily_row={"open": 100, "close": 103, "volume": 1000},
        previous_daily_row={"close": 99},
    )


def test_exact_cross_provider_agreement() -> None:
    result = compare_provider_rows(_session("KBS"), _session("VCI"), domain="ATC")
    assert result["classification"] == STRONG_AGREEMENT
    assert result["closing_volume_abs_diff"] == 0


def test_volume_mismatch_is_weak_without_hidden_tolerance() -> None:
    left = _session("KBS")
    right = _session("VCI")
    right["candidate_closing_boundary_volume"] += 1
    result = compare_provider_rows(left, right, domain="ATC")
    assert result["classification"] == WEAK_AGREEMENT
    assert result["closing_volume_abs_diff"] == 1


def test_missing_provider_is_single_source() -> None:
    result = compare_provider_rows(_session("KBS"), None, domain="ATC")
    assert result["classification"] == SINGLE_SOURCE


def test_missing_boundary_bar_is_unavailable() -> None:
    row = _session(closing=False)
    assert row["closing_inference_quality"] == UNAVAILABLE
    result = compare_provider_rows(row, None, domain="ATC")
    assert result["classification"] == UNAVAILABLE


def test_mixed_0915_opening_bar_cannot_be_exact_ato() -> None:
    row = _session(opening_mixed=True)
    assert row["opening_bar_mixed"]
    assert not row["opening_bar_isolated"]
    assert row["opening_inference_quality"] == UNAVAILABLE


def test_isolated_1445_closing_bar_is_inferred_only() -> None:
    row = _session()
    assert row["closing_bar_isolated"]
    assert row["candidate_closing_boundary_volume"] == 580
    assert row["closing_inference_quality"] == INFERRED_BOUNDARY


def test_daily_volume_reconciliation_exact() -> None:
    result = reconcile_daily_volume(1000, 1000)
    assert result["reconciled_exactly"]
    assert result["volume_diff"] == 0


def test_daily_volume_reconciliation_mismatch_is_not_forced_equal() -> None:
    result = reconcile_daily_volume(999, 1000)
    assert not result["reconciled_exactly"]
    assert not result["reconciled_within_rounding_or_provider_semantics"]
    assert result["volume_diff"] == -1


def test_provider_timestamp_difference_is_disagreement() -> None:
    left = _session("KBS")
    right = _session("VCI")
    right["final_time"] = f"{DATE} 14:46:00"
    result = compare_provider_rows(left, right, domain="ATC")
    assert result["classification"] == DISAGREEMENT


def test_historical_boundary_never_gets_proven_quality() -> None:
    row = _session()
    assert row["quality_tier"] == INFERRED_BOUNDARY
    assert row["opening_inference_quality"] == INFERRED_BOUNDARY
    assert row["closing_inference_quality"] == INFERRED_BOUNDARY
    assert "PROVEN" not in row.values()


def test_audit_retains_raw_boundary_ohlcv_and_provider_fields() -> None:
    bar = _bar("09:15", 100, 100)
    bar["provider_id"] = "raw-1"
    row = audit_provider_session(
        provider="KBS",
        symbol="FPT",
        trading_date=DATE,
        minute_bars=[bar],
        daily_row={"open": 100, "volume": 100},
    )
    assert row["opening_boundary_bar"]["provider_fields"] == {"provider_id": "raw-1"}


def test_mixed_opening_evidence_recommends_no_bootstrap() -> None:
    rows = [_session("KBS", opening_mixed=True), _session("VCI", opening_mixed=True)]
    comparisons = [compare_provider_rows(rows[0], rows[1], domain="ATO")]
    result = recommend_domain(rows, comparisons, domain="ATO")
    assert result["recommendation"] == "DO_NOT_BOOTSTRAP"


def test_atc_with_daily_mismatch_remains_diagnostic_only() -> None:
    rows = [_session("KBS"), _session("VCI")]
    rows[1]["reconciled_exactly"] = False
    comparisons = [compare_provider_rows(rows[0], rows[1], domain="ATC")]
    result = recommend_domain(rows, comparisons, domain="ATC")
    assert result["recommendation"] == "DIAGNOSTIC_ONLY"
