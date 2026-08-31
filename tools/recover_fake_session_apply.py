from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

import recover_fake_session_dry_run as dry

CONFIRM_TOKEN = "RECOVER-2026-08-31-TO-2026-08-28"
WRITE_TIMEOUT = 120
BATCH_SIZE = 100


def parse_args():
    p = argparse.ArgumentParser(
        description="Apply the audited 2026-08-31 fake-session recovery."
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Enable writes. Without this flag the script refuses to write.",
    )
    return p.parse_args()


def request_write(
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    payload: Any = None,
    prefer: str | None = None,
) -> requests.Response:
    headers = dry.headers()
    headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    response = requests.request(
        method,
        f"{dry.SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=params,
        json=payload,
        timeout=WRITE_TIMEOUT,
    )
    response.raise_for_status()
    return response


def get_all_star(table: str, filters: dict[str, str]) -> list[dict[str, Any]]:
    params = {"select": "*", **filters}
    return dry.get_all(table, params, max_pages=100)


def clean_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (pd.Timestamp, datetime, date, time)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float):
        if value != value:
            return None
        return float(value)
    if isinstance(value, int):
        return int(value)
    return value


def records_jsonable(df: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in df[columns].to_dict(orient="records"):
        rows.append({key: clean_value(value) for key, value in record.items()})
    return rows


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_gzip_json(path: Path, rows: Any) -> dict[str, Any]:
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, separators=(",", ":"))
    return {
        "file": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "rows": len(rows) if isinstance(rows, list) else None,
    }


def load_stock_state() -> tuple[int, int]:
    invalid = dry.get_all(
        "stock_snapshot",
        {
            "select": "symbol",
            "trading_date": f"eq.{dry.INVALID_DATE.isoformat()}",
            "order": "symbol.asc",
        },
    )
    target = dry.get_all(
        "stock_snapshot",
        {
            "select": "symbol",
            "trading_date": f"eq.{dry.TARGET_DATE.isoformat()}",
            "order": "symbol.asc",
        },
    )
    return len(invalid), len(target)


def load_invalid_intraday_count() -> int:
    rows = dry.get_all(
        "intraday_snapshots",
        {
            "select": "symbol",
            "trading_date": f"eq.{dry.INVALID_DATE.isoformat()}",
            "order": "symbol.asc",
        },
        max_pages=100,
    )
    return len(rows)


def validate_reconstructed(df: pd.DataFrame) -> None:
    total = len(df)
    k4 = int((df["signal_count"] == 4).sum())
    ge3 = int((df["signal_count"] >= 3).sum())
    ge2 = int((df["signal_count"] >= 2).sum())
    rvol200 = int(df["signal_rvol30_200pct"].sum())
    four = sorted(df.loc[df["signal_count"] == 4, "symbol"].tolist())

    checks = {
        "total": (total, dry.EXPECTED_TOTAL),
        "4/4": (k4, dry.EXPECTED_SIGNAL_4),
        ">=3": (ge3, dry.EXPECTED_SIGNAL_GE3),
        ">=2": (ge2, dry.EXPECTED_SIGNAL_GE2),
        "rvol200": (rvol200, dry.EXPECTED_RVOL200),
    }
    failures = [
        f"{name}: expected {expected}, got {actual}"
        for name, (actual, expected) in checks.items()
        if actual != expected
    ]
    if four != dry.EXPECTED_4_SYMBOLS:
        failures.append(
            f"4/4 symbols: expected {dry.EXPECTED_4_SYMBOLS}, got {four}"
        )
    if int(df["previous_close"].isna().sum()) != 0:
        failures.append("missing baseline rows remain")
    if df["symbol"].nunique() != dry.EXPECTED_TOTAL:
        failures.append("symbol uniqueness check failed")

    if failures:
        raise RuntimeError("Reconstruction validation failed: " + "; ".join(failures))


def build_stock_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    columns = [
        "symbol",
        "exchange",
        "current_price",
        "previous_close",
        "price_change_pct",
        "volume_accumulated",
        "avg_volume_10",
        "avg_volume_sessions",
        "daily_volume_pct",
        "ma200",
        "ma200_sessions",
        "ma200_distance_pct",
        "volume_30m",
        "avg_volume_30m_10",
        "rvol30_pct",
        "rvol30_sessions",
        "signal_price_3pct",
        "signal_daily_volume_200pct",
        "signal_above_ma200",
        "signal_rvol30_200pct",
        "signal_count",
        "trading_date",
        "time_slot",
        "updated_at",
        "data_status",
        "ma10",
        "ma10_sessions",
        "ma10_distance_pct",
    ]
    work = df.copy()
    work["trading_date"] = dry.TARGET_DATE.isoformat()
    work["time_slot"] = "15:00:00"
    work["data_status"] = "OK"
    # Reuse the real 28/08 15:00 snapshot timestamp already stored per symbol.
    return records_jsonable(work, columns)


