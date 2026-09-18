from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence


CONFIRMED_INFERRED_BOUNDARY = "CONFIRMED_INFERRED_BOUNDARY"
UNCONFIRMED_BOUNDARY = "UNCONFIRMED_BOUNDARY"
UNAVAILABLE = "UNAVAILABLE"
INFERRED_BOUNDARY = "INFERRED_BOUNDARY"
PROOF = "CROSS_PROVIDER_BOUNDARY_CONFIRMED_V1"
SOURCE = "SSI_REST"

CLOSING_START = time(14, 30)
CLOSING_END = time(14, 47)
LAST_CONTINUOUS_CUTOFF = time(14, 29)
WITNESS_PRICE_MULTIPLIER = Decimal("1000")


def normalize_provider_minute(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[1]
    elif " " in text:
        text = text.rsplit(" ", 1)[-1]
    text = text.removesuffix("Z").split("+", 1)[0]
    for pattern in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M", "%H%M%S"):
        try:
            return datetime.strptime(text, pattern).strftime("%H:%M")
        except ValueError:
            continue
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _json_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def normalize_witness_price(value: Any) -> int | float | None:
    price = _decimal(value)
    return _json_number(price * WITNESS_PRICE_MULTIPLIER) if price is not None else None


def _field(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if row.get(name) is not None:
            return row[name]
    return None


def _bar(row: Mapping[str, Any]) -> dict[str, Any] | None:
    raw_time = _field(row, "provider_time", "time", "minute")
    minute = normalize_provider_minute(raw_time)
    if minute is None:
        return None
    prices = {name: _decimal(row.get(name)) for name in ("open", "high", "low", "close")}
    volume = _decimal(row.get("volume"))
    if any(value is None for value in prices.values()) or volume is None:
        return None
    if volume < 0 or volume != volume.to_integral_value():
        return None
    return {
        "provider_time": str(raw_time),
        "minute": minute,
        **{name: _json_number(value) for name, value in prices.items()},
        "volume": int(volume),
    }


def _minute_time(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def _witness_values(witness: Mapping[str, Any] | None) -> dict[str, Any]:
    if witness is None:
        return {"minute": None, "price_raw": None, "price": None, "volume": None}
    raw_price = _field(witness, "boundary_price", "final_price", "price")
    return {
        "minute": normalize_provider_minute(
            _field(witness, "boundary_time", "final_time", "minute")
        ),
        "price_raw": raw_price,
        "price": normalize_witness_price(raw_price),
        "volume": _field(
            witness,
            "boundary_volume",
            "candidate_closing_boundary_volume",
            "volume",
        ),
    }


def prove_ssi_atc_boundary(
    *,
    symbol: str,
    trading_date: str,
    ssi_bars: Iterable[Mapping[str, Any]],
    ssi_daily_volume: int | None,
    kbs_witness: Mapping[str, Any] | None,
    vci_witness: Mapping[str, Any] | None,
) -> dict[str, Any]:
    date.fromisoformat(trading_date)
    normalized = [bar for row in ssi_bars if (bar := _bar(row)) is not None]
    normalized.sort(key=lambda row: (row["minute"], row["provider_time"]))
    intraday_volume = sum(row["volume"] for row in normalized) if normalized else None
    daily_volume = int(ssi_daily_volume) if ssi_daily_volume is not None else None
    volume_diff = (
        intraday_volume - daily_volume
        if intraday_volume is not None and daily_volume is not None
        else None
    )

    last_continuous = next(
        (
            row
            for row in reversed(normalized)
            if _minute_time(row["minute"]) <= LAST_CONTINUOUS_CUTOFF
        ),
        None,
    )
    candidates = [
        row
        for row in normalized
        if CLOSING_START <= _minute_time(row["minute"]) <= CLOSING_END
    ]
    final_bar = normalized[-1] if normalized else None
    boundary = candidates[0] if len(candidates) == 1 else None
    kbs = _witness_values(kbs_witness)
    vci = _witness_values(vci_witness)

    result: dict[str, Any] = {
        "symbol": symbol.upper(),
        "trading_date": trading_date,
        "source": SOURCE,
        "proof": None,
        "classification": UNAVAILABLE,
        "quality": UNAVAILABLE,
        "failure_reasons": [],
        "ssi_bar_count": len(normalized),
        "ssi_last_continuous_time_raw": last_continuous["provider_time"] if last_continuous else None,
        "ssi_last_continuous_minute": last_continuous["minute"] if last_continuous else None,
        "ssi_last_continuous_price": last_continuous["close"] if last_continuous else None,
        "ssi_candidate_boundary_bars": candidates,
        "ssi_boundary_time_raw": boundary["provider_time"] if boundary else None,
        "ssi_boundary_minute": boundary["minute"] if boundary else None,
        "ssi_boundary_price": boundary["close"] if boundary else None,
        "ssi_boundary_volume": boundary["volume"] if boundary else None,
        "ssi_final_bar": final_bar,
        "ssi_intraday_total_volume": intraday_volume,
        "ssi_daily_volume": daily_volume,
        "ssi_volume_diff": volume_diff,
        "ssi_daily_reconciled_exactly": volume_diff == 0 if volume_diff is not None else False,
        "kbs_boundary_minute": kbs["minute"],
        "kbs_boundary_price_raw": kbs["price_raw"],
        "kbs_boundary_price": kbs["price"],
        "kbs_boundary_volume": kbs["volume"],
        "vci_boundary_minute": vci["minute"],
        "vci_boundary_price_raw": vci["price_raw"],
        "vci_boundary_price": vci["price"],
        "vci_boundary_volume": vci["volume"],
        "minute_match_kbs": False,
        "minute_match_vci": False,
        "price_match_kbs": False,
        "price_match_vci": False,
        "volume_match_kbs": False,
        "volume_match_vci": False,
    }
    failures: list[str] = result["failure_reasons"]
    if not normalized:
        failures.append("SSI_MINUTE_DATA_MISSING")
        return result
    if last_continuous is None:
        failures.append("LAST_CONTINUOUS_MISSING")
        return result
    if not candidates:
        failures.append("CLOSING_BOUNDARY_MISSING")
        return result

    result["classification"] = UNCONFIRMED_BOUNDARY
    result["quality"] = UNCONFIRMED_BOUNDARY
    if len(candidates) != 1:
        failures.append("MULTIPLE_CLOSING_BOUNDARY_BARS")
        return result
    if final_bar != boundary:
        failures.append("BOUNDARY_NOT_FINAL_BAR")
    if len({boundary[name] for name in ("open", "high", "low", "close")}) != 1:
        failures.append("BOUNDARY_OHLC_NOT_SINGLE_PRICE")
    if volume_diff != 0:
        failures.append("SSI_DAILY_VOLUME_MISMATCH")
    if kbs_witness is None:
        failures.append("KBS_WITNESS_MISSING")
    if vci_witness is None:
        failures.append("VCI_WITNESS_MISSING")

    result["minute_match_kbs"] = boundary["minute"] == kbs["minute"]
    result["minute_match_vci"] = boundary["minute"] == vci["minute"]
    result["price_match_kbs"] = _decimal(boundary["close"]) == _decimal(kbs["price"])
    result["price_match_vci"] = _decimal(boundary["close"]) == _decimal(vci["price"])
    result["volume_match_kbs"] = _decimal(boundary["volume"]) == _decimal(kbs["volume"])
    result["volume_match_vci"] = _decimal(boundary["volume"]) == _decimal(vci["volume"])
    for check, reason in (
        (result["minute_match_kbs"], "KBS_BOUNDARY_MINUTE_MISMATCH"),
        (result["minute_match_vci"], "VCI_BOUNDARY_MINUTE_MISMATCH"),
        (result["price_match_kbs"], "KBS_BOUNDARY_PRICE_MISMATCH"),
        (result["price_match_vci"], "VCI_BOUNDARY_PRICE_MISMATCH"),
        (result["volume_match_kbs"], "KBS_BOUNDARY_VOLUME_MISMATCH"),
        (result["volume_match_vci"], "VCI_BOUNDARY_VOLUME_MISMATCH"),
    ):
        if not check:
            failures.append(reason)

    if not failures:
        result["classification"] = CONFIRMED_INFERRED_BOUNDARY
        result["quality"] = INFERRED_BOUNDARY
        result["proof"] = PROOF
    return result


def exact_previous_sessions(
    observed_dates: Iterable[str], *, as_of_date: str, lookback: int = 10
) -> list[str]:
    cutoff = date.fromisoformat(as_of_date)
    valid: set[str] = set()
    for value in observed_dates:
        try:
            parsed = date.fromisoformat(value)
        except (TypeError, ValueError):
            continue
        if parsed < cutoff and parsed.isoformat() == value:
            valid.add(value)
    return sorted(valid)[-lookback:]


def exact10_coverage(
    *,
    symbols: Sequence[str],
    candidate_dates: Sequence[str],
    proof_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    fixed = tuple(candidate_dates)
    confirmed = {
        (str(row.get("symbol", "")).upper(), str(row.get("trading_date", "")))
        for row in proof_rows
        if row.get("classification") == CONFIRMED_INFERRED_BOUNDARY
    }
    return [
        {
            "symbol": symbol.upper(),
            "exact_previous_10_dates": list(fixed),
            "confirmed_inferred_count_in_exact_10": sum(
                (symbol.upper(), session) in confirmed for session in fixed
            ),
            "temporary_baseline_usable": len(fixed) == 10
            and all((symbol.upper(), session) in confirmed for session in fixed),
        }
        for symbol in symbols
    ]
