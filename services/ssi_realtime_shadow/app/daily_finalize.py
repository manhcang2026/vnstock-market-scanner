"""Deterministic REST-canonical EOD settlement.

The transaction boundary is one symbol/session. A symbol is fully preflighted
before its minute, daily, and auction rows are committed. Other symbols can
therefore settle when one symbol is corrupt, and a retry is idempotent. Raw
FastConnect is accepted only as explicit ATO/ATC provider-session proof.  SSI
REST IntradayOhlc and DailyOhlc own ordinary canonical history.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable, Mapping

from .auction import CLOSE_AUCTION, OPEN_AUCTION
from .auction_history import (
    PROVEN,
    SSI_STREAM,
    AuctionHistoryConflict,
    AuctionHistoryRow,
    store_auction_history_row,
)
from .daily_history import (
    DAILY_SOURCE,
    TRUSTED_QUALITY,
    DailyBar,
    normalize_daily_ohlc_record,
)
from .market_session import VN_TZ, normalize_exchange
from .market_storage_schema import canonical_timestamp, ensure_market_storage_schema
from .volume_baseline import volume_market_grid


SAFE_AFTER = time(15, 20)
STREAM_DAILY_SOURCE = SSI_STREAM
MIN_STREAM_SYMBOLS = 500
MIN_STREAM_MINUTES = 200
MAX_STREAM_FIRST_MINUTE = "09:15"
MIN_STREAM_LAST_MINUTE = "14:45"
MAX_TARGETED_REPAIR_SYMBOLS = 50
SETTLEABLE_EVENT_QUALITIES = frozenset({"TRUSTED"})
CANONICAL_MINUTE_SOURCES = frozenset({"SSI_REST"})
MINUTE_COLUMNS = (
    "trading_date",
    "minute",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "last_total_volume",
    "event_count",
    "is_partial",
    "exchange",
    "quality_status",
    "has_gap",
    "gap_from",
    "gap_to",
    "data_source",
    "provider_time",
    "updated_at",
)


@dataclass(frozen=True, slots=True)
class DayAudit:
    trading_date: str
    rows: int
    symbols: int
    event_anomaly_rows: int
    unresolved_gap_rows: int
    quality_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class SymbolFinalizeResult:
    symbol: str
    status: str
    reasons: tuple[str, ...]
    source_rows: int
    represented_volume: int
    daily_volume: int | None
    event_anomaly_rows: int
    event_anomalies: tuple[str, ...]
    unresolved_gaps: int
    minute_rows_inserted: int
    minute_rows_identical: int
    minute_conflicts: int
    daily_rows_inserted: int
    daily_rows_existing: int
    daily_conflicts: int
    ato_proven_inserted: int
    ato_proven_existing: int
    ato_conflicts: int
    atc_proven_inserted: int
    atc_proven_superseded: int
    atc_proven_existing: int
    atc_conflicts: int


@dataclass(frozen=True, slots=True)
class FinalizeResult:
    trading_date: str
    mode: str
    status: str
    started_at: str
    finalized_at: str
    source_rows: int
    source_symbols: int
    symbols_attempted: int
    symbols_trusted: int
    symbols_blocked: int
    symbols_unavailable: int
    minute_rows_inserted: int
    minute_rows_identical: int
    minute_conflicts: int
    daily_rows_inserted: int
    daily_rows_existing: int
    daily_conflicts: int
    ato_proven_inserted: int
    ato_proven_existing: int
    ato_conflicts: int
    atc_proven_inserted: int
    atc_proven_superseded: int
    atc_proven_existing: int
    atc_conflicts: int
    event_anomaly_rows: int
    settled_reconciliations: int
    volume_mismatches: int
    missing_daily_ohlc: int
    unresolved_gaps: int
    symbols: tuple[SymbolFinalizeResult, ...]


@dataclass(frozen=True, slots=True)
class RepairPlan:
    bounded: bool
    symbols: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class CanonicalDayCompleteness:
    complete: bool
    expected_symbols: tuple[str, ...]
    complete_symbols: tuple[str, ...]
    provider_unavailable: tuple[str, ...]
    missing_daily_bars: tuple[str, ...]
    missing_history: tuple[str, ...]
    unsafe_daily_bars: tuple[str, ...]
    unsafe_history: tuple[str, ...]
    volume_mismatches: tuple[str, ...]
    unfinalized_stream: tuple[str, ...]
    unsafe_stream_source: tuple[str, ...]


_JOURNAL_COLUMNS: Mapping[str, str] = {
    "mode": "TEXT NOT NULL DEFAULT 'WRITE'",
    "started_at": "TEXT NOT NULL DEFAULT ''",
    "source_symbols": "INTEGER NOT NULL DEFAULT 0",
    "symbols_attempted": "INTEGER NOT NULL DEFAULT 0",
    "symbols_trusted": "INTEGER NOT NULL DEFAULT 0",
    "symbols_blocked": "INTEGER NOT NULL DEFAULT 0",
    "symbols_unavailable": "INTEGER NOT NULL DEFAULT 0",
    "minute_rows_inserted": "INTEGER NOT NULL DEFAULT 0",
    "minute_rows_identical": "INTEGER NOT NULL DEFAULT 0",
    "minute_conflicts": "INTEGER NOT NULL DEFAULT 0",
    "daily_rows_inserted": "INTEGER NOT NULL DEFAULT 0",
    "daily_rows_existing": "INTEGER NOT NULL DEFAULT 0",
    "daily_conflicts": "INTEGER NOT NULL DEFAULT 0",
    "ato_proven_inserted": "INTEGER NOT NULL DEFAULT 0",
    "ato_proven_existing": "INTEGER NOT NULL DEFAULT 0",
    "ato_conflicts": "INTEGER NOT NULL DEFAULT 0",
    "atc_proven_inserted": "INTEGER NOT NULL DEFAULT 0",
    "atc_proven_superseded": "INTEGER NOT NULL DEFAULT 0",
    "atc_proven_existing": "INTEGER NOT NULL DEFAULT 0",
    "atc_conflicts": "INTEGER NOT NULL DEFAULT 0",
    "event_anomaly_rows": "INTEGER NOT NULL DEFAULT 0",
    "settled_reconciliations": "INTEGER NOT NULL DEFAULT 0",
    "volume_mismatches": "INTEGER NOT NULL DEFAULT 0",
    "missing_daily_ohlc": "INTEGER NOT NULL DEFAULT 0",
    "unresolved_gaps": "INTEGER NOT NULL DEFAULT 0",
}


def yearly_history_path(directory: Path, trading_date: str) -> Path:
    """Return the deterministic yearly canonical history path."""
    year = date.fromisoformat(trading_date).year
    return Path(directory) / f"ssi_history_{year}.db"


def _connect_existing(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Required SQLite database does not exist: {resolved}")
    if read_only:
        connection = sqlite3.connect(
            f"file:{resolved.as_posix()}?mode=ro", uri=True, timeout=30
        )
    else:
        connection = sqlite3.connect(resolved, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def _table_exists(connection: sqlite3.Connection, name: str, schema: str = "main") -> bool:
    if schema not in {"main", "history"}:
        raise ValueError("unsupported SQLite schema")
    return connection.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def ensure_finalize_schema(
    connection: sqlite3.Connection, *, schema: str = "main"
) -> None:
    """Create or additively migrate the yearly EOD journal."""
    if schema not in {"main", "history"}:
        raise ValueError("unsupported SQLite schema")
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {schema}.daily_finalize_runs (
            trading_date TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finalized_at TEXT NOT NULL,
            source_rows INTEGER NOT NULL,
            source_symbols INTEGER NOT NULL,
            symbols_attempted INTEGER NOT NULL,
            symbols_trusted INTEGER NOT NULL,
            symbols_blocked INTEGER NOT NULL,
            symbols_unavailable INTEGER NOT NULL,
            minute_rows_inserted INTEGER NOT NULL,
            minute_rows_identical INTEGER NOT NULL,
            minute_conflicts INTEGER NOT NULL,
            daily_rows_inserted INTEGER NOT NULL,
            daily_rows_existing INTEGER NOT NULL,
            daily_conflicts INTEGER NOT NULL,
            ato_proven_inserted INTEGER NOT NULL,
            ato_proven_existing INTEGER NOT NULL,
            ato_conflicts INTEGER NOT NULL,
            atc_proven_inserted INTEGER NOT NULL,
            atc_proven_superseded INTEGER NOT NULL,
            atc_proven_existing INTEGER NOT NULL,
            atc_conflicts INTEGER NOT NULL,
            event_anomaly_rows INTEGER NOT NULL,
            settled_reconciliations INTEGER NOT NULL,
            volume_mismatches INTEGER NOT NULL,
            missing_daily_ohlc INTEGER NOT NULL,
            unresolved_gaps INTEGER NOT NULL,
            details_json TEXT NOT NULL
        )
        """
    )
    columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA {schema}.table_info(daily_finalize_runs)")
    }
    for name, definition in _JOURNAL_COLUMNS.items():
        if name not in columns:
            connection.execute(
                f"ALTER TABLE {schema}.daily_finalize_runs ADD COLUMN {name} {definition}"
            )


