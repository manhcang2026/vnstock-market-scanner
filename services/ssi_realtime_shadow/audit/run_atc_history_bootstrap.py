from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.auction_history import (  # noqa: E402
    bootstrap_auction_history,
    load_approved_proof_rows,
)
from app.market_storage_schema import ensure_market_storage_schema  # noqa: E402


VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _open_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError("Dry-run database must already exist: " + str(path))
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


def run(
    *,
    proof_csv: Path,
    database_path: Path | None,
    write: bool,
    recorded_at: str,
) -> dict:
    rows, rejected = load_approved_proof_rows(proof_csv)
    if write:
        if database_path is None:
            raise ValueError("--write requires an explicit --db local path")
        connection = sqlite3.connect(database_path)
        ensure_market_storage_schema(connection, applied_at=recorded_at)
    elif database_path is None:
        connection = sqlite3.connect(":memory:")
        ensure_market_storage_schema(connection, applied_at=recorded_at)
    else:
        connection = _open_read_only(database_path)

    try:
        report = bootstrap_auction_history(
            connection,
            rows,
            recorded_at=recorded_at,
            dry_run=not write,
            rejected=rejected,
        )
        if write:
            connection.commit()
        canonical_rows = connection.execute(
            "SELECT COUNT(*) FROM auction_session_history"
        ).fetchone()[0]
        ato_rows = connection.execute(
            "SELECT COUNT(*) FROM auction_session_history WHERE auction_type='OPEN_AUCTION'"
        ).fetchone()[0]
    finally:
        connection.close()
    return {
        "mode": "WRITE" if write else "DRY_RUN",
        "database": str(database_path) if database_path else ":memory:",
        **report.to_dict(),
        "canonical_rows_after": int(canonical_rows),
        "ato_rows_after": int(ato_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dry-run-first SSI ATC canonical history bootstrap"
    )
    parser.add_argument(
        "--proof-csv",
        type=Path,
        default=Path(__file__).resolve().parent / "ssi_atc_proof_rows.csv",
    )
    parser.add_argument("--db", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--recorded-at",
        default=datetime.now(VN_TZ).isoformat(timespec="seconds"),
    )
    args = parser.parse_args()
    result = run(
        proof_csv=args.proof_csv,
        database_path=args.db,
        write=args.write,
        recorded_at=args.recorded_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
