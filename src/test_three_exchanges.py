from pathlib import Path

import pandas as pd
from vnstock import Listing


OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "three_exchanges_symbols.csv"

TARGET_EXCHANGES = {
    "HOSE",
    "HSX",
    "HNX",
    "UPCOM",
}


def find_column(columns, possible_names):
    """Tìm tên cột mà không phân biệt chữ hoa, chữ thường."""
    lookup = {str(column).strip().lower(): column for column in columns}

    for name in possible_names:
        found = lookup.get(name.lower())
        if found is not None:
            return found

    return None


def main() -> None:
    print("Bat dau lay danh sach ma chung khoan...")

    listing = Listing(source="KBS")
    data = listing.symbols_by_exchange()

    if data is None or data.empty:
        raise RuntimeError("Vnstock khong tra ve danh sach ma chung khoan.")

    print(f"Tong so dong Vnstock tra ve: {len(data)}")
    print("Danh sach cot:")
    print(list(data.columns))

    symbol_column = find_column(
        data.columns,
        ["symbol", "ticker", "code"],
    )

    exchange_column = find_column(
        data.columns,
        ["exchange", "comgroupcode", "board", "market"],
    )

    if symbol_column is None:
        raise RuntimeError(
            f"Khong tim thay cot ma co phieu. Cac cot hien co: {list(data.columns)}"
        )

    if exchange_column is None:
        raise RuntimeError(
            f"Khong tim thay cot san giao dich. Cac cot hien co: {list(data.columns)}"
        )

    result = data.copy()

    result[symbol_column] = (
        result[symbol_column]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    result[exchange_column] = (
        result[exchange_column]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # Chuẩn hóa HSX thành HOSE để bảng kết quả dễ đọc.
    result[exchange_column] = result[exchange_column].replace(
        {
            "HSX": "HOSE",
        }
    )

    result = result[
        result[exchange_column].isin({"HOSE", "HNX", "UPCOM"})
    ].copy()

    result = result.drop_duplicates(
        subset=[symbol_column, exchange_column]
    )

    result = result.sort_values(
        by=[exchange_column, symbol_column]
    ).reset_index(drop=True)

    print("")
    print("So luong ma theo san:")
    exchange_counts = (
        result.groupby(exchange_column)[symbol_column]
        .nunique()
        .sort_index()
    )
    print(exchange_counts.to_string())

    print("")
    print(f"Tong cong ba san: {result[symbol_column].nunique()} ma")

    print("")
    print("10 dong dau tien:")
    print(
        result[
            [symbol_column, exchange_column]
        ].head(10).to_string(index=False)
    )

    print("")
    print("10 dong cuoi cung:")
    print(
        result[
            [symbol_column, exchange_column]
        ].tail(10).to_string(index=False)
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("")
    print(f"Da luu file: {OUTPUT_FILE}")
    print("Hoan tat kiem tra danh sach ba san.")


if __name__ == "__main__":
    main()
