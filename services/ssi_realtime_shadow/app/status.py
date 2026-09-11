from __future__ import annotations

import sqlite3
from pathlib import Path

from .settings import Settings


def main() -> int:
    settings = Settings.from_env()
    db = Path(settings.database_path)
    if not db.exists():
        print(f"Database not found: {db}")
        return 1

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        print(f"DB: {db} ({db.stat().st_size / 1024 / 1024:.2f} MB)")
        print("\nBy trading date:")
        rows = conn.execute(
            """
            SELECT trading_date,
                   COUNT(*) AS minute_rows,
                   COUNT(DISTINCT symbol) AS symbols,
                   COUNT(DISTINCT minute) AS minutes,
                   SUM(CASE WHEN is_partial = 1 THEN 1 ELSE 0 END) AS partial_rows
            FROM minute_bars
            GROUP BY trading_date
            ORDER BY trading_date DESC
            LIMIT 15
            """
        ).fetchall()
        for row in rows:
            print(
                f"  {row['trading_date']}: rows={row['minute_rows']:,} "
                f"symbols={row['symbols']} minutes={row['minutes']} partial={row['partial_rows']:,}"
            )

        quote_count = conn.execute("SELECT COUNT(*) FROM latest_quotes").fetchone()[0]
        print(f"\nLatest quotes: {quote_count:,}")

        meta = conn.execute(
            "SELECT key, value, updated_at FROM collector_meta ORDER BY key"
        ).fetchall()
        if meta:
            print("\nCollector meta:")
            for row in meta:
                print(f"  {row['key']}={row['value']} ({row['updated_at']})")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
