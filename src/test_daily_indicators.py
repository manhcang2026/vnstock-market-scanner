from datetime import date, timedelta
from pathlib import Path
from time import perf_counter, sleep

import pandas as pd
from vnstock.api.quote import Quote


WATCHLIST_FILE = Path("config/watchlist.csv")
OUTPUT_DIR = Path("output")

SUMMARY_FILE = OUTPUT_DIR / "daily_indicators_test_summary.csv"
DETAIL_FILE = OUTPUT_DIR / "daily_indicators_test_detail.csv"

TEST_LIMIT = 20

PRIMARY_SOURCE = "KBS"
FALLBACK_SOURCE = "VCI"

MIN_MA_SESSIONS = 200
AVG_VOLUME_SESSIONS = 10


def normalize_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )


def load_test_watchlist() -> pd.DataFrame:
    if not WATCHLIST_FILE.exists():
        raise FileNotFoundError(
            f"Khong tim thay file: {WATCHLIST_FILE}"
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
        subset=["symbol"]
    )

    watchlist = watchlist.sort_values(
        by=["exchange", "symbol"]
    ).reset_index(drop=True)

    return watchlist.head(TEST_LIMIT).copy()


def get_history(
    symbol: str,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, str]:
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

            errors.append(
                f"{source}: du lieu rong"
            )

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

    latest_row = history.iloc[-1]

    latest_date = latest_row["time"].date().isoformat()
    latest_close = float(latest_row["close"])

    if session_count >= MIN_MA_SESSIONS:
        ma200 = float(
            history["close"]
            .tail(MIN_MA_SESSIONS)
            .mean()
        )
        ma_status = "OK"
    else:
        ma200 = None
        ma_status = "NOT_ENOUGH_DATA"

    if session_count >= AVG_VOLUME_SESSIONS:
        avg_volume_10 = float(
            history["volume"]
            .tail(AVG_VOLUME_SESSIONS)
            .mean()
        )
        volume_status = "OK"
    else:
        avg_volume_10 = None
        volume_status = "NOT_ENOUGH_DATA"

    return {
        "sessions_available": session_count,
        "latest_date": latest_date,
        "latest_close": latest_close,
        "ma200": ma200,
        "ma200_status": ma_status,
        "avg_volume_10": avg_volume_10,
        "avg_volume_10_status": volume_status,
    }


def main() -> None:
    watchlist = load_test_watchlist()

    end_date = date.today()
    start_date = end_date - timedelta(days=430)

    start_text = start_date.isoformat()
    end_text = end_date.isoformat()

    print("========================================")
    print("TEST DAILY INDICATORS")
    print("========================================")
    print(f"So ma thu nghiem: {len(watchlist)}")
    print(f"Khoang du lieu: {start_text} den {end_text}")
    print("")

    summaries = []
    details = []

    total_start = perf_counter()

    for index, row in watchlist.iterrows():
        position = index + 1
        symbol = row["symbol"]
        exchange = row["exchange"]

        print(
            f"[{position}/{len(watchlist)}] "
            f"Dang xu ly {symbol} - {exchange}..."
        )

        symbol_start = perf_counter()

        try:
            raw_history, source_used = get_history(
                symbol=symbol,
                start_date=start_text,
                end_date=end_text,
            )

            history = prepare_history(raw_history)

            indicators = calculate_indicators(
                history
            )

            elapsed = round(
                perf_counter() - symbol_start,
                2,
            )

            status = (
                "OK"
                if (
                    indicators["ma200_status"] == "OK"
                    and indicators[
                        "avg_volume_10_status"
                    ] == "OK"
                )
                else "PARTIAL"
            )

            summaries.append(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "status": status,
                    "source": source_used,
                    **indicators,
                    "elapsed_seconds": elapsed,
                    "error": "",
                }
            )

            history_detail = history.tail(220).copy()

            history_detail.insert(
                0,
                "symbol",
                symbol,
            )

            history_detail.insert(
                1,
                "exchange",
                exchange,
            )

            history_detail.insert(
                2,
                "source",
                source_used,
            )

            details.append(history_detail)

            ma_text = (
                f"{indicators['ma200']:.2f}"
                if indicators["ma200"] is not None
                else "N/A"
            )

            volume_text = (
                f"{indicators['avg_volume_10']:,.0f}"
                if indicators[
                    "avg_volume_10"
                ] is not None
                else "N/A"
            )

            print(
                f"  {status} | source={source_used} "
                f"| sessions="
                f"{indicators['sessions_available']} "
                f"| MA200={ma_text} "
                f"| KLTB10={volume_text} "
                f"| time={elapsed}s"
            )

        except Exception as error:
            elapsed = round(
                perf_counter() - symbol_start,
                2,
            )

            summaries.append(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "status": "ERROR",
                    "source": "",
                    "sessions_available": 0,
                    "latest_date": "",
                    "latest_close": "",
                    "ma200": "",
                    "ma200_status": "ERROR",
                    "avg_volume_10": "",
                    "avg_volume_10_status": "ERROR",
                    "elapsed_seconds": elapsed,
                    "error": str(error),
                }
            )

            print(f"  LOI: {error}")

        sleep(0.4)

    total_elapsed = round(
        perf_counter() - total_start,
        2,
    )

    summary_df = pd.DataFrame(summaries)

    if details:
        detail_df = pd.concat(
            details,
            ignore_index=True,
        )
    else:
        detail_df = pd.DataFrame()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_df.to_csv(
        SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    detail_df.to_csv(
        DETAIL_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("")
    print("========================================")
    print("TONG KET")
    print("========================================")

    output_columns = [
        "symbol",
        "exchange",
        "status",
        "source",
        "sessions_available",
        "latest_close",
        "ma200",
        "avg_volume_10",
        "elapsed_seconds",
    ]

    print(
        summary_df[
            output_columns
        ].to_string(index=False)
    )

    ok_count = int(
        (summary_df["status"] == "OK").sum()
    )

    partial_count = int(
        (summary_df["status"] == "PARTIAL").sum()
    )

    error_count = int(
        (summary_df["status"] == "ERROR").sum()
    )

    print("")
    print(f"Du MA200 va KLTB10: {ok_count}")
    print(f"Thieu mot phan du lieu: {partial_count}")
    print(f"Bi loi: {error_count}")
    print(f"Tong thoi gian: {total_elapsed} giay")
    print(f"Da luu: {SUMMARY_FILE}")
    print(f"Da luu: {DETAIL_FILE}")

    if error_count > 0:
        print("")
        print("CAC MA BI LOI:")
        print(
            summary_df.loc[
                summary_df["status"] == "ERROR",
                ["symbol", "exchange", "error"],
            ].to_string(index=False)
        )


if __name__ == "__main__":
    main()
