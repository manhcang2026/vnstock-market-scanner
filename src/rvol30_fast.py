from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from common import normalize_exchange_value, rvol_window_slots, safe_pct

SupabaseRequest = Callable[..., Any]

RVOL_COLUMNS = [
    "volume_30m",
    "avg_volume_30m_10",
    "rvol30_pct",
    "rvol30_sessions",
]


def _db_time(slot: str) -> str:
    slot = str(slot or "").strip()
    return f"{slot}:00" if len(slot) == 5 else slot


def _empty_rvol(scan: pd.DataFrame) -> pd.DataFrame:
    output = scan[["symbol", "volume_accumulated"]].copy()
    output["volume_30m"] = pd.NA
    output["avg_volume_30m_10"] = pd.NA
    output["rvol30_pct"] = pd.NA
    output["rvol30_sessions"] = 0
    return output


def _load_baseline(
    supabase_request: SupabaseRequest,
    start_slot: str,
    end_slot: str,
) -> pd.DataFrame:
    response = supabase_request(
        "GET",
        "rvol30_baseline",
        params={
            "select": (
                "symbol,avg_volume_30m_10,historical_sessions,"
                "latest_trading_date"
            ),
            "start_slot": f"eq.{_db_time(start_slot)}",
            "end_slot": f"eq.{_db_time(end_slot)}",
            "order": "symbol.asc",
            "limit": "1000",
        },
    )
    rows = response.json()
    if not isinstance(rows, list):
        raise RuntimeError("Supabase rvol30_baseline khong tra ve danh sach rows")

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "avg_volume_30m_10",
                "historical_sessions",
                "latest_trading_date",
            ]
        )

    df["symbol"] = df["symbol"].fillna("").astype(str).str.strip().str.upper()
    df["avg_volume_30m_10"] = pd.to_numeric(
        df["avg_volume_30m_10"], errors="coerce"
    )
    df["historical_sessions"] = (
        pd.to_numeric(df["historical_sessions"], errors="coerce")
        .fillna(0)
        .clip(lower=0, upper=10)
        .astype(int)
    )
    df = df[df["symbol"] != ""].drop_duplicates("symbol", keep="first")
    print(
        f"RVOL baseline {start_slot}->{end_slot}: {len(df)} ma "
        "(doc bang baseline da tinh san)."
    )
    return df


def _load_today_slot(
    supabase_request: SupabaseRequest,
    trading_date: str,
    slot: str,
    output_column: str,
) -> pd.DataFrame:
    response = supabase_request(
        "GET",
        "intraday_snapshots",
        params={
            "select": "symbol,volume_accumulated",
            "trading_date": f"eq.{trading_date}",
            "time_slot": f"eq.{_db_time(slot)}",
            "order": "symbol.asc",
            "limit": "1000",
        },
    )
    rows = response.json()
    if not isinstance(rows, list):
        raise RuntimeError("Supabase intraday_snapshots khong tra ve danh sach rows")

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["symbol", output_column])

    df["symbol"] = df["symbol"].fillna("").astype(str).str.strip().str.upper()
    df["volume_accumulated"] = pd.to_numeric(
        df["volume_accumulated"], errors="coerce"
    )
    df = (
        df[df["symbol"] != ""]
        .drop_duplicates("symbol", keep="last")
        .rename(columns={"volume_accumulated": output_column})
    )
    print(f"RVOL snapshot hom nay {slot}: {len(df)} ma.")
    return df[["symbol", output_column]]


