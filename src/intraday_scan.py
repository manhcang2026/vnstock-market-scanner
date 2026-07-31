from __future__ import annotations

import pandas as pd
from vnstock import Trading

from common import (
    floor_slot,
    gas_request,
    is_market_slot,
    load_watchlist,
    now_vn,
    records,
    rvol_window_slots,
    safe_pct,
)

SOURCE = "KBS"
PRICE_THRESHOLD_PCT = 3.0
DAILY_VOLUME_THRESHOLD_PCT = 200.0
RVOL30_THRESHOLD_PCT = 200.0


def fetch_price_board(symbols: list[str]) -> pd.DataFrame:
    data = Trading(source=SOURCE).price_board(symbols)
    if data is None or not isinstance(data, pd.DataFrame) or data.empty:
        raise RuntimeError("Price board rong hoac khong hop le")
    required = {"symbol", "close_price", "volume_accumulated"}
    missing = required.difference(data.columns)
    if missing:
        raise RuntimeError(f"Price board thieu cot {sorted(missing)}; hien co {list(data.columns)}")
    df = data.copy()
    df["symbol"] = df["symbol"].fillna("").astype(str).str.strip().str.upper()
    df["close_price"] = pd.to_numeric(df["close_price"], errors="coerce")
    df["volume_accumulated"] = pd.to_numeric(df["volume_accumulated"], errors="coerce")
    if "exchange" in df.columns:
        df["exchange"] = df["exchange"].fillna("").astype(str).str.upper().replace({"HSX": "HOSE"})
    return df.drop_duplicates("symbol", keep="last")


