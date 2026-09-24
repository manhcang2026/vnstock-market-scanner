"""Import legacy SSI REST minute history into canonical year shards."""

from __future__ import annotations

import argparse
import math
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from .canonical_market_store import CanonicalMarketStore, utc_now


DEFAULT_BATCH_SIZE = 20

LEGACY_MINUTE_COLUMNS = {
    "trading_date",
    "minute",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "last_total_volume",
    "exchange",
    "quality_status",
    "data_source",
    "provider_time",
    "updated_at",
}
LEGACY_CHECKPOINT_COLUMNS = {
    "symbol",
    "from_date",
    "to_date",
    "resolution",
    "status",
}

# Only rows that can satisfy the canonical identity and NOT NULL contract are
# imported. Market values deliberately remain nullable.
VALID_MINUTE_SQL = """
    m.symbol IS NOT NULL AND TRIM(m.symbol) <> ''
    AND m.trading_date IS NOT NULL
    AND m.trading_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
    AND m.minute IS NOT NULL
    AND m.minute GLOB '[0-2][0-9]:[0-5][0-9]'
    AND SUBSTR(m.minute, 1, 2) <= '23'
    AND m.data_source IS NOT NULL AND TRIM(m.data_source) <> ''
    AND m.quality_status IS NOT NULL AND TRIM(m.quality_status) <> ''
    AND m.updated_at IS NOT NULL AND TRIM(m.updated_at) <> ''
"""

IMPORT_MINUTES_SQL = f"""
    INSERT INTO minute_bars(
        symbol, trading_date, minute, exchange, open, high, low, close,
        volume, value, provider_total_volume, provider_session, provider_time,
        first_event_at, last_event_at, source, quality_status, is_finalized,
        updated_at
    )
    SELECT
        m.symbol, m.trading_date, m.minute, m.exchange,
        m.open, m.high, m.low, m.close, m.volume,
        NULL, m.last_total_volume, NULL, m.provider_time,
        NULL, NULL, m.data_source, m.quality_status, 1, m.updated_at
    FROM legacy.minute_bars AS m
    WHERE {VALID_MINUTE_SQL}
      AND m.trading_date BETWEEN ? AND ?
    ON CONFLICT(symbol, trading_date, minute) DO NOTHING
"""

IMPORT_SESSION_PROOFS_SQL = f"""
    INSERT INTO rest_session_status(
        mode, symbol, trading_date, resolution, status, rows_received, updated_at
    )
    SELECT
        'minute', m.symbol, m.trading_date, 1, 'COMPLETED', COUNT(*), ?
    FROM legacy.minute_bars AS m
    WHERE {VALID_MINUTE_SQL}
      AND m.trading_date BETWEEN ? AND ?
      AND EXISTS (
          SELECT 1
          FROM legacy.historical_bootstrap_checkpoints AS c
          WHERE c.symbol = m.symbol
            AND c.resolution = 1
            AND UPPER(TRIM(c.status)) = 'COMPLETED'
            AND m.trading_date BETWEEN c.from_date AND c.to_date
      )
    GROUP BY m.symbol, m.trading_date
    ON CONFLICT(mode, symbol, trading_date, resolution) DO NOTHING
"""


@dataclass(frozen=True, slots=True)
class ImportSummary:
    rows_read: int
    rows_upserted: int
    dates: int
    symbols: int
    session_proofs_upserted: int
    elapsed_seconds: float


def _canonical_input_date(value: date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value).strip()).isoformat()


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _validate_source_schema(connection: sqlite3.Connection) -> None:
    for table, required in (
        ("minute_bars", LEGACY_MINUTE_COLUMNS),
        ("historical_bootstrap_checkpoints", LEGACY_CHECKPOINT_COLUMNS),
    ):
        columns = _table_columns(connection, table)
        missing = sorted(required - columns)
        if missing:
            raise ValueError(
                f"legacy table {table!r} is missing required columns: "
                + ", ".join(missing)
            )


def _source_range(
    connection: sqlite3.Connection,
    requested_from: str | None,
    requested_to: str | None,
) -> tuple[str, str]:
    row = connection.execute(
        f"""SELECT MIN(m.trading_date), MAX(m.trading_date)
            FROM minute_bars AS m
            WHERE {VALID_MINUTE_SQL}"""
    ).fetchone()
    available_from, available_to = row if row else (None, None)
    if available_from is None or available_to is None:
        raise ValueError("legacy minute_bars contains no valid rows")
    selected_from = requested_from or str(available_from)
    selected_to = requested_to or str(available_to)
    if selected_from > selected_to:
        raise ValueError("from_date must not be after to_date")
    return selected_from, selected_to


def _source_stats(
    connection: sqlite3.Connection, from_date: str, to_date: str
) -> tuple[int, int]:
    row = connection.execute(
        f"""SELECT COUNT(DISTINCT m.trading_date), COUNT(DISTINCT m.symbol)
            FROM minute_bars AS m
            WHERE {VALID_MINUTE_SQL}
              AND m.trading_date BETWEEN ? AND ?""",
        (from_date, to_date),
    ).fetchone()
    return int(row[0]), int(row[1])


def _year_date_counts(
    connection: sqlite3.Connection, from_date: str, to_date: str
):
    return connection.execute(
        f"""SELECT CAST(SUBSTR(m.trading_date, 1, 4) AS INTEGER),
                   COUNT(DISTINCT m.trading_date)
            FROM minute_bars AS m
            WHERE {VALID_MINUTE_SQL}
              AND m.trading_date BETWEEN ? AND ?
            GROUP BY SUBSTR(m.trading_date, 1, 4)
            ORDER BY 1""",
        (from_date, to_date),
    )


