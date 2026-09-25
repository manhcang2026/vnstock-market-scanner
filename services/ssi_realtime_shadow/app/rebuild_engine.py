"""Rebuild disposable CCC engine state from symbol-scoped market reads."""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import fmean
from typing import Callable

from .canonical_engine_store import (
    CanonicalEngineStore,
    CurrentState,
    TechnicalBaseline,
    VolumeBaselinePoint,
)
from .canonical_market_store import utc_now
from .market_session import VN_TZ, classify_market_session, normalize_exchange
from .volume_baseline import VolumeGridPoint, volume_market_grid


SHARD_RE = re.compile(r"^ccc_market_(\d{4})\.db$")
TARGET_BASELINE_SESSIONS = 10


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Bounded data for exactly one symbol."""

    symbol: str
    daily_history: tuple[sqlite3.Row, ...]
    prior_session_dates: tuple[str, ...]
    current_minutes: dict[str, sqlite3.Row]
    current_session_complete: bool
    load_completed_session: Callable[[str], dict[str, sqlite3.Row] | None]


@dataclass(frozen=True, slots=True)
class SymbolCalculation:
    technical: TechnicalBaseline
    volume: tuple[VolumeBaselinePoint, ...]
    current: CurrentState


class MarketShardReader:
    """Keep shards read-only and issue only symbol/date-bounded row reads."""

    def __init__(self, db_dir: str | Path) -> None:
        paths = sorted(
            path
            for path in Path(db_dir).glob("ccc_market_*.db")
            if SHARD_RE.fullmatch(path.name)
        )
        if not paths:
            raise FileNotFoundError(f"No ccc_market_YYYY.db shards in {db_dir}")
        self._connections: dict[int, sqlite3.Connection] = {}
        for path in paths:
            match = SHARD_RE.fullmatch(path.name)
            assert match is not None
            connection = sqlite3.connect(
                f"file:{path.resolve().as_posix()}?mode=ro", uri=True
            )
            connection.row_factory = sqlite3.Row
            self._connections[int(match.group(1))] = connection

    def close(self) -> None:
        for connection in self._connections.values():
            connection.close()
        self._connections.clear()

    def __enter__(self) -> "MarketShardReader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def symbols(self) -> tuple[str, ...]:
        symbols: set[str] = set()
        for connection in self._connections.values():
            symbols.update(
                str(row[0])
                for row in connection.execute(
                    "SELECT symbol FROM daily_bars GROUP BY symbol"
                )
            )
            symbols.update(
                str(row[0])
                for row in connection.execute(
                    "SELECT symbol FROM minute_bars GROUP BY symbol"
                )
            )
        return tuple(sorted(symbols))

    def _daily_history(self, symbol: str, as_of: str) -> tuple[sqlite3.Row, ...]:
        rows: list[sqlite3.Row] = []
        for connection in self._connections.values():
            rows.extend(
                connection.execute(
                    """SELECT symbol,trading_date,exchange,close,volume
                       FROM daily_bars
                       WHERE symbol=? AND trading_date<?
                       ORDER BY trading_date DESC""",
                    (symbol, as_of),
                )
            )
        rows.sort(key=lambda row: str(row["trading_date"]), reverse=True)
        return tuple(rows)

    def _prior_session_dates(self, symbol: str, as_of: str) -> tuple[str, ...]:
        dates: set[str] = set()
        for connection in self._connections.values():
            dates.update(
                str(row[0])
                for row in connection.execute(
                    """SELECT trading_date FROM daily_bars
                       WHERE symbol=? AND trading_date<?
                       ORDER BY trading_date DESC""",
                    (symbol, as_of),
                )
            )
        return tuple(sorted(dates, reverse=True))

    def _minute_rows(self, symbol: str, trading_date: str) -> dict[str, sqlite3.Row]:
        connection = self._connections.get(date.fromisoformat(trading_date).year)
        if connection is None:
            return {}
        rows = connection.execute(
            """SELECT symbol,trading_date,minute,exchange,close,volume,
                      provider_total_volume
               FROM minute_bars WHERE symbol=? AND trading_date=?
               ORDER BY minute""",
            (symbol, trading_date),
        )
        return {str(row["minute"]): row for row in rows}

    def _session_complete(self, symbol: str, trading_date: str) -> bool:
        connection = self._connections.get(date.fromisoformat(trading_date).year)
        if connection is None:
            return False
        if connection.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type='table' AND name='rest_session_status'"""
        ).fetchone() is None:
            return False
        return connection.execute(
            """SELECT 1 FROM rest_session_status
               WHERE mode='minute' AND symbol=? AND trading_date=?
                 AND resolution=1 AND status='COMPLETED'""",
            (symbol, trading_date),
        ).fetchone() is not None

    def _daily_session_exists(self, symbol: str, trading_date: str) -> bool:
        connection = self._connections.get(date.fromisoformat(trading_date).year)
        if connection is None:
            return False
        return connection.execute(
            """SELECT 1 FROM daily_bars
               WHERE symbol=? AND trading_date=? LIMIT 1""",
            (symbol, trading_date),
        ).fetchone() is not None

    def load_symbol(self, symbol: str, as_of: str) -> MarketSnapshot:
        daily_history = self._daily_history(symbol, as_of)
        prior_dates = self._prior_session_dates(symbol, as_of)
        current = self._minute_rows(symbol, as_of)

        def load_completed_session(trading_date: str) -> dict[str, sqlite3.Row] | None:
            # prior_dates proves daily_bars evidence; the exact session row
            # separately proves that sparse minute gaps may mean zero trades.
            if trading_date not in prior_dates:
                return None
            if not self._session_complete(symbol, trading_date):
                return None
            return self._minute_rows(symbol, trading_date)

        return MarketSnapshot(
            symbol=symbol,
            daily_history=daily_history,
            prior_session_dates=prior_dates,
            current_minutes=current,
            current_session_complete=(
                self._daily_session_exists(symbol, as_of)
                and self._session_complete(symbol, as_of)
            ),
            load_completed_session=load_completed_session,
        )


