from datetime import date, timedelta
from pathlib import Path
from time import perf_counter, sleep

import pandas as pd
from vnstock.api.quote import Quote


OUTPUT_DIR = Path("output")
DETAIL_FILE = OUTPUT_DIR / "history_sample_detail.csv"
SUMMARY_FILE = OUTPUT_DIR / "history_sample_summary.csv"

# 12 mã đại diện của ba sàn.
TEST_SYMBOLS = [
    # HOSE
    {"symbol": "VNM", "exchange": "HOSE"},
    {"symbol": "FPT", "exchange": "HOSE"},
    {"symbol": "HPG", "exchange": "HOSE"},
    {"symbol": "VCB", "exchange": "HOSE"},

    # HNX
    {"symbol": "SHS", "exchange": "HNX"},
    {"symbol": "PVS", "exchange": "HNX"},
    {"symbol": "IDC", "exchange": "HNX"},
    {"symbol": "MBS", "exchange": "HNX"},

    # UPCOM
    {"symbol": "ACV", "exchange": "UPCOM"},
    {"symbol": "VGI", "exchange": "UPCOM"},
    {"symbol": "MCH", "exchange": "UPCOM"},
    {"symbol": "BSR", "exchange": "UPCOM"},
]

PRIMARY_SOURCE = "KBS"
FALLBACK_SOURCE = "VCI"


def get_history(
    symbol: str,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, str]:
    """
    Lấy dữ liệu từ KBS trước.
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
                f"{source}: {type(error).__name__}: {error}"
            )

    raise RuntimeError(" | ".join(errors))


def normalize_history(
    data: pd.DataFrame,
    symbol: str,
    exchange: str,
    source: str,
) -> pd.DataFrame:
    """Chuẩn hóa các cột cần dùng cho việc tính KLTB 10 phiên."""

    required_columns = {
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    missing_columns = required_columns.difference(data.columns)

    if missing_columns:
        raise RuntimeError(
            f"Thieu cot: {sorted(missing_columns)}. "
            f"Cot hien co: {list(data.columns)}"
        )

    result = data.copy()

    result["time"] = pd.to_datetime(
        result["time"],
        errors="coerce",
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for column in numeric_columns:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    result = result.dropna(
        subset=["time", "close", "volume"]
    )

    result = result.sort_values(
        by="time"
    ).reset_index(drop=True)

    # Chỉ giữ 10 phiên hoàn chỉnh gần nhất.
    result = result.tail(10).copy()

    result.insert(0, "symbol", symbol)
    result.insert(1, "exchange", exchange)
    result.insert(2, "source", source)

    return result


def main() -> None:
    end = date.today()
    start = end - timedelta(days=45)

    start_text = start.isoformat()
    end_text = end.isoformat()

    print("========================================")
    print("KIEM TRA LICH SU 10 PHIEN")
    print("========================================")
    print(f"Khoang truy van: {start_text} den {end_text}")
    print(f"So ma thu nghiem: {len(TEST_SYMBOLS)}")
    print("")

    all_details = []
    summaries = []

    total_start = perf_counter()

    for index, item in enumerate(TEST_SYMBOLS, start=1):
        symbol = item["symbol"]
        exchange = item["exchange"]

        print(
            f"[{index}/{len(TEST_SYMBOLS)}] "
            f"Dang lay {symbol} - {exchange}..."
        )

        symbol_start = perf_counter()

        try:
            raw_data, source_used = get_history(
                symbol=symbol,
                start_date=start_text,
                end_date=end_text,
            )

            normalized = normalize_history(
                data=raw_data,
                symbol=symbol,
                exchange=exchange,
                source=source_used,
            )

            elapsed = round(
                perf_counter() - symbol_start,
                2,
            )

            session_count = len(normalized)

            average_volume_10 = (
                normalized["volume"].mean()
                if session_count > 0
                else None
            )

            latest_close = (
                normalized["close"].iloc[-1]
                if session_count > 0
                else None
            )

            latest_date = (
                normalized["time"].iloc[-1].date().isoformat()
                if session_count > 0
                else None
            )

            status = (
                "OK"
                if session_count == 10
                else "LESS_THAN_10_SESSIONS"
            )

            summaries.append(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "status": status,
                    "source": source_used,
                    "sessions": session_count,
                    "latest_date": latest_date,
                    "latest_close": latest_close,
                    "avg_volume_10": average_volume_10,
                    "elapsed_seconds": elapsed,
                    "error": "",
                }
            )

            all_details.append(normalized)

            print(
                f"  Thanh cong | source={source_used} "
                f"| sessions={session_count} "
                f"| avg_volume_10={average_volume_10:,.0f} "
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
                    "sessions": 0,
                    "latest_date": "",
                    "latest_close": "",
                    "avg_volume_10": "",
                    "elapsed_seconds": elapsed,
                    "error": str(error),
                }
            )

            print(f"  LOI: {error}")

        # Nghỉ nhẹ giữa các mã để giảm nguy cơ bị giới hạn request.
        sleep(0.4)

    total_elapsed = round(
        perf_counter() - total_start,
        2,
    )

    summary_df = pd.DataFrame(summaries)

    if all_details:
        detail_df = pd.concat(
            all_details,
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

    print(
        summary_df[
            [
                "symbol",
                "exchange",
                "status",
                "source",
                "sessions",
                "avg_volume_10",
                "elapsed_seconds",
            ]
        ].to_string(index=False)
    )

    success_count = int(
        (summary_df["status"] == "OK").sum()
    )

    error_count = int(
        (summary_df["status"] == "ERROR").sum()
    )

    print("")
    print(f"Thanh cong du 10 phien: {success_count}")
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
