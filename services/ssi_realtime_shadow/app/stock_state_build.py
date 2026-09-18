"""Offline/local materializer for the CCC V2 ``stock_state_current`` table."""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

from .daily_ma import calculate_moving_averages_from_db
from .market_session import VN_TZ, classify_market_session, normalize_exchange
from .market_storage_schema import ensure_market_storage_schema
from .price_momentum import MinutePrice, calculate_price_momentum
from .realtime_volume import RealtimeVolumeEngine, VolumeEvent
from .stock_state_current import (
    LatestQuote,
    project_stock_state,
    upsert_stock_state_current,
)
from .volume_baseline import COVERAGE_PROOF, prove_replay_volume_session


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SYMBOLS = ("HPG", "SHS", "VGI")


class StockStateBuildError(RuntimeError):
    """Raised when the offline source databases cannot support a safe build."""


def _open_readonly(path: Path) -> sqlite3.Connection:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Database does not exist: {source}")
    connection = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _require_table(connection: sqlite3.Connection, table: str) -> None:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if row is None:
        raise StockStateBuildError(f"Required source table is missing: {table}")


def determine_latest_trading_date(connection: sqlite3.Connection) -> str:
    """Return the latest date present in stored SSI minute bars, never wall clock."""
    _require_table(connection, "minute_bars")
    row = connection.execute(
        "SELECT MAX(trading_date) FROM minute_bars WHERE trading_date IS NOT NULL"
    ).fetchone()
    value = str(row[0] or "").strip() if row else ""
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise StockStateBuildError("No valid stored SSI trading date is available") from exc
    if parsed.isoformat() != value:
        raise StockStateBuildError(f"Stored trading date is not canonical: {value!r}")
    return value


def _event_at(trading_date: str, raw_time: object) -> datetime:
    text = str(raw_time or "").strip()
    if not text:
        raise ValueError("latest quote has no event_time")
    try:
        if "T" in text:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=VN_TZ)
            else:
                parsed = parsed.astimezone(VN_TZ)
        else:
            parsed_time = None
            for pattern in ("%H:%M:%S", "%H:%M:%S.%f", "%H:%M"):
                try:
                    parsed_time = datetime.strptime(text, pattern).time()
                    break
                except ValueError:
                    continue
            if parsed_time is None:
                raise ValueError("invalid quote event_time")
            parsed = datetime.combine(
                date.fromisoformat(trading_date), parsed_time, tzinfo=VN_TZ
            )
    except ValueError as exc:
        raise ValueError(f"invalid quote event_time: {text!r}") from exc
    if parsed.date().isoformat() != trading_date:
        raise ValueError("quote event_time does not match trading_date")
    return parsed


def _finite_float(value: object, *, required: bool = False) -> float | None:
    if value in (None, ""):
        if required:
            raise ValueError("required numeric value is missing")
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("numeric value must be finite")
    return parsed


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed < 0:
        raise ValueError("integer value must not be negative")
    return parsed


def _quote_from_row(row: sqlite3.Row) -> LatestQuote:
    symbol = str(row["symbol"] or "").strip().upper()
    exchange = normalize_exchange(str(row["exchange"] or ""))
    trading_date = str(row["trading_date"] or "").strip()
    event_at = _event_at(trading_date, row["event_time"])
    last_price = _finite_float(row["last_price"], required=True)
    assert last_price is not None
    if last_price <= 0:
        raise ValueError("last_price must be positive")
    updated_at = str(row["updated_at"] or "").strip() or event_at.isoformat()
    return LatestQuote(
        symbol=symbol,
        exchange=exchange,
        trading_date=trading_date,
        event_at=event_at,
        updated_at=updated_at,
        last_price=last_price,
        total_volume=_optional_int(row["total_volume"]),
        ref_price=_finite_float(row["ref_price"]),
        open_price=_finite_float(row["open"]),
        high_price=_finite_float(row["high"]),
        low_price=_finite_float(row["low"]),
        bid_price1=_finite_float(row["bid_price1"]),
        bid_volume1=_optional_int(row["bid_vol1"]),
        ask_price1=_finite_float(row["ask_price1"]),
        ask_volume1=_optional_int(row["ask_vol1"]),
        change_value=_finite_float(row["change"]),
        change_pct=_finite_float(row["ratio_change"]),
    )


