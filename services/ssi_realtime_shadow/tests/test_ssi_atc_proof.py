from __future__ import annotations

from app.ssi_atc_proof import (
    CONFIRMED_INFERRED_BOUNDARY,
    INFERRED_BOUNDARY,
    PROOF,
    UNCONFIRMED_BOUNDARY,
    UNAVAILABLE,
    exact10_coverage,
    exact_previous_sessions,
    prove_ssi_atc_boundary,
)


DATE = "2026-09-17"


def _bar(at: str, price: int, volume: int, **overrides: int) -> dict:
    return {
        "provider_time": at,
        "open": overrides.get("open", price),
        "high": overrides.get("high", price),
        "low": overrides.get("low", price),
        "close": overrides.get("close", price),
        "volume": volume,
    }


def _witness(**overrides) -> dict:
    return {
        "final_time": overrides.get("final_time", f"{DATE} 14:45:00"),
        "final_price": overrides.get("final_price", 74.3),
        "candidate_closing_boundary_volume": overrides.get("volume", 1_887_000),
    }


def _proof(**overrides):
    bars = overrides.pop(
        "bars",
        [_bar("14:29:59", 74_000, 4_739_700), _bar("14:45:04", 74_300, 1_887_000)],
    )
    return prove_ssi_atc_boundary(
        symbol="FPT",
        trading_date=DATE,
        ssi_bars=bars,
        ssi_daily_volume=overrides.pop("daily", 6_626_700),
        kbs_witness=overrides.pop("kbs", _witness()),
        vci_witness=overrides.pop("vci", _witness()),
        **overrides,
    )


def test_exact_ssi_kbs_vci_match_confirms_inferred_boundary() -> None:
    result = _proof()
    assert result["classification"] == CONFIRMED_INFERRED_BOUNDARY
    assert result["quality"] == INFERRED_BOUNDARY
    assert result["proof"] == PROOF


def test_ssi_price_difference_rejects() -> None:
    result = _proof(bars=[_bar("14:29:59", 74_000, 4_739_700), _bar("14:45:04", 74_400, 1_887_000)])
    assert result["classification"] == UNCONFIRMED_BOUNDARY
    assert "KBS_BOUNDARY_PRICE_MISMATCH" in result["failure_reasons"]


def test_ssi_volume_difference_rejects() -> None:
    result = _proof(bars=[_bar("14:29:59", 74_000, 4_739_699), _bar("14:45:04", 74_300, 1_887_001)])
    assert result["classification"] == UNCONFIRMED_BOUNDARY
    assert "KBS_BOUNDARY_VOLUME_MISMATCH" in result["failure_reasons"]


def test_ssi_boundary_minute_difference_rejects() -> None:
    result = _proof(bars=[_bar("14:29:59", 74_000, 4_739_700), _bar("14:46:04", 74_300, 1_887_000)])
    assert result["classification"] == UNCONFIRMED_BOUNDARY
    assert "KBS_BOUNDARY_MINUTE_MISMATCH" in result["failure_reasons"]


def test_ssi_daily_volume_mismatch_rejects() -> None:
    result = _proof(daily=6_626_701)
    assert result["classification"] == UNCONFIRMED_BOUNDARY
    assert "SSI_DAILY_VOLUME_MISMATCH" in result["failure_reasons"]


def test_multiple_post_1429_bars_reject() -> None:
    result = _proof(
        bars=[
            _bar("14:29:59", 74_000, 4_700_000),
            _bar("14:44:59", 74_200, 39_700),
            _bar("14:45:04", 74_300, 1_887_000),
        ]
    )
    assert result["classification"] == UNCONFIRMED_BOUNDARY
    assert "MULTIPLE_CLOSING_BOUNDARY_BARS" in result["failure_reasons"]


def test_closing_bar_ohlc_not_single_price_rejects() -> None:
    result = _proof(
        bars=[
            _bar("14:29:59", 74_000, 4_739_700),
            _bar("14:45:04", 74_300, 1_887_000, high=74_400),
        ]
    )
    assert result["classification"] == UNCONFIRMED_BOUNDARY
    assert "BOUNDARY_OHLC_NOT_SINGLE_PRICE" in result["failure_reasons"]


def test_missing_kbs_witness_rejects() -> None:
    result = _proof(kbs=None)
    assert result["classification"] == UNCONFIRMED_BOUNDARY
    assert "KBS_WITNESS_MISSING" in result["failure_reasons"]


def test_missing_vci_witness_rejects() -> None:
    result = _proof(vci=None)
    assert result["classification"] == UNCONFIRMED_BOUNDARY
    assert "VCI_WITNESS_MISSING" in result["failure_reasons"]


def test_historical_result_can_never_be_proven() -> None:
    result = _proof()
    assert "PROVEN" not in result.values()


def test_exact_previous_10_uses_fixed_candidate_dates() -> None:
    dates = [f"2026-09-{day:02d}" for day in range(1, 12)]
    assert exact_previous_sessions(dates, as_of_date="2026-09-18") == dates[-10:]


def test_failed_candidate_is_not_replaced_by_older_11th() -> None:
    dates = [f"2026-09-{day:02d}" for day in range(1, 12)]
    exact = exact_previous_sessions(dates, as_of_date="2026-09-18")
    failed = exact[4]
    rows = [
        {
            "symbol": "FPT",
            "trading_date": item,
            "classification": (
                UNCONFIRMED_BOUNDARY if item == failed else CONFIRMED_INFERRED_BOUNDARY
            ),
        }
        for item in dates
    ]
    coverage = exact10_coverage(symbols=["FPT"], candidate_dates=exact, proof_rows=rows)[0]
    assert dates[0] not in coverage["exact_previous_10_dates"]
    assert coverage["confirmed_inferred_count_in_exact_10"] == 9
    assert not coverage["temporary_baseline_usable"]


def test_fpt_20260917_deterministic_fixture() -> None:
    result = _proof()
    assert result["ssi_last_continuous_minute"] == "14:29"
    assert result["ssi_last_continuous_price"] == 74_000
    assert result["ssi_boundary_time_raw"] == "14:45:04"
    assert result["ssi_boundary_minute"] == "14:45"
    assert result["ssi_boundary_price"] == 74_300
    assert result["ssi_boundary_volume"] == 1_887_000
    assert result["ssi_daily_volume"] == 6_626_700
    assert result["classification"] == CONFIRMED_INFERRED_BOUNDARY
