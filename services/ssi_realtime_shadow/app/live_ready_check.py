"""No-network local readiness audit for the CCC V2 live-state runtime."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .auction_history import read_atc_exact10, read_ato_exact10
from .daily_ma import calculate_moving_averages_from_db
from .market_storage_schema import STORAGE_SCHEMA_VERSION
from .settings import ROOT
from .signal_config import load_signal_config
from .realtime_volume import load_volume_baseline
from .volume_baseline import COVERAGE_PROOF, load_candidate_market_sessions


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _quick_check(connection: sqlite3.Connection) -> str:
    row = connection.execute("PRAGMA quick_check").fetchone()
    return str(row[0]) if row is not None else "missing"


def _schema_version(connection: sqlite3.Connection) -> int | None:
    if "engine_meta" not in _tables(connection):
        return None
    row = connection.execute(
        "SELECT value FROM engine_meta WHERE key='storage_schema'"
    ).fetchone()
    try:
        return int(row[0]) if row is not None else None
    except (TypeError, ValueError):
        return None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table})")
    }


def _symbols(connection: sqlite3.Connection, target: str) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT symbol FROM daily_bars "
            "WHERE trading_date < ? ORDER BY symbol",
            (target,),
        )
    ]


def inspect_live_readiness(
    *,
    target_trading_date: str,
    hot_db: Path,
    market_db: Path,
    history_db: Path,
    baseline_db: Path,
) -> dict[str, Any]:
    parsed = date.fromisoformat(target_trading_date)
    if parsed.isoformat() != target_trading_date:
        raise ValueError("target trading date must be canonical YYYY-MM-DD")
    result: dict[str, Any] = {
        "target_trading_date": target_trading_date,
        "configured_paths": {
            "hot": str(hot_db.resolve()),
            "market": str(market_db.resolve()),
            "history": str(history_db.resolve()),
            "baseline": str(baseline_db.resolve()),
        },
        "db_quick_check": {},
        "active_trading_date": None,
        "signal_config_ok": False,
        "contract_version": None,
        "config_version": None,
        "engine_version": None,
        "hot_db_exists": hot_db.is_file(),
        "hot_schema_ok": False,
        "market_db_exists": market_db.is_file(),
        "market_schema_version": None,
        "history_db_exists": history_db.is_file(),
        "history_min_date": None,
        "history_max_date": None,
        "baseline_exists": baseline_db.is_file(),
        "baseline_schema_version": None,
        "baseline_lookback": None,
        "baseline_coverage_proof": None,
        "baseline_as_of_date": None,
        "baseline_date_matches_target": False,
        "baseline_symbols_total": 0,
        "baseline_symbols_exact10": 0,
        "baseline_symbols_partial": 0,
        "daily_symbols_total": 0,
        "ma10_ready_symbols": 0,
        "ma200_ready_symbols": 0,
        "auction_ato_exact10_symbols": 0,
        "auction_atc_exact10_symbols": 0,
        "live_metrics_total": 0,
        "live_metrics_trusted": 0,
        "live_metrics_untrusted": 0,
        "auction_bucket_coverage": {},
        "latest_eod_status": None,
        "latest_eod_date": None,
        "next_session_baseline_ready": False,
        "blocking_errors": [],
        "warnings": [],
        "ready_for_live_signal": False,
    }
    blocking: list[str] = result["blocking_errors"]
    warnings: list[str] = result["warnings"]

    try:
        config = load_signal_config()
        result.update(
            signal_config_ok=True,
            contract_version=config.contract_version,
            config_version=config.config_version,
            engine_version=config.engine_version,
        )
    except Exception as exc:
        blocking.append(f"SIGNAL_CONFIG_INVALID:{type(exc).__name__}")

    if hot_db.is_file():
        try:
            hot = _readonly(hot_db)
            try:
                result["db_quick_check"]["hot"] = _quick_check(hot)
                if result["db_quick_check"]["hot"] != "ok":
                    blocking.append("HOT_DB_QUICK_CHECK_FAILED")
                required_tables = {
                    "minute_bars", "latest_quotes", "auction_session_buckets"
                }
                result["hot_schema_ok"] = (
                    required_tables <= _tables(hot)
                    and {
                        "trading_date", "minute", "symbol", "volume",
                        "last_total_volume", "exchange", "quality_status",
                        "is_partial", "has_gap",
                    } <= _columns(hot, "minute_bars")
                    and {
                        "symbol", "trading_date", "event_time", "last_price",
                        "exchange", "updated_at",
                    } <= _columns(hot, "latest_quotes")
                )
                if result["hot_schema_ok"]:
                    row = hot.execute(
                        """
                        SELECT MAX(trading_date) FROM (
                            SELECT trading_date FROM minute_bars
                            UNION ALL
                            SELECT trading_date FROM latest_quotes
                        )
                        """
                    ).fetchone()
                    result["active_trading_date"] = row[0] if row else None
                    coverage: dict[str, dict[str, int]] = {}
                    for bucket in hot.execute(
                        """
                        SELECT auction_type, quality_status, COUNT(*)
                        FROM auction_session_buckets
                        WHERE trading_date=(SELECT MAX(trading_date) FROM auction_session_buckets)
                        GROUP BY auction_type, quality_status
                        """
                    ):
                        coverage.setdefault(str(bucket[0]), {})[str(bucket[1])] = int(
                            bucket[2]
                        )
                    result["auction_bucket_coverage"] = coverage
            finally:
                hot.close()
            if not result["hot_schema_ok"]:
                blocking.append("HOT_SCHEMA_INVALID")
        except Exception as exc:
            blocking.append(f"HOT_DB_UNREADABLE:{type(exc).__name__}")
    else:
        blocking.append("HOT_DB_MISSING")

    market: sqlite3.Connection | None = None
    symbols: list[str] = []
    if market_db.is_file():
        try:
            market = _readonly(market_db)
            result["db_quick_check"]["market"] = _quick_check(market)
            if result["db_quick_check"]["market"] != "ok":
                blocking.append("MARKET_DB_QUICK_CHECK_FAILED")
            result["market_schema_version"] = _schema_version(market)
            if result["market_schema_version"] != STORAGE_SCHEMA_VERSION:
                blocking.append("MARKET_SCHEMA_VERSION_MISMATCH")
            if "daily_bars" in _tables(market):
                symbols = _symbols(market, target_trading_date)
                result["daily_symbols_total"] = len(symbols)
                for symbol in symbols:
                    ma = calculate_moving_averages_from_db(
                        market, symbol=symbol, as_of_date=target_trading_date
                    )
                    result["ma10_ready_symbols"] += int(ma.ma10 is not None)
                    result["ma200_ready_symbols"] += int(ma.ma200 is not None)
            else:
                blocking.append("MARKET_DAILY_BARS_MISSING")
            if "stock_state_current" in _tables(market):
                row = market.execute(
                    """
                    SELECT COUNT(*),
                           COALESCE(SUM(CASE WHEN metrics_trusted=1 THEN 1 ELSE 0 END),0)
                    FROM stock_state_current
                    """
                ).fetchone()
                total = int(row[0]) if row else 0
                trusted = int(row[1]) if row else 0
                result["live_metrics_total"] = total
                result["live_metrics_trusted"] = trusted
                result["live_metrics_untrusted"] = total - trusted
                if total and not trusted:
                    blocking.append("LIVE_METRICS_ALL_UNTRUSTED")
        except sqlite3.Error as exc:
            blocking.append(f"MARKET_DB_UNREADABLE:{type(exc).__name__}")
            if market is not None:
                market.close()
                market = None
    else:
        blocking.append("MARKET_DB_MISSING")

    history: sqlite3.Connection | None = None
    if history_db.is_file():
        try:
            history = _readonly(history_db)
            result["db_quick_check"]["history"] = _quick_check(history)
            if result["db_quick_check"]["history"] != "ok":
                blocking.append("HISTORY_DB_QUICK_CHECK_FAILED")
            if "minute_bars" not in _tables(history):
                warnings.append("HISTORY_MINUTE_BARS_MISSING")
            else:
                row = history.execute(
                    "SELECT MIN(trading_date), MAX(trading_date) FROM minute_bars"
                ).fetchone()
                result["history_min_date"] = row[0] if row else None
                result["history_max_date"] = row[1] if row else None
                if result["history_min_date"] is None:
                    warnings.append("HISTORY_EMPTY:auction_metrics_unavailable")
            if "daily_finalize_runs" in _tables(history):
                row = history.execute(
                    """
                    SELECT trading_date, status FROM daily_finalize_runs
                    ORDER BY trading_date DESC LIMIT 1
                    """
                ).fetchone()
                if row is not None:
                    result["latest_eod_date"] = str(row[0])
                    result["latest_eod_status"] = str(row[1])
                    if str(row[1]).upper() not in {"PASS", "REST_PASS"}:
                        blocking.append("LATEST_EOD_NOT_PASS")
        except sqlite3.Error as exc:
            blocking.append(f"HISTORY_DB_UNREADABLE:{type(exc).__name__}")
            if history is not None:
                history.close()
                history = None
    else:
        blocking.append("HISTORY_DB_MISSING")
        warnings.append("HISTORY_DB_MISSING:auction_metrics_unavailable")

    if baseline_db.is_file():
        try:
            baseline_connection = _readonly(baseline_db)
            try:
                result["db_quick_check"]["baseline"] = _quick_check(
                    baseline_connection
                )
            finally:
                baseline_connection.close()
            if result["db_quick_check"]["baseline"] != "ok":
                blocking.append("BASELINE_DB_QUICK_CHECK_FAILED")
            baseline = load_volume_baseline(baseline_db)
            exact = sum(
                item.usable
                and item.baseline_sessions_used == 10
                and item.active_sessions_used >= item.baseline_sessions_used
                for item in baseline.coverage.values()
            )
            accepted_9 = sum(
                item.usable
                and item.baseline_sessions_used == 9
                and item.active_sessions_used >= item.baseline_sessions_used
                for item in baseline.coverage.values()
            )
            accepted_8 = sum(
                item.usable
                and item.baseline_sessions_used == 8
                and item.active_sessions_used >= item.baseline_sessions_used
                for item in baseline.coverage.values()
            )
            usable = exact + accepted_9 + accepted_8
            unusable = len(baseline.coverage) - usable
            partial = sum(
                0 < item.baseline_sessions_used < 10
                or 0 < item.active_sessions_used < 10
                for item in baseline.coverage.values()
            )
            result.update(
                baseline_schema_version=baseline.schema_version,
                baseline_lookback=baseline.lookback,
                baseline_coverage_proof=baseline.coverage_proof,
                baseline_as_of_date=baseline.as_of_date,
                baseline_date_matches_target=(
                    baseline.as_of_date == target_trading_date
                ),
                baseline_symbols_total=len(baseline.coverage),
                baseline_symbols_exact10=exact,
                baseline_symbols_accepted9=accepted_9,
                baseline_symbols_accepted8=accepted_8,
                baseline_symbols_usable=usable,
                baseline_symbols_unusable=unusable,
                baseline_symbols_partial=partial,
            )
            if baseline.schema_version != 2:
                blocking.append("BASELINE_SCHEMA_VERSION_MISMATCH")
            if baseline.lookback != 10:
                blocking.append("BASELINE_LOOKBACK_MISMATCH")
            if baseline.coverage_proof != COVERAGE_PROOF:
                blocking.append("BASELINE_COVERAGE_PROOF_MISMATCH")
            if baseline.as_of_date != target_trading_date:
                blocking.append("BASELINE_DATE_MISMATCH")
            if usable == 0:
                blocking.append("BASELINE_HAS_NO_USABLE_SYMBOLS")
            if partial:
                warnings.append(f"BASELINE_PARTIAL_SYMBOLS:{partial}")
            result["next_session_baseline_ready"] = bool(
                baseline.as_of_date == target_trading_date and usable > 0
            )
        except Exception as exc:
            blocking.append(f"BASELINE_INVALID:{type(exc).__name__}")
    else:
        blocking.append("BASELINE_MISSING")

    if market is not None and history is not None:
        tables = _tables(market)
        if "auction_session_history" not in tables:
            warnings.append("AUCTION_HISTORY_TABLE_MISSING")
        else:
            try:
                candidate_dates = tuple(
                    load_candidate_market_sessions(
                        history,
                        market,
                        as_of_date=target_trading_date,
                        lookback=10,
                    )
                )
            except (sqlite3.Error, TypeError, ValueError):
                candidate_dates = ()
            for symbol in symbols:
                try:
                    ato = read_ato_exact10(
                        market, history, market,
                        symbol=symbol, as_of_date=target_trading_date,
                        candidate_dates=candidate_dates,
                    )
                    atc = read_atc_exact10(
                        market, history, market,
                        symbol=symbol, as_of_date=target_trading_date,
                        candidate_dates=candidate_dates,
                    )
                    result["auction_ato_exact10_symbols"] += int(
                        ato.baseline_usable and ato.sessions_used == 10
                        and ato.proven_sessions == 10
                    )
                    result["auction_atc_exact10_symbols"] += int(
                        atc.baseline_usable and atc.sessions_used == 10
                    )
                except (sqlite3.Error, TypeError, ValueError):
                    continue
            if result["auction_ato_exact10_symbols"] < len(symbols):
                warnings.append(
                    "ATO_EXACT10_PARTIAL_EXPECTED:no_historical_bootstrap"
                )
            if result["auction_atc_exact10_symbols"] < len(symbols):
                warnings.append("ATC_EXACT10_PARTIAL")

    if history is not None:
        history.close()
    if market is not None:
        market.close()
    result["ready_for_live_signal"] = not blocking
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--hot-db", type=Path, default=os.getenv("DATABASE_PATH"))
    parser.add_argument(
        "--market-db", type=Path, default=os.getenv("MARKET_V2_DATABASE_PATH")
    )
    parser.add_argument(
        "--history-db", type=Path, default=os.getenv("SSI_HISTORY_PATH")
    )
    parser.add_argument(
        "--baseline-db", type=Path, default=os.getenv("VOLUME_BASELINE_PATH")
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    missing = [
        name
        for name, value in (
            ("DATABASE_PATH/--hot-db", args.hot_db),
            ("MARKET_V2_DATABASE_PATH/--market-db", args.market_db),
            ("SSI_HISTORY_PATH/--history-db", args.history_db),
            ("VOLUME_BASELINE_PATH/--baseline-db", args.baseline_db),
        )
        if value is None
    ]
    if missing:
        parser.error("missing explicit database configuration: " + ", ".join(missing))
    report = inspect_live_readiness(
        target_trading_date=args.trading_date,
        hot_db=args.hot_db,
        market_db=args.market_db,
        history_db=args.history_db,
        baseline_db=args.baseline_db,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ready_for_live_signal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