def exact_price_change(
    *,
    exchange: str,
    trading_date: str,
    current_minute: str,
    current_price: float | None,
    closes: dict[str, float],
    window: int,
    unresolved_gap_minutes: set[str] | frozenset[str] = frozenset(),
) -> float | None:
    """Compare price state at an exact clock anchor in one continuous segment."""
    if current_price is None or not math.isfinite(current_price) or current_price <= 0:
        return None
    try:
        selected = datetime.fromisoformat(
            f"{date.fromisoformat(trading_date).isoformat()}T{current_minute}:00"
        ).replace(tzinfo=VN_TZ)
    except ValueError:
        return None
    anchor_at = selected - timedelta(minutes=window)
    selected_session = classify_market_session(exchange, selected)
    anchor_session = classify_market_session(exchange, anchor_at)
    if (
        not selected_session.is_continuous
        or not anchor_session.is_continuous
        or selected_session.session_type is not anchor_session.session_type
    ):
        return None
    anchor = price_state_at(
        exchange=exchange,
        trading_date=trading_date,
        target_minute=anchor_at.strftime("%H:%M"),
        closes=closes,
        unresolved_gap_minutes=unresolved_gap_minutes,
    )
    if anchor is None:
        return None
    return (current_price / anchor - 1.0) * 100.0


def price_state_at(
    *,
    exchange: str,
    trading_date: str,
    target_minute: str,
    closes: dict[str, float],
    unresolved_gap_minutes: set[str] | frozenset[str] = frozenset(),
) -> float | None:
    """Return the latest valid price carried within one continuous segment.

    The helper is deliberately pure and symbol/day-bounded. Sparse minutes are
    no-trade evidence only when the caller has established that fact; callers
    pass unknown intervals explicitly through ``unresolved_gap_minutes``.
    """
    try:
        selected = datetime.fromisoformat(
            f"{date.fromisoformat(trading_date).isoformat()}T{target_minute}:00"
        ).replace(tzinfo=VN_TZ)
    except (TypeError, ValueError):
        return None
    selected_session = classify_market_session(exchange, selected)
    if not selected_session.is_continuous:
        return None

    target = selected.strftime("%H:%M")
    gaps = {
        str(minute)[:5]
        for minute in unresolved_gap_minutes
        if str(minute)[:5] <= target
    }
    if target in gaps:
        return None

    candidates: list[tuple[str, float]] = []
    for minute, raw_price in closes.items():
        try:
            canonical_minute = datetime.strptime(str(minute), "%H:%M").strftime(
                "%H:%M"
            )
        except ValueError:
            continue
        price = usable_price(raw_price)
        if price is None or canonical_minute > target or canonical_minute in gaps:
            continue
        candidate_at = datetime.fromisoformat(
            f"{selected.date().isoformat()}T{canonical_minute}:00"
        ).replace(tzinfo=VN_TZ)
        candidate_session = classify_market_session(exchange, candidate_at)
        if candidate_session.session_id == selected_session.session_id:
            candidates.append((canonical_minute, price))
    if not candidates:
        return None

    source_minute, price = max(candidates)
    if any(source_minute < gap <= target for gap in gaps):
        return None
    return price