def _canonical_daily_bars(
    bars: Iterable[DailyBar],
    trading_date: str,
    *,
    allowed_sources: frozenset[str] = frozenset({DAILY_SOURCE}),
) -> dict[str, DailyBar]:
    canonical: dict[str, DailyBar] = {}
    for bar in bars:
        symbol = str(bar.symbol or "").strip().upper()
        exchange = normalize_exchange(bar.exchange)
        values = (bar.open, bar.high, bar.low, bar.close)
        if (
            symbol != bar.symbol
            or bar.trading_date != trading_date
            or bar.source not in allowed_sources
            or bar.quality_status != TRUSTED_QUALITY
            or not all(math.isfinite(float(value)) and float(value) > 0 for value in values)
            or float(bar.high) < float(bar.low)
            or not float(bar.low) <= float(bar.open) <= float(bar.high)
            or not float(bar.low) <= float(bar.close) <= float(bar.high)
            or isinstance(bar.volume, bool)
            or int(bar.volume) != bar.volume
            or int(bar.volume) < 0
            or (
                bar.value is not None
                and (not math.isfinite(float(bar.value)) or float(bar.value) < 0)
            )
        ):
            raise ValueError(f"Invalid canonical DailyOhlc input for {symbol or '<empty>'}")
        normalized = DailyBar(
            symbol=symbol,
            trading_date=trading_date,
            exchange=exchange,
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=int(bar.volume),
            value=None if bar.value is None else float(bar.value),
            source=bar.source,
            quality_status=bar.quality_status,
        )
        existing = canonical.get(symbol)
        if existing is not None and existing != normalized:
            raise ValueError(f"Conflicting DailyOhlc input for {symbol}/{trading_date}")
        canonical[symbol] = normalized
    return canonical


def _stream_coverage_reasons(
    rows_by_symbol: Mapping[str, list[sqlite3.Row]],
    *,
    minimum_symbols: int = MIN_STREAM_SYMBOLS,
    minimum_minutes: int = MIN_STREAM_MINUTES,
) -> tuple[str, ...]:
    minutes = sorted(
        {
            str(row["minute"] or "")
            for rows in rows_by_symbol.values()
            for row in rows
            if row["minute"]
        }
    )
    reasons: list[str] = []
    symbol_count = sum(bool(symbol) for symbol in rows_by_symbol)
    if symbol_count < minimum_symbols:
        reasons.append(f"STREAM_SYMBOLS<{minimum_symbols}")
    if len(minutes) < minimum_minutes:
        reasons.append(f"STREAM_MINUTES<{minimum_minutes}")
    if not minutes or minutes[0] > MAX_STREAM_FIRST_MINUTE:
        reasons.append(f"STREAM_FIRST_MINUTE>{MAX_STREAM_FIRST_MINUTE}")
    if not minutes or minutes[-1] < MIN_STREAM_LAST_MINUTE:
        reasons.append(f"STREAM_LAST_MINUTE<{MIN_STREAM_LAST_MINUTE}")
    return tuple(reasons)


def _stream_daily_bars(
    rows_by_symbol: Mapping[str, list[sqlite3.Row]], trading_date: str
) -> tuple[DailyBar, ...]:
    """Aggregate stream rows without claiming that REST DailyOhlc supplied them."""
    bars: list[DailyBar] = []
    for symbol, raw_rows in sorted(rows_by_symbol.items()):
        if not symbol:
            continue
        rows = sorted(raw_rows, key=lambda row: str(row["minute"] or ""))
        try:
            exchanges = {
                normalize_exchange(str(row["exchange"] or "")) for row in rows
            }
            if len(exchanges) != 1 or not rows or not all(_valid_ohlcv(row) for row in rows):
                continue
            bars.append(
                DailyBar(
                    symbol=symbol,
                    trading_date=trading_date,
                    exchange=next(iter(exchanges)),
                    open=float(rows[0]["open"]),
                    high=max(float(row["high"]) for row in rows),
                    low=min(float(row["low"]) for row in rows),
                    close=float(rows[-1]["close"]),
                    volume=sum(int(row["volume"]) for row in rows),
                    value=None,
                    source=STREAM_DAILY_SOURCE,
                    quality_status=TRUSTED_QUALITY,
                )
            )
        except (TypeError, ValueError):
            continue
    return tuple(bars)


