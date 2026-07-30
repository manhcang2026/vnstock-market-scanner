from datetime import datetime, time
from pathlib import Path
from time import perf_counter

import pandas as pd
from zoneinfo import ZoneInfo
from vnstock import Trading


# ============================================================
# PHAN 01 - CAU HINH
# ============================================================

TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

WATCHLIST_FILE = Path("config/watchlist.csv")
DAILY_INDICATORS_FILE = Path("data/daily_indicators.csv")

DATA_DIR = Path("data")

LATEST_SNAPSHOT_FILE = DATA_DIR / "latest_snapshot.csv"
MARKET_SCAN_FILE = DATA_DIR / "market_scan_latest.csv"
LATEST_SIGNALS_FILE = DATA_DIR / "signals_latest.csv"

SOURCE = "KBS"

PRICE_SURGE_THRESHOLD_PCT = 3.0
RVOL_THRESHOLD = 2.0

MORNING_START = time(9, 0)
MORNING_END = time(11, 30)

AFTERNOON_START = time(13, 0)
AFTERNOON_END = time(15, 0)

MORNING_SESSION_MINUTES = 150
AFTERNOON_SESSION_MINUTES = 120
TOTAL_SESSION_MINUTES = 270


# ============================================================
# PHAN 02 - HAM CHUNG
# ============================================================

def normalize_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series,
        errors="coerce",
    )


def load_watchlist() -> pd.DataFrame:
    if not WATCHLIST_FILE.exists():
        raise FileNotFoundError(
            f"Khong tim thay watchlist: {WATCHLIST_FILE}"
        )

    watchlist = pd.read_csv(WATCHLIST_FILE)

    required_columns = {
        "symbol",
        "exchange",
    }

    missing_columns = required_columns.difference(
        watchlist.columns
    )

    if missing_columns:
        raise RuntimeError(
            f"Watchlist thieu cot: {sorted(missing_columns)}"
        )

    watchlist = watchlist.copy()

    watchlist["symbol"] = normalize_text(
        watchlist["symbol"]
    )

    watchlist["exchange"] = normalize_text(
        watchlist["exchange"]
    )

    watchlist = watchlist[
        watchlist["symbol"] != ""
    ].drop_duplicates(
        subset=["symbol"],
        keep="first",
    )

    return watchlist.reset_index(drop=True)


def load_daily_indicators() -> pd.DataFrame:
    if not DAILY_INDICATORS_FILE.exists():
        raise FileNotFoundError(
            "Khong tim thay du lieu MA200 va KLTB10: "
            f"{DAILY_INDICATORS_FILE}"
        )

    indicators = pd.read_csv(
        DAILY_INDICATORS_FILE
    )

    required_columns = {
        "symbol",
        "ma200",
        "ma200_status",
        "avg_volume_10",
        "avg_volume_10_status",
    }

    missing_columns = required_columns.difference(
        indicators.columns
    )

    if missing_columns:
        raise RuntimeError(
            "Daily indicators thieu cot: "
            f"{sorted(missing_columns)}"
        )

    indicators = indicators.copy()

    indicators["symbol"] = normalize_text(
        indicators["symbol"]
    )

    indicators["ma200"] = to_numeric(
        indicators["ma200"]
    )

    indicators["avg_volume_10"] = to_numeric(
        indicators["avg_volume_10"]
    )

    indicators["latest_close"] = to_numeric(
        indicators.get(
            "latest_close",
            pd.Series(index=indicators.index, dtype=float),
        )
    )

    indicators["ma200_status"] = normalize_text(
        indicators["ma200_status"]
    )

    indicators["avg_volume_10_status"] = normalize_text(
        indicators["avg_volume_10_status"]
    )

    keep_columns = [
        "symbol",
        "latest_date",
        "latest_close",
        "ma200",
        "ma200_status",
        "avg_volume_10",
        "avg_volume_10_status",
    ]

    keep_columns = [
        column
        for column in keep_columns
        if column in indicators.columns
    ]

    return indicators[
        keep_columns
    ].drop_duplicates(
        subset=["symbol"],
        keep="last",
    )


