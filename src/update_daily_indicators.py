from datetime import date, timedelta
from pathlib import Path
from time import perf_counter, sleep

import pandas as pd
from vnstock.api.quote import Quote


WATCHLIST_FILE = Path("config/watchlist.csv")
OUTPUT_DIR = Path("data")
OUTPUT_FILE = OUTPUT_DIR / "daily_indicators.csv"

PRIMARY_SOURCE = "KBS"
FALLBACK_SOURCE = "VCI"

MA_SESSIONS = 200
AVERAGE_VOLUME_SESSIONS = 10

# Khoảng 430 ngày thường đủ để lấy hơn 200 phiên giao dịch.
HISTORY_LOOKBACK_DAYS = 430

# Nghỉ nhẹ giữa các mã để hạn chế gọi API quá nhanh.
REQUEST_DELAY_SECONDS = 0.30


def normalize_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )


def load_watchlist() -> pd.DataFrame:
    if not WATCHLIST_FILE.exists():
        raise FileNotFoundError(
            f"Khong tim thay watchlist: {WATCHLIST_FILE}"
        )

    watchlist = pd.read_csv(WATCHLIST_FILE)

    required_columns = {"symbol", "exchange"}
    missing = required_columns.difference(watchlist.columns)

    if missing:
        raise RuntimeError(
            f"Watchlist thieu cot: {sorted(missing)}"
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

    watchlist = watchlist.sort_values(
        by=["exchange", "symbol"]
    ).reset_index(drop=True)

    return watchlist


def get_history(
    symbol: str,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, str]:
    """
    Thử nguồn KBS trước.
    Nếu KBS lỗi hoặc không có dữ liệu thì thử VCI.
    """
    errors = []

    for source in [PRIMARY_SOURCE, FALLBACK_SOURCE]:
        try:
            quote = Quote(
                symbol=symbol,
                source=source,
            )

            data = quote.history(
                start=start_date,
                end=end_date,
                interval="1D",
            )

            if data is not None and not data.empty:
                return data.copy(), source

            errors.append(f"{source}: du lieu rong")

        except Exception as error:
            errors.append(
                f"{source}: "
                f"{type(error).__name__}: {error}"
            )

    raise RuntimeError(" | ".join(errors))


def prepare_history(data: pd.DataFrame) -> pd.DataFrame:
    required_columns = {
        "time",
        "close",
        "volume",
    }

    missing = required_columns.difference(data.columns)

    if missing:
        raise RuntimeError(
            f"Thieu cot {sorted(missing)}. "
            f"Cot hien co: {list(data.columns)}"
        )

    result = data.copy()

    result["time"] = pd.to_datetime(
        result["time"],
        errors="coerce",
    )

    result["close"] = pd.to_numeric(
        result["close"],
        errors="coerce",
    )

    result["volume"] = pd.to_numeric(
        result["volume"],
        errors="coerce",
    )

    result = result.dropna(
        subset=["time", "close", "volume"]
    )

    result = result[
        (result["close"] > 0)
        & (result["volume"] >= 0)
    ]

    result = result.sort_values(
        by="time"
    ).drop_duplicates(
        subset=["time"],
        keep="last",
    ).reset_index(drop=True)

    return result


def calculate_indicators(
    history: pd.DataFrame,
) -> dict:
    session_count = len(history)

    if session_count == 0:
        raise RuntimeError("Khong con du lieu hop le sau khi xu ly.")

    latest_row = history.iloc[-1]

    latest_date = latest_row["time"].date().isoformat()
    latest_close = float(latest_row["close"])

    if session_count >= MA_SESSIONS:
        ma200 = float(
            history["close"]
            .tail(MA_SESSIONS)
            .mean()
        )
        ma200_status = "OK"
    else:
        ma200 = None
        ma200_status = "NOT_ENOUGH_DATA"

    if session_count >= AVERAGE_VOLUME_SESSIONS:
        avg_volume_10 = float(
            history["volume"]
            .tail(AVERAGE_VOLUME_SESSIONS)
            .mean()
        )
        avg_volume_10_status = "OK"
    else:
        avg_volume_10 = None
        avg_volume_10_status = "NOT_ENOUGH_DATA"

    if (
        ma200_status == "OK"
        and avg_volume_10_status == "OK"
    ):
        status = "OK"
    else:
        status = "PARTIAL"

    return {
        "status": status,
        "sessions_available": session_count,
        "latest_date": latest_date,
        "latest_close": latest_close,
        "ma200": ma200,
        "ma200_status": ma200_status,
        "avg_volume_10": avg_volume_10,
        "avg_volume_10_status": avg_volume_10_status,
    }


def main() -> None:
    watchlist = load_watchlist()

    end_date = date.today()
    start_date = end_date - timedelta(
        days=HISTORY_LOOKBACK_DAYS
    )

    start_text = start_date.isoformat()
    end_text = end_date.isoformat()

    print("========================================")
    print("CAP NHAT MA200 VA KLTB10")
    print("========================================")
    print(f"So ma watchlist: {len(watchlist)}")
    print(f"Khoang du lieu: {start_text} den {end_text}")
    print("")

    results = []
    total_start = perf_counter()

    for index, row in watchlist.iterrows():
        position = index + 1
        symbol = row["symbol"]
        exchange = row["exchange"]

        print(
            f"[{position}/{len(watchlist)}] "
            f"{symbol} - {exchange}"
        )

        symbol_start = perf_counter()

        try:
            raw_history, source_used = get_history(
                symbol=symbol,
                start_date=start_text,
                end_date=end_text,
            )

            history = prepare_history(raw_history)
            indicators = calculate_indicators(history)

            elapsed = round(
                perf_counter() - symbol_start,
                2,
            )

            results.append(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "source": source_used,
                    **indicators,
                    "updated_at": pd.Timestamp.now(
                        tz="Asia/Ho_Chi_Minh"
                    ).isoformat(),
                    "elapsed_seconds": elapsed,
                    "error": "",
                }
            )

            ma_text = (
                f"{indicators['ma200']:.4f}"
                if indicators["ma200"] is not None
                else "N/A"
            )

            volume_text = (
                f"{indicators['avg_volume_10']:,.0f}"
                if indicators["avg_volume_10"] is not None
                else "N/A"
            )

            print(
                f"  {indicators['status']} "
                f"| sessions="
                f"{indicators['sessions_available']} "
                f"| MA200={ma_text} "
                f"| KLTB10={volume_text} "
                f"| source={source_used} "
                f"| {elapsed}s"
            )

        except Exception as error:
            elapsed = round(
                perf_counter() - symbol_start,
                2,
            )

            results.append(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "source": "",
                    "status": "ERROR",
                    "sessions_available": 0,
                    "latest_date": "",
                    "latest_close": "",
                    "ma200": "",
                    "ma200_status": "ERROR",
                    "avg_volume_10": "",
                    "avg_volume_10_status": "ERROR",
                    "updated_at": pd.Timestamp.now(
                        tz="Asia/Ho_Chi_Minh"
                    ).isoformat(),
                    "elapsed_seconds": elapsed,
                    "error": str(error),
                }
            )

            print(f"  ERROR | {error}")

        sleep(REQUEST_DELAY_SECONDS)

    result_df = pd.DataFrame(results)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    total_elapsed = round(
        perf_counter() - total_start,
        2,
    )

    ok_count = int(
        (result_df["status"] == "OK").sum()
    )

    partial_count = int(
        (result_df["status"] == "PARTIAL").sum()
    )

    error_count = int(
        (result_df["status"] == "ERROR").sum()
    )

    print("")
    print("========================================")
    print("TONG KET")
    print("========================================")
    print(f"Tong watchlist: {len(result_df)}")
    print(f"Du MA200 va KLTB10: {ok_count}")
    print(f"Thieu mot phan du lieu: {partial_count}")
    print(f"Bi loi: {error_count}")
    print(f"Tong thoi gian: {total_elapsed} giay")
    print(f"Da luu: {OUTPUT_FILE}")

    if error_count > 0:
        print("")
        print("CAC MA BI LOI:")
        print(
            result_df.loc[
                result_df["status"] == "ERROR",
                ["symbol", "exchange", "error"],
            ].to_string(index=False)
        )

    # Không làm workflow thất bại chỉ vì một vài mã riêng lẻ bị lỗi.
    # Nhưng nếu quá 20% watchlist lỗi thì coi là lỗi hệ thống.
    maximum_allowed_errors = max(
        5,
        int(len(result_df) * 0.20),
    )

    if error_count > maximum_allowed_errors:
        raise RuntimeError(
            f"Co {error_count} ma loi, vuot nguong "
            f"cho phep {maximum_allowed_errors}."
        )


if __name__ == "__main__":
    main()
