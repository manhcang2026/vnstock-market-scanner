from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from threading import RLock
from types import MappingProxyType
from typing import Mapping

from .market_session import VN_TZ, SessionType, classify_market_session, normalize_exchange
from .volume_baseline import (
    MAX_BREAK_BLOCKS,
    MINIMUM_BASELINE_SESSIONS,
    VolumeGridPoint,
    volume_market_grid,
)


class BaselineValidationError(ValueError):
    """Raised when a derived volume baseline cannot be trusted."""


@dataclass(frozen=True, slots=True)
class BaselineCoverage:
    symbol: str
    exchange: str | None
    available_sessions: int
    baseline_sessions_used: int
    active_sessions_available: int
    active_sessions_used: int
    first_history_date: str | None
    last_history_date: str | None
    break_blocks: int = 0
    coverage_tier: str = "INSUFFICIENT"
    stopped_reason: str | None = None

    @property
    def usable(self) -> bool:
        return (
            self.baseline_sessions_used >= MINIMUM_BASELINE_SESSIONS
            and self.break_blocks <= MAX_BREAK_BLOCKS
        )


@dataclass(frozen=True, slots=True)
class BaselinePoint:
    symbol: str
    exchange: str
    minute: str
    session_segment: str
    historical_sessions: int
    avg_cumulative_volume: float
    avg_volume_15: float | None
    avg_volume_30: float | None
    avg_opening_volume: float | None


@dataclass(frozen=True, slots=True)
class VolumeBaselineSnapshot:
    source_path: Path
    schema_version: int
    lookback: int
    coverage_proof: str | None
    as_of_date: str | None
    coverage: Mapping[str, BaselineCoverage]
    points: Mapping[tuple[str, str], BaselinePoint]


@dataclass(frozen=True, slots=True)
class VolumeEvent:
    """Canonical volume event produced after SSI collector normalization."""

    symbol: str
    exchange: str
    trading_date: str
    event_time: datetime
    minute: str
    volume_delta: int
    total_volume: int | None
    quality_status: str
    is_partial: bool = False
    has_gap: bool = False
    provider_session: str = ""
    provider_total_volume: int | None = None
    data_source: str = "SSI_STREAM"

    def __post_init__(self) -> None:
        symbol = str(self.symbol or "").strip().upper()
        if not symbol:
            raise ValueError("VolumeEvent symbol is required")
        object.__setattr__(self, "symbol", symbol)

        exchange_text = str(self.exchange or "").strip().upper()
        canonical_exchange = normalize_exchange(exchange_text)
        if exchange_text != canonical_exchange:
            raise ValueError(
                f"VolumeEvent exchange must be canonical: {self.exchange!r}"
            )
        object.__setattr__(self, "exchange", canonical_exchange)

        trading_date = _valid_iso_date(self.trading_date, "VolumeEvent trading_date")
        object.__setattr__(self, "trading_date", trading_date)
        minute = _valid_minute(self.minute, "VolumeEvent minute")
        object.__setattr__(self, "minute", minute)

        if not isinstance(self.event_time, datetime):
            raise ValueError("VolumeEvent event_time must be a datetime")
        local_event_time = _as_local(self.event_time)
        if local_event_time.date().isoformat() != trading_date:
            raise ValueError("VolumeEvent event_time date does not match trading_date")
        if local_event_time.strftime("%H:%M") != minute:
            raise ValueError("VolumeEvent event_time does not match minute")
        object.__setattr__(self, "event_time", local_event_time)

        if isinstance(self.volume_delta, bool) or not isinstance(self.volume_delta, int):
            raise ValueError("VolumeEvent volume_delta must be an integer")
        if self.volume_delta < 0:
            raise ValueError("VolumeEvent volume_delta must not be negative")
        if self.total_volume is not None:
            if isinstance(self.total_volume, bool) or not isinstance(
                self.total_volume, int
            ):
                raise ValueError("VolumeEvent total_volume must be an integer or None")
            if self.total_volume < 0:
                raise ValueError("VolumeEvent total_volume must not be negative")
        if self.provider_total_volume is not None:
            if isinstance(self.provider_total_volume, bool) or not isinstance(
                self.provider_total_volume, int
            ):
                raise ValueError(
                    "VolumeEvent provider_total_volume must be an integer or None"
                )
            if self.provider_total_volume < 0:
                raise ValueError(
                    "VolumeEvent provider_total_volume must not be negative"
                )

        quality_status = str(self.quality_status or "").strip().upper()
        if not quality_status:
            raise ValueError("VolumeEvent quality_status is required")
        object.__setattr__(self, "quality_status", quality_status)
        object.__setattr__(
            self,
            "provider_session",
            str(self.provider_session or "").strip().upper(),
        )
        object.__setattr__(
            self, "data_source", str(self.data_source or "").strip().upper()
        )


