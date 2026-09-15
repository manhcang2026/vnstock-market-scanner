from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DEFAULT_SOURCE = Path("/app/data/ssi_shadow.db")
DEFAULT_HISTORY = Path("/app/data/ssi_history_2026.db")
DEFAULT_MIN_SYMBOLS = 500
DEFAULT_MIN_MINUTES = 200
DEFAULT_MIN_ROWS = 20_000
DEFAULT_MIN_LAST_MINUTE = "14:45"
SAFE_AFTER = time(15, 20)


@dataclass(frozen=True)
class DayAudit:
    trading_date: str
    rows: int
    symbols: int
    minutes: int
    first_minute: str | None
    last_minute: str | None
    partial_rows: int
    gap_rows: int
    invalid_ohlc_rows: int
    negative_volume_rows: int
    quality_counts: dict[str, int]


@dataclass(frozen=True)
class FinalizeResult:
    trading_date: str
    status: str
    source_rows: int
    history_rows_before: int
    inserted_rows: int
    history_rows_after: int
    audit: DayAudit
    reasons: tuple[str, ...]


def _connect(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    else:
        conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def audit_day(conn: sqlite3.Connection, trading_date: str) -> DayAudit:
    row = conn.execute(
        """
        SELECT
          COUNT(*) rows,
          COUNT(DISTINCT symbol) symbols,
          COUNT(DISTINCT minute) minutes,
          MIN(minute) first_minute,
          MAX(minute) last_minute,
          COALESCE(SUM(is_partial), 0) partial_rows,
          COALESCE(SUM(has_gap), 0) gap_rows,
          COALESCE(SUM(CASE
            WHEN high < low
              OR open < low OR open > high
              OR close < low OR close > high
            THEN 1 ELSE 0 END), 0) invalid_ohlc_rows,
          COALESCE(SUM(CASE WHEN volume < 0 THEN 1 ELSE 0 END), 0)
            negative_volume_rows
        FROM minute_bars
        WHERE trading_date = ?
        """,
        (trading_date,),
    ).fetchone()
    quality_counts = {
        str(item["quality_status"]): int(item["rows"])
        for item in conn.execute(
            """
            SELECT quality_status, COUNT(*) rows
            FROM minute_bars
            WHERE trading_date = ?
            GROUP BY quality_status
            ORDER BY quality_status
            """,
            (trading_date,),
        ).fetchall()
    }
    return DayAudit(
        trading_date=trading_date,
        rows=int(row["rows"]),
        symbols=int(row["symbols"]),
        minutes=int(row["minutes"]),
        first_minute=row["first_minute"],
        last_minute=row["last_minute"],
        partial_rows=int(row["partial_rows"]),
        gap_rows=int(row["gap_rows"]),
        invalid_ohlc_rows=int(row["invalid_ohlc_rows"]),
        negative_volume_rows=int(row["negative_volume_rows"]),
        quality_counts=quality_counts,
    )


def gate_reasons(
    audit: DayAudit,
    *,
    min_symbols: int = DEFAULT_MIN_SYMBOLS,
    min_minutes: int = DEFAULT_MIN_MINUTES,
    min_rows: int = DEFAULT_MIN_ROWS,
    min_last_minute: str = DEFAULT_MIN_LAST_MINUTE,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if audit.rows < min_rows:
        reasons.append(f"rows<{min_rows}")
    if audit.symbols < min_symbols:
        reasons.append(f"symbols<{min_symbols}")
    if audit.minutes < min_minutes:
        reasons.append(f"minutes<{min_minutes}")
    if audit.last_minute is None or audit.last_minute < min_last_minute:
        reasons.append(f"last_minute<{min_last_minute}")
    if audit.gap_rows:
        reasons.append(f"gap_rows={audit.gap_rows}")
    if audit.invalid_ohlc_rows:
        reasons.append(f"invalid_ohlc_rows={audit.invalid_ohlc_rows}")
    if audit.negative_volume_rows:
        reasons.append(f"negative_volume_rows={audit.negative_volume_rows}")
    return tuple(reasons)


def ensure_finalize_schema(history: sqlite3.Connection) -> None:
    history.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_finalize_runs (
            trading_date TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            source_rows INTEGER NOT NULL,
            inserted_rows INTEGER NOT NULL,
            history_rows INTEGER NOT NULL,
            symbols INTEGER NOT NULL,
            minutes INTEGER NOT NULL,
            partial_rows INTEGER NOT NULL,
            gap_rows INTEGER NOT NULL,
            invalid_ohlc_rows INTEGER NOT NULL,
            quality_json TEXT NOT NULL,
            details_json TEXT NOT NULL,
            finalized_at TEXT NOT NULL
        )
        """
    )
    history.commit()


def _history_count(history: sqlite3.Connection, trading_date: str) -> int:
    return int(
        history.execute(
            "SELECT COUNT(*) FROM minute_bars WHERE trading_date = ?",
            (trading_date,),
        ).fetchone()[0]
    )


def _record_result(
    history: sqlite3.Connection,
    result: FinalizeResult,
    finalized_at: str,
) -> None:
    history.execute(
        """
        INSERT INTO daily_finalize_runs (
            trading_date, status, source_rows, inserted_rows, history_rows,
            symbols, minutes, partial_rows, gap_rows, invalid_ohlc_rows,
            quality_json, details_json, finalized_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(trading_date) DO UPDATE SET
            status=excluded.status,
            source_rows=excluded.source_rows,
            inserted_rows=excluded.inserted_rows,
            history_rows=excluded.history_rows,
            symbols=excluded.symbols,
            minutes=excluded.minutes,
            partial_rows=excluded.partial_rows,
            gap_rows=excluded.gap_rows,
            invalid_ohlc_rows=excluded.invalid_ohlc_rows,
            quality_json=excluded.quality_json,
            details_json=excluded.details_json,
            finalized_at=excluded.finalized_at
        """,
        (
            result.trading_date,
            result.status,
            result.source_rows,
            result.inserted_rows,
            result.history_rows_after,
            result.audit.symbols,
            result.audit.minutes,
            result.audit.partial_rows,
            result.audit.gap_rows,
            result.audit.invalid_ohlc_rows,
            json.dumps(result.audit.quality_counts, sort_keys=True),
            json.dumps({"reasons": list(result.reasons)}, sort_keys=True),
            finalized_at,
        ),
    )
    history.commit()


def finalize_day(
    *,
    source_path: Path,
    history_path: Path,
    trading_date: str,
    dry_run: bool = False,
    min_symbols: int = DEFAULT_MIN_SYMBOLS,
    min_minutes: int = DEFAULT_MIN_MINUTES,
    min_rows: int = DEFAULT_MIN_ROWS,
    min_last_minute: str = DEFAULT_MIN_LAST_MINUTE,
    now: datetime | None = None,
) -> FinalizeResult:
    now = now or datetime.now(VN_TZ)
    source = _connect(source_path, read_only=True)
    history = _connect(history_path)
    try:
        ensure_finalize_schema(history)
        audit = audit_day(source, trading_date)
        reasons = gate_reasons(
            audit,
            min_symbols=min_symbols,
            min_minutes=min_minutes,
            min_rows=min_rows,
            min_last_minute=min_last_minute,
        )
        before = _history_count(history, trading_date)
        if reasons:
            result = FinalizeResult(
                trading_date=trading_date,
                status="BLOCKED",
                source_rows=audit.rows,
                history_rows_before=before,
                inserted_rows=0,
                history_rows_after=before,
                audit=audit,
                reasons=reasons,
            )
            if not dry_run:
                _record_result(history, result, now.isoformat())
            return result

        if dry_run:
            return FinalizeResult(
                trading_date=trading_date,
                status="DRY_RUN_PASS",
                source_rows=audit.rows,
                history_rows_before=before,
                inserted_rows=0,
                history_rows_after=before,
                audit=audit,
                reasons=(),
            )

        source_rows = source.execute(
            """
            SELECT trading_date, minute, symbol, open, high, low, close,
                   volume, last_total_volume, event_count, is_partial, exchange,
                   quality_status, has_gap, gap_from, gap_to, provider_time,
                   updated_at
            FROM minute_bars
            WHERE trading_date = ?
            ORDER BY trading_date, minute, symbol
            """,
            (trading_date,),
        )
        inserted = 0
        for row in source_rows:
            cursor = history.execute(
                """
                INSERT OR IGNORE INTO minute_bars (
                    trading_date, minute, symbol, open, high, low, close,
                    volume, last_total_volume, event_count, is_partial, exchange,
                    quality_status, has_gap, gap_from, gap_to, data_source,
                    provider_time, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["trading_date"],
                    row["minute"],
                    row["symbol"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    row["last_total_volume"],
                    row["event_count"],
                    row["is_partial"],
                    row["exchange"],
                    row["quality_status"],
                    row["has_gap"],
                    row["gap_from"],
                    row["gap_to"],
                    "SSI_STREAM_FINAL",
                    row["provider_time"],
                    row["updated_at"],
                ),
            )
            inserted += max(0, cursor.rowcount)
        history.commit()
        after = _history_count(history, trading_date)
        status = "PASS" if after >= audit.rows else "BLOCKED"
        reasons = () if status == "PASS" else (
            f"history_rows_after={after}<source_rows={audit.rows}",
        )
        result = FinalizeResult(
            trading_date=trading_date,
            status=status,
            source_rows=audit.rows,
            history_rows_before=before,
            inserted_rows=inserted,
            history_rows_after=after,
            audit=audit,
            reasons=reasons,
        )
        _record_result(history, result, now.isoformat())
        return result
    finally:
        source.close()
        history.close()


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def _default_trading_date(now: datetime) -> date:
    return now.date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="QA and promote one completed SSI realtime session into history"
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--date", type=_parse_date)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--min-symbols", type=int, default=DEFAULT_MIN_SYMBOLS)
    parser.add_argument("--min-minutes", type=int, default=DEFAULT_MIN_MINUTES)
    parser.add_argument("--min-rows", type=int, default=DEFAULT_MIN_ROWS)
    parser.add_argument("--min-last-minute", default=DEFAULT_MIN_LAST_MINUTE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now = datetime.now(VN_TZ)
    target = args.date or _default_trading_date(now)
    if not args.force and target == now.date() and now.timetz().replace(tzinfo=None) < SAFE_AFTER:
        raise SystemExit(
            f"Refusing to finalize {target.isoformat()} before {SAFE_AFTER.strftime('%H:%M')} VN"
        )
    result = finalize_day(
        source_path=args.source,
        history_path=args.history,
        trading_date=target.isoformat(),
        dry_run=args.dry_run,
        min_symbols=args.min_symbols,
        min_minutes=args.min_minutes,
        min_rows=args.min_rows,
        min_last_minute=args.min_last_minute,
        now=now,
    )
    print(json.dumps({**asdict(result), "audit": asdict(result.audit)}, ensure_ascii=False))
    return 0 if result.status in {"PASS", "DRY_RUN_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