def _load_quotes(
    connection: sqlite3.Connection, trading_date: str
) -> tuple[dict[str, LatestQuote], list[dict[str, str]], int, int]:
    _require_table(connection, "latest_quotes")
    rows = connection.execute(
        "SELECT * FROM latest_quotes WHERE trading_date=? ORDER BY symbol",
        (trading_date,),
    ).fetchall()
    quotes: dict[str, LatestQuote] = {}
    skipped: list[dict[str, str]] = []
    valid_exchange_count = 0
    for row in rows:
        symbol = str(row["symbol"] or "").strip().upper() or "<EMPTY>"
        try:
            normalize_exchange(str(row["exchange"] or ""))
            valid_exchange_count += 1
            quote = _quote_from_row(row)
            if not quote.symbol:
                raise ValueError("symbol is empty")
            quotes[quote.symbol] = quote
        except (TypeError, ValueError) as exc:
            skipped.append({"symbol": symbol, "reason": str(exc)})
    return quotes, skipped, valid_exchange_count, len(rows)


def _load_and_replay_minutes(
    connection: sqlite3.Connection,
    *,
    trading_date: str,
    quotes: dict[str, LatestQuote],
    volume_engine: RealtimeVolumeEngine,
) -> tuple[dict[str, list[MinutePrice]], set[str]]:
    rows = connection.execute(
        """
        SELECT trading_date, minute, symbol, close, volume, last_total_volume,
               is_partial, exchange, quality_status, has_gap
        FROM minute_bars
        WHERE trading_date=?
        ORDER BY symbol, minute
        """,
        (trading_date,),
    )
    minute_prices: dict[str, list[MinutePrice]] = defaultdict(list)
    failed: set[str] = set()
    for row in rows:
        symbol = str(row["symbol"] or "").strip().upper()
        if symbol not in quotes or symbol in failed:
            continue
        try:
            row_exchange = str(row["exchange"] or "").strip()
            exchange = normalize_exchange(row_exchange or quotes[symbol].exchange)
            if exchange != quotes[symbol].exchange:
                raise ValueError("minute-bar exchange conflicts with latest quote")
            minute = str(row["minute"] or "").strip()
            close = float(row["close"])
            quality = str(row["quality_status"] or "").strip().upper()
            partial = bool(row["is_partial"])
            gap = bool(row["has_gap"])
            minute_prices[symbol].append(
                MinutePrice(trading_date, minute, close, quality, partial, gap)
            )
            event_time = datetime.combine(
                date.fromisoformat(trading_date),
                datetime.strptime(minute, "%H:%M").time(),
                tzinfo=VN_TZ,
            )
            volume_engine.on_event(
                VolumeEvent(
                    symbol=symbol,
                    exchange=exchange,
                    trading_date=trading_date,
                    event_time=event_time,
                    minute=minute,
                    volume_delta=int(row["volume"]),
                    total_volume=_optional_int(row["last_total_volume"]),
                    quality_status=quality,
                    is_partial=partial,
                    has_gap=gap,
                )
            )
        except (TypeError, ValueError):
            failed.add(symbol)
    completion = datetime.combine(
        date.fromisoformat(trading_date) + timedelta(days=1), time.min, tzinfo=VN_TZ
    )
    volume_engine.advance_time(completion)
    return dict(minute_prices), failed


