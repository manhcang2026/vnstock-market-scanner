"""Post-close reconciliation for the canonical SSI market store."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Mapping

from .canonical_config import CanonicalMetadataConfig, CanonicalRestConfig
from .canonical_market_store import CanonicalMarketStore
from .clean_rest_bootstrap import AMBIGUOUS_EMPTY_RESPONSE, RestFetcher, run_bootstrap
from .market_session import (
    VN_TZ,
    SessionType,
    classify_market_session,
    market_day_feed_start,
)
from .ssi_historical import SSIHistoricalClient
from .universe import load_exchange_map


EOD_CURRENT_DAY_READY_AT = time(16, 15)


@dataclass(frozen=True, slots=True)
class CanonicalEodResult:
    day: str
    minute_completed: int = 0
    minute_nodata: int = 0
    minute_failed: int = 0
    daily_completed: int = 0
    daily_nodata: int = 0
    daily_failed: int = 0
    accepted_degraded: int = 0
    critical_failures: int = 0
    status: str = "FAIL"
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EodTargetResolution:
    status: str
    day: date | None = None
    reason: str | None = None


def _fetch_status(
    connection: sqlite3.Connection, *, mode: str, symbol: str, day: date
):
    return connection.execute(
        """SELECT * FROM rest_fetch_status
           WHERE mode=? AND symbol=? AND from_date=? AND to_date=?
             AND resolution=? AND year=?""",
        (
            mode,
            symbol,
            day.isoformat(),
            day.isoformat(),
            1 if mode == "minute" else 0,
            day.year,
        ),
    ).fetchone()


def _has_positive_rest_session(
    connection: sqlite3.Connection, *, symbol: str, day: date
) -> bool:
    return connection.execute(
        """SELECT 1 FROM rest_session_status
           WHERE mode='minute' AND symbol=? AND trading_date=?
             AND resolution=1 AND status='COMPLETED' AND rows_received>0
           LIMIT 1""",
        (symbol, day.isoformat()),
    ).fetchone() is not None


def live_evidence_count(store: CanonicalMarketStore, day: date) -> int:
    row = store.connection(day.year).execute(
        "SELECT COUNT(*) FROM minute_bars WHERE trading_date=?", (day.isoformat(),)
    ).fetchone()
    return int(row[0])


def validate_eod_pairs(
    *,
    store: CanonicalMarketStore,
    day: date,
    exchange_map: Mapping[str, str],
) -> CanonicalEodResult:
    return _validate_eod_pairs(
        connection=store.connection(day.year), day=day, exchange_map=exchange_map
    )


def _validate_eod_pairs(
    *,
    connection: sqlite3.Connection,
    day: date,
    exchange_map: Mapping[str, str],
) -> CanonicalEodResult:
    counts = {
        "minute_completed": 0,
        "minute_nodata": 0,
        "minute_failed": 0,
        "daily_completed": 0,
        "daily_nodata": 0,
        "daily_failed": 0,
    }
    accepted_degraded = 0
    reasons: list[str] = []
    day_text = day.isoformat()

    for symbol in sorted(exchange_map):
        minute = _fetch_status(connection, mode="minute", symbol=symbol, day=day)
        daily = _fetch_status(connection, mode="daily", symbol=symbol, day=day)
        minute_status = str(minute["status"]) if minute is not None else "MISSING"
        daily_status = str(daily["status"]) if daily is not None else "MISSING"
        minute_key = {
            "COMPLETED": "minute_completed",
            "NO_DATA": "minute_nodata",
            "FAILED": "minute_failed",
        }.get(minute_status)
        daily_key = {
            "COMPLETED": "daily_completed",
            "NO_DATA": "daily_nodata",
            "FAILED": "daily_failed",
        }.get(daily_status)
        if minute_key:
            counts[minute_key] += 1
        if daily_key:
            counts[daily_key] += 1

        minute_rows = int(
            connection.execute(
                "SELECT COUNT(*) FROM minute_bars WHERE symbol=? AND trading_date=?",
                (symbol, day_text),
            ).fetchone()[0]
        )
        daily_rows = connection.execute(
            """SELECT symbol,trading_date,exchange,open,high,low,close,volume,
                      quality_status
               FROM daily_bars
               WHERE symbol=? AND trading_date=?""",
            (symbol, day_text),
        ).fetchall()

        pair = (minute_status, daily_status)
        if pair == ("COMPLETED", "COMPLETED"):
            if not _has_positive_rest_session(
                connection, symbol=symbol, day=day
            ):
                reasons.append(
                    f"{symbol}:MINUTE_COMPLETED_WITHOUT_REST_SESSION_PROOF"
                )
                continue
            if minute_rows <= 0:
                reasons.append(f"{symbol}:MINUTE_COMPLETED_WITHOUT_DAY_ROWS")
                continue
            if len(daily_rows) != 1:
                reasons.append(f"{symbol}:DAILY_COMPLETED_WITHOUT_EXACT_IDENTITY")
                continue
            daily_row = daily_rows[0]
            if (
                daily_row["symbol"] != symbol
                or daily_row["trading_date"] != day_text
                or daily_row["exchange"] != exchange_map[symbol]
            ):
                reasons.append(f"{symbol}:DAILY_CANONICAL_IDENTITY_MISMATCH")
                continue
            authority_error = CanonicalMarketStore.daily_quote_authority_error(
                daily_row
            )
            if authority_error is not None:
                reasons.append(
                    f"{symbol}:DAILY_QUOTE_NOT_AUTHORITATIVE:{authority_error}"
                )
                continue
            latest = connection.execute(
                """SELECT trading_date,last_price,total_volume,open,high,low,close
                   FROM latest_quotes WHERE symbol=? AND trading_date=?""",
                (symbol, day_text),
            ).fetchone()
            if latest is None:
                reasons.append(f"{symbol}:LATEST_QUOTE_MISSING_FOR_COMPLETED_PAIR")
                continue
            expected = {
                "last_price": daily_row["close"],
                "total_volume": daily_row["volume"],
                "open": daily_row["open"],
                "high": daily_row["high"],
                "low": daily_row["low"],
                "close": daily_row["close"],
            }
            mismatches = [
                field for field, value in expected.items() if latest[field] != value
            ]
            if mismatches:
                reasons.append(
                    f"{symbol}:LATEST_QUOTE_DAILY_MISMATCH:{','.join(mismatches)}"
                )
            continue

        if pair == ("NO_DATA", "NO_DATA"):
            if daily_rows:
                reasons.append(f"{symbol}:DAILY_NO_DATA_WITH_CANONICAL_ROW")
            else:
                accepted_degraded += 1
            continue

        if pair == ("NO_DATA", "FAILED"):
            error = str(daily["last_error"] or "") if daily is not None else ""
            if error == AMBIGUOUS_EMPTY_RESPONSE and not daily_rows:
                accepted_degraded += 1
            else:
                reasons.append(f"{symbol}:UNACCEPTED_DAILY_FAILURE:{error}")
            continue

        reasons.append(f"{symbol}:INCONSISTENT_PAIR:{minute_status}+{daily_status}")

    status = "FAIL" if reasons else ("DEGRADED" if accepted_degraded else "PASS")
    return CanonicalEodResult(
        day=day_text,
        **counts,
        accepted_degraded=accepted_degraded,
        critical_failures=len(reasons),
        status=status,
        reasons=tuple(reasons),
    )


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{path.resolve().as_posix()}?mode=ro", uri=True
    )
    connection.row_factory = sqlite3.Row
    return connection


def _market_day_is_active(now: datetime, exchange_map: Mapping[str, str]) -> bool:
    local = now.astimezone(VN_TZ) if now.tzinfo else now.replace(tzinfo=VN_TZ)
    exchanges = set(exchange_map.values())
    starts = [
        start
        for exchange in exchanges
        if (start := market_day_feed_start(local, exchange)) is not None
    ]
    if not starts or local < min(starts):
        return False
    return any(
        classify_market_session(exchange, local).session_type is not SessionType.CLOSED
        for exchange in exchanges
    )


def _latest_evidence_date(db_dir: Path, *, on_or_before: date) -> date | None:
    candidates: set[date] = set()
    for path in db_dir.glob("ccc_market_[0-9][0-9][0-9][0-9].db"):
        with closing(_read_only_connection(path)) as connection:
            candidates.update(
                date.fromisoformat(str(row[0]))
                for row in connection.execute(
                    """SELECT DISTINCT trading_date FROM minute_bars
                       WHERE trading_date<=?""",
                    (on_or_before.isoformat(),),
                )
            )
    return max(candidates) if candidates else None


def resolve_eod_target(
    *,
    db_dir: Path,
    now: datetime,
    exchange_map: Mapping[str, str],
) -> EodTargetResolution:
    local = now.astimezone(VN_TZ) if now.tzinfo else now.replace(tzinfo=VN_TZ)
    if _market_day_is_active(local, exchange_map):
        return EodTargetResolution(
            status="REFUSED_ACTIVE_MARKET",
            reason="MARKET_DAY_IN_PROGRESS",
        )

    exchanges = set(exchange_map.values())
    starts = [
        start
        for exchange in exchanges
        if (start := market_day_feed_start(local, exchange)) is not None
    ]
    before_weekday_market = bool(starts) and local < min(starts)
    cutoff = (
        local.date() - timedelta(days=1)
        if before_weekday_market
        else local.date()
    )
    target = _latest_evidence_date(db_dir, on_or_before=cutoff)
    if target is None:
        return EodTargetResolution(
            status="SKIP_NO_EOD_TARGET", reason="NO_CANONICAL_LIVE_EVIDENCE"
        )

    if (
        target == local.date()
        and local.weekday() < 5
        and local.time().replace(tzinfo=None) < EOD_CURRENT_DAY_READY_AT
    ):
        return EodTargetResolution(
            status="REFUSED_EOD_NOT_READY",
            day=target,
            reason=f"CURRENT_DAY_READY_AT_{EOD_CURRENT_DAY_READY_AT.strftime('%H:%M')}",
        )

    path = db_dir / f"ccc_market_{target.year}.db"
    with closing(_read_only_connection(path)) as connection:
        result = _validate_eod_pairs(
            connection=connection, day=target, exchange_map=exchange_map
        )
    if result.status in {"PASS", "DEGRADED"}:
        return EodTargetResolution(
            status="SKIP_NO_EOD_TARGET",
            day=target,
            reason=f"LATEST_EVIDENCE_ALREADY_{result.status}",
        )
    return EodTargetResolution(status="EOD_TARGET", day=target)


def print_resolution(
    resolution: EodTargetResolution, output: Callable[[str], None] = print
) -> None:
    values = [resolution.status]
    if resolution.day is not None:
        values.append(f"day={resolution.day.isoformat()}")
    if resolution.reason:
        values.append(f"reason={resolution.reason}")
    output(" ".join(values))


def run_canonical_eod(
    *,
    day: date,
    store: CanonicalMarketStore,
    client: RestFetcher,
    exchange_map: Mapping[str, str],
    output: Callable[[str], None] = print,
) -> CanonicalEodResult | None:
    if live_evidence_count(store, day) == 0:
        output(f"SKIP_NO_LIVE_EVIDENCE day={day.isoformat()}")
        return None

    symbols = set(exchange_map)
    connection = store.connection(day.year)
    repair_symbols = {
        symbol
        for symbol in symbols
        if (
            (status := _fetch_status(
                connection, mode="minute", symbol=symbol, day=day
            ))
            is not None
            and status["status"] == "COMPLETED"
            and not _has_positive_rest_session(
                connection, symbol=symbol, day=day
            )
        )
    }
    if repair_symbols:
        run_bootstrap(
            mode="minute",
            store=store,
            client=client,
            symbols=repair_symbols,
            exchange_map=exchange_map,
            from_date=day,
            to_date=day,
            retry_failed=True,
            refresh_completed=True,
            output=output,
        )
    for mode in ("minute", "daily"):
        mode_symbols = symbols - repair_symbols if mode == "minute" else symbols
        if not mode_symbols:
            continue
        run_bootstrap(
            mode=mode,
            store=store,
            client=client,
            symbols=mode_symbols,
            exchange_map=exchange_map,
            from_date=day,
            to_date=day,
            retry_failed=True,
            output=output,
        )
    for symbol in sorted(symbols):
        store.finalize_eod_latest_quote(
            symbol=symbol,
            trading_date=day.isoformat(),
            expected_exchange=exchange_map[symbol],
        )
    return validate_eod_pairs(store=store, day=day, exchange_map=exchange_map)


def print_result(result: CanonicalEodResult, output: Callable[[str], None] = print) -> None:
    output("CANONICAL_EOD_RESULT")
    for field in (
        "day",
        "minute_completed",
        "minute_nodata",
        "minute_failed",
        "daily_completed",
        "daily_nodata",
        "daily_failed",
        "accepted_degraded",
        "critical_failures",
        "status",
    ):
        output(f"{field}={getattr(result, field)}")
    for reason in result.reasons:
        output(f"failure={reason}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--date", type=date.fromisoformat)
    target.add_argument("--resolve-target", action="store_true")
    parser.add_argument("--db-dir", type=Path, default=Path("data"))
    parser.add_argument("--request-interval", type=float, default=0.5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metadata_config = CanonicalMetadataConfig.from_env()
        exchange_map = load_exchange_map(metadata_config)
        if not exchange_map:
            raise RuntimeError("No symbols selected")
        if args.resolve_target:
            resolution = resolve_eod_target(
                db_dir=args.db_dir,
                now=datetime.now(VN_TZ),
                exchange_map=exchange_map,
            )
            print_resolution(resolution)
            return 0
        rest_config = CanonicalRestConfig.from_env()
        client = SSIHistoricalClient(
            base_url=rest_config.ssi_url,
            consumer_id=rest_config.ssi_consumer_id,
            consumer_secret=rest_config.ssi_consumer_secret,
            auth_type=rest_config.ssi_auth_type,
            request_interval=args.request_interval,
        )
        with CanonicalMarketStore(args.db_dir) as store:
            result = run_canonical_eod(
                day=args.date,
                store=store,
                client=client,
                exchange_map=exchange_map,
            )
    except Exception as exc:
        result = CanonicalEodResult(
            day=(
                args.date.isoformat()
                if args.date
                else datetime.now(VN_TZ).date().isoformat()
            ),
            critical_failures=1,
            status="FAIL",
            reasons=(f"OPERATIONAL_ERROR:{type(exc).__name__}:{exc}",),
        )
    if result is None:
        return 0
    print_result(result)
    return 1 if result.status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
