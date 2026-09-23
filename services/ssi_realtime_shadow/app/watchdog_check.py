from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .market_session import VN_TZ


HEARTBEAT_KEY = "main_loop_heartbeat_at"


def check_heartbeat(
    database: Path,
    *,
    max_age_seconds: float,
    now: datetime | None = None,
) -> tuple[bool, str]:
    if max_age_seconds < 0:
        return False, "WATCHDOG_UNHEALTHY reason=invalid_max_age"

    path = database.expanduser().resolve()
    try:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro",
            uri=True,
            timeout=2,
        )
        try:
            connection.execute("PRAGMA query_only=ON")
            row = connection.execute(
                "SELECT value FROM collector_meta WHERE key = ?",
                (HEARTBEAT_KEY,),
            ).fetchone()
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        return (
            False,
            "WATCHDOG_UNHEALTHY reason=database_unreadable "
            f"error_type={type(exc).__name__}",
        )

    if row is None:
        return False, "WATCHDOG_UNHEALTHY reason=heartbeat_missing"

    raw_timestamp = str(row[0])
    try:
        heartbeat_at = datetime.fromisoformat(raw_timestamp)
        if heartbeat_at.tzinfo is None or heartbeat_at.utcoffset() is None:
            raise ValueError("heartbeat timestamp must include timezone")
    except (TypeError, ValueError):
        return False, "WATCHDOG_UNHEALTHY reason=heartbeat_malformed"

    current = now or datetime.now(VN_TZ)
    if current.tzinfo is None or current.utcoffset() is None:
        return False, "WATCHDOG_UNHEALTHY reason=current_time_not_aware"
    age_seconds = (current - heartbeat_at).total_seconds()
    if age_seconds > max_age_seconds:
        return (
            False,
            "WATCHDOG_UNHEALTHY reason=heartbeat_stale "
            f"age_seconds={age_seconds:.1f} max_age_seconds={max_age_seconds:g}",
        )
    return (
        True,
        "WATCHDOG_HEALTHY "
        f"age_seconds={age_seconds:.1f} max_age_seconds={max_age_seconds:g}",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check the canonical collector main-loop heartbeat."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--max-age-seconds", required=True, type=float)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    healthy, diagnostic = check_heartbeat(
        args.database,
        max_age_seconds=args.max_age_seconds,
    )
    print(diagnostic)
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
