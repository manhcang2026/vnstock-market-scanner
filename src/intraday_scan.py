from __future__ import annotations

import os

import pandas as pd
from vnstock import Trading

from common import (
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


DASHBOARD_COLUMNS = [
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


SNAPSHOT_COLUMNS = [
    "trading_date",
    "time_slot",
    "symbol",
    "exchange",
    "current_price",
    "volume_accumulated",
    "updated_at",
    "data_status",
]


def env_bool(name: str, default: bool = False) -> bool:
    """Đọc biến môi trường dạng boolean."""
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def fetch_price_board(
    symbols: list[str],
) -> pd.DataFrame:
    """Lấy bảng giá hiện tại từ vnstock."""
    data = Trading(
        source=SOURCE
    ).price_board(symbols)

    if (
        data is None
        or not isinstance(data, pd.DataFrame)
        or data.empty
    ):
        raise RuntimeError(
            "Price board rong hoac khong hop le"
        )

    required = {
        "symbol",
        "close_price",
        "volume_accumulated",
    }

    missing = required.difference(
        data.columns
    )

    if missing:
        raise RuntimeError(
            "Price board thieu cot "
            f"{sorted(missing)}; "
            f"hien co {list(data.columns)}"
        )

    df = data.copy()

    df["symbol"] = (
        df["symbol"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["close_price"] = pd.to_numeric(
        df["close_price"],
        errors="coerce",
    )

    df["volume_accumulated"] = (
        pd.to_numeric(
            df["volume_accumulated"],
            errors="coerce",
        )
    )

    if "exchange" in df.columns:
        df["exchange"] = (
            df["exchange"]
            .fillna("")
            .astype(str)
            .str.upper()
            .replace(
                {
                    "HSX": "HOSE",
                    "UPCO": "UPCOM",
                }
            )
        )

    return df.drop_duplicates(
        "symbol",
        keep="last",
    )


def build_rvol_reference(
    reference_rows: list[dict],
    start_slot: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chuẩn bị dữ liệu tham chiếu RVOL30."""
    ref = pd.DataFrame(reference_rows)

    if ref.empty:
        return (
            pd.DataFrame(
                columns=[
                    "symbol",
                    "start_volume_today",
                ]
            ),
            pd.DataFrame(
                columns=[
                    "symbol",
                    "avg_volume_30m_10",
                    "rvol30_sessions",
                ]
            ),
        )

    ref["volume_accumulated"] = (
        pd.to_numeric(
            ref["volume_accumulated"],
            errors="coerce",
        )
    )

    ref["trading_date"] = (
        ref["trading_date"]
        .astype(str)
    )

    ref["time_slot"] = (
        ref["time_slot"]
        .astype(str)
    )

    today = now_vn().date().isoformat()

    today_start = (
        ref[
            (ref["trading_date"] == today)
            & (
                ref["time_slot"]
                == start_slot
            )
        ][
            [
                "symbol",
                "volume_accumulated",
            ]
        ]
        .drop_duplicates(
            "symbol",
            keep="last",
        )
        .rename(
            columns={
                "volume_accumulated":
                    "start_volume_today"
            }
        )
    )

    historical = ref[
        ref["trading_date"] != today
    ].copy()

    pivot = historical.pivot_table(
        index=[
            "trading_date",
            "symbol",
        ],
        columns="time_slot",
        values="volume_accumulated",
        aggfunc="last",
    ).reset_index()

    return today_start, pivot


def calculate_rvol(
    scan: pd.DataFrame,
    reference_rows: list[dict],
    current_slot: str,
    start_slot: str | None,
) -> pd.DataFrame:
    """Tính RVOL30 trong giờ giao dịch."""
    output = scan[
        [
            "symbol",
            "volume_accumulated",
        ]
    ].copy()

    output["volume_30m"] = pd.NA
    output["avg_volume_30m_10"] = pd.NA
    output["rvol30_pct"] = pd.NA
    output["rvol30_sessions"] = 0

    if not start_slot:
        return output

    today_start, pivot = (
        build_rvol_reference(
            reference_rows,
            start_slot,
        )
    )

    output = output.merge(
        today_start,
        on="symbol",
        how="left",
    )

    output["volume_30m"] = (
        output["volume_accumulated"]
        - output["start_volume_today"]
    )

    output.loc[
        output["volume_30m"] < 0,
        "volume_30m",
    ] = pd.NA

    if (
        not pivot.empty
        and current_slot in pivot.columns
        and start_slot in pivot.columns
    ):
        pivot["historical_volume_30m"] = (
            pivot[current_slot]
            - pivot[start_slot]
        )

        pivot = pivot[
            pivot["historical_volume_30m"]
            >= 0
        ]

        stats = (
            pivot.groupby("symbol")[
                "historical_volume_30m"
            ]
            .agg(["mean", "count"])
            .reset_index()
        )

        stats = stats.rename(
            columns={
                "mean":
                    "avg_volume_30m_10",
                "count":
                    "rvol30_sessions",
            }
        )

        output = (
            output.drop(
                columns=[
                    "avg_volume_30m_10",
                    "rvol30_sessions",
                ]
            )
            .merge(
                stats,
                on="symbol",
                how="left",
            )
        )

        output["rvol30_sessions"] = (
            output["rvol30_sessions"]
            .fillna(0)
            .astype(int)
        )

        output["rvol30_pct"] = safe_pct(
            output["volume_30m"],
            output["avg_volume_30m_10"],
        )

    return output.drop(
        columns=["start_volume_today"],
        errors="ignore",
    )


def build_empty_rvol(
    scan: pd.DataFrame,
) -> pd.DataFrame:
    """
    RVOL rỗng cho lần force ngoài giờ.

    Không giả lập dữ liệu và không tự nhận
    có đủ số phiên tham chiếu.
    """
    output = scan[
        [
            "symbol",
            "volume_accumulated",
        ]
    ].copy()

    output["volume_30m"] = pd.NA
    output["avg_volume_30m_10"] = pd.NA
    output["rvol30_pct"] = pd.NA
    output["rvol30_sessions"] = 0

    return output


def main() -> None:
    scan_at = now_vn()

    force_run = env_bool(
        "FORCE_RUN",
        default=False,
    )

    in_market = is_market_slot(scan_at)

    forced_outside_session = (
        force_run and not in_market
    )

    if not in_market and not force_run:
        print(
            "Ngoai gio giao dich; bo qua."
        )
        return

    if forced_outside_session:
        print(
            "FORCE_RUN=true: "
            "chay kiem tra ngoai gio. "
            "Khong tinh tin hieu va "
            "khong ghi Intraday_Snapshots."
        )

    watchlist = load_watchlist()

    baseline_result = gas_request(
        "get_daily_baseline"
    )

    baseline = pd.DataFrame(
        baseline_result.get(
            "rows",
            [],
        )
    )

    if baseline.empty:
        raise RuntimeError(
            "Daily_Baseline dang rong. "
            "Hay chay job 01:00 truoc."
        )

    for column in [
        "previous_close",
        "ma10",
        "ma200",
        "avg_volume_10",
        "ma200_sessions",
        "avg_volume_sessions",
        "ma10_sessions",
    ]:
        if column in baseline.columns:
            baseline[column] = (
                pd.to_numeric(
                    baseline[column],
                    errors="coerce",
                )
            )

    price = fetch_price_board(
        watchlist["symbol"].tolist()
    )

    if in_market:
        current_slot, start_slot = (
            rvol_window_slots(scan_at)
        )

    else:
        # Chỉ là nhãn cho lần kiểm tra ngoài giờ.
        # Không dùng để tính hoặc lưu snapshot.
        current_slot = (
            scan_at.strftime("%H:%M")
        )
        start_slot = None

    result = watchlist.merge(
        price,
        on="symbol",
        how="left",
        suffixes=(
            "_watchlist",
            "_market",
        ),
    )

    result["exchange"] = result.get(
        "exchange_market",
        result.get(
            "exchange_watchlist",
            "",
        ),
    )

    result = result.drop(
        columns=[
            "exchange_watchlist",
            "exchange_market",
        ],
        errors="ignore",
    )

    result = result.merge(
        baseline,
        on="symbol",
        how="left",
        suffixes=(
            "",
            "_baseline",
        ),
    )

    if in_market:
        reference = []

        if start_slot:
            reference_result = gas_request(
                "get_rvol_reference",
                current_slot=current_slot,
                start_slot=start_slot,
                trading_date=(
                    scan_at.date().isoformat()
                ),
            )

            reference = reference_result.get(
                "rows",
                [],
            )

        rvol = calculate_rvol(
            result,
            reference,
            current_slot,
            start_slot,
        )

    else:
        rvol = build_empty_rvol(result)

    result = result.merge(
        rvol.drop(
            columns=[
                "volume_accumulated"
            ],
            errors="ignore",
        ),
        on="symbol",
        how="left",
    )

    result["price_change_pct"] = (
        result["close_price"]
        / result["previous_close"]
        - 1
    ) * 100

    result["daily_volume_pct"] = safe_pct(
        result["volume_accumulated"],
        result["avg_volume_10"],
    )

    result["ma200_distance_pct"] = (
        result["close_price"]
        / result["ma200"]
        - 1
    ) * 100

    # MA10 chi la chi so tham khao xu huong ngan han.
    # Khong dua cot nay vao signal_columns va signal_count.
    result["ma10_distance_pct"] = (
        result["close_price"]
        / result["ma10"]
        - 1
    ) * 100

    signal_columns = [
        "signal_price_3pct",
        "signal_daily_volume_200pct",
        "signal_above_ma200",
        "signal_rvol30_200pct",
    ]

    if in_market:
        result["signal_price_3pct"] = (
            result["price_change_pct"]
            >= PRICE_THRESHOLD_PCT
        )

        result[
            "signal_daily_volume_200pct"
        ] = (
            result["daily_volume_pct"]
            >= DAILY_VOLUME_THRESHOLD_PCT
        )

        result["signal_above_ma200"] = (
            result["close_price"]
            > result["ma200"]
        )

        result[
            "signal_rvol30_200pct"
        ] = (
            result["rvol30_pct"]
            >= RVOL30_THRESHOLD_PCT
        )

        result[signal_columns] = (
            result[signal_columns]
            .fillna(False)
            .astype(bool)
        )

        result["signal_count"] = (
            result[signal_columns]
            .sum(axis=1)
            .astype(int)
        )

    else:
        # Bảo vệ tuyệt đối cho dữ liệu force.
        # Không sinh tín hiệu ngoài giờ.
        for column in signal_columns:
            result[column] = False

        result["signal_count"] = 0

    result["trading_date"] = (
        scan_at.date().isoformat()
    )

    result["time_slot"] = current_slot

    result["updated_at"] = (
        scan_at.isoformat()
    )

    has_market_data = (
        result["close_price"].notna()
        & result[
            "volume_accumulated"
        ].notna()
    )

    if forced_outside_session:
        result["data_status"] = (
            "OUT_OF_SESSION_TEST"
        )

        result.loc[
            ~has_market_data,
            "data_status",
        ] = "MISSING_MARKET_DATA"

    else:
        result["data_status"] = (
            "MISSING_MARKET_DATA"
        )

        result.loc[
            has_market_data,
            "data_status",
        ] = "OK"

    result = result.rename(
        columns={
            "close_price":
                "current_price"
        }
    )

    for column in DASHBOARD_COLUMNS:
        if column not in result.columns:
            result[column] = None

    dashboard = (
        result[DASHBOARD_COLUMNS]
        .sort_values(
            [
                "signal_count",
                "rvol30_pct",
                "price_change_pct",
            ],
            ascending=[
                False,
                False,
                False,
            ],
            na_position="last",
        )
    )

    if forced_outside_session:
        # Không làm bẩn lịch sử dùng tính RVOL30.
        snapshots = pd.DataFrame(
            columns=SNAPSHOT_COLUMNS
        )

    else:
        snapshots = dashboard[
            SNAPSHOT_COLUMNS
        ].copy()

    failed = int(
        (
            dashboard["data_status"]
            == "MISSING_MARKET_DATA"
        ).sum()
    )

    successful = (
        len(watchlist) - failed
    )

    job_type = (
        "INTRADAY_FORCE_TEST"
        if forced_outside_session
        else "INTRADAY_SCAN"
    )

    run_status = (
        "SUCCESS"
        if failed == 0
        else "PARTIAL"
    )

    run_message = (
        "FORCED_OUT_OF_SESSION; "
        "signals_disabled=true; "
        "snapshots_written=0"
        if forced_outside_session
        else (
            f"slot={current_slot}; "
            f"rvol_start={start_slot}"
        )
    )

    response = gas_request(
        "update_intraday_scan",

        snapshots=records(snapshots),

        dashboard=records(dashboard),

        run_log={
            "run_id": scan_at.strftime(
                "intraday-%Y%m%d-%H%M%S"
            ),

            "job_type": job_type,

            "started_at":
                scan_at.isoformat(),

            "finished_at":
                now_vn().isoformat(),

            "status": run_status,

            "symbols_requested":
                len(watchlist),

            "symbols_success":
                successful,

            "symbols_failed":
                failed,

            "message":
                run_message,
        },
    )

    print(response)


if __name__ == "__main__":
    main()