def import_legacy_history(
    source: str | Path,
    *,
    db_dir: str | Path,
    from_date: date | str | None = None,
    to_date: date | str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    verbose: bool = False,
    output: Callable[[str], None] = print,
    monotonic: Callable[[], float] = time.monotonic,
) -> ImportSummary:
    """Import bounded trading-date batches without materializing minute rows."""
    source_path = Path(source).expanduser().resolve()
    target_dir = Path(db_dir).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"legacy database not found: {source_path}")
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    source_uri = f"{source_path.as_uri()}?mode=ro"
    requested_from = _canonical_input_date(from_date)
    requested_to = _canonical_input_date(to_date)
    started = monotonic()
    rows_read = rows_upserted = proofs_upserted = completed_batches = 0

    source_connection = sqlite3.connect(source_uri, uri=True)
    try:
        source_connection.execute("PRAGMA query_only=ON")
        _validate_source_schema(source_connection)
        selected_from, selected_to = _source_range(
            source_connection, requested_from, requested_to
        )
        date_count, symbol_count = _source_stats(
            source_connection, selected_from, selected_to
        )
        year_counts = tuple(
            _year_date_counts(source_connection, selected_from, selected_to)
        )
        total_batches = sum(
            math.ceil(int(count) / batch_size) for _, count in year_counts
        )

        with CanonicalMarketStore(target_dir) as store:
            for year, _ in year_counts:
                year = int(year)
                target_path = store.path_for_year(year).resolve()
                if target_path == source_path:
                    raise ValueError("source database cannot also be a canonical target")
                target = store.connection(year)
                target.execute("ATTACH DATABASE ? AS legacy", (str(source_path),))
                try:
                    last_date = ""
                    while True:
                        date_cursor = source_connection.execute(
                            f"""SELECT DISTINCT m.trading_date
                                FROM minute_bars AS m
                                WHERE {VALID_MINUTE_SQL}
                                  AND m.trading_date BETWEEN ? AND ?
                                  AND SUBSTR(m.trading_date, 1, 4) = ?
                                  AND m.trading_date > ?
                                ORDER BY m.trading_date
                                LIMIT ?""",
                            (
                                selected_from,
                                selected_to,
                                str(year),
                                last_date,
                                batch_size,
                            ),
                        )
                        date_rows = date_cursor.fetchmany(batch_size)
                        date_cursor.close()
                        if not date_rows:
                            break
                        batch_from = str(date_rows[0][0])
                        batch_to = str(date_rows[-1][0])
                        last_date = batch_to
                        read = int(
                            target.execute(
                                f"""SELECT COUNT(*)
                                    FROM legacy.minute_bars AS m
                                    WHERE {VALID_MINUTE_SQL}
                                      AND m.trading_date BETWEEN ? AND ?""",
                                (batch_from, batch_to),
                            ).fetchone()[0]
                        )
                        try:
                            target.execute("BEGIN IMMEDIATE")
                            minute_cursor = target.execute(
                                IMPORT_MINUTES_SQL, (batch_from, batch_to)
                            )
                            target.commit()
                        except BaseException:
                            target.rollback()
                            raise

                        # Canonical rows are durable before completeness proof is
                        # derived, per STORE FIRST -- CALCULATE SECOND.
                        try:
                            target.execute("BEGIN IMMEDIATE")
                            proof_cursor = target.execute(
                                IMPORT_SESSION_PROOFS_SQL,
                                (utc_now(), batch_from, batch_to),
                            )
                            target.commit()
                        except BaseException:
                            target.rollback()
                            raise

                        rows_read += read
                        rows_upserted += max(0, int(minute_cursor.rowcount))
                        proofs_upserted += max(0, int(proof_cursor.rowcount))
                        completed_batches += 1
                        output(
                            f"[{completed_batches}/{total_batches}] "
                            f"dates={batch_from}..{batch_to} read={read} "
                            f"upserted={minute_cursor.rowcount}"
                        )
                        if verbose:
                            output(
                                f"  session_proofs_upserted={proof_cursor.rowcount} "
                                f"target={target_path}"
                            )
                finally:
                    target.execute("DETACH DATABASE legacy")
    finally:
        source_connection.close()

    return ImportSummary(
        rows_read=rows_read,
        rows_upserted=rows_upserted,
        dates=date_count,
        symbols=symbol_count,
        session_proofs_upserted=proofs_upserted,
        elapsed_seconds=max(0.0, monotonic() - started),
    )


def _cli_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError("expected yyyy-mm-dd or dd/mm/yyyy")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--db-dir", type=Path, default=Path("data"))
    parser.add_argument("--from-date", type=_cli_date)
    parser.add_argument("--to-date", type=_cli_date)
    parser.add_argument("--batch-size", type=_positive_int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = import_legacy_history(
        args.source,
        db_dir=args.db_dir,
        from_date=args.from_date,
        to_date=args.to_date,
        batch_size=args.batch_size,
        verbose=args.verbose,
    )
    print(
        "summary "
        f"read={summary.rows_read} upserted={summary.rows_upserted} "
        f"dates={summary.dates} symbols={summary.symbols} "
        f"session_proofs_upserted={summary.session_proofs_upserted} "
        f"elapsed_seconds={summary.elapsed_seconds:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