def usable_price(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _exchange_for(snapshot: MarketSnapshot) -> str | None:
    candidates: list[object] = []
    candidates.extend(row["exchange"] for row in snapshot.current_minutes.values())
    candidates.extend(row["exchange"] for row in snapshot.daily_history)
    for candidate in candidates:
        if candidate:
            try:
                return normalize_exchange(str(candidate))
            except ValueError:
                continue
    return None


def _technical(symbol: str, as_of: str, snapshot: MarketSnapshot) -> TechnicalBaseline:
    previous_close = (
        usable_price(snapshot.daily_history[0]["close"])
        if snapshot.daily_history
        else None
    )
    closes = [
        close
        for row in snapshot.daily_history
        if (close := usable_price(row["close"])) is not None
    ]
    recent10 = closes[:10]
    recent200 = closes[:200]
    return TechnicalBaseline(
        symbol=symbol,
        as_of_date=as_of,
        previous_close=previous_close,
        ma10=fmean(recent10) if len(recent10) == 10 else None,
        ma10_sessions=len(recent10),
        ma200=fmean(recent200) if len(recent200) == 200 else None,
        ma200_sessions=len(recent200),
    )


def grid_volumes(
    rows: dict[str, sqlite3.Row],
    grid: tuple[VolumeGridPoint, ...],
    *,
    complete: bool,
) -> list[int | None]:
    values: list[int | None] = []
    for point in grid:
        row = rows.get(point.minute)
        if row is None:
            values.append(0 if complete else None)
            continue
        raw_volume = row["volume"]
        if raw_volume is None or int(raw_volume) < 0:
            values.append(None)
        else:
            values.append(int(raw_volume))
    return values


def rolling_volume(
    values: list[int | None],
    grid: tuple[VolumeGridPoint, ...],
    index: int,
    window: int,
) -> int | None:
    point = grid[index]
    ready = point.rolling_15_ready if window == 15 else point.rolling_30_ready
    if not point.is_continuous or not ready:
        return None
    segment_indices = [
        candidate
        for candidate in range(index + 1)
        if grid[candidate].is_continuous
        and grid[candidate].session_segment == point.session_segment
    ]
    selected = segment_indices[-window:]
    if len(selected) != window or any(
        values[candidate] is None for candidate in selected
    ):
        return None
    return sum(values[candidate] for candidate in selected)  # type: ignore[arg-type]


def _baseline(
    symbol: str,
    as_of: str,
    exchange: str,
    snapshot: MarketSnapshot,
) -> tuple[VolumeBaselinePoint, ...]:
    grid = volume_market_grid(exchange, include_provider_boundaries=True)
    cumulative_samples = {point.minute: [] for point in grid}
    samples15 = {point.minute: [] for point in grid if point.rolling_15_ready}
    samples30 = {point.minute: [] for point in grid if point.rolling_30_ready}

    def enough() -> bool:
        buckets = (
            list(cumulative_samples.values())
            + list(samples15.values())
            + list(samples30.values())
        )
        return bool(buckets) and all(
            len(bucket) >= TARGET_BASELINE_SESSIONS for bucket in buckets
        )

    for trading_date in snapshot.prior_session_dates:
        rows = snapshot.load_completed_session(trading_date)
        if rows is None:
            continue
        volumes = grid_volumes(rows, grid, complete=True)
        cumulative = 0
        cumulative_valid = True
        for index, point in enumerate(grid):
            volume = volumes[index]
            if volume is None:
                cumulative_valid = False
            elif cumulative_valid:
                cumulative += volume
            if cumulative_valid and len(cumulative_samples[point.minute]) < 10:
                cumulative_samples[point.minute].append(float(cumulative))
            rolling15 = rolling_volume(volumes, grid, index, 15)
            if rolling15 is not None and len(samples15.get(point.minute, ())) < 10:
                samples15[point.minute].append(float(rolling15))
            rolling30 = rolling_volume(volumes, grid, index, 30)
            if rolling30 is not None and len(samples30.get(point.minute, ())) < 10:
                samples30[point.minute].append(float(rolling30))
        if enough():
            break

    return tuple(
        VolumeBaselinePoint(
            symbol=symbol,
            minute=point.minute,
            as_of_date=as_of,
            avg_cumulative_volume=(
                fmean(cumulative_samples[point.minute])
                if cumulative_samples[point.minute]
                else None
            ),
            day_sessions_used=len(cumulative_samples[point.minute]),
            avg_volume_15=(
                fmean(samples15[point.minute])
                if samples15.get(point.minute)
                else None
            ),
            rvol15_sessions_used=len(samples15.get(point.minute, ())),
            avg_volume_30=(
                fmean(samples30[point.minute])
                if samples30.get(point.minute)
                else None
            ),
            rvol30_sessions_used=len(samples30.get(point.minute, ())),
        )
        for point in grid
    )


def safe_ratio(
    numerator: float | int | None, denominator: float | None
) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return float(numerator) / denominator


def calculate_symbol(
    symbol: str, as_of: str, snapshot: MarketSnapshot
) -> SymbolCalculation:
    technical = _technical(symbol, as_of, snapshot)
    exchange = _exchange_for(snapshot)
    if exchange is None:
        return SymbolCalculation(
            technical,
            (),
            CurrentState(
                symbol=symbol,
                exchange=None,
                trading_date=as_of,
                minute=None,
                last_price=None,
                cumulative_volume=None,
                day_rvol=None,
                rvol15=None,
                rvol30=None,
                price5_pct=None,
                price15_pct=None,
                ma10=technical.ma10,
                ma200=technical.ma200,
                distance_ma10_pct=None,
                distance_ma200_pct=None,
                baseline_sessions_used=0,
                day_rvol_sessions_used=0,
                rvol15_sessions_used=0,
                rvol30_sessions_used=0,
                quality_status="PARTIAL",
                reason_codes_json=json.dumps(["MISSING_EXCHANGE"]),
            ),
        )

    grid = volume_market_grid(exchange, include_provider_boundaries=True)
    baseline = _baseline(symbol, as_of, exchange, snapshot)
    baseline_map = {point.minute: point for point in baseline}
    today = snapshot.current_minutes
    candidates = [point.minute for point in grid if point.minute in today]
    selected = candidates[-1] if candidates else None
    cumulative: int | None = None
    window15: int | None = None
    window30: int | None = None
    if selected is not None:
        index = next(i for i, point in enumerate(grid) if point.minute == selected)
        cumulative = next(
            (
                int(today[point.minute]["provider_total_volume"])
                for point in reversed(grid[: index + 1])
                if point.minute in today
                and today[point.minute]["provider_total_volume"] is not None
                and int(today[point.minute]["provider_total_volume"]) >= 0
            ),
            None,
        )
        volumes = grid_volumes(
            today, grid, complete=snapshot.current_session_complete
        )
        prefix = volumes[: index + 1]
        if cumulative is None and all(value is not None for value in prefix):
            cumulative = sum(prefix)  # type: ignore[arg-type]
        window15 = rolling_volume(volumes, grid, index, 15)
        window30 = rolling_volume(volumes, grid, index, 30)

    point = baseline_map.get(selected) if selected else None
    closes = {
        minute: close
        for minute, row in today.items()
        if (close := usable_price(row["close"])) is not None
    }
    unresolved_price_gaps: set[str] = set()
    if selected is not None and not snapshot.current_session_complete:
        selected_session = next(
            point.session_segment for point in grid if point.minute == selected
        )
        unresolved_price_gaps = {
            point.minute
            for point in grid
            if point.is_continuous
            and point.session_segment == selected_session
            and point.minute <= selected
            and point.minute not in today
        }
    last_price = (
        price_state_at(
            exchange=exchange,
            trading_date=as_of,
            target_minute=selected,
            closes=closes,
            unresolved_gap_minutes=unresolved_price_gaps,
        )
        if selected is not None
        else None
    )
    price5 = exact_price_change(
        exchange=exchange,
        trading_date=as_of,
        current_minute=selected or "",
        current_price=last_price,
        closes=closes,
        window=5,
        unresolved_gap_minutes=unresolved_price_gaps,
    )
    price15 = exact_price_change(
        exchange=exchange,
        trading_date=as_of,
        current_minute=selected or "",
        current_price=last_price,
        closes=closes,
        window=15,
        unresolved_gap_minutes=unresolved_price_gaps,
    )
    day_rvol = safe_ratio(cumulative, point.avg_cumulative_volume if point else None)
    rvol15 = safe_ratio(window15, point.avg_volume_15 if point else None)
    rvol30 = safe_ratio(window30, point.avg_volume_30 if point else None)
    distance10 = (
        (last_price / technical.ma10 - 1) * 100
        if last_price is not None and technical.ma10
        else None
    )
    distance200 = (
        (last_price / technical.ma200 - 1) * 100
        if last_price is not None and technical.ma200
        else None
    )
    reasons = [
        name
        for name, value in (
            ("MISSING_CURRENT_PRICE", last_price),
            ("INSUFFICIENT_DAY_RVOL", day_rvol),
            ("INSUFFICIENT_RVOL15", rvol15),
            ("INSUFFICIENT_RVOL30", rvol30),
            ("MISSING_PRICE5_ANCHOR", price5),
            ("MISSING_PRICE15_ANCHOR", price15),
            ("INSUFFICIENT_MA10", technical.ma10),
            ("INSUFFICIENT_MA200", technical.ma200),
        )
        if value is None
    ]
    return SymbolCalculation(
        technical,
        baseline,
        CurrentState(
            symbol=symbol,
            exchange=exchange,
            trading_date=as_of,
            minute=selected,
            last_price=last_price,
            cumulative_volume=cumulative,
            day_rvol=day_rvol,
            rvol15=rvol15,
            rvol30=rvol30,
            price5_pct=price5,
            price15_pct=price15,
            ma10=technical.ma10,
            ma200=technical.ma200,
            distance_ma10_pct=distance10,
            distance_ma200_pct=distance200,
            baseline_sessions_used=point.day_sessions_used if point else 0,
            day_rvol_sessions_used=point.day_sessions_used if point else 0,
            rvol15_sessions_used=point.rvol15_sessions_used if point else 0,
            rvol30_sessions_used=point.rvol30_sessions_used if point else 0,
            quality_status="OK" if not reasons else "PARTIAL",
            reason_codes_json=json.dumps(reasons, separators=(",", ":")),
        ),
    )


def _failed_state(symbol: str, as_of: str, exc: Exception) -> CurrentState:
    return CurrentState(
        symbol=symbol,
        exchange=None,
        trading_date=as_of,
        minute=None,
        last_price=None,
        cumulative_volume=None,
        day_rvol=None,
        rvol15=None,
        rvol30=None,
        price5_pct=None,
        price15_pct=None,
        ma10=None,
        ma200=None,
        distance_ma10_pct=None,
        distance_ma200_pct=None,
        baseline_sessions_used=0,
        day_rvol_sessions_used=0,
        rvol15_sessions_used=0,
        rvol30_sessions_used=0,
        quality_status="FAILED",
        reason_codes_json=json.dumps([f"CALCULATION_ERROR:{type(exc).__name__}"]),
        updated_at=utc_now(),
    )


def rebuild_engine(
    *,
    market_db_dir: str | Path,
    engine_db: str | Path,
    as_of_date: date | str,
    calculator: Callable[[str, str, MarketSnapshot], SymbolCalculation] = calculate_symbol,
) -> tuple[int, int]:
    as_of = (
        as_of_date.isoformat()
        if isinstance(as_of_date, date)
        else date.fromisoformat(as_of_date).isoformat()
    )
    failures = 0
    with MarketShardReader(market_db_dir) as reader, CanonicalEngineStore(
        engine_db
    ) as store:
        symbols = reader.symbols()
        store.begin_rebuild(as_of)
        for symbol in symbols:
            snapshot = reader.load_symbol(symbol, as_of)
            try:
                result = calculator(symbol, as_of, snapshot)
                store.write_symbol(
                    technical=result.technical,
                    volume=result.volume,
                    current=result.current,
                )
            except Exception as exc:
                failures += 1
                store.write_symbol(
                    technical=None,
                    volume=(),
                    current=_failed_state(symbol, as_of, exc),
                )
    return len(symbols), failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-db-dir", type=Path, default=Path("data"))
    parser.add_argument("--engine-db", type=Path, default=Path("data/ccc_engine.db"))
    parser.add_argument("--as-of-date", required=True, type=date.fromisoformat)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    symbols, failures = rebuild_engine(
        market_db_dir=args.market_db_dir,
        engine_db=args.engine_db,
        as_of_date=args.as_of_date,
    )
    print(f"engine_rebuild symbols={symbols} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
