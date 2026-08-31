from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests

TARGET_DATE = date(2026, 8, 28)
INVALID_DATE = date(2026, 8, 31)
LOOKBACK_DAYS = 35

EXPECTED_TOTAL = 800
EXPECTED_SIGNAL_4 = 3
EXPECTED_SIGNAL_GE3 = 21
EXPECTED_SIGNAL_GE2 = 89
EXPECTED_RVOL200 = 137
EXPECTED_4_SYMBOLS = ["BVS", "SSB", "TLP"]

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SECRET_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)
PAGE_SIZE = 1000
TIMEOUT = 60


def headers() -> dict[str, str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "Missing SUPABASE_URL and SUPABASE_SECRET_KEY/SUPABASE_SERVICE_ROLE_KEY"
        )
    result = {"apikey": SUPABASE_KEY}
    if not SUPABASE_KEY.startswith("sb_secret_"):
        result["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return result


def get_page(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers(),
        params=params,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise RuntimeError(f"{table} did not return a JSON list")
    return rows


def get_all(
    table: str,
    params: dict[str, str],
    *,
    page_size: int = PAGE_SIZE,
    max_pages: int = 100,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(max_pages):
        page_params = dict(params)
        page_params["limit"] = str(page_size)
        page_params["offset"] = str(page * page_size)
        part = get_page(table, page_params)
        rows.extend(part)
        if len(part) < page_size:
            return rows
    raise RuntimeError(f"{table} exceeded safe pagination limit ({max_pages} pages)")


def norm_symbol(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.upper()


def num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = num(denominator)
    numerator = num(numerator)
    return numerator.div(denominator.where(denominator > 0)).mul(100)


def load_target_eod(target: date) -> pd.DataFrame:
    rows = get_all(
        "intraday_snapshots",
        {
            "select": (
                "symbol,exchange,current_price,volume_accumulated,"
                "trading_date,time_slot,updated_at"
            ),
            "trading_date": f"eq.{target.isoformat()}",
            "time_slot": "eq.15:00:00",
            "order": "symbol.asc,updated_at.desc",
        },
    )
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"No EOD rows for {target}")
    df["symbol"] = norm_symbol(df["symbol"])
    df = df[df["symbol"] != ""].drop_duplicates("symbol", keep="first")
    df["current_price"] = num(df["current_price"])
    df["volume_accumulated"] = num(df["volume_accumulated"])
    return df


def load_baseline_as_of(target: date) -> pd.DataFrame:
    start = target - timedelta(days=90)
    rows = get_all(
        "daily_baseline",
        {
            "select": (
                "symbol,exchange,trading_date,previous_close,"
                "ma10,ma10_sessions,ma200,ma200_sessions,"
                "avg_volume_10,avg_volume_sessions,updated_at"
            ),
            "and": (
                f"(trading_date.lt.{target.isoformat()},"
                f"trading_date.gte.{start.isoformat()})"
            ),
            "order": "symbol.asc,trading_date.desc,updated_at.desc",
        },
        max_pages=100,
    )
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No historical daily_baseline rows")
    df["symbol"] = norm_symbol(df["symbol"])
    df = df[df["symbol"] != ""]
    df["trading_date"] = pd.to_datetime(df["trading_date"], errors="coerce")
    df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce", utc=True)
    df = df.sort_values(
        ["symbol", "trading_date", "updated_at"],
        ascending=[True, False, False],
        na_position="last",
    ).drop_duplicates("symbol", keep="first")

    for column in [
        "previous_close",
        "ma10",
        "ma10_sessions",
        "ma200",
        "ma200_sessions",
        "avg_volume_10",
        "avg_volume_sessions",
    ]:
        df[column] = num(df[column])
    return df


def load_rvol_raw(target: date) -> pd.DataFrame:
    start = target - timedelta(days=LOOKBACK_DAYS)
    rows = get_all(
        "intraday_snapshots",
        {
            "select": (
                "trading_date,time_slot,symbol,volume_accumulated"
            ),
            "and": (
                f"(trading_date.gte.{start.isoformat()},"
                f"trading_date.lte.{target.isoformat()})"
            ),
            "time_slot": "in.(14:15:00,14:30:00,14:45:00,15:00:00)",
            "order": "trading_date.asc,time_slot.asc,symbol.asc",
        },
        max_pages=100,
    )
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No raw snapshots for RVOL reconstruction")
    df["symbol"] = norm_symbol(df["symbol"])
    df["trading_date"] = pd.to_datetime(df["trading_date"], errors="coerce").dt.date
    df["time_slot"] = df["time_slot"].astype(str).str.slice(0, 5)
    df["volume_accumulated"] = num(df["volume_accumulated"])
    return df


def build_rvol(
    eod: pd.DataFrame,
    raw: pd.DataFrame,
    target: date,
) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []

    for exchange, group in eod.groupby("exchange", dropna=False):
        ex = str(exchange or "").strip().upper()
        if ex in {"HOSE", "HSX", "HNX"}:
            start_slot, end_slot = "14:15", "14:45"
        else:
            start_slot, end_slot = "14:30", "15:00"

        symbols = set(group["symbol"])
        subset = raw[raw["symbol"].isin(symbols)].copy()

        start_rows = subset[subset["time_slot"] == start_slot][
            ["trading_date", "symbol", "volume_accumulated"]
        ].rename(columns={"volume_accumulated": "start_volume"})
        end_rows = subset[subset["time_slot"] == end_slot][
            ["trading_date", "symbol", "volume_accumulated"]
        ].rename(columns={"volume_accumulated": "end_volume"})

        windows = start_rows.merge(
            end_rows,
            on=["trading_date", "symbol"],
            how="inner",
        )
        windows["volume_30m"] = windows["end_volume"] - windows["start_volume"]
        windows = windows[windows["volume_30m"] >= 0]

        current = windows[windows["trading_date"] == target][
            ["symbol", "volume_30m"]
        ].drop_duplicates("symbol", keep="last")

        hist = windows[windows["trading_date"] < target].copy()
        hist = hist.sort_values(
            ["symbol", "trading_date"],
            ascending=[True, False],
        )
        hist["rank"] = hist.groupby("symbol").cumcount() + 1
        hist = hist[hist["rank"] <= 10]

        avg = hist.groupby("symbol", as_index=False).agg(
            avg_volume_30m_10=("volume_30m", "mean"),
            historical_sessions=("volume_30m", "count"),
        )

        part = group[["symbol"]].merge(current, on="symbol", how="left")
        part = part.merge(avg, on="symbol", how="left")
        part["historical_sessions"] = (
            num(part["historical_sessions"]).fillna(0).clip(0, 10).astype(int)
        )
        part["rvol30_sessions"] = (
            part["historical_sessions"]
            + part["volume_30m"].notna().astype(int)
        ).clip(upper=10).astype(int)
        part["rvol30_pct"] = pct(
            part["volume_30m"],
            part["avg_volume_30m_10"],
        )
        pieces.append(part)

    return pd.concat(pieces, ignore_index=True)


def reconstruct(target: date) -> pd.DataFrame:
    eod = load_target_eod(target)
    baseline = load_baseline_as_of(target)
    raw = load_rvol_raw(target)
    rvol = build_rvol(eod, raw, target)

    df = eod.merge(
        baseline[
            [
                "symbol",
                "trading_date",
                "previous_close",
                "ma10",
                "ma10_sessions",
                "ma200",
                "ma200_sessions",
                "avg_volume_10",
                "avg_volume_sessions",
            ]
        ].rename(columns={"trading_date": "baseline_trading_date"}),
        on="symbol",
        how="left",
    )
    df = df.merge(rvol, on="symbol", how="left")

    df["price_change_pct"] = (
        num(df["current_price"])
        .div(num(df["previous_close"]).where(num(df["previous_close"]) > 0))
        .sub(1)
        .mul(100)
    )
    df["daily_volume_pct"] = pct(
        df["volume_accumulated"],
        df["avg_volume_10"],
    )
    df["ma200_distance_pct"] = (
        num(df["current_price"])
        .div(num(df["ma200"]).where(num(df["ma200"]) > 0))
        .sub(1)
        .mul(100)
    )
    df["ma10_distance_pct"] = (
        num(df["current_price"])
        .div(num(df["ma10"]).where(num(df["ma10"]) > 0))
        .sub(1)
        .mul(100)
    )

    df["signal_price_3pct"] = df["price_change_pct"] >= 3.0
    df["signal_daily_volume_200pct"] = df["daily_volume_pct"] >= 200.0
    df["signal_above_ma200"] = num(df["current_price"]) > num(df["ma200"])
    df["signal_rvol30_200pct"] = df["rvol30_pct"] >= 200.0

    signal_cols = [
        "signal_price_3pct",
        "signal_daily_volume_200pct",
        "signal_above_ma200",
        "signal_rvol30_200pct",
    ]
    df[signal_cols] = df[signal_cols].fillna(False).astype(bool)
    df["signal_count"] = df[signal_cols].sum(axis=1).astype(int)
    return df


def load_golden_board(target: date) -> pd.DataFrame:
    rows = get_all(
        "golden_board_daily",
        {
            "select": (
                "symbol,trading_date,latest_signal_count,"
                "latest_observed_slot,last_hit_slot"
            ),
            "trading_date": f"eq.{target.isoformat()}",
            "order": "symbol.asc",
        },
    )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["symbol"] = norm_symbol(df["symbol"])
        df["latest_signal_count"] = num(df["latest_signal_count"]).fillna(-1).astype(int)
    return df


def compare_invalid_to_target(target: date, invalid: date) -> dict[str, int | float]:
    target_eod = load_target_eod(target)
    invalid_eod = load_target_eod(invalid)

    m = invalid_eod[
        ["symbol", "current_price", "volume_accumulated"]
    ].merge(
        target_eod[
            ["symbol", "current_price", "volume_accumulated"]
        ],
        on="symbol",
        suffixes=("_invalid", "_target"),
    )

    same_price = (
        num(m["current_price_invalid"]) == num(m["current_price_target"])
    )
    same_volume = (
        num(m["volume_accumulated_invalid"])
        == num(m["volume_accumulated_target"])
    )
    same_both = same_price & same_volume

    fake_rows = get_all(
        "intraday_snapshots",
        {
            "select": "symbol",
            "trading_date": f"eq.{invalid.isoformat()}",
            "order": "symbol.asc",
        },
        max_pages=100,
    )
    fake_stock = get_all(
        "stock_snapshot",
        {
            "select": "symbol",
            "trading_date": f"eq.{invalid.isoformat()}",
            "order": "symbol.asc",
        },
    )

    return {
        "invalid_intraday_rows": len(fake_rows),
        "invalid_stock_snapshot_rows": len(fake_stock),
        "eod_comparable": len(m),
        "eod_identical_both": int(same_both.sum()),
        "eod_identical_ratio": float(same_both.mean()) if len(m) else 0.0,
    }


def main() -> None:
    print("=" * 72)
    print("STAGE 2 RECOVERY DRY RUN — READ ONLY")
    print("No INSERT / UPDATE / DELETE method exists in this script.")
    print("=" * 72)

    reconstructed = reconstruct(TARGET_DATE)

    total = len(reconstructed)
    k4 = int((reconstructed["signal_count"] == 4).sum())
    ge3 = int((reconstructed["signal_count"] >= 3).sum())
    ge2 = int((reconstructed["signal_count"] >= 2).sum())
    rvol200 = int(reconstructed["signal_rvol30_200pct"].sum())
    four_symbols = sorted(
        reconstructed.loc[
            reconstructed["signal_count"] == 4,
            "symbol",
        ].tolist()
    )

    missing_baseline = int(reconstructed["previous_close"].isna().sum())
    missing_rvol = int(reconstructed["rvol30_pct"].isna().sum())

    print(f"Target session:           {TARGET_DATE}")
    print(f"Reconstructed rows:      {total}")
    print("Baseline policy:         latest row strictly BEFORE target session")
    print(f"Missing baseline:        {missing_baseline}")
    print(f"Missing RVOL value:      {missing_rvol}")
    print(f"4/4:                     {k4}")
    print(f">=3 signals:             {ge3}")
    print(f">=2 signals:             {ge2}")
    print(f"RVOL30 >= 200%:          {rvol200}")
    print(f"4/4 symbols:             {','.join(four_symbols)}")

    gb = load_golden_board(TARGET_DATE)
    gb_eod = sorted(
        gb.loc[gb["latest_signal_count"] == 4, "symbol"].tolist()
    ) if not gb.empty else []
    print(f"Golden Board EOD 4/4:    {','.join(gb_eod) or '-'}")

    contamination = compare_invalid_to_target(TARGET_DATE, INVALID_DATE)
    print("-" * 72)
    print(f"Invalid session:         {INVALID_DATE}")
    print(
        "Intraday fake rows:      "
        f"{contamination['invalid_intraday_rows']}"
    )
    print(
        "Fake stock_snapshot:     "
        f"{contamination['invalid_stock_snapshot_rows']}"
    )
    print(
        "EOD identical price+vol: "
        f"{contamination['eod_identical_both']}/"
        f"{contamination['eod_comparable']} "
        f"({contamination['eod_identical_ratio']:.2%})"
    )

    failures: list[str] = []
    if total != EXPECTED_TOTAL:
        failures.append(f"rows expected {EXPECTED_TOTAL}, got {total}")
    if missing_baseline != 0:
        failures.append(f"missing baseline = {missing_baseline}")
    if k4 != EXPECTED_SIGNAL_4:
        failures.append(f"4/4 expected {EXPECTED_SIGNAL_4}, got {k4}")
    if ge3 != EXPECTED_SIGNAL_GE3:
        failures.append(f">=3 expected {EXPECTED_SIGNAL_GE3}, got {ge3}")
    if ge2 != EXPECTED_SIGNAL_GE2:
        failures.append(f">=2 expected {EXPECTED_SIGNAL_GE2}, got {ge2}")
    if rvol200 != EXPECTED_RVOL200:
        failures.append(f"RVOL200 expected {EXPECTED_RVOL200}, got {rvol200}")
    if four_symbols != EXPECTED_4_SYMBOLS:
        failures.append(
            f"4/4 symbols expected {EXPECTED_4_SYMBOLS}, got {four_symbols}"
        )
    if gb_eod and gb_eod != EXPECTED_4_SYMBOLS:
        failures.append(
            f"Golden Board EOD expected {EXPECTED_4_SYMBOLS}, got {gb_eod}"
        )
    if contamination["eod_comparable"] != EXPECTED_TOTAL:
        failures.append(
            f"invalid EOD comparable expected {EXPECTED_TOTAL}, "
            f"got {contamination['eod_comparable']}"
        )
    if contamination["eod_identical_ratio"] < 0.995:
        failures.append(
            "invalid session is not >=99.5% identical to target EOD"
        )

    print("=" * 72)
    if failures:
        print("DRY RUN FAILED — NOTHING WAS WRITTEN")
        for item in failures:
            print(f" - {item}")
        raise SystemExit(2)

    print("DRY RUN PASS — NOTHING WAS WRITTEN")
    print("Safe to prepare a SEPARATE Stage 2B write package.")
    print("=" * 72)


if __name__ == "__main__":
    main()