def _sample(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_symbol = {str(row["symbol"]): row for row in rows}
    fields = (
        "symbol", "exchange", "trading_date", "last_price", "day_rvol",
        "rvol15", "rvol30", "ma10", "ma200", "price5_pct", "price15_pct",
        "baseline_sessions_used", "quality_status", "metrics_trusted",
    )
    return [
        {field: by_symbol[symbol][field] for field in fields}
        for symbol in SAMPLE_SYMBOLS
        if symbol in by_symbol
    ]


def _audit_replay_day(
    source: sqlite3.Connection,
    daily: sqlite3.Connection,
    *,
    trading_date: str,
    universe_symbols: set[str],
    quote_symbols: set[str],
) -> tuple[dict[str, Any], set[str]]:
    counts = source.execute(
        """
        SELECT
          SUM(CASE WHEN quality_status='TRUSTED' THEN 1 ELSE 0 END) AS trusted_rows,
          SUM(CASE WHEN is_partial<>0 THEN 1 ELSE 0 END) AS partial_rows,
          SUM(CASE WHEN has_gap<>0 THEN 1 ELSE 0 END) AS gap_rows,
          SUM(CASE WHEN quality_status<>'TRUSTED' THEN 1 ELSE 0 END) AS nontrusted_rows
        FROM minute_bars WHERE trading_date=?
        """,
        (trading_date,),
    ).fetchone()
    unsafe_symbols = {
        str(row[0]).strip().upper()
        for row in source.execute(
            """
            SELECT DISTINCT symbol FROM minute_bars
            WHERE trading_date=? AND
              (quality_status<>'TRUSTED' OR is_partial<>0 OR has_gap<>0)
            """,
            (trading_date,),
        )
    }
    minute_ranges = [
        {"exchange": str(row[0] or ""), "min_minute": row[1], "max_minute": row[2]}
        for row in source.execute(
            """
            SELECT exchange, MIN(minute), MAX(minute) FROM minute_bars
            WHERE trading_date=? GROUP BY exchange ORDER BY exchange
            """,
            (trading_date,),
        )
    ]
    replay_proven: set[str] = set()
    failures: list[dict[str, Any]] = []
    for symbol in sorted(universe_symbols):
        proof = prove_replay_volume_session(
            source, daily, symbol=symbol, trading_date=trading_date
        )
        if proof.proven:
            replay_proven.add(symbol)
        elif len(failures) < 10:
            failures.append(proof.failure_sample())
    complete = (
        bool(universe_symbols)
        and universe_symbols == quote_symbols
        and replay_proven == universe_symbols
    )
    audit = {
        "latest_stored_trading_date": trading_date,
        "minute_corpus_symbols": len(universe_symbols),
        "latest_quote_symbols": len(quote_symbols),
        "market_minute_ranges": minute_ranges,
        "trusted_rows": int(counts["trusted_rows"] or 0),
        "partial_rows": int(counts["partial_rows"] or 0),
        "gap_rows": int(counts["gap_rows"] or 0),
        "nontrusted_rows": int(counts["nontrusted_rows"] or 0),
        "unsafe_symbols": len(unsafe_symbols),
        "symbols_with_gap_partial_or_nontrusted_rows": len(unsafe_symbols),
        "daily_volume_proven_symbols": len(replay_proven),
        "replay_day_completeness_proven": complete,
        "failure_samples": failures,
    }
    return audit, replay_proven


def build_stock_state_current(
    *, realtime_db: Path, baseline_db: Path, market_db: Path
) -> dict[str, Any]:
    """Materialize the latest stored SSI day into a local V2 current-state DB."""
    resolved = [Path(item).resolve() for item in (realtime_db, baseline_db, market_db)]
    if resolved[2] in resolved[:2]:
        raise StockStateBuildError("market DB must be separate from read-only source DBs")

    source = _open_readonly(resolved[0])
    target: sqlite3.Connection | None = None
    try:
        latest_date = determine_latest_trading_date(source)
        universe_symbols = {
            str(row[0]).strip().upper()
            for row in source.execute(
                "SELECT DISTINCT symbol FROM minute_bars WHERE trading_date=?",
                (latest_date,),
            )
            if str(row[0] or "").strip()
        }
        quotes, skipped, valid_exchange_count, latest_quote_count = _load_quotes(
            source, latest_date
        )

        resolved[2].parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(resolved[2])
        target.row_factory = sqlite3.Row
        ensure_market_storage_schema(target)
        replay_audit, replay_proven_symbols = _audit_replay_day(
            source,
            target,
            trading_date=latest_date,
            universe_symbols=universe_symbols,
            quote_symbols=set(quotes),
        )

        volume_engine = RealtimeVolumeEngine(resolved[1])
        if volume_engine.baseline.lookback != 10:
            raise StockStateBuildError(
                "Volume baseline lookback must be exactly 10 for BETA-01"
            )
        minute_prices, replay_failed = _load_and_replay_minutes(
            source,
            trading_date=latest_date,
            quotes=quotes,
            volume_engine=volume_engine,
        )

        projections: list[dict[str, Any]] = []
        baseline_proven_symbols: set[str] = set()
        for symbol, quote in sorted(quotes.items()):
            try:
                session = classify_market_session(quote.exchange, quote.event_at)
                volume = (
                    None if symbol in replay_failed else volume_engine.get_snapshot(symbol)
                )
                moving_averages = calculate_moving_averages_from_db(
                    target, symbol=symbol, as_of_date=latest_date
                )
                momentum = calculate_price_momentum(
                    exchange=quote.exchange,
                    selected_at=quote.event_at,
                    current_price=quote.last_price,
                    minute_prices=minute_prices.get(symbol, ()),
                )
                baseline_coverage = volume_engine.baseline.coverage.get(symbol)
                baseline_proven = bool(
                    volume_engine.baseline.coverage_proof == COVERAGE_PROOF
                    and volume_engine.baseline.as_of_date == latest_date
                    and baseline_coverage is not None
                    and baseline_coverage.baseline_sessions_used == 10
                    and baseline_coverage.active_sessions_used == 10
                    and symbol in replay_proven_symbols
                    and volume is not None
                    and volume.metrics_trusted
                )
                if baseline_proven:
                    baseline_proven_symbols.add(symbol)
                projections.append(
                    project_stock_state(
                        quote=quote,
                        session=session,
                        volume=volume,
                        moving_averages=moving_averages,
                        price_momentum=momentum,
                        baseline_coverage_proven=baseline_proven,
                    )
                )
            except (TypeError, ValueError) as exc:
                skipped.append({"symbol": symbol, "reason": str(exc)})

        target.execute("BEGIN IMMEDIATE")
        try:
            for projection in projections:
                upsert_stock_state_current(target, projection)
            target.commit()
        except Exception:
            target.rollback()
            raise

        baseline_full = sum(
            row["baseline_sessions_used"] == 10 for row in projections
        )
        baseline_partial = sum(
            0 < row["baseline_sessions_used"] < 10 for row in projections
        )
        no_baseline = sum(row["baseline_sessions_used"] == 0 for row in projections)
        trusted = sum(bool(row["metrics_trusted"]) for row in projections)
        return {
            "latest_trading_date": latest_date,
            "universe_symbols": len(universe_symbols),
            "latest_quote_symbols": latest_quote_count,
            "state_rows_written": len(projections),
            "skipped_symbols": len(skipped),
            "skipped_symbol_details": sorted(
                skipped, key=lambda item: (item["symbol"], item["reason"])
            ),
            "symbols_with_valid_exchange": valid_exchange_count,
            "baseline_10_10_count": baseline_full,
            "partial_baseline_count": baseline_partial,
            "no_baseline_count": no_baseline,
            "ma10_ready_count": sum(row["ma10"] is not None for row in projections),
            "ma200_ready_count": sum(row["ma200"] is not None for row in projections),
            "price5_available_count": sum(
                row["price5_pct"] is not None for row in projections
            ),
            "price15_available_count": sum(
                row["price15_pct"] is not None for row in projections
            ),
            "trusted_state_count": trusted,
            "degraded_unavailable_state_count": len(projections) - trusted,
            "baseline_coverage_proven": bool(projections) and len(
                baseline_proven_symbols
            ) == len(projections),
            "baseline_proven_symbol_count": len(baseline_proven_symbols),
            "replay_day_audit": replay_audit,
            "sample": _sample(projections),
        }
    finally:
        source.close()
        if target is not None:
            target.close()


def _path_from_env(name: str, fallback: str) -> Path:
    return Path(os.environ.get(name, str(SERVICE_ROOT / "data" / fallback))).expanduser()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build local CCC V2 stock_state_current from stored SSI data"
    )
    parser.add_argument(
        "--realtime-db",
        type=Path,
        default=_path_from_env("DATABASE_PATH", "ssi_shadow.db"),
    )
    parser.add_argument(
        "--baseline-db",
        type=Path,
        default=_path_from_env("VOLUME_BASELINE_PATH", "ccc_v2_baseline.db"),
    )
    parser.add_argument(
        "--market-db",
        type=Path,
        default=_path_from_env("MARKET_V2_DATABASE_PATH", "ccc_market_v2.db"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = build_stock_state_current(
        realtime_db=args.realtime_db,
        baseline_db=args.baseline_db,
        market_db=args.market_db,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
