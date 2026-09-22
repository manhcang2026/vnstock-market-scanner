from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

from .market_session import VN_TZ, SessionType, classify_market_session, normalize_exchange


COVERAGE_PROOF = "SSI_INTRADAY_ENDPOINT_COMPLETE_V1"
TRUSTED_DAILY_SOURCE = "SSI_DAILY_OHLC"
TRUSTED_DAILY_SOURCES = frozenset({TRUSTED_DAILY_SOURCE})
TRUSTED_INTRADAY_SOURCE = "SSI_REST"
TRUSTED_REPLAY_SOURCES = frozenset({"SSI_REST", "SSI_STREAM"})
TRUSTED_HISTORICAL_SOURCES = frozenset({TRUSTED_INTRADAY_SOURCE})
SAMPLE_SYMBOLS = ("HPG", "SHS", "VGI")
TARGET_BASELINE_SESSIONS = 10
MINIMUM_BASELINE_SESSIONS = 8
MAX_BREAK_BLOCKS = 2
DEFAULT_MAX_SCAN_SESSIONS = 20

BASELINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS volume_baseline (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    minute TEXT NOT NULL,
    session_segment TEXT NOT NULL,
    historical_sessions INTEGER NOT NULL,
    avg_cumulative_volume REAL NOT NULL,
    avg_volume_15 REAL,
    avg_volume_30 REAL,
    avg_opening_volume REAL,
    PRIMARY KEY (symbol, minute)
);
CREATE INDEX IF NOT EXISTS idx_volume_baseline_exchange_minute
    ON volume_baseline(exchange, minute, symbol);

CREATE TABLE IF NOT EXISTS volume_baseline_coverage (
    symbol TEXT PRIMARY KEY,
    exchange TEXT,
    available_sessions INTEGER NOT NULL,
    baseline_sessions_used INTEGER NOT NULL,
    active_sessions_available INTEGER NOT NULL,
    active_sessions_used INTEGER NOT NULL,
    first_history_date TEXT,
    last_history_date TEXT,
    break_blocks INTEGER NOT NULL DEFAULT 0,
    scanned_sessions INTEGER NOT NULL DEFAULT 0,
    skipped_sessions INTEGER NOT NULL DEFAULT 0,
    coverage_tier TEXT NOT NULL DEFAULT 'INSUFFICIENT',
    stopped_reason TEXT
);

CREATE TABLE IF NOT EXISTS volume_baseline_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class VolumeGridPoint:
    minute: str
    session_segment: str
    is_continuous: bool
    is_opening: bool
    is_closing: bool
    rolling_15_ready: bool
    rolling_30_ready: bool


@dataclass(frozen=True)
class RawVolumeBar:
    trading_date: str
    minute: str
    exchange: str
    volume: int
    data_source: str = TRUSTED_INTRADAY_SOURCE
    quality_status: str = "TRUSTED"
    is_partial: bool = False
    has_gap: bool = False