@dataclass(frozen=True, slots=True)
class VolumeSnapshot:
    symbol: str
    exchange: str
    trading_date: str
    as_of_minute: str | None
    cumulative_volume: int
    avg_cumulative_volume: float | None
    day_rvol: float | None
    volume_15: int | None
    avg_volume_15: float | None
    rvol_15: float | None
    volume_30: int | None
    avg_volume_30: float | None
    rvol_30: float | None
    opening_volume: int | None
    avg_opening_volume: float | None
    opening_rvol: float | None
    historical_sessions: int
    available_sessions: int
    baseline_sessions_used: int
    active_sessions_available: int
    active_sessions_used: int
    first_history_date: str | None
    last_history_date: str | None
    quality_status: str
    metrics_trusted: bool
    metric_availability: Mapping[str, bool]
    reasons: tuple[str, ...]
    baseline_break_blocks: int = 0


@dataclass(slots=True)
class _DayState:
    symbol: str
    exchange: str
    trading_date: str
    minute_buckets: dict[str, int] = field(default_factory=dict)
    bucket_reasons: dict[str, set[str]] = field(default_factory=dict)
    cumulative_volume: int = 0
    opening_volume: int | None = None
    segment_name: str | None = None
    segment_volumes: list[int] = field(default_factory=list)
    last_finalized_index: int = -1
    latest_total_volume: int | None = None
    latest_quality_status: str = "TRUSTED"
    latest_event_time: datetime | None = None
    latest_is_partial: bool = False
    latest_has_gap: bool = False
    integrity_reasons: set[str] = field(default_factory=set)
    finalized_quality_reasons: set[str] = field(default_factory=set)
    snapshot: VolumeSnapshot | None = None


_REQUIRED_COLUMNS = {
    "volume_baseline_metadata": {"key", "value"},
    "volume_baseline_coverage": {
        "symbol",
        "exchange",
        "available_sessions",
        "baseline_sessions_used",
        "active_sessions_available",
        "active_sessions_used",
        "first_history_date",
        "last_history_date",
    },
    "volume_baseline": {
        "symbol",
        "exchange",
        "minute",
        "session_segment",
        "historical_sessions",
        "avg_cumulative_volume",
        "avg_volume_15",
        "avg_volume_30",
        "avg_opening_volume",
    },
}


def _as_local(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=VN_TZ)
    return moment.astimezone(VN_TZ)


def _valid_iso_date(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}") from exc
    if parsed.isoformat() != text:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}")
    return text


def _valid_minute(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError as exc:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}") from exc
    if parsed.strftime("%H:%M") != text:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}")
    return text


def _canonical_baseline_exchange(value: object, field_name: str) -> str:
    text = str(value or "").strip().upper()
    try:
        canonical = normalize_exchange(text)
    except ValueError as exc:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}") from exc
    if text != canonical:
        raise BaselineValidationError(f"Non-canonical {field_name}: {value!r}")
    return canonical


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}") from exc
    if parsed < 0 or str(parsed) != str(value).strip():
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}")
    return parsed


def _finite_nonnegative_float(
    value: object, field_name: str, *, optional: bool = False
) -> float | None:
    if value is None and optional:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise BaselineValidationError(f"Malformed {field_name}: {value!r}")
    return parsed


def _validate_columns(connection: sqlite3.Connection) -> None:
    for table, required in _REQUIRED_COLUMNS.items():
        columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        missing = required - columns
        if missing:
            raise BaselineValidationError(
                f"Baseline table {table} is missing columns: {sorted(missing)}"
            )