def _load_source_rows(
    source: sqlite3.Connection, trading_date: str
) -> dict[str, list[sqlite3.Row]]:
    if not _table_exists(source, "minute_bars"):
        raise ValueError("Hot database has no minute_bars table")
    rows = source.execute(
        f"""
        SELECT {', '.join(MINUTE_COLUMNS)}
        FROM minute_bars
        WHERE trading_date=?
        ORDER BY symbol, minute
        """,
        (trading_date,),
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        symbol = str(row["symbol"] or "").strip().upper()
        grouped.setdefault(symbol, []).append(row)
    return grouped


def audit_day(rows_by_symbol: Mapping[str, list[sqlite3.Row]], trading_date: str) -> DayAudit:
    rows = [row for values in rows_by_symbol.values() for row in values]
    quality_counts = Counter(str(row["quality_status"] or "").upper() for row in rows)
    return DayAudit(
        trading_date=trading_date,
        rows=len(rows),
        symbols=len(rows_by_symbol),
        event_anomaly_rows=sum(
            str(row["quality_status"] or "").upper() != "TRUSTED"
            or bool(row["is_partial"])
            for row in rows
        ),
        unresolved_gap_rows=sum(bool(row["has_gap"]) for row in rows),
        quality_counts=dict(sorted(quality_counts.items())),
    )


def _daily_values(bar: DailyBar) -> tuple[object, ...]:
    return (
        bar.symbol,
        bar.trading_date,
        bar.exchange,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        bar.value,
        bar.source,
        bar.quality_status,
    )


def _daily_outcome(connection: sqlite3.Connection, bar: DailyBar) -> str:
    existing = connection.execute(
        """
        SELECT symbol, trading_date, exchange, open, high, low, close,
               volume, value, source, quality_status
        FROM daily_bars WHERE symbol=? AND trading_date=?
        """,
        (bar.symbol, bar.trading_date),
    ).fetchone()
    if existing is None:
        return "INSERT"
    return "EXISTING" if tuple(existing) == _daily_values(bar) else "CONFLICT"


def _valid_ohlcv(row: sqlite3.Row) -> bool:
    try:
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        raw_volume = float(row["volume"])
    except (TypeError, ValueError):
        return False
    return (
        all(math.isfinite(value) and value > 0 for value in (open_price, high, low, close))
        and math.isfinite(raw_volume)
        and raw_volume >= 0
        and raw_volume.is_integer()
        and high >= low
        and low <= open_price <= high
        and low <= close <= high
    )


def _settled_minute_values(row: sqlite3.Row, symbol: str, exchange: str) -> tuple[object, ...]:
    return (
        str(row["trading_date"]),
        str(row["minute"]),
        symbol,
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        int(row["volume"]),
        row["last_total_volume"],
        int(row["event_count"]),
        0,
        exchange,
        "TRUSTED",
        0,
        None,
        None,
        "SSI_REST",
        row["provider_time"],
        str(row["updated_at"]),
    )


def _same_canonical_minute(existing: sqlite3.Row, settled: tuple[object, ...]) -> bool:
    indexes = {name: index for index, name in enumerate(MINUTE_COLUMNS)}
    core = (
        "trading_date",
        "minute",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "exchange",
    )
    return (
        str(existing["data_source"]) in CANONICAL_MINUTE_SOURCES
        and str(existing["quality_status"]).upper() == "TRUSTED"
        and not bool(existing["is_partial"])
        and not bool(existing["has_gap"])
        and all(existing[name] == settled[indexes[name]] for name in core)
    )


def _auction_rows(
    source: sqlite3.Connection, symbol: str, trading_date: str
) -> list[sqlite3.Row]:
    if not _table_exists(source, "auction_session_buckets"):
        return []
    return source.execute(
        """
        SELECT symbol, trading_date, exchange, auction_type, provider_session,
               auction_price, pre_auction_price, auction_volume, event_count,
               quality_status, finalized, data_source
        FROM auction_session_buckets
        WHERE symbol=? AND trading_date=? AND finalized=1
        ORDER BY auction_type
        """,
        (symbol, trading_date),
    ).fetchall()


def _eod_checkpoint_pairs(
    source: sqlite3.Connection, trading_date: str
) -> dict[str, tuple[str | None, str | None]]:
    """Return explicit intraday/daily EOD states when the wrapper supplied them."""
    if not _table_exists(source, "eod_daily_checkpoints"):
        return {}
    intraday = {
        str(row["symbol"] or "").strip().upper(): str(row["status"] or "").upper()
        for row in source.execute(
            """
            SELECT symbol, status FROM historical_bootstrap_checkpoints
            WHERE from_date=? AND to_date=? AND resolution=1
            """,
            (trading_date, trading_date),
        )
        if str(row["symbol"] or "").strip()
    }
    daily = {
        str(row["symbol"] or "").strip().upper(): str(row["status"] or "").upper()
        for row in source.execute(
            """
            SELECT symbol, status FROM eod_daily_checkpoints
            WHERE trading_date=?
            """,
            (trading_date,),
        )
        if str(row["symbol"] or "").strip()
    }
    return {
        symbol: (intraday.get(symbol), daily.get(symbol))
        for symbol in sorted(set(intraday) | set(daily))
    }


def _proven_auction(row: sqlite3.Row) -> AuctionHistoryRow:
    auction_type = str(row["auction_type"] or "").upper()
    provider_session = str(row["provider_session"] or "").upper()
    expected = "ATO" if auction_type == OPEN_AUCTION else "ATC"
    if (
        auction_type not in {OPEN_AUCTION, CLOSE_AUCTION}
        or provider_session != expected
        or str(row["data_source"] or "").upper() != SSI_STREAM
        or str(row["quality_status"] or "").upper() != "TRUSTED"
        or int(row["event_count"] or 0) <= 0
    ):
        raise ValueError("auction bucket lacks trusted provider-session evidence")
    return AuctionHistoryRow(
        symbol=str(row["symbol"]),
        trading_date=str(row["trading_date"]),
        exchange=str(row["exchange"]),
        auction_type=auction_type,
        auction_price=float(row["auction_price"]),
        pre_auction_price=(
            None
            if row["pre_auction_price"] is None
            else float(row["pre_auction_price"])
        ),
        auction_volume=int(row["auction_volume"]),
        provider_session=provider_session,
        source=SSI_STREAM,
        quality=PROVEN,
        proof_code=None,
        finalized=True,
    )


def _empty_symbol_result(
    symbol: str,
    status: str,
    reasons: Iterable[str],
    rows: list[sqlite3.Row],
    daily_volume: int | None,
) -> SymbolFinalizeResult:
    anomalies = Counter()
    for row in rows:
        quality = str(row["quality_status"] or "").upper()
        if quality != "TRUSTED":
            anomalies[quality or "EMPTY_QUALITY"] += 1
        if bool(row["is_partial"]):
            anomalies["IS_PARTIAL"] += 1
    return SymbolFinalizeResult(
        symbol=symbol,
        status=status,
        reasons=tuple(sorted(set(reasons))),
        source_rows=len(rows),
        represented_volume=sum(max(0, int(row["volume"] or 0)) for row in rows),
        daily_volume=daily_volume,
        event_anomaly_rows=sum(
            str(row["quality_status"] or "").upper() != "TRUSTED"
            or bool(row["is_partial"])
            for row in rows
        ),
        event_anomalies=tuple(f"{key}={value}" for key, value in sorted(anomalies.items())),
        unresolved_gaps=sum(bool(row["has_gap"]) for row in rows),
        minute_rows_inserted=0,
        minute_rows_identical=0,
        minute_conflicts=0,
        daily_rows_inserted=0,
        daily_rows_existing=0,
        daily_conflicts=0,
        ato_proven_inserted=0,
        ato_proven_existing=0,
        ato_conflicts=0,
        atc_proven_inserted=0,
        atc_proven_superseded=0,
        atc_proven_existing=0,
        atc_conflicts=0,
    )


def _replace_result(result: SymbolFinalizeResult, **changes: int) -> SymbolFinalizeResult:
    values = asdict(result)
    values.update(changes)
    return SymbolFinalizeResult(**values)


def _settle_symbol(
    connection: sqlite3.Connection,
    source: sqlite3.Connection,
    *,
    symbol: str,
    trading_date: str,
    rows: list[sqlite3.Row],
    daily_bar: DailyBar | None,
    recorded_at: str,
    dry_run: bool,
    auction_source: sqlite3.Connection,
    intraday_no_data: bool = False,
) -> SymbolFinalizeResult:
    if daily_bar is None:
        return _empty_symbol_result(symbol, "UNAVAILABLE", ("DAILY_MISSING",), rows, None)
    if not rows:
        if intraday_no_data:
            if daily_bar.volume != 0:
                return _empty_symbol_result(
                    symbol,
                    "BLOCKED",
                    ("VOLUME_MISMATCH",),
                    rows,
                    daily_bar.volume,
                )
            daily_outcome = _daily_outcome(connection, daily_bar)
            if daily_outcome == "CONFLICT":
                return _replace_result(
                    _empty_symbol_result(
                        symbol,
                        "BLOCKED",
                        ("DAILY_CONFLICT",),
                        rows,
                        daily_bar.volume,
                    ),
                    daily_conflicts=1,
                )
            if not dry_run and daily_outcome == "INSERT":
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        """
                        INSERT INTO daily_bars (
                            symbol, trading_date, exchange, open, high, low, close,
                            volume, value, source, quality_status, finalized_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        _daily_values(daily_bar) + (recorded_at,),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
            return _replace_result(
                _empty_symbol_result(symbol, "TRUSTED", (), rows, daily_bar.volume),
                daily_rows_inserted=daily_outcome == "INSERT",
                daily_rows_existing=daily_outcome == "EXISTING",
            )
        return _empty_symbol_result(
            symbol, "UNAVAILABLE", ("SOURCE_MISSING",), rows, daily_bar.volume
        )

    reasons: list[str] = []
    valid_minutes = {point.minute for point in volume_market_grid(daily_bar.exchange)}
    anomalies = Counter()
    represented = 0
    settled_rows: list[tuple[object, ...]] = []
    for row in rows:
        quality = str(row["quality_status"] or "").upper()
        if quality != "TRUSTED":
            anomalies[quality or "EMPTY_QUALITY"] += 1
        if bool(row["is_partial"]):
            anomalies["IS_PARTIAL"] += 1
        try:
            row_exchange = normalize_exchange(str(row["exchange"] or ""))
        except ValueError:
            reasons.append("INVALID_EXCHANGE")
            continue
        if row_exchange != daily_bar.exchange:
            reasons.append("EXCHANGE_MISMATCH")
        if str(row["data_source"] or "").upper() != "SSI_REST":
            reasons.append("NON_REST_SOURCE")
        if str(row["minute"] or "") not in valid_minutes:
            reasons.append("INVALID_MARKET_MINUTE")
        if not _valid_ohlcv(row):
            reasons.append("INVALID_OHLCV")
            continue
        if bool(row["has_gap"]):
            reasons.append("UNRESOLVED_GAP")
        if bool(row["is_partial"]):
            reasons.append("PARTIAL_STREAM_ROW")
        if quality not in SETTLEABLE_EVENT_QUALITIES:
            reasons.append("UNRESOLVED_EVENT_ANOMALY")
        represented += int(row["volume"])
        settled_rows.append(_settled_minute_values(row, symbol, daily_bar.exchange))

    if represented != daily_bar.volume:
        reasons.append("VOLUME_MISMATCH")
    if reasons:
        return _empty_symbol_result(symbol, "BLOCKED", reasons, rows, daily_bar.volume)

    daily_outcome = _daily_outcome(connection, daily_bar)
    if daily_outcome == "CONFLICT":
        return _replace_result(
            _empty_symbol_result(
                symbol, "BLOCKED", ("DAILY_CONFLICT",), rows, daily_bar.volume
            ),
            daily_conflicts=1,
        )

    minute_inserted = minute_identical = minute_conflicts = 0
    new_settled_rows: list[tuple[object, ...]] = []
    for settled in settled_rows:
        existing = connection.execute(
            """
            SELECT trading_date, minute, symbol, open, high, low, close, volume,
                   is_partial, exchange, quality_status, has_gap, data_source
            FROM history.minute_bars
            WHERE trading_date=? AND minute=? AND symbol=?
            """,
            settled[:3],
        ).fetchone()
        if existing is None:
            minute_inserted += 1
            new_settled_rows.append(settled)
        elif _same_canonical_minute(existing, settled):
            minute_identical += 1
        else:
            minute_conflicts += 1
    if minute_conflicts:
        return _replace_result(
            _empty_symbol_result(
                symbol, "BLOCKED", ("MINUTE_CONFLICT",), rows, daily_bar.volume
            ),
            minute_conflicts=minute_conflicts,
        )

    auctions: list[tuple[AuctionHistoryRow, str]] = []
    ato_conflicts = atc_conflicts = 0
    for raw_bucket in _auction_rows(auction_source, symbol, trading_date):
        auction_type = str(raw_bucket["auction_type"] or "").upper()
        try:
            auction = _proven_auction(raw_bucket)
        except (TypeError, ValueError):
            # Hot auction evidence is optional.  Buckets that cannot prove the
            # required provider session are not promoted into canonical history
            # and must not block otherwise valid REST/Daily settlement.
            continue
        try:
            outcome = store_auction_history_row(
                connection, auction, recorded_at=recorded_at, dry_run=True
            )
            auctions.append((auction, outcome))
        except AuctionHistoryConflict:
            if auction_type == OPEN_AUCTION:
                ato_conflicts += 1
            else:
                atc_conflicts += 1
    if ato_conflicts or atc_conflicts:
        return _replace_result(
            _empty_symbol_result(
                symbol, "BLOCKED", ("AUCTION_CONFLICT",), rows, daily_bar.volume
            ),
            ato_conflicts=ato_conflicts,
            atc_conflicts=atc_conflicts,
        )

    ato_inserted = ato_existing = 0
    atc_inserted = atc_existing = atc_superseded = 0
    for auction, outcome in auctions:
        if auction.auction_type == OPEN_AUCTION:
            ato_inserted += outcome == "WOULD_INSERT"
            ato_existing += outcome == "ALREADY_IDENTICAL"
        else:
            atc_inserted += outcome == "WOULD_INSERT"
            atc_existing += outcome == "ALREADY_IDENTICAL"
            atc_superseded += outcome == "WOULD_SUPERSEDE"

    if not dry_run:
        connection.execute("BEGIN IMMEDIATE")
        try:
            if daily_outcome == "INSERT":
                connection.execute(
                    """
                    INSERT INTO daily_bars (
                        symbol, trading_date, exchange, open, high, low, close,
                        volume, value, source, quality_status, finalized_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _daily_values(daily_bar) + (recorded_at,),
                )
            for settled in new_settled_rows:
                connection.execute(
                    f"""
                    INSERT INTO history.minute_bars ({', '.join(MINUTE_COLUMNS)})
                    VALUES ({', '.join('?' for _ in MINUTE_COLUMNS)})
                    """,
                    settled,
                )
            for auction, _ in auctions:
                store_auction_history_row(
                    connection, auction, recorded_at=recorded_at, dry_run=False
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return SymbolFinalizeResult(
        symbol=symbol,
        status="TRUSTED",
        reasons=(),
        source_rows=len(rows),
        represented_volume=represented,
        daily_volume=daily_bar.volume,
        event_anomaly_rows=sum(
            str(row["quality_status"] or "").upper() != "TRUSTED"
            or bool(row["is_partial"])
            for row in rows
        ),
        event_anomalies=tuple(f"{key}={value}" for key, value in sorted(anomalies.items())),
        unresolved_gaps=0,
        minute_rows_inserted=minute_inserted,
        minute_rows_identical=minute_identical,
        minute_conflicts=0,
        daily_rows_inserted=daily_outcome == "INSERT",
        daily_rows_existing=daily_outcome == "EXISTING",
        daily_conflicts=0,
        ato_proven_inserted=ato_inserted,
        ato_proven_existing=ato_existing,
        ato_conflicts=0,
        atc_proven_inserted=atc_inserted,
        atc_proven_superseded=atc_superseded,
        atc_proven_existing=atc_existing,
        atc_conflicts=0,
    )


def _sum(results: Iterable[SymbolFinalizeResult], field: str) -> int:
    return sum(int(getattr(result, field)) for result in results)


def _build_result(
    *,
    trading_date: str,
    dry_run: bool,
    started_at: str,
    finalized_at: str,
    audit: DayAudit,
    symbols: tuple[SymbolFinalizeResult, ...],
) -> FinalizeResult:
    trusted = sum(result.status == "TRUSTED" for result in symbols)
    blocked = sum(result.status == "BLOCKED" for result in symbols)
    unavailable = sum(result.status == "UNAVAILABLE" for result in symbols)
    proven_unavailable = sum(
        result.status == "UNAVAILABLE" and result.reasons == ("PROVIDER_NO_DATA",)
        for result in symbols
    )
    canonical_conflicts = sum(
        _sum(symbols, field)
        for field in ("minute_conflicts", "daily_conflicts", "ato_conflicts", "atc_conflicts")
    )
    if canonical_conflicts:
        status = "BLOCKED"
    elif trusted + proven_unavailable == len(symbols) and symbols:
        status = "DRY_RUN_PASS" if dry_run else "PASS"
    elif trusted:
        status = "PARTIAL"
    else:
        status = "BLOCKED"
    return FinalizeResult(
        trading_date=trading_date,
        mode="DRY_RUN" if dry_run else "WRITE",
        status=status,
        started_at=started_at,
        finalized_at=finalized_at,
        source_rows=audit.rows,
        source_symbols=audit.symbols,
        symbols_attempted=len(symbols),
        symbols_trusted=trusted,
        symbols_blocked=blocked,
        symbols_unavailable=unavailable,
        minute_rows_inserted=_sum(symbols, "minute_rows_inserted"),
        minute_rows_identical=_sum(symbols, "minute_rows_identical"),
        minute_conflicts=_sum(symbols, "minute_conflicts"),
        daily_rows_inserted=_sum(symbols, "daily_rows_inserted"),
        daily_rows_existing=_sum(symbols, "daily_rows_existing"),
        daily_conflicts=_sum(symbols, "daily_conflicts"),
        ato_proven_inserted=_sum(symbols, "ato_proven_inserted"),
        ato_proven_existing=_sum(symbols, "ato_proven_existing"),
        ato_conflicts=_sum(symbols, "ato_conflicts"),
        atc_proven_inserted=_sum(symbols, "atc_proven_inserted"),
        atc_proven_superseded=_sum(symbols, "atc_proven_superseded"),
        atc_proven_existing=_sum(symbols, "atc_proven_existing"),
        atc_conflicts=_sum(symbols, "atc_conflicts"),
        event_anomaly_rows=audit.event_anomaly_rows,
        settled_reconciliations=trusted,
        volume_mismatches=sum("VOLUME_MISMATCH" in result.reasons for result in symbols),
        missing_daily_ohlc=sum("DAILY_MISSING" in result.reasons for result in symbols),
        unresolved_gaps=audit.unresolved_gap_rows,
        symbols=symbols,
    )


def _record_result(connection: sqlite3.Connection, result: FinalizeResult) -> None:
    columns = [
        "trading_date", "mode", "status", "started_at", "finalized_at",
        "source_rows", "source_symbols", "symbols_attempted", "symbols_trusted",
        "symbols_blocked", "symbols_unavailable", "minute_rows_inserted",
        "minute_rows_identical", "minute_conflicts", "daily_rows_inserted",
        "daily_rows_existing", "daily_conflicts", "ato_proven_inserted",
        "ato_proven_existing", "ato_conflicts", "atc_proven_inserted",
        "atc_proven_superseded", "atc_proven_existing", "atc_conflicts",
        "event_anomaly_rows", "settled_reconciliations", "volume_mismatches",
        "missing_daily_ohlc", "unresolved_gaps", "details_json",
    ]
    payload = asdict(result)
    values = [
        json.dumps(payload["symbols"], sort_keys=True)
        if name == "details_json"
        else payload[name]
        for name in columns
    ]
    existing_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA history.table_info(daily_finalize_runs)")
    }
    legacy_values = {
        "inserted_rows": result.minute_rows_inserted,
        "history_rows": int(
            connection.execute(
                "SELECT COUNT(*) FROM history.minute_bars WHERE trading_date=?",
                (result.trading_date,),
            ).fetchone()[0]
        ),
        "symbols": result.source_symbols,
        "minutes": int(
            connection.execute(
                "SELECT COUNT(DISTINCT minute) FROM history.minute_bars "
                "WHERE trading_date=?",
                (result.trading_date,),
            ).fetchone()[0]
        ),
        "partial_rows": result.event_anomaly_rows,
        "gap_rows": result.unresolved_gaps,
        "invalid_ohlc_rows": sum(
            "INVALID_OHLCV" in symbol.reasons for symbol in result.symbols
        ),
        "quality_json": json.dumps(
            dict(Counter(symbol.status for symbol in result.symbols)),
            sort_keys=True,
        ),
    }
    for name, value in legacy_values.items():
        if name in existing_columns:
            columns.append(name)
            values.append(value)
    updates = ", ".join(
        f"{name}=excluded.{name}" for name in columns if name != "trading_date"
    )
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            f"""
            INSERT INTO history.daily_finalize_runs ({', '.join(columns)})
            VALUES ({', '.join('?' for _ in columns)})
            ON CONFLICT(trading_date) DO UPDATE SET {updates}
            """,
            tuple(values),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def repair_plan_from_details(
    details: object,
    *,
    status: str,
    maximum_symbols: int = MAX_TARGETED_REPAIR_SYMBOLS,
) -> RepairPlan:
    """Return a bounded symbol repair set or an explicit fail-closed reason."""
    canonical_status = str(status or "").strip().upper()
    if canonical_status not in {"PARTIAL", "BLOCKED", "REST_BLOCKED"}:
        return RepairPlan(False, (), f"STATUS_NOT_REPAIRABLE:{canonical_status or 'EMPTY'}")
    if not isinstance(details, list):
        return RepairPlan(False, (), "MISSING_SYMBOL_DETAILS")

    symbol_results = [
        item
        for item in details
        if isinstance(item, dict) and str(item.get("symbol") or "").strip()
    ]
    if not symbol_results:
        return RepairPlan(False, (), "MISSING_SYMBOL_DETAILS")
    if any(
        any(str(reason).startswith("STREAM_") for reason in item.get("reasons") or ())
        for item in symbol_results
    ):
        return RepairPlan(False, (), "GLOBAL_STREAM_COVERAGE_FAILURE")

    targets = tuple(
        sorted(
            {
                str(item["symbol"]).strip().upper()
                for item in symbol_results
                if str(item.get("status") or "").strip().upper() != "TRUSTED"
            }
        )
    )
    if not targets:
        return RepairPlan(False, (), "NO_NON_TRUSTED_SYMBOLS")
    if len(targets) > maximum_symbols:
        return RepairPlan(
            False,
            (),
            f"REPAIR_SET_TOO_LARGE:{len(targets)}>{maximum_symbols}",
        )
    return RepairPlan(True, targets, "TARGETED_REPAIR")


def rest_repair_status(
    *,
    prior_status: str,
    checkpoints_complete: bool,
    canonical_complete: bool,
) -> str:
    """REST repair passes only when checkpoints and canonical outputs are complete."""
    if checkpoints_complete and canonical_complete:
        return "REST_PASS"
    canonical_prior = str(prior_status or "").strip().upper()
    return canonical_prior if canonical_prior in {"PARTIAL", "BLOCKED"} else "REST_BLOCKED"


def _journal_symbol_states(
    history: sqlite3.Connection, trading_date: str
) -> tuple[set[str], set[str], set[str]]:
    if not _table_exists(history, "daily_finalize_runs"):
        return set(), set(), set()
    columns = {
        str(row["name"])
        for row in history.execute("PRAGMA table_info(daily_finalize_runs)")
    }
    selected = ["details_json"]
    selected.extend(name for name in ("status", "mode") if name in columns)
    row = history.execute(
        f"SELECT {', '.join(selected)} FROM daily_finalize_runs WHERE trading_date=?",
        (trading_date,),
    ).fetchone()
    if row is None:
        return set(), set(), set()
    try:
        details = json.loads(str(row["details_json"] or ""))
    except (TypeError, ValueError):
        return set(), set(), set()
    if not isinstance(details, list):
        return set(), set(), set()
    successful_write = (
        "status" in columns
        and "mode" in columns
        and str(row["status"] or "").strip().upper() == "PASS"
        and str(row["mode"] or "").strip().upper() == "WRITE"
    )
    journal_symbols: set[str] = set()
    trusted_symbols: set[str] = set()
    provider_unavailable: set[str] = set()
    for item in details:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        journal_symbols.add(symbol)
        if (
            str(item.get("status") or "").strip().upper() == "TRUSTED"
            and not item.get("reasons")
        ):
            trusted_symbols.add(symbol)
        reasons = item.get("reasons")
        if (
            successful_write
            and str(item.get("status") or "").strip().upper() == "UNAVAILABLE"
            and isinstance(reasons, list)
            and tuple(str(reason).strip().upper() for reason in reasons)
            == ("PROVIDER_NO_DATA",)
        ):
            provider_unavailable.add(symbol)
    return journal_symbols, trusted_symbols, provider_unavailable


def _safe_canonical_history_row(
    row: sqlite3.Row, *, exchange: str, valid_minutes: set[str]
) -> bool:
    try:
        return (
            str(row["data_source"] or "").strip().upper()
            in CANONICAL_MINUTE_SOURCES
            and str(row["quality_status"] or "").strip().upper()
            == TRUSTED_QUALITY
            and not bool(row["is_partial"])
            and not bool(row["has_gap"])
            and str(row["minute"] or "") in valid_minutes
            and normalize_exchange(str(row["exchange"] or "")) == exchange
            and _valid_ohlcv(row)
        )
    except (TypeError, ValueError):
        return False


def _minute_core(row: sqlite3.Row) -> tuple[object, ...]:
    return (
        str(row["minute"]),
        normalize_exchange(str(row["exchange"] or "")),
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        int(row["volume"]),
    )


def canonical_day_completeness(
    *,
    source_path: Path,
    history_path: Path,
    market_path: Path,
    trading_date: str,
) -> CanonicalDayCompleteness:
    """Prove that every observed day symbol has safe minute and daily outputs."""
    target = date.fromisoformat(trading_date)
    if target.isoformat() != trading_date:
        raise ValueError("trading_date must be canonical YYYY-MM-DD")
    source = _connect_existing(source_path, read_only=True)
    history = _connect_existing(history_path, read_only=True)
    market = _connect_existing(market_path, read_only=True)
    try:
        source_symbols = (
            {
                str(row[0]).strip().upper()
                for row in source.execute(
                    "SELECT DISTINCT symbol FROM minute_bars WHERE trading_date=?",
                    (trading_date,),
                )
                if str(row[0] or "").strip()
            }
            if _table_exists(source, "minute_bars")
            else set()
        )
        history_symbols = (
            {
                str(row[0]).strip().upper()
                for row in history.execute(
                    "SELECT DISTINCT symbol FROM minute_bars WHERE trading_date=?",
                    (trading_date,),
                )
                if str(row[0] or "").strip()
            }
            if _table_exists(history, "minute_bars")
            else set()
        )
        daily_symbols = (
            {
                str(row[0]).strip().upper()
                for row in market.execute(
                    "SELECT DISTINCT symbol FROM daily_bars WHERE trading_date=?",
                    (trading_date,),
                )
                if str(row[0] or "").strip()
            }
            if _table_exists(market, "daily_bars")
            else set()
        )
        (
            journal_symbols,
            trusted_journal_symbols,
            journal_provider_unavailable,
        ) = _journal_symbol_states(history, trading_date)
        checkpoint_pairs = _eod_checkpoint_pairs(source, trading_date)
        expected = tuple(
            sorted(
                source_symbols
                | history_symbols
                | daily_symbols
                | journal_symbols
                | set(checkpoint_pairs)
            )
        )
        complete_symbols: list[str] = []
        provider_unavailable: list[str] = []
        missing_daily: list[str] = []
        missing_history: list[str] = []
        unsafe_daily: list[str] = []
        unsafe_history: list[str] = []
        volume_mismatches: list[str] = []
        unfinalized_stream: list[str] = []
        unsafe_stream_source: list[str] = []

        for symbol in expected:
            checkpoint_pair = checkpoint_pairs.get(symbol)
            explicit_provider_unavailable = checkpoint_pair == (
                "NO_DATA",
                "NO_DATA",
            )
            durable_provider_unavailable = (
                checkpoint_pair is None and symbol in journal_provider_unavailable
            )
            if explicit_provider_unavailable or durable_provider_unavailable:
                if symbol in (source_symbols | history_symbols | daily_symbols):
                    unsafe_history.append(symbol)
                else:
                    provider_unavailable.append(symbol)
                continue
            if symbol in journal_provider_unavailable:
                unsafe_history.append(symbol)
                continue
            if checkpoint_pair is not None and checkpoint_pair not in {
                ("COMPLETED", "COMPLETED"),
                ("NO_DATA", "COMPLETED"),
            }:
                unsafe_history.append(symbol)
                continue
            if checkpoint_pair == ("NO_DATA", "COMPLETED") and symbol in (
                source_symbols | history_symbols
            ):
                unsafe_history.append(symbol)
                continue

            daily_row = (
                market.execute(
                    """
                    SELECT exchange, open, high, low, close, volume,
                           source, quality_status
                    FROM daily_bars WHERE symbol=? AND trading_date=?
                    """,
                    (symbol, trading_date),
                ).fetchone()
                if _table_exists(market, "daily_bars")
                else None
            )
            if daily_row is None:
                missing_daily.append(symbol)
                continue
            try:
                exchange = normalize_exchange(str(daily_row["exchange"] or ""))
                daily_volume = int(daily_row["volume"])
                daily_source = str(daily_row["source"] or "").strip().upper()
                if (
                    not _valid_ohlcv(daily_row)
                    or daily_source != DAILY_SOURCE
                    or str(daily_row["quality_status"] or "").strip().upper()
                    != TRUSTED_QUALITY
                ):
                    raise ValueError
            except (TypeError, ValueError):
                unsafe_daily.append(symbol)
                continue

            if checkpoint_pair == ("NO_DATA", "COMPLETED") and daily_volume != 0:
                volume_mismatches.append(symbol)
                continue

            rows = (
                history.execute(
                    f"""
                    SELECT {', '.join(MINUTE_COLUMNS)}
                    FROM minute_bars WHERE symbol=? AND trading_date=?
                    ORDER BY minute
                    """,
                    (symbol, trading_date),
                ).fetchall()
                if _table_exists(history, "minute_bars")
                else []
            )
            if not rows:
                if daily_volume == 0 and checkpoint_pair != (
                    "COMPLETED",
                    "COMPLETED",
                ):
                    complete_symbols.append(symbol)
                    continue
                missing_history.append(symbol)
                continue
            valid_minutes = {point.minute for point in volume_market_grid(exchange)}
            if any(
                not _safe_canonical_history_row(
                    row, exchange=exchange, valid_minutes=valid_minutes
                )
                for row in rows
            ):
                unsafe_history.append(symbol)
                continue
            if sum(int(row["volume"]) for row in rows) != daily_volume:
                volume_mismatches.append(symbol)
                continue
            complete_symbols.append(symbol)

        complete = bool(expected) and (
            len(complete_symbols) + len(provider_unavailable) == len(expected)
        )
        return CanonicalDayCompleteness(
            complete=complete,
            expected_symbols=expected,
            complete_symbols=tuple(complete_symbols),
            provider_unavailable=tuple(provider_unavailable),
            missing_daily_bars=tuple(missing_daily),
            missing_history=tuple(missing_history),
            unsafe_daily_bars=tuple(unsafe_daily),
            unsafe_history=tuple(unsafe_history),
            volume_mismatches=tuple(volume_mismatches),
            unfinalized_stream=tuple(unfinalized_stream),
            unsafe_stream_source=tuple(unsafe_stream_source),
        )
    finally:
        source.close()
        history.close()
        market.close()


def finalize_day(
    *,
    source_path: Path,
    history_path: Path,
    market_path: Path,
    trading_date: str,
    daily_bars: Iterable[DailyBar],
    dry_run: bool = True,
    now: datetime | None = None,
    auction_source_path: Path | None = None,
    _allowed_daily_sources: frozenset[str] = frozenset({DAILY_SOURCE}),
    _day_block_reasons: tuple[str, ...] = (),
) -> FinalizeResult:
    """Settle one completed day, using one atomic transaction per symbol."""
    target = date.fromisoformat(trading_date)
    if target.isoformat() != trading_date:
        raise ValueError("trading_date must be canonical YYYY-MM-DD")
    resolved = [Path(value).resolve() for value in (source_path, history_path, market_path)]
    if len(set(resolved)) != 3:
        raise ValueError("source, yearly history, and market paths must be distinct")
    for path in resolved:
        if not path.is_file():
            raise FileNotFoundError(f"Required SQLite database does not exist: {path}")
    resolved_auction = Path(auction_source_path or source_path).resolve()
    if not resolved_auction.is_file():
        raise FileNotFoundError(
            f"Required auction evidence database does not exist: {resolved_auction}"
        )

    moment = now or datetime.now(VN_TZ)
    started_at = canonical_timestamp(moment)
    canonical_daily = _canonical_daily_bars(
        daily_bars, trading_date, allowed_sources=_allowed_daily_sources
    )
    source = _connect_existing(resolved[0], read_only=True)
    auction_source = _connect_existing(resolved_auction, read_only=True)
    connection = _connect_existing(resolved[2])
    try:
        if not dry_run:
            ensure_market_storage_schema(connection, applied_at=moment)
        elif not _table_exists(connection, "daily_bars") or not _table_exists(
            connection, "auction_session_history"
        ):
            raise ValueError("Dry-run market database lacks canonical V2 schema")
        connection.execute("ATTACH DATABASE ? AS history", (str(resolved[1]),))
        if not _table_exists(connection, "minute_bars", "history"):
            raise ValueError("Yearly history database has no minute_bars table")
        if not dry_run:
            ensure_finalize_schema(connection, schema="history")
            connection.commit()
        else:
            connection.execute("PRAGMA query_only=ON")

        rows_by_symbol = _load_source_rows(source, trading_date)
        audit = audit_day(rows_by_symbol, trading_date)
        checkpoint_pairs = _eod_checkpoint_pairs(source, trading_date)
        universe = sorted(
            set(rows_by_symbol) | set(canonical_daily) | set(checkpoint_pairs)
        )
        symbol_results: list[SymbolFinalizeResult] = []
        for symbol in universe:
            rows = rows_by_symbol.get(symbol, [])
            daily_bar = canonical_daily.get(symbol)
            if _day_block_reasons:
                symbol_results.append(
                    _empty_symbol_result(
                        symbol,
                        "BLOCKED",
                        _day_block_reasons,
                        rows,
                        daily_bar.volume if daily_bar is not None else None,
                    )
                )
                continue
            pair = checkpoint_pairs.get(symbol)
            intraday_no_data = False
            if pair is not None:
                intraday_status, daily_status = pair
                valid_statuses = {"COMPLETED", "NO_DATA"}
                if (
                    intraday_status not in valid_statuses
                    or daily_status not in valid_statuses
                ):
                    reason = (
                        "CHECKPOINT_FAILED"
                        if "FAILED" in pair
                        else "CHECKPOINT_INCOMPLETE"
                    )
                    symbol_results.append(
                        _empty_symbol_result(
                            symbol,
                            "BLOCKED",
                            (reason,),
                            rows,
                            daily_bar.volume if daily_bar is not None else None,
                        )
                    )
                    continue
                if intraday_status == "NO_DATA" and daily_status == "NO_DATA":
                    if rows or daily_bar is not None:
                        symbol_results.append(
                            _empty_symbol_result(
                                symbol,
                                "BLOCKED",
                                ("CHECKPOINT_DATA_CONFLICT",),
                                rows,
                                daily_bar.volume if daily_bar is not None else None,
                            )
                        )
                    else:
                        symbol_results.append(
                            _empty_symbol_result(
                                symbol,
                                "UNAVAILABLE",
                                ("PROVIDER_NO_DATA",),
                                rows,
                                None,
                            )
                        )
                    continue
                if daily_status == "NO_DATA":
                    symbol_results.append(
                        _empty_symbol_result(
                            symbol,
                            "BLOCKED",
                            ("DAILY_NO_DATA_WITH_INTRADAY",),
                            rows,
                            daily_bar.volume if daily_bar is not None else None,
                        )
                    )
                    continue
                if daily_bar is None:
                    symbol_results.append(
                        _empty_symbol_result(
                            symbol,
                            "BLOCKED",
                            ("DAILY_CHECKPOINT_PAYLOAD_MISSING",),
                            rows,
                            None,
                        )
                    )
                    continue
                if intraday_status == "NO_DATA":
                    if rows:
                        symbol_results.append(
                            _empty_symbol_result(
                                symbol,
                                "BLOCKED",
                                ("CHECKPOINT_DATA_CONFLICT",),
                                rows,
                                daily_bar.volume,
                            )
                        )
                        continue
                    intraday_no_data = True
                elif not rows:
                    symbol_results.append(
                        _empty_symbol_result(
                            symbol,
                            "BLOCKED",
                            ("SOURCE_MISSING",),
                            rows,
                            daily_bar.volume,
                        )
                    )
                    continue
            try:
                symbol_results.append(
                    _settle_symbol(
                        connection,
                        source,
                        symbol=symbol,
                        trading_date=trading_date,
                        rows=rows,
                        daily_bar=daily_bar,
                        recorded_at=started_at,
                        dry_run=dry_run,
                        auction_source=auction_source,
                        intraday_no_data=intraday_no_data,
                    )
                )
            except Exception as exc:
                connection.rollback()
                symbol_results.append(
                    _empty_symbol_result(
                        symbol,
                        "BLOCKED",
                        (f"WRITE_FAILURE:{type(exc).__name__}",),
                        rows,
                        daily_bar.volume if daily_bar is not None else None,
                    )
                )
        result = _build_result(
            trading_date=trading_date,
            dry_run=dry_run,
            started_at=started_at,
            finalized_at=canonical_timestamp(moment),
            audit=audit,
            symbols=tuple(symbol_results),
        )
        if not dry_run:
            _record_result(connection, result)
        return result
    finally:
        source.close()
        auction_source.close()
        connection.close()


def finalize_stream_day(
    *,
    source_path: Path,
    history_path: Path,
    market_path: Path,
    trading_date: str,
    dry_run: bool = True,
    now: datetime | None = None,
    minimum_symbols: int = MIN_STREAM_SYMBOLS,
    minimum_minutes: int = MIN_STREAM_MINUTES,
) -> FinalizeResult:
    """The superseded stream-primary path is intentionally fail-closed."""
    raise RuntimeError(
        "stream-primary EOD is disabled; use SSI REST IntradayOhlc + DailyOhlc"
    )


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def _load_daily_json(path: Path, trading_date: str) -> tuple[DailyBar, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("dataList") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("daily input must be a list or official dataList envelope")
    cutoff = date.fromisoformat(trading_date) + timedelta(days=1)
    bars: list[DailyBar] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("daily input contains a non-object row")
        bar = normalize_daily_ohlc_record(record, as_of_date=cutoff)
        if bar is None or bar.trading_date != trading_date:
            raise ValueError("daily input contains an invalid or out-of-scope row")
        bars.append(bar)
    return tuple(bars)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run-first SSI EOD canonical finalizer")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--market", type=Path, required=True)
    parser.add_argument("--auction-source", type=Path, required=True)
    parser.add_argument("--daily-json", type=Path, required=True)
    parser.add_argument("--date", type=_parse_date, required=True)
    parser.add_argument("--write", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now = datetime.now(VN_TZ)
    if args.write and args.date == now.date() and now.timetz().replace(tzinfo=None) < SAFE_AFTER:
        raise SystemExit(
            f"Refusing to finalize {args.date.isoformat()} before "
            f"{SAFE_AFTER.strftime('%H:%M')} VN"
        )
    kwargs = {
        "source_path": args.source,
        "history_path": args.history,
        "market_path": args.market,
        "trading_date": args.date.isoformat(),
        "dry_run": not args.write,
        "now": now,
        "auction_source_path": args.auction_source,
    }
    result = finalize_day(
        **kwargs,
        daily_bars=_load_daily_json(args.daily_json, args.date.isoformat()),
    )
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
    successful = {"PASS", "DRY_RUN_PASS"}
    return 0 if result.status in successful else 2


if __name__ == "__main__":
    raise SystemExit(main())