def get_session_elapsed_minutes(
    current_datetime: datetime,
) -> int:
    current_time = current_datetime.time()

    if current_time < MORNING_START:
        return 0

    if MORNING_START <= current_time <= MORNING_END:
        morning_start_datetime = datetime.combine(
            current_datetime.date(),
            MORNING_START,
            tzinfo=TIMEZONE,
        )

        elapsed = (
            current_datetime
            - morning_start_datetime
        ).total_seconds() / 60

        return max(
            0,
            min(
                MORNING_SESSION_MINUTES,
                int(elapsed),
            ),
        )

    if MORNING_END < current_time < AFTERNOON_START:
        return MORNING_SESSION_MINUTES

    if AFTERNOON_START <= current_time <= AFTERNOON_END:
        afternoon_start_datetime = datetime.combine(
            current_datetime.date(),
            AFTERNOON_START,
            tzinfo=TIMEZONE,
        )

        afternoon_elapsed = (
            current_datetime
            - afternoon_start_datetime
        ).total_seconds() / 60

        afternoon_elapsed = max(
            0,
            min(
                AFTERNOON_SESSION_MINUTES,
                int(afternoon_elapsed),
            ),
        )

        return (
            MORNING_SESSION_MINUTES
            + afternoon_elapsed
        )

    return TOTAL_SESSION_MINUTES


def normalize_historical_price_to_vnd(
    historical_price,
    current_price,
):
    """
    Vnstock history co the tra gia theo don vi nghin dong:
    23.5 thay vi 23,500.

    Price board thuong tra gia theo VND:
    23,500.

    Neu phat hien chenh lech don vi, tu dong nhan 1,000.
    """
    if pd.isna(historical_price):
        return None

    if pd.isna(current_price):
        return float(historical_price)

    historical_price = float(historical_price)
    current_price = float(current_price)

    if (
        historical_price > 0
        and historical_price < 1000
        and current_price >= 1000
    ):
        return historical_price * 1000

    return historical_price


def safe_percent_change(
    current_value,
    previous_value,
):
    if pd.isna(current_value):
        return None

    if pd.isna(previous_value):
        return None

    previous_value = float(previous_value)

    if previous_value <= 0:
        return None

    return (
        (
            float(current_value)
            - previous_value
        )
        / previous_value
        * 100
    )


# ============================================================
# PHAN 03 - LAY BANG GIA
# ============================================================

def fetch_price_board(
    symbols: list[str],
) -> pd.DataFrame:
    print(
        f"Dang lay bang gia {len(symbols)} ma..."
    )

    start_time = perf_counter()

    trading = Trading(
        source=SOURCE
    )

    data = trading.price_board(
        symbols
    )

    elapsed = round(
        perf_counter() - start_time,
        2,
    )

    if data is None:
        raise RuntimeError(
            "Price board tra ve None."
        )

    if not isinstance(data, pd.DataFrame):
        raise RuntimeError(
            "Price board khong tra ve DataFrame."
        )

    if data.empty:
        raise RuntimeError(
            "Price board tra ve du lieu rong."
        )

    required_columns = {
        "symbol",
        "exchange",
        "close_price",
        "volume_accumulated",
    }

    missing_columns = required_columns.difference(
        data.columns
    )

    if missing_columns:
        raise RuntimeError(
            "Price board thieu cot: "
            f"{sorted(missing_columns)}. "
            f"Cac cot hien co: {list(data.columns)}"
        )

    result = data.copy()

    result["symbol"] = normalize_text(
        result["symbol"]
    )

    result["exchange"] = normalize_text(
        result["exchange"]
    )

    result["exchange"] = result[
        "exchange"
    ].replace(
        {
            "HSX": "HOSE",
        }
    )

    result["close_price"] = to_numeric(
        result["close_price"]
    )

    result["volume_accumulated"] = to_numeric(
        result["volume_accumulated"]
    )

    optional_numeric_columns = [
        "reference_price",
        "open_price",
        "high_price",
        "low_price",
        "average_price",
        "total_value",
        "price_change",
        "percent_change",
    ]

    for column in optional_numeric_columns:
        if column in result.columns:
            result[column] = to_numeric(
                result[column]
            )

    result = result.drop_duplicates(
        subset=["symbol"],
        keep="last",
    )

    print(
        f"Lay bang gia thanh cong trong "
        f"{elapsed} giay."
    )

    return result


# ============================================================
# PHAN 04 - DOC SNAPSHOT TRUOC
# ============================================================

