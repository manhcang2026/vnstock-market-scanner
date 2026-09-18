from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Iterable, Mapping, Sequence


PROVEN = "PROVEN"
INFERRED_BOUNDARY = "INFERRED_BOUNDARY"
UNAVAILABLE = "UNAVAILABLE"

STRONG_AGREEMENT = "STRONG_AGREEMENT"
WEAK_AGREEMENT = "WEAK_AGREEMENT"
DISAGREEMENT = "DISAGREEMENT"
SINGLE_SOURCE = "SINGLE_SOURCE"

OPENING_WINDOW_START = time(9, 13)
OPENING_WINDOW_END = time(9, 17)
OPENING_BOUNDARY = time(9, 15)
CLOSING_WINDOW_START = time(14, 28)
CLOSING_WINDOW_END = time(14, 47)
LAST_CONTINUOUS_CUTOFF = time(14, 29)

_PRICE_FIELDS = ("open", "high", "low", "close")


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().replace(tzinfo=None)
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _number(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _bar(raw: Mapping[str, Any]) -> dict[str, Any]:
    timestamp = _timestamp(raw["time"])
    normalized = {
        "time": timestamp.isoformat(sep=" "),
        **{field: _number(raw.get(field)) for field in _PRICE_FIELDS},
        "volume": _number(raw.get("volume")),
    }
    extra = {
        str(key): value
        for key, value in raw.items()
        if key not in {"time", *_PRICE_FIELDS, "volume"}
        and value is not None
    }
    if extra:
        normalized["provider_fields"] = extra
    return normalized


def _same_price(bar: Mapping[str, Any], price: Any) -> bool:
    expected = _number(price)
    return expected is not None and all(
        _number(bar.get(field)) == expected for field in _PRICE_FIELDS
    )


def _pct(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator) * 100.0


def reconcile_daily_volume(
    intraday_sum_volume: float | int | None,
    daily_volume: float | int | None,
) -> dict[str, Any]:
    intraday = _number(intraday_sum_volume)
    daily = _number(daily_volume)
    if intraday is None or daily is None:
        return {
            "intraday_sum_volume": intraday,
            "daily_volume": daily,
            "volume_diff": None,
            "volume_diff_pct": None,
            "reconciled_exactly": False,
            "reconciled_within_rounding_or_provider_semantics": False,
        }
    difference = intraday - daily
    return {
        "intraday_sum_volume": intraday,
        "daily_volume": daily,
        "volume_diff": difference,
        "volume_diff_pct": _pct(abs(difference), daily),
        "reconciled_exactly": difference == 0,
        # No undocumented tolerance is applied. This is deliberately false
        # unless a future provider contract defines its rounding semantics.
        "reconciled_within_rounding_or_provider_semantics": difference == 0,
    }


def audit_provider_session(
    *,
    provider: str,
    symbol: str,
    trading_date: str | date,
    minute_bars: Iterable[Mapping[str, Any]],
    daily_row: Mapping[str, Any] | None,
    previous_daily_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    session_date = date.fromisoformat(str(trading_date))
    bars = sorted(
        (
            _bar(raw)
            for raw in minute_bars
            if _timestamp(raw["time"]).date() == session_date
        ),
        key=lambda item: item["time"],
    )
    daily = dict(daily_row or {})
    previous_daily = dict(previous_daily_row or {})
    total_day_volume = sum(int(bar.get("volume") or 0) for bar in bars)

    opening_window = [
        bar
        for bar in bars
        if OPENING_WINDOW_START
        <= _timestamp(bar["time"]).time()
        <= OPENING_WINDOW_END
    ]
    opening_boundary_bar = next(
        (
            bar
            for bar in opening_window
            if _timestamp(bar["time"]).time() == OPENING_BOUNDARY
        ),
        None,
    )
    if opening_boundary_bar is None:
        opening_boundary_bar = next(
            (
                bar
                for bar in opening_window
                if _timestamp(bar["time"]).time() > OPENING_BOUNDARY
            ),
            opening_window[-1] if opening_window else None,
        )
    opening_at = (
        _timestamp(opening_boundary_bar["time"])
        if opening_boundary_bar is not None
        else None
    )
    last_before_opening = next(
        (
            bar
            for bar in reversed(bars)
            if opening_at is not None and _timestamp(bar["time"]) < opening_at
        ),
        None,
    )
    first_after_opening = next(
        (
            bar
            for bar in bars
            if opening_at is not None and _timestamp(bar["time"]) > opening_at
        ),
        None,
    )
    daily_open = _number(daily.get("open"))
    opening_mixed = bool(
        opening_boundary_bar is not None
        and daily_open is not None
        and not _same_price(opening_boundary_bar, daily_open)
    )
    opening_isolated = bool(
        opening_boundary_bar is not None
        and daily_open is not None
        and _same_price(opening_boundary_bar, daily_open)
    )

    closing_window = [
        bar
        for bar in bars
        if CLOSING_WINDOW_START
        <= _timestamp(bar["time"]).time()
        <= CLOSING_WINDOW_END
    ]
    last_continuous = next(
        (
            bar
            for bar in reversed(bars)
            if _timestamp(bar["time"]).time() <= LAST_CONTINUOUS_CUTOFF
        ),
        None,
    )
    closing_candidates = [
        bar
        for bar in closing_window
        if _timestamp(bar["time"]).time() > LAST_CONTINUOUS_CUTOFF
    ]
    final_bar = bars[-1] if bars else None
    closing_volume = (
        sum(int(bar.get("volume") or 0) for bar in closing_candidates)
        if closing_candidates
        else None
    )
    closing_isolated = bool(
        len(closing_candidates) == 1
        and final_bar == closing_candidates[0]
        and _same_price(closing_candidates[0], closing_candidates[0].get("close"))
        and last_continuous is not None
    )
    closing_price_impact = None
    if last_continuous and final_bar:
        preclose = _number(last_continuous.get("close"))
        final_price = _number(final_bar.get("close"))
        if preclose not in (None, 0) and final_price is not None:
            closing_price_impact = (final_price - preclose) / preclose * 100.0

    reconciliation = reconcile_daily_volume(
        total_day_volume if bars else None,
        daily.get("volume"),
    )
    return {
        "provider": provider.upper(),
        "symbol": symbol.upper(),
        "trading_date": session_date.isoformat(),
        "minute_bar_count": len(bars),
        "quality_tier": INFERRED_BOUNDARY if bars else UNAVAILABLE,
        "last_bar_before_opening": last_before_opening,
        "opening_window_bars": opening_window,
        "opening_boundary_bar": opening_boundary_bar,
        "opening_boundary_time": opening_boundary_bar["time"] if opening_boundary_bar else None,
        "opening_boundary_volume": opening_boundary_bar.get("volume") if opening_boundary_bar else None,
        "first_continuous_after_opening": first_after_opening,
        "daily_previous_close": _number(previous_daily.get("close")),
        "daily_open": daily_open,
        "opening_bar_mixed": opening_mixed,
        "opening_bar_isolated": opening_isolated,
        "opening_inference_quality": INFERRED_BOUNDARY if opening_isolated else UNAVAILABLE,
        "last_continuous_bar": last_continuous,
        "last_continuous_time": last_continuous["time"] if last_continuous else None,
        "last_continuous_price": last_continuous.get("close") if last_continuous else None,
        "closing_window_bars": closing_window,
        "closing_boundary_bars": closing_candidates,
        "candidate_closing_boundary_volume": closing_volume,
        "closing_bar_isolated": closing_isolated,
        "closing_inference_quality": INFERRED_BOUNDARY if closing_isolated else UNAVAILABLE,
        "final_bar": final_bar,
        "final_time": final_bar["time"] if final_bar else None,
        "final_price": final_bar.get("close") if final_bar else None,
        "total_day_volume": total_day_volume if bars else None,
        "candidate_closing_share_pct": _pct(closing_volume, total_day_volume),
        "inferred_closing_price_impact_pct": closing_price_impact,
        **reconciliation,
    }


def compare_provider_rows(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
    *,
    domain: str,
) -> dict[str, Any]:
    domain_upper = domain.upper()
    if domain_upper not in {"ATO", "ATC"}:
        raise ValueError("domain must be ATO or ATC")

    time_key = "opening_boundary_time" if domain_upper == "ATO" else "final_time"
    price_key = "daily_open" if domain_upper == "ATO" else "final_price"
    volume_key = (
        "opening_boundary_volume"
        if domain_upper == "ATO"
        else "candidate_closing_boundary_volume"
    )
    present = [
        row
        for row in (left, right)
        if row is not None
        and row.get(time_key)
        and _number(row.get(volume_key)) is not None
    ]
    if not present:
        classification = UNAVAILABLE
    elif len(present) == 1:
        classification = SINGLE_SOURCE
    else:
        same_time = left.get(time_key) == right.get(time_key)
        same_price = _number(left.get(price_key)) == _number(right.get(price_key))
        same_volume = _number(left.get(volume_key)) == _number(right.get(volume_key))
        if same_time and same_price and same_volume:
            classification = STRONG_AGREEMENT
        elif same_time and same_price:
            classification = WEAK_AGREEMENT
        else:
            classification = DISAGREEMENT

    left_volume = _number(left.get(volume_key)) if left else None
    right_volume = _number(right.get(volume_key)) if right else None
    left_day = _number(left.get("total_day_volume")) if left else None
    right_day = _number(right.get("total_day_volume")) if right else None
    left_price = _number(left.get(price_key)) if left else None
    right_price = _number(right.get(price_key)) if right else None
    volume_abs_diff = (
        abs(left_volume - right_volume)
        if left_volume is not None and right_volume is not None
        else None
    )
    day_abs_diff = (
        abs(left_day - right_day)
        if left_day is not None and right_day is not None
        else None
    )
    return {
        "symbol": (left or right or {}).get("symbol"),
        "trading_date": (left or right or {}).get("trading_date"),
        "domain": domain_upper,
        "classification": classification,
        "kbs_time": left.get(time_key) if left else None,
        "vci_time": right.get(time_key) if right else None,
        "kbs_price": left_price,
        "vci_price": right_price,
        "kbs_boundary_volume": left_volume,
        "vci_boundary_volume": right_volume,
        "boundary_volume_abs_diff": volume_abs_diff,
        "boundary_volume_pct_diff": _pct(
            volume_abs_diff,
            max(left_volume, right_volume)
            if left_volume is not None and right_volume is not None
            else None,
        ),
        "closing_volume_abs_diff": volume_abs_diff if domain_upper == "ATC" else None,
        "closing_volume_pct_diff": (
            _pct(volume_abs_diff, max(left_volume, right_volume))
            if domain_upper == "ATC" and left_volume is not None and right_volume is not None
            else None
        ),
        "kbs_day_volume": left_day,
        "vci_day_volume": right_day,
        "day_volume_abs_diff": day_abs_diff,
        "day_volume_pct_diff": _pct(
            day_abs_diff,
            max(left_day, right_day)
            if left_day is not None and right_day is not None
            else None,
        ),
        "price_diff": (
            abs(left_price - right_price)
            if left_price is not None and right_price is not None
            else None
        ),
        "closing_price_diff": (
            abs(left_price - right_price)
            if domain_upper == "ATC"
            and left_price is not None
            and right_price is not None
            else None
        ),
        "kbs_inference_quality": (
            left.get("opening_inference_quality" if domain_upper == "ATO" else "closing_inference_quality")
            if left
            else UNAVAILABLE
        ),
        "vci_inference_quality": (
            right.get("opening_inference_quality" if domain_upper == "ATO" else "closing_inference_quality")
            if right
            else UNAVAILABLE
        ),
    }


def recommend_domain(
    rows: Sequence[Mapping[str, Any]],
    comparisons: Sequence[Mapping[str, Any]],
    *,
    domain: str,
) -> dict[str, str]:
    domain_upper = domain.upper()
    quality_key = (
        "opening_inference_quality" if domain_upper == "ATO" else "closing_inference_quality"
    )
    usable = [row for row in rows if row.get(quality_key) == INFERRED_BOUNDARY]
    comparable = [
        row
        for row in comparisons
        if row.get("domain") == domain_upper
        and row.get("classification") != UNAVAILABLE
    ]
    if domain_upper == "ATO" and any(row.get("opening_bar_mixed") for row in rows):
        return {
            "recommendation": "DO_NOT_BOOTSTRAP",
            "reason": (
                "At least one 09:15 boundary bar mixes the official daily open "
                "with continuous-trading prices, so exact ATO volume is not isolated."
            ),
        }
    if not usable:
        return {
            "recommendation": "DO_NOT_BOOTSTRAP",
            "reason": "No session isolates a usable inferred boundary volume.",
        }

    all_rows_usable = len(usable) == len(rows) and bool(rows)
    all_comparisons_exact = bool(comparable) and all(
        item.get("classification") == STRONG_AGREEMENT for item in comparable
    )
    all_daily_exact = all(row.get("reconciled_exactly") for row in rows)
    if all_rows_usable and all_comparisons_exact and all_daily_exact:
        return {
            "recommendation": "ALLOW_TEMP_INFERRED_BOOTSTRAP",
            "reason": (
                "Every audited provider-session is isolated, cross-provider values "
                "agree exactly, and intraday volume reconciles exactly to daily volume."
            ),
        }
    return {
        "recommendation": "DIAGNOSTIC_ONLY",
        "reason": (
            "Some inferred boundaries are usable, but the complete audit set does not "
            "have exact isolation, agreement, and daily reconciliation throughout."
        ),
    }
