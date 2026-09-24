"""Minute-cadence live projector from canonical market data to ccc_engine.db."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .canonical_engine_store import CanonicalEngineStore, CurrentState
from .canonical_market_store import (
    MINUTE_FINALIZATION_GRACE_SECONDS,
    CanonicalMarketStore,
    RealtimeMarketEvent,
    RealtimeWriteResult,
)
from .market_session import VN_TZ, normalize_exchange
from .rebuild_engine import exact_price_change, rolling_volume, safe_ratio, usable_price
from .volume_baseline import VolumeGridPoint, volume_market_grid


LOG = logging.getLogger("ssi_shadow.canonical_engine")


@dataclass(frozen=True, slots=True)
class ProjectorStats:
    active_symbols: int
    dirty_symbols: int
    state_writes: int
    calculation_errors: int
    trading_date: str


class CanonicalLiveMarketReader:
    """Read the active canonical shard without using the collector connection."""

    def __init__(self, market_store: CanonicalMarketStore) -> None:
        self._path_for_year = market_store.path_for_year
        self._connection: sqlite3.Connection | None = None
        self._year: int | None = None
        self._lock = threading.RLock()

    def _for_date(self, trading_date: str) -> sqlite3.Connection | None:
        year = date.fromisoformat(trading_date).year
        with self._lock:
            if self._connection is not None and self._year == year:
                return self._connection
            if self._connection is not None:
                self._connection.close()
                self._connection = None
                self._year = None
            path = self._path_for_year(year)
            if not path.is_file():
                return None
            connection = sqlite3.connect(
                f"file:{path.resolve().as_posix()}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA query_only=ON")
            self._connection = connection
            self._year = year
            return connection

    def live_symbols(self, trading_date: str) -> tuple[str, ...]:
        connection = self._for_date(trading_date)
        if connection is None:
            return ()
        with self._lock:
            return tuple(
                str(row[0])
                for row in connection.execute(
                    """SELECT symbol FROM minute_bars
                       WHERE trading_date=? GROUP BY symbol ORDER BY symbol""",
                    (trading_date,),
                )
            )

    def read_live_day(
        self, symbol: str, trading_date: str
    ) -> tuple[
        tuple[sqlite3.Row, ...], tuple[sqlite3.Row, ...], sqlite3.Row | None
    ]:
        connection = self._for_date(trading_date)
        if connection is None:
            return (), (), None
        canonical_symbol = symbol.strip().upper()
        with self._lock:
            rows = tuple(
                connection.execute(
                    """SELECT symbol,trading_date,minute,exchange,close,volume,
                              provider_total_volume,quality_status,is_finalized
                       FROM minute_bars
                       WHERE symbol=? AND trading_date=? ORDER BY minute""",
                    (canonical_symbol, trading_date),
                )
            )
            gaps = tuple(
                connection.execute(
                    """SELECT symbol,minute_from,minute_to,reason,status
                       FROM data_gaps
                       WHERE trading_date=? AND (symbol IS NULL OR symbol=?)
                         AND UPPER(status) NOT IN ('RESOLVED','FILLED')
                       ORDER BY minute_from""",
                    (trading_date, canonical_symbol),
                )
            )
            latest = connection.execute(
                """SELECT symbol,trading_date,event_time,last_price,total_volume,
                          exchange,provider_session
                   FROM latest_quotes
                   WHERE symbol=? AND trading_date=?""",
                (canonical_symbol, trading_date),
            ).fetchone()
        return rows, gaps, latest

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
                self._year = None


def _local(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=VN_TZ)
    return moment.astimezone(VN_TZ)


def _gap_minute(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if "T" in text:
            return datetime.fromisoformat(text).strftime("%H:%M")
        return datetime.strptime(text[:5], "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


def _target_point(
    exchange: str, observed_at: datetime
) -> tuple[tuple[VolumeGridPoint, ...], int] | None:
    local = _local(observed_at)
    if local.weekday() >= 5:
        return None
    cutoff = local - timedelta(
        minutes=1, seconds=MINUTE_FINALIZATION_GRACE_SECONDS
    )
    if cutoff.date() != local.date():
        return None
    grid = volume_market_grid(exchange, include_provider_boundaries=True)
    eligible = [
        index
        for index, point in enumerate(grid)
        if point.is_continuous and point.minute <= cutoff.strftime("%H:%M")
    ]
    return (grid, eligible[-1]) if eligible else None


class CanonicalLiveEngine:
    """Projects active symbols at most once per eligible minute.

    The stream-thread hook only mutates in-memory sets. All canonical reads,
    calculations, and disposable engine writes happen from ``advance``.
    """

    def __init__(
        self,
        *,
        market_store: CanonicalMarketStore,
        engine_path: str | Path,
        active_at: datetime,
    ) -> None:
        self.engine_store = CanonicalEngineStore(engine_path)
        self.market_reader = CanonicalLiveMarketReader(market_store)
        self._lock = threading.RLock()
        self._trading_date = _local(active_at).date().isoformat()
        self.engine_store.expire_current_state(self._trading_date)
        self._active = set(self.market_reader.live_symbols(self._trading_date))
        self._dirty = {symbol: "" for symbol in self._active}
        self._dirty_generation = {symbol: 0 for symbol in self._active}
        self._exchanges: dict[str, str] = {}
        self._last_projected: dict[str, str] = {}
        self._state_writes = 0
        self._calculation_errors = 0

    def mark_dirty(
        self, event: RealtimeMarketEvent, _result: RealtimeWriteResult
    ) -> None:
        """Lightweight post-commit hook; never reads or writes a database."""
        symbol = event.symbol.strip().upper()
        with self._lock:
            self._active.add(symbol)
            if event.exchange:
                try:
                    self._exchanges[symbol] = normalize_exchange(event.exchange)
                except ValueError:
                    pass
            current = self._dirty.get(symbol)
            self._dirty[symbol] = (
                min(current, event.minute) if current not in (None, "") else event.minute
            )
            self._dirty_generation[symbol] = (
                self._dirty_generation.get(symbol, 0) + 1
            )

    def advance(self, observed_at: datetime) -> int:
        local = _local(observed_at)
        trading_date = local.date().isoformat()
        with self._lock:
            if trading_date != self._trading_date:
                self.engine_store.expire_current_state(trading_date)
                self._trading_date = trading_date
                self._active = set(self.market_reader.live_symbols(trading_date))
                self._dirty = {symbol: "" for symbol in self._active}
                self._dirty_generation = {symbol: 0 for symbol in self._active}
                self._exchanges.clear()
                self._last_projected.clear()
            symbols = tuple(sorted(self._active))

        written = 0
        for symbol in symbols:
            try:
                exchange = self._exchange_for_symbol(symbol, trading_date)
                target = _target_point(exchange, local) if exchange else None
                if target is None:
                    continue
                target_minute = target[0][target[1]].minute
                with self._lock:
                    dirty_minute = self._dirty.get(symbol)
                    projection_generation = self._dirty_generation.get(symbol, 0)
                    dirty_is_eligible = (
                        dirty_minute is not None
                        and (dirty_minute == "" or dirty_minute <= target_minute)
                    )
                    already_projected = (
                        self._last_projected.get(symbol) == target_minute
                    )
                if already_projected and not dirty_is_eligible:
                    continue
                state = self._calculate(symbol, trading_date, local)
                if state is None:
                    continue
                self.engine_store.upsert_current(state)
            except Exception:
                with self._lock:
                    self._calculation_errors += 1
                LOG.exception(
                    "Canonical live-engine projection failed; will retry: symbol=%s",
                    symbol,
                )
                continue
            with self._lock:
                self._last_projected[symbol] = str(state.minute)
                dirty_minute = self._dirty.get(symbol)
                generation_unchanged = (
                    self._dirty_generation.get(symbol, 0)
                    == projection_generation
                )
                if generation_unchanged and dirty_minute is not None and (
                    dirty_minute == "" or dirty_minute <= str(state.minute)
                ):
                    self._dirty.pop(symbol, None)
                self._state_writes += 1
            written += 1
        return written

    def _exchange_for_symbol(
        self, symbol: str, trading_date: str
    ) -> str | None:
        with self._lock:
            cached = self._exchanges.get(symbol)
        if cached is not None:
            return cached
        rows, _, _ = self.market_reader.read_live_day(symbol, trading_date)
        for row in reversed(rows):
            if not row["exchange"]:
                continue
            try:
                exchange = normalize_exchange(str(row["exchange"]))
            except ValueError:
                continue
            with self._lock:
                self._exchanges[symbol] = exchange
            return exchange
        return None

    def _calculate(
        self, symbol: str, trading_date: str, observed_at: datetime
    ) -> CurrentState | None:
        rows, gaps, latest_quote = self.market_reader.read_live_day(
            symbol, trading_date
        )
        exchange: str | None = None
        for row in reversed(rows):
            if row["exchange"]:
                try:
                    exchange = normalize_exchange(str(row["exchange"]))
                except ValueError:
                    continue
                break
        if exchange is None:
            return None

        target = _target_point(exchange, observed_at)
        if target is None:
            return None
        grid, target_index = target
        target_minute = grid[target_index].minute
        elapsed_rows = [row for row in rows if str(row["minute"]) <= target_minute]
        if not elapsed_rows or not bool(elapsed_rows[-1]["is_finalized"]):
            return None

        row_by_minute = {str(row["minute"]): row for row in elapsed_rows}
        closes = {
            minute: close
            for minute, row in row_by_minute.items()
            if (close := usable_price(row["close"])) is not None
        }
        minute_price = next(
            (
                price
                for row in reversed(elapsed_rows)
                if (price := usable_price(row["close"])) is not None
            ),
            None,
        )
        latest_quote_price = (
            usable_price(latest_quote["last_price"])
            if latest_quote is not None
            and latest_quote["event_time"] is not None
            and str(latest_quote["event_time"])[:5] <= target_minute
            else None
        )
        latest_price = (
            latest_quote_price
            if latest_quote_price is not None
            else minute_price
        )
        cumulative_evidence = next(
            (
                (str(row["minute"]), int(row["provider_total_volume"]))
                for row in reversed(elapsed_rows)
                if row["provider_total_volume"] is not None
                and int(row["provider_total_volume"]) >= 0
            ),
            None,
        )
        cumulative = cumulative_evidence[1] if cumulative_evidence else None

        gap_minutes: set[str] = set()
        for gap in gaps:
            start = _gap_minute(gap["minute_from"])
            end = _gap_minute(gap["minute_to"]) or start
            if start is None:
                continue
            gap_minutes.update(
                point.minute
                for point in grid
                if start <= point.minute <= end
            )

        cumulative_gap_uncertain = any(
            minute <= target_minute
            and (
                cumulative_evidence is None or cumulative_evidence[0] < minute
            )
            for minute in gap_minutes
        )
        if cumulative_gap_uncertain:
            cumulative = None

        volumes: list[int | None] = []
        for index, point in enumerate(grid):
            if index > target_index:
                volumes.append(None)
                continue
            row = row_by_minute.get(point.minute)
            if point.minute in gap_minutes:
                volumes.append(None)
            elif row is None:
                volumes.append(0)
            elif row["volume"] is None or int(row["volume"]) < 0:
                volumes.append(None)
            else:
                volumes.append(int(row["volume"]))

        if cumulative is None:
            prefix = volumes[: target_index + 1]
            cumulative = (
                sum(prefix)  # type: ignore[arg-type]
                if all(value is not None for value in prefix)
                else None
            )

        window15 = rolling_volume(volumes, grid, target_index, 15)
        window30 = rolling_volume(volumes, grid, target_index, 30)
        technical = self.engine_store.load_technical(symbol, trading_date)
        baseline = self.engine_store.load_volume_point(
            symbol, target_minute, trading_date
        )
        ma10 = usable_price(technical["ma10"]) if technical is not None else None
        ma200 = usable_price(technical["ma200"]) if technical is not None else None
        day_rvol = safe_ratio(
            cumulative,
            baseline["avg_cumulative_volume"] if baseline is not None else None,
        )
        rvol15 = safe_ratio(
            window15, baseline["avg_volume_15"] if baseline is not None else None
        )
        rvol30 = safe_ratio(
            window30, baseline["avg_volume_30"] if baseline is not None else None
        )
        price5 = exact_price_change(
            exchange=exchange,
            trading_date=trading_date,
            current_minute=target_minute,
            current_price=latest_price,
            closes=closes,
            window=5,
        )
        price15 = exact_price_change(
            exchange=exchange,
            trading_date=trading_date,
            current_minute=target_minute,
            current_price=latest_price,
            closes=closes,
            window=15,
        )
        distance10 = (
            (latest_price / ma10 - 1.0) * 100.0
            if latest_price is not None and ma10 is not None
            else None
        )
        distance200 = (
            (latest_price / ma200 - 1.0) * 100.0
            if latest_price is not None and ma200 is not None
            else None
        )
        reasons = [
            name
            for name, value in (
                ("MISSING_CURRENT_PRICE", latest_price),
                ("INSUFFICIENT_DAY_RVOL", day_rvol),
                ("INSUFFICIENT_RVOL15", rvol15),
                ("INSUFFICIENT_RVOL30", rvol30),
                ("MISSING_PRICE5_ANCHOR", price5),
                ("MISSING_PRICE15_ANCHOR", price15),
                ("INSUFFICIENT_MA10", ma10),
                ("INSUFFICIENT_MA200", ma200),
            )
            if value is None
        ]
        relevant_segment = grid[target_index].session_segment
        relevant_gap = any(
            point.minute in gap_minutes
            for point in grid[max(0, target_index - 29) : target_index + 1]
            if point.session_segment == relevant_segment
        )
        if relevant_gap or cumulative_gap_uncertain:
            reasons.append("CURRENT_GAP")
        if technical is None and baseline is None:
            reasons.append("NO_BASELINE")

        day_sessions = int(baseline["day_sessions_used"] or 0) if baseline else 0
        sessions15 = (
            int(baseline["rvol15_sessions_used"] or 0) if baseline else 0
        )
        sessions30 = (
            int(baseline["rvol30_sessions_used"] or 0) if baseline else 0
        )
        return CurrentState(
            symbol=symbol,
            exchange=exchange,
            trading_date=trading_date,
            minute=target_minute,
            last_price=latest_price,
            cumulative_volume=cumulative,
            day_rvol=day_rvol,
            rvol15=rvol15,
            rvol30=rvol30,
            price5_pct=price5,
            price15_pct=price15,
            ma10=ma10,
            ma200=ma200,
            distance_ma10_pct=distance10,
            distance_ma200_pct=distance200,
            baseline_sessions_used=day_sessions,
            day_rvol_sessions_used=day_sessions,
            rvol15_sessions_used=sessions15,
            rvol30_sessions_used=sessions30,
            quality_status="OK" if not reasons else "PARTIAL",
            reason_codes_json=json.dumps(reasons, separators=(",", ":")),
        )

    def stats(self) -> ProjectorStats:
        with self._lock:
            return ProjectorStats(
                active_symbols=len(self._active),
                dirty_symbols=len(self._dirty),
                state_writes=self._state_writes,
                calculation_errors=self._calculation_errors,
                trading_date=self._trading_date,
            )

    def close(self) -> None:
        try:
            self.market_reader.close()
        finally:
            self.engine_store.close()