def _load_metadata(
    connection: sqlite3.Connection,
) -> tuple[int, int, str | None, str | None]:
    metadata: dict[str, str] = {}
    for row in connection.execute("SELECT key, value FROM volume_baseline_metadata"):
        key = str(row["key"])
        if key in metadata:
            raise BaselineValidationError(f"Duplicate baseline metadata key: {key}")
        metadata[key] = str(row["value"])
    try:
        schema_version = int(metadata["schema_version"])
        lookback = int(metadata["lookback"])
    except (KeyError, ValueError) as exc:
        raise BaselineValidationError("Missing or malformed baseline metadata") from exc
    if schema_version != 2:
        raise BaselineValidationError(
            f"Unsupported baseline schema_version={schema_version}; expected 2"
        )
    if lookback < 1:
        raise BaselineValidationError("Baseline lookback must be positive")
    coverage_proof = metadata.get("coverage_proof")
    as_of_date = metadata.get("as_of_date")
    if as_of_date is not None:
        as_of_date = _valid_iso_date(as_of_date, "baseline as_of_date")
    return schema_version, lookback, coverage_proof, as_of_date


def _load_coverage(
    connection: sqlite3.Connection,
) -> dict[str, BaselineCoverage]:
    coverage: dict[str, BaselineCoverage] = {}
    rows = connection.execute(
        """
        SELECT symbol, exchange, available_sessions, baseline_sessions_used,
               active_sessions_available, active_sessions_used,
               first_history_date, last_history_date, break_blocks,
               coverage_tier, stopped_reason
        FROM volume_baseline_coverage
        """
    )
    for row in rows:
        symbol = str(row["symbol"] or "").strip().upper()
        if not symbol:
            raise BaselineValidationError("Baseline coverage contains an empty symbol")
        if symbol in coverage:
            raise BaselineValidationError(f"Duplicate baseline coverage symbol: {symbol}")
        available = _nonnegative_int(
            row["available_sessions"], f"available_sessions for {symbol}"
        )
        used = _nonnegative_int(
            row["baseline_sessions_used"], f"baseline_sessions_used for {symbol}"
        )
        active_available = _nonnegative_int(
            row["active_sessions_available"],
            f"active_sessions_available for {symbol}",
        )
        active_used = _nonnegative_int(
            row["active_sessions_used"], f"active_sessions_used for {symbol}"
        )
        break_blocks = _nonnegative_int(
            row["break_blocks"], f"break_blocks for {symbol}"
        )
        if (
            used > available
            or active_available > available
            or active_used > used
            or active_used > active_available
        ):
            raise BaselineValidationError(f"Inconsistent coverage counts for {symbol}")
        raw_exchange = row["exchange"]
        exchange = (
            _canonical_baseline_exchange(raw_exchange, f"exchange for {symbol}")
            if raw_exchange is not None and str(raw_exchange).strip()
            else None
        )
        if used > 0 and exchange is None:
            raise BaselineValidationError(
                f"Baseline coverage for {symbol} has sessions but no exchange"
            )
        first_history_date = (
            _valid_iso_date(row["first_history_date"], f"first_history_date for {symbol}")
            if row["first_history_date"] is not None
            else None
        )
        last_history_date = (
            _valid_iso_date(row["last_history_date"], f"last_history_date for {symbol}")
            if row["last_history_date"] is not None
            else None
        )
        if (first_history_date is None) != (last_history_date is None):
            raise BaselineValidationError(f"Incomplete history dates for {symbol}")
        if used > 0 and first_history_date is None:
            raise BaselineValidationError(f"Missing history dates for {symbol}")
        if used == 0 and first_history_date is not None:
            raise BaselineValidationError(
                f"No-proven-session symbol {symbol} unexpectedly has history dates"
            )
        if first_history_date and first_history_date > last_history_date:
            raise BaselineValidationError(f"Reversed history dates for {symbol}")
        coverage[symbol] = BaselineCoverage(
            symbol=symbol,
            exchange=exchange,
            available_sessions=available,
            baseline_sessions_used=used,
            active_sessions_available=active_available,
            active_sessions_used=active_used,
            first_history_date=first_history_date,
            last_history_date=last_history_date,
            break_blocks=break_blocks,
            coverage_tier=str(row["coverage_tier"] or "INSUFFICIENT"),
            stopped_reason=(
                str(row["stopped_reason"])
                if row["stopped_reason"] is not None
                else None
            ),
        )
    return coverage


