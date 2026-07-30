from pathlib import Path
from time import perf_counter

import pandas as pd
from vnstock import Trading


WATCHLIST_FILE = Path("config/watchlist.csv")
OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "price_board_batch_test.csv"

SOURCE = "KBS"


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
            f"Khong tim thay file: {WATCHLIST_FILE}"
        )

    watchlist = pd.read_csv(WATCHLIST_FILE)

    required_columns = {"symbol", "exchange"}
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
    ).reset_index(drop=True)

    return watchlist


def find_column(
    columns,
    possible_names,
):
    lookup = {
        str(column).strip().lower(): column
        for column in columns
    }

    for name in possible_names:
        found = lookup.get(name.lower())

        if found is not None:
            return found

    return None


def main() -> None:
    watchlist = load_watchlist()
    symbols = watchlist["symbol"].tolist()

    print("========================================")
    print("TEST PRICE BOARD HANG LOAT")
    print("========================================")
    print(f"So ma gui len API: {len(symbols)}")
    print(f"Nguon du lieu: {SOURCE}")
    print("")

    start_time = perf_counter()

    trading = Trading(source=SOURCE)

    data = trading.price_board(symbols)

    elapsed_seconds = round(
        perf_counter() - start_time,
        2,
    )

    if data is None:
        raise RuntimeError(
            "price_board tra ve None."
        )

    if not isinstance(data, pd.DataFrame):
        raise RuntimeError(
            f"Ket qua khong phai DataFrame: {type(data)}"
        )

    if data.empty:
        raise RuntimeError(
            "price_board tra ve DataFrame rong."
        )

    result = data.copy()

    print(f"Thoi gian truy van: {elapsed_seconds} giay")
    print(f"So dong nhan duoc: {len(result)}")
    print("")
    print("Danh sach cot:")
    print(list(result.columns))

    symbol_column = find_column(
        result.columns,
        [
            "symbol",
            "ticker",
            "code",
        ],
    )

    exchange_column = find_column(
        result.columns,
        [
            "exchange",
            "market",
            "board",
        ],
    )

    price_column = find_column(
        result.columns,
        [
            "match_price",
            "close_price",
            "price",
            "last_price",
        ],
    )

    volume_column = find_column(
        result.columns,
        [
            "volume_accumulated",
            "total_volume",
            "accumulated_volume",
            "volume",
        ],
    )

    if symbol_column is None:
        raise RuntimeError(
            "Khong tim thay cot ma chung khoan."
        )

    result[symbol_column] = normalize_text(
        result[symbol_column]
    )

    received_symbols = set(
        result[symbol_column].tolist()
    )

    requested_symbols = set(symbols)

    missing_symbols = sorted(
        requested_symbols - received_symbols
    )

    unexpected_symbols = sorted(
        received_symbols - requested_symbols
    )

    print("")
    print("========================================")
    print("KET QUA DOI CHIEU")
    print("========================================")
    print(f"So ma yeu cau: {len(requested_symbols)}")
    print(f"So ma nhan duoc: {len(received_symbols)}")
    print(f"So ma bi thieu: {len(missing_symbols)}")
    print(
        f"So ma ngoai watchlist: "
        f"{len(unexpected_symbols)}"
    )

    if exchange_column is not None:
        result[exchange_column] = normalize_text(
            result[exchange_column]
        )

        print("")
        print("So dong theo san:")

        print(
            result.groupby(exchange_column)[symbol_column]
            .nunique()
            .sort_index()
            .to_string()
        )
    else:
        print("")
        print(
            "Khong co cot exchange trong ket qua."
        )

    print("")
    print("Cot gia phat hien:")
    print(price_column)

    print("Cot volume phat hien:")
    print(volume_column)

    if missing_symbols:
        print("")
        print("CAC MA BI THIEU:")
        print(", ".join(missing_symbols))

    if unexpected_symbols:
        print("")
        print("CAC MA NGOAI WATCHLIST:")
        print(", ".join(unexpected_symbols))

    display_columns = [
        column
        for column in [
            symbol_column,
            exchange_column,
            price_column,
            volume_column,
        ]
        if column is not None
    ]

    print("")
    print("20 DONG DAU:")
    print(
        result[
            display_columns
        ].head(20).to_string(index=False)
    )

    print("")
    print("20 DONG CUOI:")
    print(
        result[
            display_columns
        ].tail(20).to_string(index=False)
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("")
    print("========================================")
    print("TONG KET")
    print("========================================")
    print(f"Thoi gian: {elapsed_seconds} giay")
    print(f"Yeu cau: {len(requested_symbols)} ma")
    print(f"Nhan duoc: {len(received_symbols)} ma")
    print(f"Bi thieu: {len(missing_symbols)} ma")
    print(f"Da luu: {OUTPUT_FILE}")

    # Không cho workflow xanh giả nếu dữ liệu thiếu quá nhiều.
    maximum_missing = max(
        5,
        int(len(requested_symbols) * 0.10),
    )

    if len(missing_symbols) > maximum_missing:
        raise RuntimeError(
            f"Thieu {len(missing_symbols)} ma, "
            f"vuot nguong cho phep "
            f"{maximum_missing}."
        )


if __name__ == "__main__":
    main()