@dataclass(frozen=True)
class SessionProof:
    symbol: str
    trading_date: str
    exchange: str | None
    daily_volume: int | None
    represented_intraday_volume: int
    reason: str
    bars: tuple[RawVolumeBar, ...] = ()

    @property
    def proven(self) -> bool:
        return self.reason in {"PROVEN", "PROVEN_ZERO"}

    def failure_sample(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "trading_date": self.trading_date,
            "daily_volume": self.daily_volume,
            "represented_intraday_volume": self.represented_intraday_volume,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BaselineRow:
    symbol: str
    exchange: str
    minute: str
    session_segment: str
    historical_sessions: int
    avg_cumulative_volume: float
    avg_volume_15: float | None
    avg_volume_30: float | None
    avg_opening_volume: float | None


@dataclass(frozen=True)
class CoverageRow:
    symbol: str
    exchange: str | None
    available_sessions: int
    baseline_sessions_used: int
    active_sessions_available: int
    active_sessions_used: int
    first_history_date: str | None
    last_history_date: str | None
    break_blocks: int
    scanned_sessions: int
    skipped_sessions: int
    coverage_tier: str
    stopped_reason: str


@dataclass(frozen=True)
class SessionSelection:
    selected: tuple[SessionProof, ...]
    skipped: tuple[SessionProof, ...]
    scanned: tuple[SessionProof, ...]
    break_blocks: int
    stopped_reason: str

    @property
    def stopped_by_third_break_block(self) -> bool:
        return self.stopped_reason == "THIRD_BREAK_BLOCK"

    @property
    def exhausted_max_scan(self) -> bool:
        return self.stopped_reason == "MAX_SCAN_EXHAUSTED"

    @property
    def coverage_tier(self) -> str:
        if self.break_blocks > MAX_BREAK_BLOCKS:
            return "INSUFFICIENT"
        return coverage_tier(len(self.selected))

    @property
    def usable(self) -> bool:
        return (
            len(self.selected) >= MINIMUM_BASELINE_SESSIONS
            and self.break_blocks <= MAX_BREAK_BLOCKS
        )


@dataclass(frozen=True)
class BaselineBuildSummary:
    as_of_date: str
    candidate_market_sessions: int
    lookback: int
    max_scan_sessions: int
    symbols_processed: int
    symbols_10_sessions: int
    symbols_9_sessions: int
    symbols_8_sessions: int
    symbols_under_8_sessions: int
    symbols_stopped_third_break_block: int
    symbols_exhausted_max_scan: int
    symbols_no_history: int
    symbols_10_10_proven: int
    symbols_partial: int
    symbols_zero_proven: int
    sessions_proven: int
    sessions_unproven: int
    daily_missing_count: int
    volume_mismatch_count: int
    unsafe_intraday_count: int
    exchange_mismatch_count: int
    baseline_rows: int
    coverage_proof: str
    samples: tuple[dict[str, Any], ...]

    @property
    def symbols(self) -> int:
        return self.symbols_processed

    @property
    def symbols_without_history(self) -> int:
        return self.symbols_processed - self.symbols_10_10_proven - self.symbols_partial

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["samples"] = list(self.samples)
        return value


@dataclass
class _PointSamples:
    cumulative: list[int]
    rolling_15: list[int]
    rolling_30: list[int]
    opening: list[int]


_GRID_REFERENCE_DATE = date(2026, 9, 14)
_OPENING_BUCKETS = {"HOSE": "09:15"}
_CLOSING_BUCKETS = {"HOSE": "14:45", "HNX": "14:45"}


def volume_market_grid(exchange: str) -> tuple[VolumeGridPoint, ...]:
    canonical = normalize_exchange(exchange)
    points: list[VolumeGridPoint] = []
    counts = {SessionType.AM_CONTINUOUS.value: 0, SessionType.PM_CONTINUOUS.value: 0}
    start = datetime.combine(_GRID_REFERENCE_DATE, datetime.min.time(), tzinfo=VN_TZ)
    moment = start.replace(hour=9)
    end = start.replace(hour=15)
    while moment <= end:
        minute = moment.strftime("%H:%M")
        session = classify_market_session(canonical, moment)
        if _OPENING_BUCKETS.get(canonical) == minute:
            points.append(VolumeGridPoint(minute, "OPENING_BUCKET", False, True, False, False, False))
        elif _CLOSING_BUCKETS.get(canonical) == minute:
            points.append(VolumeGridPoint(minute, "CLOSE_BUCKET", False, False, True, False, False))
        elif session.is_continuous:
            segment = session.session_type.value
            counts[segment] += 1
            points.append(VolumeGridPoint(minute, segment, True, False, False, counts[segment] >= 15, counts[segment] >= 30))
        moment += timedelta(minutes=1)
    return tuple(points)


def _average(values: Sequence[int]) -> float | None:
    return sum(values) / len(values) if values else None


def coverage_tier(session_count: int) -> str:
    if session_count >= TARGET_BASELINE_SESSIONS:
        return "FULL"
    if session_count == 9:
        return "ACCEPTABLE"
    if session_count == 8:
        return "ACCEPTABLE_MINIMUM"
    return "INSUFFICIENT"


def select_volume_sessions(
    proofs_newest_first: Iterable[SessionProof],
    *,
    target_sessions: int = TARGET_BASELINE_SESSIONS,
    max_scan_sessions: int = DEFAULT_MAX_SCAN_SESSIONS,
    max_break_blocks: int = MAX_BREAK_BLOCKS,
) -> SessionSelection:
    if target_sessions < 1:
        raise ValueError("target_sessions must be positive")
    if max_scan_sessions < 1:
        raise ValueError("max_scan_sessions must be positive")
    if max_break_blocks < 0:
        raise ValueError("max_break_blocks must not be negative")

    selected: list[SessionProof] = []
    skipped: list[SessionProof] = []
    scanned: list[SessionProof] = []
    break_blocks = 0
    inside_bad_block = False
    stopped_reason = "CANDIDATES_EXHAUSTED"

    for proof in proofs_newest_first:
        if len(scanned) >= max_scan_sessions:
            stopped_reason = "MAX_SCAN_EXHAUSTED"
            break
        scanned.append(proof)
        if proof.proven:
            selected.append(proof)
            inside_bad_block = False
            if len(selected) >= target_sessions:
                stopped_reason = "TARGET_REACHED"
                break
            continue

        skipped.append(proof)
        if not inside_bad_block:
            break_blocks += 1
            inside_bad_block = True
            if break_blocks > max_break_blocks:
                stopped_reason = "THIRD_BREAK_BLOCK"
                break
    else:
        if len(scanned) >= max_scan_sessions and len(selected) < target_sessions:
            stopped_reason = "MAX_SCAN_EXHAUSTED"

    return SessionSelection(
        selected=tuple(selected),
        skipped=tuple(skipped),
        scanned=tuple(scanned),
        break_blocks=break_blocks,
        stopped_reason=stopped_reason,
    )


def build_symbol_volume_baseline(
    symbol: str,
    selection: SessionSelection,
    *,
    lookback: int,
    candidate_sessions: Sequence[str],
    opening_proofs: Iterable[SessionProof] | None = None,
) -> tuple[CoverageRow, list[BaselineRow]]:
    if lookback != TARGET_BASELINE_SESSIONS:
        raise ValueError(
            f"lookback must be {TARGET_BASELINE_SESSIONS} for the approved policy"
        )
    selected = list(selection.selected)
    exchanges = {proof.exchange for proof in selected if proof.exchange}
    if len(exchanges) > 1:
        selected = []
        exchanges = set()
    exchange = next(iter(exchanges), None)
    dates = [proof.trading_date for proof in selected]
    coverage = CoverageRow(
        symbol=symbol,
        exchange=exchange,
        available_sessions=len(candidate_sessions),
        baseline_sessions_used=len(selected),
        active_sessions_available=len(selected),
        active_sessions_used=len(selected),
        first_history_date=min(dates) if dates else None,
        last_history_date=max(dates) if dates else None,
        break_blocks=selection.break_blocks,
        scanned_sessions=len(selection.scanned),
        skipped_sessions=len(selection.skipped),
        coverage_tier=(selection.coverage_tier if selected else "INSUFFICIENT"),
        stopped_reason=selection.stopped_reason,
    )
    if not exchange or not selection.usable:
        return coverage, []

    grid = volume_market_grid(exchange)
    samples = {point.minute: _PointSamples([], [], [], []) for point in grid}
    for proof in selected:
        day = {bar.minute: bar.volume for bar in proof.bars}
        cumulative = 0
        segment_volumes: dict[str, list[int]] = {
            SessionType.AM_CONTINUOUS.value: [],
            SessionType.PM_CONTINUOUS.value: [],
        }
        for point in grid:
            # The complete Intraday endpoint result is authoritative for the
            # minute profile, so sparse no-trade minutes contribute zero.
            volume = day.get(point.minute, 0)
            cumulative += volume
            point_samples = samples[point.minute]
            point_samples.cumulative.append(cumulative)
            if point.is_continuous:
                segment = segment_volumes[point.session_segment]
                segment.append(volume)
                if point.rolling_15_ready:
                    point_samples.rolling_15.append(sum(segment[-15:]))
                if point.rolling_30_ready:
                    point_samples.rolling_30.append(sum(segment[-30:]))
            elif point.is_opening:
                point_samples.opening.append(volume)

    if opening_proofs is not None:
        opening_minute = _OPENING_BUCKETS.get(exchange)
        if opening_minute is not None:
            exact_window_opening: list[int] = []
            for proof in opening_proofs:
                if not proof.proven or proof.exchange != exchange:
                    continue
                day = {bar.minute: bar.volume for bar in proof.bars}
                exact_window_opening.append(day.get(opening_minute, 0))
            samples[opening_minute].opening = exact_window_opening

    rows: list[BaselineRow] = []
    for point in grid:
        point_samples = samples[point.minute]
        average_cumulative = _average(point_samples.cumulative)
        if average_cumulative is not None:
            rows.append(BaselineRow(
                symbol, exchange, point.minute, point.session_segment,
                len(point_samples.cumulative), average_cumulative,
                _average(point_samples.rolling_15), _average(point_samples.rolling_30),
                _average(point_samples.opening),
            ))
    return coverage, rows


def _open_readonly(path: Path, label: str) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"{label} database does not exist: {path}")
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _migrate_output_schema(connection: sqlite3.Connection) -> None:
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(volume_baseline_coverage)")
    }
    additions = {
        "active_sessions_available": "INTEGER NOT NULL DEFAULT 0",
        "active_sessions_used": "INTEGER NOT NULL DEFAULT 0",
        "break_blocks": "INTEGER NOT NULL DEFAULT 0",
        "scanned_sessions": "INTEGER NOT NULL DEFAULT 0",
        "skipped_sessions": "INTEGER NOT NULL DEFAULT 0",
        "coverage_tier": "TEXT NOT NULL DEFAULT 'INSUFFICIENT'",
        "stopped_reason": "TEXT",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.execute(
                f"ALTER TABLE volume_baseline_coverage ADD COLUMN {name} "
                f"{definition}"
            )


def load_candidate_market_sessions(
    history: sqlite3.Connection,
    daily: sqlite3.Connection,
    *,
    as_of_date: str,
    lookback: int,
) -> list[str]:
    date.fromisoformat(as_of_date)
    if _table_exists(daily, "trading_calendar"):
        calendar_dates = {
            str(row[0])
            for row in daily.execute(
                """
                SELECT DISTINCT trading_date FROM trading_calendar
                WHERE is_trading_day=1 AND trading_date < ?
                """,
                (as_of_date,),
            )
        }
        if calendar_dates:
            canonical_calendar_dates: list[str] = []
            for value in calendar_dates:
                try:
                    if date.fromisoformat(value).isoformat() == value:
                        canonical_calendar_dates.append(value)
                except ValueError:
                    continue
            return sorted(canonical_calendar_dates)[-lookback:]

    observed_dates = {
        str(row[0])
        for row in daily.execute(
            """
            SELECT DISTINCT trading_date FROM daily_bars
            WHERE source='SSI_DAILY_OHLC'
              AND quality_status='TRUSTED' AND trading_date < ?
            """,
            (as_of_date,),
        )
    }
    observed_dates.update(
        str(row[0])
        for row in history.execute(
            """
            SELECT DISTINCT trading_date FROM minute_bars
            WHERE data_source='SSI_REST'
              AND exchange IN ('HOSE', 'HNX', 'UPCOM')
              AND trading_date < ?
            """,
            (as_of_date,),
        )
    )
    canonical_dates: list[str] = []
    for value in observed_dates:
        try:
            if date.fromisoformat(value).isoformat() == value:
                canonical_dates.append(value)
        except ValueError:
            continue
    return sorted(canonical_dates)[-lookback:]


def _prove_volume_session(
    history: sqlite3.Connection,
    daily: sqlite3.Connection,
    *,
    symbol: str,
    trading_date: str,
    allowed_intraday_sources: frozenset[str],
    require_finalized_stream: bool = False,
    volume_match_sources: frozenset[str] = frozenset(),
) -> SessionProof:
    daily_row = daily.execute(
        """
        SELECT exchange, volume, source, quality_status FROM daily_bars
        WHERE symbol=? AND trading_date=?
        """,
        (symbol, trading_date),
    ).fetchone()
    if (
        daily_row is None
        or str(daily_row["source"]) not in TRUSTED_DAILY_SOURCES
        or str(daily_row["quality_status"]).upper() != "TRUSTED"
    ):
        return SessionProof(symbol, trading_date, None, None, 0, "DAILY_MISSING")
    try:
        exchange = normalize_exchange(str(daily_row["exchange"] or ""))
        daily_volume = int(daily_row["volume"])
        if daily_volume < 0:
            raise ValueError
    except (TypeError, ValueError):
        return SessionProof(symbol, trading_date, None, None, 0, "DAILY_UNSAFE")

    rows = history.execute(
        """
        SELECT trading_date, minute, exchange, volume, data_source,
               quality_status, is_partial, has_gap
        FROM minute_bars WHERE symbol=? AND trading_date=? ORDER BY minute
        """,
        (symbol, trading_date),
    ).fetchall()
    if (
        require_finalized_stream
        and any(str(row["data_source"] or "") == "SSI_STREAM" for row in rows)
        and not _has_finalized_stream_evidence(history, symbol, trading_date)
    ):
        return SessionProof(
            symbol, trading_date, exchange, daily_volume, 0, "UNFINALIZED_STREAM"
        )
    valid_minutes = {point.minute for point in volume_market_grid(exchange)}
    bars: list[RawVolumeBar] = []
    unsafe = False
    mismatch = False
    represented = 0
    for row in rows:
        data_source = str(row["data_source"] or "")
        raw_exchange = str(row["exchange"] or "")
        try:
            row_exchange = normalize_exchange(raw_exchange)
        except ValueError:
            unsafe = True
            continue
        try:
            volume = int(row["volume"])
        except (TypeError, ValueError):
            unsafe = True
            continue
        minute = str(row["minute"] or "")
        if row_exchange != exchange:
            mismatch = True
        if (
            data_source not in allowed_intraday_sources
            or str(row["quality_status"] or "").upper() != "TRUSTED"
            or bool(row["is_partial"])
            or bool(row["has_gap"])
            or minute not in valid_minutes
            or volume < 0
        ):
            unsafe = True
            continue
        represented += volume
        bars.append(
            RawVolumeBar(
                trading_date,
                minute,
                row_exchange,
                volume,
                data_source=data_source,
            )
        )
    if mismatch:
        return SessionProof(symbol, trading_date, exchange, daily_volume, represented, "EXCHANGE_MISMATCH")
    if unsafe:
        return SessionProof(symbol, trading_date, exchange, daily_volume, represented, "UNSAFE_INTRADAY")
    if represented != daily_volume and any(
        bar.data_source in volume_match_sources for bar in bars
    ):
        return SessionProof(symbol, trading_date, exchange, daily_volume, represented, "VOLUME_MISMATCH")
    if not bars and daily_volume != 0:
        return SessionProof(symbol, trading_date, exchange, daily_volume, represented, "INTRADAY_MISSING")
    reason = "PROVEN_ZERO" if daily_volume == 0 and not bars else "PROVEN"
    return SessionProof(symbol, trading_date, exchange, daily_volume, represented, reason, tuple(bars))


def _has_finalized_stream_evidence(
    history: sqlite3.Connection,
    symbol: str,
    trading_date: str,
) -> bool:
    """Require the yearly-history EOD journal before baseline trusts STREAM rows.

    Hot ``ssi_shadow.db`` rows also identify as ``SSI_STREAM``.  The journal and
    per-symbol TRUSTED result make the canonical yearly storage boundary explicit
    without inventing a synthetic provider source.
    """
    if not _table_exists(history, "daily_finalize_runs"):
        return False
    columns = {
        str(row[1])
        for row in history.execute("PRAGMA table_info(daily_finalize_runs)")
    }
    if not {"mode", "details_json"} <= columns:
        return False
    row = history.execute(
        """
        SELECT mode, details_json FROM daily_finalize_runs
        WHERE trading_date=?
        """,
        (trading_date,),
    ).fetchone()
    if row is None or str(row["mode"] or "").upper() != "WRITE":
        return False
    try:
        details = json.loads(str(row["details_json"] or ""))
    except (TypeError, ValueError):
        return False
    if not isinstance(details, list):
        return False
    canonical_symbol = str(symbol or "").strip().upper()
    return any(
        isinstance(item, dict)
        and str(item.get("symbol") or "").strip().upper() == canonical_symbol
        and str(item.get("status") or "").upper() == "TRUSTED"
        and not item.get("reasons")
        for item in details
    )


def prove_volume_session(
    history: sqlite3.Connection,
    daily: sqlite3.Connection,
    *,
    symbol: str,
    trading_date: str,
) -> SessionProof:
    """Prove canonical REST minutes alongside independent trusted DailyOhlc."""
    return _prove_volume_session(
        history,
        daily,
        symbol=symbol,
        trading_date=trading_date,
        allowed_intraday_sources=TRUSTED_HISTORICAL_SOURCES,
        require_finalized_stream=False,
    )


def prove_replay_volume_session(
    history: sqlite3.Connection,
    daily: sqlite3.Connection,
    *,
    symbol: str,
    trading_date: str,
) -> SessionProof:
    """Prove replay bars; stream replay retains its final-volume safety gate."""
    return _prove_volume_session(
        history,
        daily,
        symbol=symbol,
        trading_date=trading_date,
        allowed_intraday_sources=TRUSTED_REPLAY_SOURCES,
        volume_match_sources=frozenset({"SSI_STREAM"}),
    )


def _source_symbols(
    history: sqlite3.Connection,
    daily: sqlite3.Connection,
    candidate_sessions: Sequence[str],
    requested: Iterable[str] | None,
) -> list[str]:
    if requested is not None:
        return sorted({str(value).strip().upper() for value in requested if str(value).strip()})
    symbols = {
        str(row[0]).strip().upper()
        for row in history.execute("SELECT DISTINCT symbol FROM minute_bars WHERE symbol IS NOT NULL")
        if str(row[0]).strip()
    }
    if candidate_sessions:
        placeholders = ",".join("?" for _ in candidate_sessions)
        symbols.update(
            str(row[0]).strip().upper()
            for row in daily.execute(
                f"SELECT DISTINCT symbol FROM daily_bars WHERE trading_date IN ({placeholders})",
                tuple(candidate_sessions),
            )
            if str(row[0]).strip()
        )
    if _table_exists(history, "historical_bootstrap_checkpoints"):
        symbols.update(
            str(row[0]).strip().upper()
            for row in history.execute("SELECT DISTINCT symbol FROM historical_bootstrap_checkpoints WHERE symbol IS NOT NULL")
            if str(row[0]).strip()
        )
    return sorted(symbols)


def build_volume_baseline(
    *,
    history_db: Path,
    daily_db: Path,
    output_db: Path,
    as_of_date: str,
    lookback: int = TARGET_BASELINE_SESSIONS,
    max_scan_sessions: int = DEFAULT_MAX_SCAN_SESSIONS,
    symbols: Iterable[str] | None = None,
) -> BaselineBuildSummary:
    if lookback != TARGET_BASELINE_SESSIONS:
        raise ValueError(
            f"lookback must be {TARGET_BASELINE_SESSIONS} for the approved policy"
        )
    if max_scan_sessions < 1:
        raise ValueError("max_scan_sessions must be positive")
    parsed_as_of = date.fromisoformat(as_of_date)
    if parsed_as_of.isoformat() != as_of_date:
        raise ValueError("as_of_date must be canonical YYYY-MM-DD")
    resolved = [Path(value).resolve() for value in (history_db, daily_db, output_db)]
    if resolved[2] in resolved[:2]:
        raise ValueError("output_db must be different from both source databases")

    history = _open_readonly(resolved[0], "History")
    daily = _open_readonly(resolved[1], "Daily")
    output: sqlite3.Connection | None = None
    try:
        if not _table_exists(history, "minute_bars"):
            raise ValueError("History database has no minute_bars table")
        if not _table_exists(daily, "daily_bars"):
            raise ValueError("Daily database has no daily_bars table")
        candidates = load_candidate_market_sessions(
            history,
            daily,
            as_of_date=as_of_date,
            lookback=lookback,
        )
        selected_symbols = _source_symbols(history, daily, candidates, symbols)
        all_proofs: dict[str, list[SessionProof]] = {}
        opening_proofs: dict[str, list[SessionProof]] = {}
        selections: dict[str, SessionSelection] = {}
        for symbol in selected_symbols:
            proof_cache: dict[str, SessionProof] = {}

            def proof_for(session: str) -> SessionProof:
                proof = proof_cache.get(session)
                if proof is None:
                    proof = prove_volume_session(
                        history,
                        daily,
                        symbol=symbol,
                        trading_date=session,
                    )
                    proof_cache[session] = proof
                return proof

            selection = select_volume_sessions(
                (proof_for(session) for session in reversed(candidates)),
                target_sessions=lookback,
                max_scan_sessions=max_scan_sessions,
            )
            selections[symbol] = selection
            all_proofs[symbol] = list(selection.scanned)
            opening_proofs[symbol] = [
                proof_for(session)
                for session in reversed(candidates[-lookback:])
            ]

        output_db.parent.mkdir(parents=True, exist_ok=True)
        output = sqlite3.connect(output_db)
        output.executescript(BASELINE_SCHEMA)
        _migrate_output_schema(output)
        output.execute("BEGIN IMMEDIATE")
        output.execute("DELETE FROM volume_baseline")
        output.execute("DELETE FROM volume_baseline_coverage")
        output.execute("DELETE FROM volume_baseline_metadata")
        output.executemany(
            "INSERT INTO volume_baseline_metadata(key,value) VALUES (?,?)",
            (
                ("schema_version", "2"),
                ("lookback", str(lookback)),
                ("max_scan_sessions", str(max_scan_sessions)),
                ("minimum_baseline_sessions", str(MINIMUM_BASELINE_SESSIONS)),
                ("coverage_proof", COVERAGE_PROOF),
                ("as_of_date", as_of_date),
            ),
        )

        baseline_row_count = 0
        coverages: dict[str, CoverageRow] = {}
        for symbol in selected_symbols:
            coverage, rows = build_symbol_volume_baseline(
                symbol,
                selections[symbol],
                lookback=lookback,
                candidate_sessions=candidates,
                opening_proofs=opening_proofs[symbol],
            )
            coverages[symbol] = coverage
            output.execute(
                """INSERT INTO volume_baseline_coverage (
                    symbol, exchange, available_sessions, baseline_sessions_used,
                    active_sessions_available, active_sessions_used,
                    first_history_date, last_history_date, break_blocks,
                    scanned_sessions, skipped_sessions, coverage_tier,
                    stopped_reason
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    coverage.symbol,
                    coverage.exchange,
                    coverage.available_sessions,
                    coverage.baseline_sessions_used,
                    coverage.active_sessions_available,
                    coverage.active_sessions_used,
                    coverage.first_history_date,
                    coverage.last_history_date,
                    coverage.break_blocks,
                    coverage.scanned_sessions,
                    coverage.skipped_sessions,
                    coverage.coverage_tier,
                    coverage.stopped_reason,
                ),
            )
            output.executemany(
                "INSERT INTO volume_baseline VALUES (?,?,?,?,?,?,?,?,?)",
                [(row.symbol, row.exchange, row.minute, row.session_segment,
                  row.historical_sessions, row.avg_cumulative_volume,
                  row.avg_volume_15, row.avg_volume_30, row.avg_opening_volume)
                 for row in rows],
            )
            baseline_row_count += len(rows)
        output.commit()

        flattened = [proof for values in all_proofs.values() for proof in values]
        samples: list[dict[str, Any]] = []
        for symbol in SAMPLE_SYMBOLS:
            if symbol not in all_proofs:
                continue
            selection = selections[symbol]
            failed = [proof.failure_sample() for proof in selection.skipped]
            coverage = coverages[symbol]
            samples.append({
                "symbol": symbol,
                "candidate_sessions": len(candidates),
                "sessions_proven": coverage.baseline_sessions_used,
                "selected_dates": [
                    proof.trading_date for proof in selection.selected
                ],
                "skipped_dates": [
                    proof.trading_date for proof in selection.skipped
                ],
                "break_blocks": selection.break_blocks,
                "scanned_sessions": len(selection.scanned),
                "coverage_tier": coverage.coverage_tier,
                "stopped_reason": selection.stopped_reason,
                "failures": failed[:3],
            })
        proven = [proof for proof in flattened if proof.proven]
        selected_counts = {
            symbol: coverage.baseline_sessions_used
            for symbol, coverage in coverages.items()
        }
        return BaselineBuildSummary(
            as_of_date=as_of_date,
            candidate_market_sessions=len(candidates),
            lookback=lookback,
            max_scan_sessions=max_scan_sessions,
            symbols_processed=len(selected_symbols),
            symbols_10_sessions=sum(
                count >= TARGET_BASELINE_SESSIONS
                for count in selected_counts.values()
            ),
            symbols_9_sessions=sum(count == 9 for count in selected_counts.values()),
            symbols_8_sessions=sum(count == 8 for count in selected_counts.values()),
            symbols_under_8_sessions=sum(
                count < MINIMUM_BASELINE_SESSIONS
                for count in selected_counts.values()
            ),
            symbols_stopped_third_break_block=sum(
                selection.stopped_by_third_break_block
                for selection in selections.values()
            ),
            symbols_exhausted_max_scan=sum(
                selection.exhausted_max_scan
                for selection in selections.values()
            ),
            symbols_no_history=sum(
                count == 0 for count in selected_counts.values()
            ),
            symbols_10_10_proven=sum(
                count == lookback for count in selected_counts.values()
            ),
            symbols_partial=sum(
                0 < count < lookback for count in selected_counts.values()
            ),
            symbols_zero_proven=sum(any(proof.reason == "PROVEN_ZERO" for proof in proofs) for proofs in all_proofs.values()),
            sessions_proven=len(proven),
            sessions_unproven=len(flattened) - len(proven),
            daily_missing_count=sum(proof.reason == "DAILY_MISSING" for proof in flattened),
            volume_mismatch_count=sum(
                bool(proof.bars)
                and proof.daily_volume is not None
                and proof.represented_intraday_volume != proof.daily_volume
                for proof in flattened
            ),
            unsafe_intraday_count=sum(
                proof.reason
                in {"UNSAFE_INTRADAY", "DAILY_UNSAFE", "UNFINALIZED_STREAM"}
                for proof in flattened
            ),
            exchange_mismatch_count=sum(proof.reason == "EXCHANGE_MISMATCH" for proof in flattened),
            baseline_rows=baseline_row_count,
            coverage_proof=COVERAGE_PROOF,
            samples=tuple(samples),
        )
    except Exception:
        if output is not None:
            output.rollback()
        raise
    finally:
        if output is not None:
            output.close()
        daily.close()
        history.close()