def _load_points(
    connection: sqlite3.Connection,
    coverage: Mapping[str, BaselineCoverage],
) -> dict[tuple[str, str], BaselinePoint]:
    points: dict[tuple[str, str], BaselinePoint] = {}
    grid_by_exchange = {
        exchange: {point.minute: point for point in volume_market_grid(exchange)}
        for exchange in ("HOSE", "HNX", "UPCOM")
    }
    keys_by_symbol: dict[str, set[tuple[str, str]]] = {}
    rows = connection.execute(
        """
        SELECT symbol, exchange, minute, session_segment, historical_sessions,
               avg_cumulative_volume, avg_volume_15, avg_volume_30,
               avg_opening_volume
        FROM volume_baseline
        """
    )
    for row in rows:
        symbol = str(row["symbol"] or "").strip().upper()
        symbol_coverage = coverage.get(symbol)
        if symbol_coverage is None:
            raise BaselineValidationError(
                f"Baseline point references missing coverage symbol: {symbol}"
            )
        exchange = _canonical_baseline_exchange(
            row["exchange"], f"exchange for {symbol}"
        )
        if symbol_coverage.exchange != exchange:
            raise BaselineValidationError(f"Conflicting baseline exchange for {symbol}")
        minute = _valid_minute(row["minute"], f"minute for {symbol}")
        key = (symbol, minute)
        if key in points:
            raise BaselineValidationError(
                f"Duplicate volume baseline key: {symbol}/{minute}"
            )
        grid_point = grid_by_exchange[exchange].get(minute)
        if grid_point is None:
            raise BaselineValidationError(
                f"Baseline minute is outside the {exchange} grid: {symbol}/{minute}"
            )
        session_segment = str(row["session_segment"] or "").strip()
        if session_segment != grid_point.session_segment:
            raise BaselineValidationError(
                f"Baseline session segment mismatch for {symbol}/{minute}"
            )
        historical_sessions = _nonnegative_int(
            row["historical_sessions"], f"historical_sessions for {symbol}/{minute}"
        )
        if historical_sessions < 1 or historical_sessions != symbol_coverage.baseline_sessions_used:
            raise BaselineValidationError(
                f"Baseline point has inconsistent historical sessions: {symbol}/{minute}"
            )
        points[key] = BaselinePoint(
            symbol=symbol,
            exchange=exchange,
            minute=minute,
            session_segment=session_segment,
            historical_sessions=historical_sessions,
            avg_cumulative_volume=_finite_nonnegative_float(
                row["avg_cumulative_volume"],
                f"avg_cumulative_volume for {symbol}/{minute}",
            ),
            avg_volume_15=_finite_nonnegative_float(
                row["avg_volume_15"],
                f"avg_volume_15 for {symbol}/{minute}",
                optional=True,
            ),
            avg_volume_30=_finite_nonnegative_float(
                row["avg_volume_30"],
                f"avg_volume_30 for {symbol}/{minute}",
                optional=True,
            ),
            avg_opening_volume=_finite_nonnegative_float(
                row["avg_opening_volume"],
                f"avg_opening_volume for {symbol}/{minute}",
                optional=True,
            ),
        )
        keys_by_symbol.setdefault(symbol, set()).add(key)

    for symbol, item in coverage.items():
        symbol_keys = keys_by_symbol.get(symbol, set())
        if not item.usable:
            if symbol_keys:
                raise BaselineValidationError(
                    f"Insufficient-baseline coverage symbol {symbol} "
                    "unexpectedly has points"
                )
            continue
        assert item.exchange is not None
        expected_keys = {
            (symbol, point.minute) for point in volume_market_grid(item.exchange)
        }
        if symbol_keys != expected_keys:
            missing = len(expected_keys - symbol_keys)
            extra = len(symbol_keys - expected_keys)
            raise BaselineValidationError(
                f"Incomplete baseline grid for {symbol}: missing={missing}, extra={extra}"
            )
    return points