def _calculate_group(
    scan: pd.DataFrame,
    baseline: pd.DataFrame,
    today_start: pd.DataFrame,
    today_end: pd.DataFrame | None,
    *,
    current_slot: str,
    live_snapshot_slot: str,
) -> pd.DataFrame:
    output = scan[["symbol", "volume_accumulated"]].copy()
    output = output.merge(today_start, on="symbol", how="left")

    if current_slot == live_snapshot_slot:
        output["end_volume_for_rvol"] = output["volume_accumulated"]
    else:
        if today_end is None:
            today_end = pd.DataFrame(columns=["symbol", "end_volume_today"])
        output = output.merge(today_end, on="symbol", how="left")
        output["end_volume_for_rvol"] = output["end_volume_today"]

    output["volume_30m"] = (
        pd.to_numeric(output["end_volume_for_rvol"], errors="coerce")
        - pd.to_numeric(output["start_volume_today"], errors="coerce")
    )
    output.loc[output["volume_30m"] < 0, "volume_30m"] = pd.NA

    output = output.merge(
        baseline[
            ["symbol", "avg_volume_30m_10", "historical_sessions"]
        ],
        on="symbol",
        how="left",
    )
    output["historical_sessions"] = (
        pd.to_numeric(output["historical_sessions"], errors="coerce")
        .fillna(0)
        .clip(lower=0, upper=10)
        .astype(int)
    )

    # Keep the existing UI semantics: current valid session is included in x/10,
    # but it is NEVER included in the historical average used as denominator.
    current_valid = output["volume_30m"].notna().astype(int)
    output["rvol30_sessions"] = (
        output["historical_sessions"] + current_valid
    ).clip(upper=10).astype(int)
    output["rvol30_pct"] = safe_pct(
        output["volume_30m"], output["avg_volume_30m_10"]
    )

    return output.drop(
        columns=[
            "start_volume_today",
            "end_volume_today",
            "end_volume_for_rvol",
            "historical_sessions",
        ],
        errors="ignore",
    )


def calculate_rvol_by_exchange_fast(
    result: pd.DataFrame,
    scan_at,
    live_snapshot_slot: str,
    supabase_request: SupabaseRequest,
) -> tuple[pd.DataFrame, dict[str, tuple[str | None, str | None]]]:
    """Fast RVOL30 path for 800+ symbols.

    Instead of downloading 35 calendar days of raw snapshots every 5 minutes,
    this function reads:
      1) one precomputed rvol30_baseline row per symbol for the active window;
      2) today's start snapshot for that window;
      3) today's fixed end snapshot only when HOSE/HNX are capped at 14:45.

    Historical raw snapshots remain untouched in Supabase.
    """
    pieces: list[pd.DataFrame] = []
    windows: dict[str, tuple[str | None, str | None]] = {}
    baseline_cache: dict[tuple[str, str], pd.DataFrame] = {}
    today_slot_cache: dict[tuple[str, str], pd.DataFrame] = {}
    trading_date = scan_at.date().isoformat()

    for exchange, group in result.groupby("exchange", dropna=False, sort=False):
        normalized_exchange = normalize_exchange_value(exchange)
        current_slot, start_slot = rvol_window_slots(scan_at, normalized_exchange)
        windows[normalized_exchange or "UNKNOWN"] = (current_slot, start_slot)

        if not start_slot or not current_slot:
            pieces.append(_empty_rvol(group))
            continue

        pair_key = (start_slot, current_slot)
        if pair_key not in baseline_cache:
            baseline_cache[pair_key] = _load_baseline(
                supabase_request, start_slot, current_slot
            )

        start_key = (trading_date, start_slot)
        if start_key not in today_slot_cache:
            today_slot_cache[start_key] = _load_today_slot(
                supabase_request,
                trading_date,
                start_slot,
                "start_volume_today",
            )

        today_end = None
        if current_slot != live_snapshot_slot:
            end_key = (trading_date, current_slot)
            if end_key not in today_slot_cache:
                today_slot_cache[end_key] = _load_today_slot(
                    supabase_request,
                    trading_date,
                    current_slot,
                    "end_volume_today",
                )
            today_end = today_slot_cache[end_key]

        pieces.append(
            _calculate_group(
                group,
                baseline_cache[pair_key],
                today_slot_cache[start_key],
                today_end,
                current_slot=current_slot,
                live_snapshot_slot=live_snapshot_slot,
            )
        )

    if not pieces:
        return _empty_rvol(result), windows
    return pd.concat(pieces, ignore_index=True), windows