def upsert_batches(
    table: str,
    rows: list[dict[str, Any]],
    conflict: str,
) -> None:
    for offset in range(0, len(rows), BATCH_SIZE):
        batch = rows[offset:offset + BATCH_SIZE]
        request_write(
            "POST",
            table,
            params={"on_conflict": conflict},
            payload=batch,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        print(
            f"{table}: wrote {min(offset + len(batch), len(rows))}/{len(rows)}"
        )


def verify_stock_snapshot() -> None:
    rows = dry.get_all(
        "stock_snapshot",
        {
            "select": (
                "symbol,trading_date,time_slot,signal_count,"
                "signal_rvol30_200pct"
            ),
            "order": "symbol.asc",
        },
    )
    df = pd.DataFrame(rows)
    if len(df) != dry.EXPECTED_TOTAL:
        raise RuntimeError(f"stock_snapshot rows expected 800, got {len(df)}")
    df["signal_count"] = pd.to_numeric(df["signal_count"], errors="coerce").fillna(0)
    k4 = int((df["signal_count"] == 4).sum())
    ge3 = int((df["signal_count"] >= 3).sum())
    ge2 = int((df["signal_count"] >= 2).sum())
    rvol200 = int(
        df["signal_rvol30_200pct"].fillna(False).astype(bool).sum()
    )
    four = sorted(df.loc[df["signal_count"] == 4, "symbol"].tolist())
    bad_date = int((df["trading_date"].astype(str) != dry.TARGET_DATE.isoformat()).sum())
    bad_slot = int((df["time_slot"].astype(str).str.slice(0, 5) != "15:00").sum())

    expected = (
        k4 == dry.EXPECTED_SIGNAL_4
        and ge3 == dry.EXPECTED_SIGNAL_GE3
        and ge2 == dry.EXPECTED_SIGNAL_GE2
        and rvol200 == dry.EXPECTED_RVOL200
        and four == dry.EXPECTED_4_SYMBOLS
        and bad_date == 0
        and bad_slot == 0
    )
    print(
        "Verify stock_snapshot: "
        f"4/4={k4}; >=3={ge3}; >=2={ge2}; RVOL200={rvol200}; "
        f"4/4 symbols={','.join(four)}; bad_date={bad_date}; bad_slot={bad_slot}"
    )
    if not expected:
        raise RuntimeError("Restored stock_snapshot verification FAILED")


def normalize_golden(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    # Compare the fields that define product history. `updated_at` is included
    # because the restore writes the original row back after stock_snapshot's
    # capture trigger fires.
    keep = [
        "symbol",
        "trading_date",
        "exchange",
        "first_hit_slot",
        "last_hit_slot",
        "hit_slots",
        "hit_count",
        "longest_streak_hits",
        "first_hit_at",
        "last_hit_at",
        "first_price",
        "first_price_change_pct",
        "first_daily_volume_pct",
        "first_ma200_distance_pct",
        "first_rvol30_pct",
        "first_rvol30_sessions",
        "last_hit_price",
        "last_hit_price_change_pct",
        "last_hit_daily_volume_pct",
        "last_hit_ma200_distance_pct",
        "last_hit_rvol30_pct",
        "last_hit_rvol30_sessions",
        "latest_observed_slot",
        "latest_observed_at",
        "latest_signal_count",
        "latest_price",
        "latest_price_change_pct",
        "latest_rvol30_pct",
        "latest_rvol30_sessions",
        "rvol30_sum",
        "max_rvol30_pct",
        "created_at",
        "updated_at",
    ]
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        out[symbol] = {key: row.get(key) for key in keep}
    return out


def main() -> None:
    args = parse_args()
    if not args.apply:
        print("WRITE DISABLED.")
        print("Run with --apply only after the dry run has passed.")
        raise SystemExit(2)

    print("=" * 72)
    print("STAGE 2B RECOVERY APPLY")
    print("Target valid session:", dry.TARGET_DATE)
    print("Invalid session:", dry.INVALID_DATE)
    print("=" * 72)

    # Re-run the complete read-only audit immediately before any write.
    dry.main()

    reconstructed = dry.reconstruct(dry.TARGET_DATE)
    validate_reconstructed(reconstructed)

    contamination = dry.compare_invalid_to_target(
        dry.TARGET_DATE,
        dry.INVALID_DATE,
    )
    invalid_stock, target_stock = load_stock_state()
    invalid_intraday = load_invalid_intraday_count()

    print("-" * 72)
    print(
        f"Current state: invalid_stock={invalid_stock}; "
        f"target_stock={target_stock}; invalid_intraday={invalid_intraday}"
    )

    if invalid_stock == 0 and target_stock == dry.EXPECTED_TOTAL and invalid_intraday == 0:
        verify_stock_snapshot()
        print("RECOVERY ALREADY COMPLETE. No writes needed.")
        return

    allowed_state_a = (
        invalid_stock == dry.EXPECTED_TOTAL
        and target_stock == 0
        and invalid_intraday == 44800
    )
    allowed_state_b = (
        invalid_stock == 0
        and target_stock == dry.EXPECTED_TOTAL
        and invalid_intraday == 44800
    )
    if not (allowed_state_a or allowed_state_b):
        raise RuntimeError(
            "Unexpected database state. Refusing to write. "
            f"invalid_stock={invalid_stock}, target_stock={target_stock}, "
            f"invalid_intraday={invalid_intraday}"
        )
    if contamination["eod_identical_ratio"] < 0.995:
        raise RuntimeError("31/08 contamination proof no longer passes >=99.5%")

    print()
    print("This operation will:")
    if allowed_state_a:
        print("  1. Backup current fake stock_snapshot + fake intraday + Golden Board.")
        print("  2. Restore stock_snapshot to the audited 28/08 15:00 state.")
        print("  3. Restore Golden Board 28/08 exactly after the stock trigger fires.")
        print("  4. Delete only intraday_snapshots where trading_date=2026-08-31.")
    else:
        print("  1. Backup current target stock_snapshot + fake intraday + Golden Board.")
        print("  2. Re-verify target stock_snapshot.")
        print("  3. Delete only intraday_snapshots where trading_date=2026-08-31.")
    print("  scan_runs will NOT be changed.")
    print()

    typed = input(f"Type exactly {CONFIRM_TOKEN} to continue: ").strip()
    if typed != CONFIRM_TOKEN:
        print("Confirmation mismatch. NOTHING WRITTEN.")
        raise SystemExit(3)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path.home() / "ccc-recovery-backups" / f"recover_20260831_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    fake_intraday_rows = get_all_star(
        "intraday_snapshots",
        {"trading_date": f"eq.{dry.INVALID_DATE.isoformat()}"},
    )
    current_stock_rows = get_all_star("stock_snapshot", {})
    golden_before = get_all_star(
        "golden_board_daily",
        {"trading_date": f"eq.{dry.TARGET_DATE.isoformat()}"},
    )
    target_rows = build_stock_rows(reconstructed)

    backup_manifest = {
        "created_local": datetime.now().isoformat(),
        "target_date": dry.TARGET_DATE.isoformat(),
        "invalid_date": dry.INVALID_DATE.isoformat(),
        "files": [],
    }
    backup_manifest["files"].append(
        save_gzip_json(backup_dir / "invalid_intraday_2026-08-31.json.gz", fake_intraday_rows)
    )
    backup_manifest["files"].append(
        save_gzip_json(backup_dir / "stock_snapshot_before.json.gz", current_stock_rows)
    )
    backup_manifest["files"].append(
        save_gzip_json(backup_dir / "golden_board_2026-08-28_before.json.gz", golden_before)
    )
    backup_manifest["files"].append(
        save_gzip_json(backup_dir / "reconstructed_stock_snapshot_2026-08-28.json.gz", target_rows)
    )
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(backup_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"BACKUP COMPLETE: {backup_dir}")

    if allowed_state_a:
        print("Restoring 800 stock_snapshot rows...")
        upsert_batches("stock_snapshot", target_rows, "symbol")

        # stock_snapshot has a Golden Board trigger. Put the exact pre-recovery
        # 28/08 Golden Board rows back so history/timestamps do not drift.
        if golden_before:
            print("Restoring Golden Board 28/08 exactly...")
            upsert_batches(
                "golden_board_daily",
                golden_before,
                "trading_date,symbol",
            )

        verify_stock_snapshot()

        golden_after = get_all_star(
            "golden_board_daily",
            {"trading_date": f"eq.{dry.TARGET_DATE.isoformat()}"},
        )
        if normalize_golden(golden_after) != normalize_golden(golden_before):
            raise RuntimeError(
                "Golden Board exact-restore verification FAILED. "
                f"Backup is at {backup_dir}. "
                "Intraday fake rows were NOT deleted."
            )
        print("Golden Board exact-restore verification: PASS")
    else:
        verify_stock_snapshot()

    print("Deleting ONLY intraday_snapshots for 2026-08-31...")
    request_write(
        "DELETE",
        "intraday_snapshots",
        params={"trading_date": f"eq.{dry.INVALID_DATE.isoformat()}"},
        prefer="return=minimal",
    )

    remaining = load_invalid_intraday_count()
    if remaining != 0:
        raise RuntimeError(
            f"Delete verification FAILED: {remaining} invalid intraday rows remain"
        )

    invalid_stock_after, target_stock_after = load_stock_state()
    if invalid_stock_after != 0 or target_stock_after != dry.EXPECTED_TOTAL:
        raise RuntimeError(
            "Final stock date verification FAILED: "
            f"invalid={invalid_stock_after}, target={target_stock_after}"
        )

    verify_stock_snapshot()

    print("=" * 72)
    print("RECOVERY COMPLETE")
    print("stock_snapshot: 800 rows restored to 2026-08-28 15:00")
    print("intraday_snapshots 2026-08-31: 0 rows")
    print("Golden Board 2026-08-28: preserved exactly")
    print("scan_runs: untouched")
    print(f"Local backup: {backup_dir}")
    print("=" * 72)


if __name__ == "__main__":
    main()
