from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HOLIDAY_FILE = ROOT / "config" / "market_holidays.csv"
COVERAGE_FILE = ROOT / "config" / "market_calendar_years.txt"

MORNING_START = time(9, 0)
MORNING_END = time(11, 34)  # includes current 4-minute scanner grace
AFTERNOON_START = time(13, 0)
AFTERNOON_END = time(15, 4)

STALE_IDENTICAL_RATIO = 0.995
STALE_MIN_COMPARABLE = 760


class MarketCalendarCoverageError(RuntimeError):
    pass


class StaleMarketDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionDecision:
    trading_day: bool
    reason: str


def _covered_years() -> set[int]:
    if not COVERAGE_FILE.exists():
        raise MarketCalendarCoverageError(
            f"Missing market calendar coverage file: {COVERAGE_FILE}"
        )
    years: set[int] = set()
    for raw in COVERAGE_FILE.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        years.add(int(raw))
    if not years:
        raise MarketCalendarCoverageError("Market calendar coverage is empty")
    return years


def _holiday_map() -> dict[date, str]:
    if not HOLIDAY_FILE.exists():
        raise MarketCalendarCoverageError(
            f"Missing market holiday file: {HOLIDAY_FILE}"
        )
    result: dict[date, str] = {}
    with HOLIDAY_FILE.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            raw = str(row.get("date") or "").strip()
            if not raw:
                continue
            d = date.fromisoformat(raw)
            result[d] = str(row.get("reason") or "market_holiday").strip()
    return result


def session_decision(value: date | datetime) -> SessionDecision:
    d = value.date() if isinstance(value, datetime) else value

    # Fail closed. A new year MUST be explicitly added before scanners may write.
    covered = _covered_years()
    if d.year not in covered:
        return SessionDecision(
            False,
            f"calendar_year_{d.year}_not_approved",
        )

    if d.weekday() >= 5:
        return SessionDecision(False, "weekend")

    holidays = _holiday_map()
    if d in holidays:
        return SessionDecision(False, holidays[d])

    return SessionDecision(True, "scheduled_trading_day")


def is_trading_day(value: date | datetime) -> bool:
    return session_decision(value).trading_day


def is_market_slot(dt: datetime) -> bool:
    decision = session_decision(dt)
    if not decision.trading_day:
        return False

    current = dt.time().replace(tzinfo=None)
    return (
        MORNING_START <= current <= MORNING_END
        or AFTERNOON_START <= current <= AFTERNOON_END
    )


def last_completed_trading_date(
    run_at: datetime,
    *,
    close_safe_after: time = time(15, 5),
    max_lookback_days: int = 370,
) -> date:
    today = run_at.date()
    now_time = run_at.time().replace(tzinfo=None)

    if is_trading_day(today) and now_time >= close_safe_after:
        return today

    probe = today - timedelta(days=1)
    for _ in range(max_lookback_days):
        decision = session_decision(probe)
        if decision.trading_day:
            return probe
        # If we crossed into an uncovered year, fail closed instead of guessing.
        if probe.year not in _covered_years():
            raise MarketCalendarCoverageError(
                f"No approved calendar coverage while searching before {today}"
            )
        probe -= timedelta(days=1)

    raise MarketCalendarCoverageError(
        f"Could not find completed trading day before {today}"
    )


def history_exclusive_date(run_at: datetime) -> date:
    """Exclusive upper bound that includes the last completed trading session."""
    return last_completed_trading_date(run_at) + timedelta(days=1)


def _numeric_equal(a: pd.Series, b: pd.Series, atol: float = 1e-9) -> pd.Series:
    left = pd.to_numeric(a, errors="coerce")
    right = pd.to_numeric(b, errors="coerce")
    both = left.notna() & right.notna()
    return both & ((left - right).abs() <= atol)


def assert_price_board_fresh(
    price_board: pd.DataFrame,
    supabase_request: Callable[..., Any],
    scan_at: datetime,
    *,
    identical_ratio: float = STALE_IDENTICAL_RATIO,
    min_comparable: int = STALE_MIN_COMPARABLE,
) -> dict[str, Any]:
    """
    Catastrophic stale-source breaker.

    It only compares against stock_snapshot when that snapshot belongs to an
    OLDER date. Same-day quiet 5-minute intervals are never rejected.

    A source is blocked only when at least `min_comparable` symbols can be
    compared and >=99.5% have BOTH identical price and accumulated volume.
    """
    if price_board is None or price_board.empty:
        raise StaleMarketDataError("Price board is empty")

    response = supabase_request(
        "GET",
        "stock_snapshot",
        params={
            "select": "symbol,current_price,volume_accumulated,trading_date",
            "order": "symbol.asc",
            "limit": "1000",
        },
    )
    previous = pd.DataFrame(response.json())
    if previous.empty or "trading_date" not in previous.columns:
        return {"checked": False, "reason": "no_previous_snapshot"}

    previous["trading_date"] = previous["trading_date"].astype(str)
    latest_date = previous["trading_date"].max()
    today = scan_at.date().isoformat()

    if latest_date >= today:
        return {
            "checked": False,
            "reason": "same_day_or_newer_snapshot",
            "previous_date": latest_date,
        }

    candidate = price_board.copy()
    candidate["symbol"] = (
        candidate["symbol"].fillna("").astype(str).str.strip().str.upper()
    )
    previous["symbol"] = (
        previous["symbol"].fillna("").astype(str).str.strip().str.upper()
    )
    previous = previous[previous["trading_date"] == latest_date]

    merged = candidate[
        ["symbol", "close_price", "volume_accumulated"]
    ].merge(
        previous[
            ["symbol", "current_price", "volume_accumulated"]
        ].rename(columns={"volume_accumulated": "previous_volume"}),
        on="symbol",
        how="inner",
    )

    comparable = len(merged)
    if comparable < min_comparable:
        return {
            "checked": True,
            "blocked": False,
            "reason": "not_enough_comparable_symbols",
            "comparable": comparable,
            "previous_date": latest_date,
        }

    same_price = _numeric_equal(merged["close_price"], merged["current_price"])
    same_volume = _numeric_equal(
        merged["volume_accumulated"], merged["previous_volume"]
    )
    identical = same_price & same_volume
    identical_count = int(identical.sum())
    ratio = identical_count / comparable

    result = {
        "checked": True,
        "blocked": ratio >= identical_ratio,
        "comparable": comparable,
        "identical": identical_count,
        "identical_ratio": round(ratio, 6),
        "previous_date": latest_date,
        "candidate_date": today,
    }

    if result["blocked"]:
        raise StaleMarketDataError(
            "STALE SOURCE BLOCKED: "
            f"{identical_count}/{comparable} symbols "
            f"({ratio:.2%}) have identical price + accumulated volume "
            f"versus previous valid snapshot {latest_date}."
        )
    return result