def load_previous_snapshot(
    current_scan_date: str,
) -> pd.DataFrame:
    if not LATEST_SNAPSHOT_FILE.exists():
        print(
            "Chua co snapshot truoc. "
            "Day se la snapshot nen."
        )

        return pd.DataFrame(
            columns=[
                "symbol",
                "previous_close_price",
                "previous_volume_accumulated",
                "previous_scan_at",
            ]
        )

    previous = pd.read_csv(
        LATEST_SNAPSHOT_FILE
    )

    required_columns = {
        "symbol",
        "scan_date",
        "scan_at",
        "close_price",
        "volume_accumulated",
    }

    missing_columns = required_columns.difference(
        previous.columns
    )

    if missing_columns:
        print(
            "Snapshot cu khong dung cau truc. "
            "Se tao snapshot nen moi."
        )

        return pd.DataFrame(
            columns=[
                "symbol",
                "previous_close_price",
                "previous_volume_accumulated",
                "previous_scan_at",
            ]
        )

    previous = previous.copy()

    previous["symbol"] = normalize_text(
        previous["symbol"]
    )

    previous["scan_date"] = (
        previous["scan_date"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # Khong so sanh snapshot cua ngay hom truoc.
    previous = previous[
        previous["scan_date"] == current_scan_date
    ].copy()

    if previous.empty:
        print(
            "Snapshot truoc khong thuoc ngay hien tai. "
            "Day se la snapshot nen dau ngay."
        )

        return pd.DataFrame(
            columns=[
                "symbol",
                "previous_close_price",
                "previous_volume_accumulated",
                "previous_scan_at",
            ]
        )

    previous["close_price"] = to_numeric(
        previous["close_price"]
    )

    previous["volume_accumulated"] = to_numeric(
        previous["volume_accumulated"]
    )

    previous = previous.rename(
        columns={
            "close_price": "previous_close_price",
            "volume_accumulated": (
                "previous_volume_accumulated"
            ),
            "scan_at": "previous_scan_at",
        }
    )

    return previous[
        [
            "symbol",
            "previous_close_price",
            "previous_volume_accumulated",
            "previous_scan_at",
        ]
    ].drop_duplicates(
        subset=["symbol"],
        keep="last",
    )


# ============================================================
# PHAN 05 - TINH TIN HIEU
# ============================================================

def calculate_market_scan(
    price_board: pd.DataFrame,
    watchlist: pd.DataFrame,
    daily_indicators: pd.DataFrame,
    previous_snapshot: pd.DataFrame,
    scan_datetime: datetime,
) -> pd.DataFrame:
    scan_date = scan_datetime.date().isoformat()
    scan_at = scan_datetime.isoformat()

    elapsed_minutes = get_session_elapsed_minutes(
        scan_datetime
    )

    session_progress = (
        elapsed_minutes
        / TOTAL_SESSION_MINUTES
        if elapsed_minutes > 0
        else 0
    )

    result = watchlist[
        [
            "symbol",
            "exchange",
        ]
    ].merge(
        price_board,
        how="left",
        on="symbol",
        suffixes=(
            "_watchlist",
            "_market",
        ),
    )

    if "exchange_market" in result.columns:
        result["exchange"] = (
            result["exchange_market"]
            .fillna(
                result["exchange_watchlist"]
            )
        )

        result = result.drop(
            columns=[
                "exchange_watchlist",
                "exchange_market",
            ],
            errors="ignore",
        )
    elif "exchange_watchlist" in result.columns:
        result = result.rename(
            columns={
                "exchange_watchlist": "exchange",
            }
        )

    result = result.merge(
        daily_indicators,
        how="left",
        on="symbol",
    )

    result = result.merge(
        previous_snapshot,
        how="left",
        on="symbol",
    )

    result["scan_date"] = scan_date
    result["scan_at"] = scan_at

    result["session_elapsed_minutes"] = (
        elapsed_minutes
    )

    result["session_progress"] = (
        session_progress
    )

    result["ma200_vnd"] = result.apply(
        lambda row: normalize_historical_price_to_vnd(
            row.get("ma200"),
            row.get("close_price"),
        ),
        axis=1,
    )

    result["latest_close_vnd"] = result.apply(
        lambda row: normalize_historical_price_to_vnd(
            row.get("latest_close"),
            row.get("close_price"),
        ),
        axis=1,
    )

    result["distance_to_ma200_pct"] = result.apply(
        lambda row: safe_percent_change(
            row.get("close_price"),
            row.get("ma200_vnd"),
        ),
        axis=1,
    )

    result["below_ma200"] = (
        result["ma200_status"].eq("OK")
        & result["ma200_vnd"].notna()
        & result["close_price"].notna()
        & (
            result["close_price"]
            < result["ma200_vnd"]
        )
    )

    result["price_change_30m_pct"] = result.apply(
        lambda row: safe_percent_change(
            row.get("close_price"),
            row.get("previous_close_price"),
        ),
        axis=1,
    )

    result["price_surge_30m"] = (
        result["price_change_30m_pct"]
        .ge(PRICE_SURGE_THRESHOLD_PCT)
        .fillna(False)
    )

    result["expected_volume_at_time"] = None

    valid_volume_baseline = (
        result["avg_volume_10_status"].eq("OK")
        & result["avg_volume_10"].notna()
        & (result["avg_volume_10"] > 0)
        & (session_progress > 0)
    )

    result.loc[
        valid_volume_baseline,
        "expected_volume_at_time",
    ] = (
        result.loc[
            valid_volume_baseline,
            "avg_volume_10",
        ]
        * session_progress
    )

    result["expected_volume_at_time"] = to_numeric(
        result["expected_volume_at_time"]
    )

    result["rvol_time"] = None

    valid_rvol = (
        result["volume_accumulated"].notna()
        & result["expected_volume_at_time"].notna()
        & (
            result["expected_volume_at_time"]
            > 0
        )
    )

    result.loc[
        valid_rvol,
        "rvol_time",
    ] = (
        result.loc[
            valid_rvol,
            "volume_accumulated",
        ]
        / result.loc[
            valid_rvol,
            "expected_volume_at_time",
        ]
    )

    result["rvol_time"] = to_numeric(
        result["rvol_time"]
    )

    result["volume_surge"] = (
        result["rvol_time"]
        .ge(RVOL_THRESHOLD)
        .fillna(False)
    )

    result["strong_setup"] = (
        result["below_ma200"]
        & result["price_surge_30m"]
        & result["volume_surge"]
    )

    result["has_any_signal"] = (
        result["below_ma200"]
        | result["price_surge_30m"]
        | result["volume_surge"]
    )

    result["signal_name"] = ""

    result.loc[
        result["below_ma200"],
        "signal_name",
    ] = "BELOW_MA200"

    result.loc[
        result["price_surge_30m"],
        "signal_name",
    ] = result.loc[
        result["price_surge_30m"],
        "signal_name",
    ].apply(
        lambda value: (
            f"{value}|PRICE_SURGE_30M"
            if value
            else "PRICE_SURGE_30M"
        )
    )

    result.loc[
        result["volume_surge"],
        "signal_name",
    ] = result.loc[
        result["volume_surge"],
        "signal_name",
    ].apply(
        lambda value: (
            f"{value}|VOLUME_SURGE"
            if value
            else "VOLUME_SURGE"
        )
    )

    result.loc[
        result["strong_setup"],
        "signal_name",
    ] = "STRONG_SETUP"

    result["is_baseline_snapshot"] = (
        result["previous_close_price"].isna()
    )

    return result


# ============================================================
# PHAN 06 - LUU FILE
# ============================================================

def save_results(
    scan_result: pd.DataFrame,
) -> None:
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    preferred_columns = [
        "scan_date",
        "scan_at",
        "symbol",
        "exchange",
        "close_price",
        "previous_close_price",
        "price_change_30m_pct",
        "volume_accumulated",
        "previous_volume_accumulated",
        "avg_volume_10",
        "expected_volume_at_time",
        "rvol_time",
        "ma200_vnd",
        "distance_to_ma200_pct",
        "below_ma200",
        "price_surge_30m",
        "volume_surge",
        "strong_setup",
        "has_any_signal",
        "signal_name",
        "is_baseline_snapshot",
        "session_elapsed_minutes",
        "session_progress",
        "ma200_status",
        "avg_volume_10_status",
        "previous_scan_at",
        "time",
        "reference_price",
        "open_price",
        "high_price",
        "low_price",
        "average_price",
        "total_value",
        "price_change",
        "percent_change",
    ]

    output_columns = [
        column
        for column in preferred_columns
        if column in scan_result.columns
    ]

    other_columns = [
        column
        for column in scan_result.columns
        if column not in output_columns
    ]

    final_result = scan_result[
        output_columns
        + other_columns
    ].copy()

    final_result = final_result.sort_values(
        by=[
            "strong_setup",
            "price_surge_30m",
            "volume_surge",
            "below_ma200",
            "exchange",
            "symbol",
        ],
        ascending=[
            False,
            False,
            False,
            False,
            True,
            True,
        ],
    ).reset_index(drop=True)

    final_result.to_csv(
        MARKET_SCAN_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    snapshot_columns = [
        "scan_date",
        "scan_at",
        "symbol",
        "exchange",
        "close_price",
        "volume_accumulated",
    ]

    snapshot = final_result[
        snapshot_columns
    ].copy()

    snapshot.to_csv(
        LATEST_SNAPSHOT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    signals = final_result[
        final_result["has_any_signal"]
    ].copy()

    signals.to_csv(
        LATEST_SIGNALS_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        f"Da luu: {MARKET_SCAN_FILE}"
    )

    print(
        f"Da luu: {LATEST_SNAPSHOT_FILE}"
    )

    print(
        f"Da luu: {LATEST_SIGNALS_FILE}"
    )


# ============================================================
# PHAN 07 - MAIN
# ============================================================

def main() -> None:
    total_start = perf_counter()

    scan_datetime = datetime.now(
        TIMEZONE
    )

    print(
        "========================================"
    )
    print(
        "CAP NHAT MARKET SNAPSHOT"
    )
    print(
        "========================================"
    )
    print(
        f"Thoi gian quet: "
        f"{scan_datetime.isoformat()}"
    )

    watchlist = load_watchlist()

    daily_indicators = load_daily_indicators()

    symbols = watchlist[
        "symbol"
    ].tolist()

    price_board = fetch_price_board(
        symbols
    )

    previous_snapshot = load_previous_snapshot(
        scan_datetime.date().isoformat()
    )

    scan_result = calculate_market_scan(
        price_board=price_board,
        watchlist=watchlist,
        daily_indicators=daily_indicators,
        previous_snapshot=previous_snapshot,
        scan_datetime=scan_datetime,
    )

    save_results(
        scan_result
    )

    baseline_count = int(
        scan_result[
            "is_baseline_snapshot"
        ].sum()
    )

    below_ma200_count = int(
        scan_result[
            "below_ma200"
        ].sum()
    )

    price_surge_count = int(
        scan_result[
            "price_surge_30m"
        ].sum()
    )

    volume_surge_count = int(
        scan_result[
            "volume_surge"
        ].sum()
    )

    strong_setup_count = int(
        scan_result[
            "strong_setup"
        ].sum()
    )

    missing_price_count = int(
        scan_result[
            "close_price"
        ].isna()
        .sum()
    )

    total_elapsed = round(
        perf_counter()
        - total_start,
        2,
    )

    print("")
    print(
        "========================================"
    )
    print(
        "TONG KET"
    )
    print(
        "========================================"
    )
    print(
        f"Tong watchlist: {len(scan_result)}"
    )
    print(
        f"Snapshot nen: {baseline_count}"
    )
    print(
        f"Gia duoi MA200: {below_ma200_count}"
    )
    print(
        f"Tang >= {PRICE_SURGE_THRESHOLD_PCT}%: "
        f"{price_surge_count}"
    )
    print(
        f"RVOL >= {RVOL_THRESHOLD}: "
        f"{volume_surge_count}"
    )
    print(
        f"Strong setup: {strong_setup_count}"
    )
    print(
        f"Thieu gia: {missing_price_count}"
    )
    print(
        f"Tong thoi gian: {total_elapsed} giay"
    )

    if strong_setup_count > 0:
        print("")
        print(
            "CAC MA STRONG SETUP:"
        )

        display_columns = [
            "symbol",
            "exchange",
            "close_price",
            "ma200_vnd",
            "price_change_30m_pct",
            "volume_accumulated",
            "avg_volume_10",
            "rvol_time",
        ]

        print(
            scan_result.loc[
                scan_result["strong_setup"],
                display_columns,
            ].to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()