def build_rvol_reference(reference_rows: list[dict], start_slot: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    ref = pd.DataFrame(reference_rows)
    if ref.empty:
        return pd.DataFrame(columns=["symbol", "start_volume_today"]), pd.DataFrame(columns=["symbol", "avg_volume_30m_10", "rvol30_sessions"])
    for col in ["volume_accumulated"]:
        ref[col] = pd.to_numeric(ref[col], errors="coerce")
    ref["trading_date"] = ref["trading_date"].astype(str)
    today = now_vn().date().isoformat()

    today_start = (
        ref[(ref["trading_date"] == today) & (ref["time_slot"] == start_slot)][["symbol", "volume_accumulated"]]
        .drop_duplicates("symbol", keep="last")
        .rename(columns={"volume_accumulated": "start_volume_today"})
    )

    historical = ref[ref["trading_date"] != today].copy()
    pivot = historical.pivot_table(
        index=["trading_date", "symbol"],
        columns="time_slot",
        values="volume_accumulated",
        aggfunc="last",
    ).reset_index()
    return today_start, pivot


def calculate_rvol(scan: pd.DataFrame, reference_rows: list[dict], current_slot: str, start_slot: str | None) -> pd.DataFrame:
    output = scan[["symbol", "volume_accumulated"]].copy()
    output["volume_30m"] = pd.NA
    output["avg_volume_30m_10"] = pd.NA
    output["rvol30_pct"] = pd.NA
    output["rvol30_sessions"] = 0
    if not start_slot:
        return output

    today_start, pivot = build_rvol_reference(reference_rows, start_slot)
    output = output.merge(today_start, on="symbol", how="left")
    output["volume_30m"] = output["volume_accumulated"] - output["start_volume_today"]
    output.loc[output["volume_30m"] < 0, "volume_30m"] = pd.NA

    if not pivot.empty and current_slot in pivot.columns and start_slot in pivot.columns:
        pivot["historical_volume_30m"] = pivot[current_slot] - pivot[start_slot]
        pivot = pivot[pivot["historical_volume_30m"] >= 0]
        stats = pivot.groupby("symbol")["historical_volume_30m"].agg(["mean", "count"]).reset_index()
        stats = stats.rename(columns={"mean": "avg_volume_30m_10", "count": "rvol30_sessions"})
        output = output.drop(columns=["avg_volume_30m_10", "rvol30_sessions"]).merge(stats, on="symbol", how="left")
        output["rvol30_sessions"] = output["rvol30_sessions"].fillna(0).astype(int)
        output["rvol30_pct"] = safe_pct(output["volume_30m"], output["avg_volume_30m_10"])
    return output.drop(columns=["start_volume_today"], errors="ignore")


def main() -> None:
    scan_at = now_vn()
    if not is_market_slot(scan_at):
        print("Ngoai gio giao dich; bo qua.")
        return

    watchlist = load_watchlist()
    baseline_result = gas_request("get_daily_baseline")
    baseline = pd.DataFrame(baseline_result.get("rows", []))
    if baseline.empty:
        raise RuntimeError("Daily_Baseline dang rong. Hay chay job 01:00 truoc.")
    for col in ["previous_close", "ma200", "avg_volume_10"]:
        baseline[col] = pd.to_numeric(baseline[col], errors="coerce")

    price = fetch_price_board(watchlist["symbol"].tolist())
    current_slot, start_slot = rvol_window_slots(scan_at)
    reference = gas_request(
        "get_rvol_reference",
        current_slot=current_slot,
        start_slot=start_slot,
        trading_date=scan_at.date().isoformat(),
    ).get("rows", []) if start_slot else []

    result = watchlist.merge(price, on="symbol", how="left", suffixes=("_watchlist", "_market"))
    result["exchange"] = result.get("exchange_market", result.get("exchange_watchlist", ""))
    result = result.drop(columns=["exchange_watchlist", "exchange_market"], errors="ignore")
    result = result.merge(baseline, on="symbol", how="left", suffixes=("", "_baseline"))

    rvol = calculate_rvol(result, reference, current_slot, start_slot)
    result = result.merge(rvol.drop(columns=["volume_accumulated"]), on="symbol", how="left")

    result["price_change_pct"] = (result["close_price"] / result["previous_close"] - 1) * 100
    result["daily_volume_pct"] = safe_pct(result["volume_accumulated"], result["avg_volume_10"])
    result["ma200_distance_pct"] = (result["close_price"] / result["ma200"] - 1) * 100

    result["signal_price_3pct"] = result["price_change_pct"] >= PRICE_THRESHOLD_PCT
    result["signal_daily_volume_200pct"] = result["daily_volume_pct"] >= DAILY_VOLUME_THRESHOLD_PCT
    result["signal_above_ma200"] = result["close_price"] > result["ma200"]
    result["signal_rvol30_200pct"] = result["rvol30_pct"] >= RVOL30_THRESHOLD_PCT
    signal_cols = ["signal_price_3pct", "signal_daily_volume_200pct", "signal_above_ma200", "signal_rvol30_200pct"]
    result[signal_cols] = result[signal_cols].fillna(False).astype(bool)
    result["signal_count"] = result[signal_cols].sum(axis=1).astype(int)
    result["trading_date"] = scan_at.date().isoformat()
    result["time_slot"] = current_slot
    result["updated_at"] = scan_at.isoformat()
    result["data_status"] = result.apply(
        lambda row: "OK" if pd.notna(row.get("close_price")) and pd.notna(row.get("volume_accumulated")) else "MISSING_MARKET_DATA",
        axis=1,
    )

    dashboard_columns = [
        "symbol", "exchange", "current_price", "previous_close", "price_change_pct",
        "volume_accumulated", "avg_volume_10", "avg_volume_sessions", "daily_volume_pct",
        "ma200", "ma200_sessions", "ma200_distance_pct",
        "volume_30m", "avg_volume_30m_10", "rvol30_pct", "rvol30_sessions",
        "signal_price_3pct", "signal_daily_volume_200pct", "signal_above_ma200",
        "signal_rvol30_200pct", "signal_count", "trading_date", "time_slot", "updated_at", "data_status",
    ]
    result = result.rename(columns={"close_price": "current_price"})
    for col in dashboard_columns:
        if col not in result.columns:
            result[col] = None
    dashboard = result[dashboard_columns].sort_values(
        ["signal_count", "rvol30_pct", "price_change_pct"], ascending=[False, False, False], na_position="last"
    )
    snapshots = dashboard[["trading_date", "time_slot", "symbol", "exchange", "current_price", "volume_accumulated", "updated_at", "data_status"]]

    failed = int((dashboard["data_status"] != "OK").sum())
    response = gas_request(
        "update_intraday_scan",
        snapshots=records(snapshots),
        dashboard=records(dashboard),
        run_log={
            "run_id": scan_at.strftime("intraday-%Y%m%d-%H%M%S"),
            "job_type": "INTRADAY_SCAN",
            "started_at": scan_at.isoformat(),
            "finished_at": now_vn().isoformat(),
            "status": "SUCCESS" if failed == 0 else "PARTIAL",
            "symbols_requested": len(watchlist),
            "symbols_success": len(watchlist) - failed,
            "symbols_failed": failed,
            "message": f"slot={current_slot}; rvol_start={start_slot}",
        },
    )
    print(response)


if __name__ == "__main__":
    main()