def load_volume_baseline(path: Path) -> VolumeBaselineSnapshot:
    """Load and fully validate a derived baseline DB through a read-only handle."""
    source_path = Path(path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Baseline database does not exist: {source_path}")
    connection = sqlite3.connect(
        f"{source_path.resolve().as_uri()}?mode=ro", uri=True
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        _validate_columns(connection)
        schema_version, lookback, coverage_proof, as_of_date = _load_metadata(
            connection
        )
        coverage = _load_coverage(connection)
        points = _load_points(connection, coverage)
    except sqlite3.DatabaseError as exc:
        raise BaselineValidationError(f"Cannot read baseline database: {exc}") from exc
    finally:
        connection.close()
    return VolumeBaselineSnapshot(
        source_path=source_path.resolve(),
        schema_version=schema_version,
        lookback=lookback,
        coverage_proof=coverage_proof,
        as_of_date=as_of_date,
        coverage=MappingProxyType(coverage),
        points=MappingProxyType(points),
    )


class RealtimeVolumeEngine:
    """In-memory completed-minute volume metrics over one immutable baseline."""

    def __init__(self, baseline_path: Path) -> None:
        self._lock = RLock()
        self._baseline = load_volume_baseline(baseline_path)
        self._states: dict[str, _DayState] = {}
        self._grids = {
            exchange: volume_market_grid(exchange)
            for exchange in ("HOSE", "HNX", "UPCOM")
        }
        self._grid_by_minute = {
            exchange: {point.minute: point for point in grid}
            for exchange, grid in self._grids.items()
        }
        self._grid_index_by_minute = {
            exchange: {point.minute: index for index, point in enumerate(grid)}
            for exchange, grid in self._grids.items()
        }
        self._closing_completion_minute = self._load_closing_completion_minutes()

    @property
    def baseline(self) -> VolumeBaselineSnapshot:
        with self._lock:
            return self._baseline

    def reload_baseline(self, path: Path) -> VolumeBaselineSnapshot:
        replacement = load_volume_baseline(path)
        with self._lock:
            for state in self._states.values():
                replacement_coverage = replacement.coverage.get(state.symbol)
                if (
                    replacement_coverage is not None
                    and replacement_coverage.exchange is not None
                    and replacement_coverage.exchange != state.exchange
                ):
                    raise BaselineValidationError(
                        f"Reload changes exchange for active symbol {state.symbol}: "
                        f"{state.exchange} -> {replacement_coverage.exchange}"
                    )
            previous = self._baseline
            previous_snapshots = {
                symbol: state.snapshot for symbol, state in self._states.items()
            }
            try:
                self._baseline = replacement
                for state in self._states.values():
                    if state.last_finalized_index >= 0:
                        point = self._grids[state.exchange][
                            state.last_finalized_index
                        ]
                        state.snapshot = self._build_snapshot(state, point)
                    else:
                        state.snapshot = self._empty_snapshot(state)
            except Exception:
                self._baseline = previous
                for symbol, snapshot in previous_snapshots.items():
                    self._states[symbol].snapshot = snapshot
                raise
            return replacement

    def on_event(self, event: VolumeEvent) -> VolumeSnapshot:
        with self._lock:
            event_coverage = self._baseline.coverage.get(event.symbol)
            if (
                event_coverage is not None
                and event_coverage.exchange is not None
                and event_coverage.exchange != event.exchange
            ):
                raise ValueError(
                    f"Event exchange conflicts with baseline for {event.symbol}: "
                    f"{event.exchange} != {event_coverage.exchange}"
                )
            state = self._states.get(event.symbol)
            if state is None or event.trading_date > state.trading_date:
                state = _DayState(event.symbol, event.exchange, event.trading_date)
                self._states[event.symbol] = state
            elif event.trading_date < state.trading_date:
                raise ValueError(
                    f"Out-of-order trading date for {event.symbol}: {event.trading_date}"
                )
            elif state.exchange != event.exchange:
                raise ValueError(
                    f"Exchange changed intraday for {event.symbol}: "
                    f"{state.exchange} -> {event.exchange}"
                )

            if state.latest_event_time and event.event_time < state.latest_event_time:
                raise ValueError(f"Out-of-order event_time for {event.symbol}")

            bucket = self._event_bucket(event)
            if bucket is not None:
                bucket_index = self._grid_index(event.exchange, bucket)
                if bucket_index <= state.last_finalized_index:
                    raise ValueError(
                        f"Event targets an already completed minute: "
                        f"{event.symbol}/{bucket}"
                    )

            event_integrity_reasons = self._event_integrity_reasons(event)
            state.latest_total_volume = event.total_volume
            state.latest_quality_status = event.quality_status
            state.latest_event_time = event.event_time
            state.latest_is_partial = event.is_partial
            state.latest_has_gap = event.has_gap
            self._finalize_before(state, event.minute)
            if bucket is not None:
                state.minute_buckets[bucket] = (
                    state.minute_buckets.get(bucket, 0) + event.volume_delta
                )
                reasons = state.bucket_reasons.setdefault(bucket, set())
                reasons.update(event_integrity_reasons)
                # Quality is sticky only for the active canonical minute.  On
                # finalization it moves to finalized_quality_reasons; a later
                # clean minute cannot erase accepted corrupt evidence.
                state.integrity_reasons = set(reasons)
            else:
                state.integrity_reasons = set(event_integrity_reasons)

            state.snapshot = self._refresh_latest_quality(state)
            return state.snapshot

    def advance_time(self, now: datetime) -> dict[str, VolumeSnapshot]:
        local_now = _as_local(now)
        changed: dict[str, VolumeSnapshot] = {}
        with self._lock:
            for symbol, state in self._states.items():
                before = state.last_finalized_index
                if state.trading_date < local_now.date().isoformat():
                    self._finalize_to(state, len(self._grids[state.exchange]) - 1)
                elif state.trading_date == local_now.date().isoformat():
                    self._finalize_before(state, local_now.strftime("%H:%M"))
                if state.last_finalized_index != before and state.snapshot is not None:
                    changed[symbol] = state.snapshot
        return changed

    def get_snapshot(self, symbol: str) -> VolumeSnapshot | None:
        with self._lock:
            state = self._states.get(str(symbol or "").strip().upper())
            return state.snapshot if state else None

    def get_all_snapshots(self) -> dict[str, VolumeSnapshot]:
        with self._lock:
            return {
                symbol: state.snapshot
                for symbol, state in self._states.items()
                if state.snapshot is not None
            }

    def _grid_index(self, exchange: str, minute: str) -> int:
        try:
            return self._grid_index_by_minute[exchange][minute]
        except KeyError as exc:
            raise ValueError(
                f"Minute is outside the {exchange} volume grid: {minute}"
            ) from exc

    def _event_bucket(self, event: VolumeEvent) -> str | None:
        grid = self._grids[event.exchange]
        exact = self._grid_by_minute[event.exchange].get(event.minute)
        session = classify_market_session(event.exchange, event.event_time)
        if session.session_type is SessionType.OPEN_AUCTION:
            return next((point.minute for point in grid if point.is_opening), None)
        if session.session_type is SessionType.CLOSE_AUCTION:
            return next((point.minute for point in grid if point.is_closing), None)
        if session.is_continuous and exact is not None:
            return exact.minute
        if (
            session.session_type is SessionType.POST_TRADING
            and event.exchange in self._closing_completion_minute
        ):
            return next(point.minute for point in grid if point.is_closing)
        return None

    @staticmethod
    def _event_integrity_reasons(event: VolumeEvent) -> set[str]:
        reasons: set[str] = set()
        if event.has_gap:
            reasons.add("CURRENT_GAP")
        if event.is_partial:
            reasons.add("CURRENT_PARTIAL")
        if event.quality_status != "TRUSTED":
            reasons.add("NON_TRUSTED_QUALITY")
        return reasons

    def _load_closing_completion_minutes(self) -> dict[str, str]:
        completion_minutes: dict[str, str] = {}
        reference_date = date(2026, 9, 14)
        for exchange, grid in self._grids.items():
            close_point = next((point for point in grid if point.is_closing), None)
            if close_point is None:
                continue
            hour, minute = (int(value) for value in close_point.minute.split(":"))
            close_label_time = datetime(
                reference_date.year,
                reference_date.month,
                reference_date.day,
                hour,
                minute,
                tzinfo=VN_TZ,
            )
            session = classify_market_session(exchange, close_label_time)
            if (
                session.session_type is not SessionType.POST_TRADING
                or session.session_end is None
            ):
                raise ValueError(
                    f"Missing post-trading completion boundary for {exchange}"
                )
            completion_minutes[exchange] = session.session_end.strftime("%H:%M")
        return completion_minutes

    def _finalize_before(self, state: _DayState, minute: str) -> None:
        grid = self._grids[state.exchange]
        target = state.last_finalized_index
        for index in range(state.last_finalized_index + 1, len(grid)):
            point = grid[index]
            completion_minute = self._closing_completion_minute.get(state.exchange)
            if point.is_closing and completion_minute is not None:
                if minute < completion_minute:
                    break
            elif point.minute >= minute:
                break
            target = index
        self._finalize_to(state, target)

    def _finalize_to(self, state: _DayState, target_index: int) -> None:
        grid = self._grids[state.exchange]
        for index in range(state.last_finalized_index + 1, target_index + 1):
            point = grid[index]
            volume = state.minute_buckets.get(point.minute, 0)
            state.cumulative_volume += volume
            if point.is_continuous:
                if state.segment_name != point.session_segment:
                    state.segment_name = point.session_segment
                    state.segment_volumes = []
                state.segment_volumes.append(volume)
            if point.is_opening:
                state.opening_volume = volume
            state.finalized_quality_reasons.update(
                state.bucket_reasons.get(point.minute, set())
            )
            state.last_finalized_index = index
            state.snapshot = self._build_snapshot(state, point)

    def _coverage(self, symbol: str) -> BaselineCoverage:
        item = self._baseline.coverage.get(symbol)
        if item is not None:
            return item
        return BaselineCoverage(symbol, None, 0, 0, 0, 0, None, None)

    def _build_snapshot(
        self, state: _DayState, point: VolumeGridPoint
    ) -> VolumeSnapshot:
        coverage = self._coverage(state.symbol)
        baseline = self._baseline.points.get((state.symbol, point.minute))
        reasons = set(state.finalized_quality_reasons | state.integrity_reasons)
        if coverage.baseline_sessions_used == 0:
            reasons.add("NO_BASELINE")
        elif not coverage.usable:
            reasons.add("INSUFFICIENT_HISTORY")
        elif baseline is None:
            reasons.add("NO_BASELINE")

        avg_cumulative = baseline.avg_cumulative_volume if baseline else None
        day_rvol = _ratio(state.cumulative_volume, avg_cumulative)
        if baseline is not None and (avg_cumulative is None or avg_cumulative <= 0):
            reasons.add("ZERO_DAY_DENOMINATOR")

        volume_15 = (
            sum(state.segment_volumes[-15:]) if point.rolling_15_ready else None
        )
        avg_volume_15 = baseline.avg_volume_15 if baseline else None
        rvol_15 = _ratio(volume_15, avg_volume_15)
        if not point.rolling_15_ready:
            reasons.add("OUTSIDE_ROLLING_WINDOW")
        elif baseline is not None and (
            avg_volume_15 is None or avg_volume_15 <= 0
        ):
            reasons.add("ZERO_RVOL15_DENOMINATOR")

        volume_30 = (
            sum(state.segment_volumes[-30:]) if point.rolling_30_ready else None
        )
        avg_volume_30 = baseline.avg_volume_30 if baseline else None
        rvol_30 = _ratio(volume_30, avg_volume_30)
        if point.rolling_30_ready and baseline is not None and (
            avg_volume_30 is None or avg_volume_30 <= 0
        ):
            reasons.add("ZERO_RVOL30_DENOMINATOR")

        opening_baseline = self._baseline.points.get((state.symbol, "09:15"))
        avg_opening = (
            opening_baseline.avg_opening_volume if opening_baseline else None
        )
        opening_rvol = _ratio(state.opening_volume, avg_opening)

        availability = MappingProxyType(
            {
                "day_rvol": day_rvol is not None,
                "rvol_15": rvol_15 is not None,
                "rvol_30": rvol_30 is not None,
                "opening_rvol": opening_rvol is not None,
            }
        )
        return VolumeSnapshot(
            symbol=state.symbol,
            exchange=state.exchange,
            trading_date=state.trading_date,
            as_of_minute=point.minute,
            cumulative_volume=state.cumulative_volume,
            avg_cumulative_volume=avg_cumulative,
            day_rvol=day_rvol,
            volume_15=volume_15,
            avg_volume_15=avg_volume_15,
            rvol_15=rvol_15,
            volume_30=volume_30,
            avg_volume_30=avg_volume_30,
            rvol_30=rvol_30,
            opening_volume=state.opening_volume,
            avg_opening_volume=avg_opening,
            opening_rvol=opening_rvol,
            historical_sessions=baseline.historical_sessions if baseline else 0,
            available_sessions=coverage.available_sessions,
            baseline_sessions_used=coverage.baseline_sessions_used,
            active_sessions_available=coverage.active_sessions_available,
            active_sessions_used=coverage.active_sessions_used,
            first_history_date=coverage.first_history_date,
            last_history_date=coverage.last_history_date,
            quality_status=state.latest_quality_status,
            metrics_trusted=bool(
                coverage.usable
                and baseline is not None
                and not state.finalized_quality_reasons
                and not state.integrity_reasons
            ),
            metric_availability=availability,
            reasons=tuple(sorted(reasons)) if reasons else ("OK",),
            baseline_break_blocks=coverage.break_blocks,
        )

    def _refresh_latest_quality(self, state: _DayState) -> VolumeSnapshot:
        if state.snapshot is None:
            return self._empty_snapshot(state)
        coverage = self._coverage(state.symbol)
        reasons = set(state.snapshot.reasons)
        reasons.discard("OK")
        reasons.update(state.integrity_reasons)
        return replace(
            state.snapshot,
            quality_status=state.latest_quality_status,
            metrics_trusted=bool(
                coverage.usable
                and not state.finalized_quality_reasons
                and not state.integrity_reasons
            ),
            reasons=tuple(sorted(reasons)) if reasons else ("OK",),
        )

    def _empty_snapshot(self, state: _DayState) -> VolumeSnapshot:
        coverage = self._coverage(state.symbol)
        reasons = {"OUTSIDE_ROLLING_WINDOW"} | state.integrity_reasons
        if coverage.baseline_sessions_used == 0:
            reasons.add("NO_BASELINE")
        elif not coverage.usable:
            reasons.add("INSUFFICIENT_HISTORY")
        return VolumeSnapshot(
            symbol=state.symbol,
            exchange=state.exchange,
            trading_date=state.trading_date,
            as_of_minute=None,
            cumulative_volume=0,
            avg_cumulative_volume=None,
            day_rvol=None,
            volume_15=None,
            avg_volume_15=None,
            rvol_15=None,
            volume_30=None,
            avg_volume_30=None,
            rvol_30=None,
            opening_volume=None,
            avg_opening_volume=None,
            opening_rvol=None,
            historical_sessions=0,
            available_sessions=coverage.available_sessions,
            baseline_sessions_used=coverage.baseline_sessions_used,
            active_sessions_available=coverage.active_sessions_available,
            active_sessions_used=coverage.active_sessions_used,
            first_history_date=coverage.first_history_date,
            last_history_date=coverage.last_history_date,
            quality_status=state.latest_quality_status,
            metrics_trusted=coverage.usable and not state.integrity_reasons,
            metric_availability=MappingProxyType(
                {
                    "day_rvol": False,
                    "rvol_15": False,
                    "rvol_30": False,
                    "opening_rvol": False,
                }
            ),
            reasons=tuple(sorted(reasons)),
            baseline_break_blocks=coverage.break_blocks,
        )


def _ratio(numerator: int | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator
