from pathlib import Path

import pandas as pd
from vnstock import Listing


OUTPUT_DIR = Path("output")

ALL_SYMBOLS_FILE = OUTPUT_DIR / "three_exchanges_symbols.csv"
TYPE_SUMMARY_FILE = OUTPUT_DIR / "security_type_summary.csv"
TYPE_EXCHANGE_FILE = OUTPUT_DIR / "security_type_by_exchange.csv"
TYPE_SAMPLES_FILE = OUTPUT_DIR / "security_type_samples.csv"


def find_column(columns, possible_names):
    """Tìm tên cột mà không phân biệt chữ hoa và chữ thường."""
    lookup = {
        str(column).strip().lower(): column
        for column in columns
    }

    for name in possible_names:
        found = lookup.get(name.lower())
        if found is not None:
            return found

    return None


def normalize_text(series: pd.Series) -> pd.Series:
    """Chuẩn hóa dữ liệu chữ để việc nhóm và so sánh chính xác hơn."""
    return (
        series.fillna("UNKNOWN")
        .astype(str)
        .str.strip()
        .str.upper()
        .replace(
            {
                "": "UNKNOWN",
                "NAN": "UNKNOWN",
                "NONE": "UNKNOWN",
            }
        )
    )


def main() -> None:
    print("Bat dau lay danh sach chung khoan ba san...")

    listing = Listing(source="KBS")
    data = listing.symbols_by_exchange()

    if data is None or data.empty:
        raise RuntimeError(
            "Vnstock khong tra ve danh sach chung khoan."
        )

    print(f"Tong so dong Vnstock tra ve: {len(data)}")
    print(f"Danh sach cot: {list(data.columns)}")

    symbol_column = find_column(
        data.columns,
        ["symbol", "ticker", "code"],
    )

    exchange_column = find_column(
        data.columns,
        ["exchange", "comgroupcode", "board", "market"],
    )

    type_column = find_column(
        data.columns,
        ["type", "security_type", "asset_type"],
    )

    if symbol_column is None:
        raise RuntimeError(
            "Khong tim thay cot ma chung khoan."
        )

    if exchange_column is None:
        raise RuntimeError(
            "Khong tim thay cot san giao dich."
        )

    if type_column is None:
        raise RuntimeError(
            "Khong tim thay cot type."
        )

    result = data.copy()

    result[symbol_column] = normalize_text(
        result[symbol_column]
    )

    result[exchange_column] = normalize_text(
        result[exchange_column]
    )

    result[type_column] = normalize_text(
        result[type_column]
    )

    # Chuẩn hóa HSX thành HOSE.
    result[exchange_column] = result[exchange_column].replace(
        {
            "HSX": "HOSE",
        }
    )

    # Chỉ giữ ba sàn cần theo dõi.
    result = result[
        result[exchange_column].isin(
            {"HOSE", "HNX", "UPCOM"}
        )
    ].copy()

    # Loại dòng trùng cùng mã, sàn và loại.
    result = result.drop_duplicates(
        subset=[
            symbol_column,
            exchange_column,
            type_column,
        ]
    )

    result = result.sort_values(
        by=[
            exchange_column,
            type_column,
            symbol_column,
        ]
    ).reset_index(drop=True)

    print("")
    print("========================================")
    print("SO LUONG MA THEO SAN")
    print("========================================")

    exchange_summary = (
        result.groupby(exchange_column)[symbol_column]
        .nunique()
        .sort_index()
    )

    print(exchange_summary.to_string())

    print("")
    print("========================================")
    print("SO LUONG MA THEO TYPE")
    print("========================================")

    type_summary = (
        result.groupby(type_column)
        .agg(
            row_count=(symbol_column, "size"),
            unique_symbols=(symbol_column, "nunique"),
        )
        .sort_values(
            by="unique_symbols",
            ascending=False,
        )
        .reset_index()
    )

    print(type_summary.to_string(index=False))

    print("")
    print("========================================")
    print("TYPE THEO TUNG SAN")
    print("========================================")

    type_exchange_summary = pd.crosstab(
        result[type_column],
        result[exchange_column],
    )

    type_exchange_summary["TOTAL"] = (
        type_exchange_summary.sum(axis=1)
    )

    type_exchange_summary = (
        type_exchange_summary
        .sort_values(
            by="TOTAL",
            ascending=False,
        )
        .reset_index()
    )

    print(type_exchange_summary.to_string(index=False))

    print("")
    print("========================================")
    print("MA MAU CUA TUNG TYPE")
    print("========================================")

    sample_columns = [
        symbol_column,
        exchange_column,
        type_column,
    ]

    optional_columns = [
        "organ_name",
        "en_organ_name",
        "id",
    ]

    for column in optional_columns:
        if column in result.columns:
            sample_columns.append(column)

    type_samples = (
        result.groupby(type_column, group_keys=False)
        .head(10)
        [sample_columns]
        .reset_index(drop=True)
    )

    for security_type, group in type_samples.groupby(type_column):
        symbols = ", ".join(
            group[symbol_column].astype(str).tolist()
        )

        print(f"{security_type}: {symbols}")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        ALL_SYMBOLS_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    type_summary.to_csv(
        TYPE_SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    type_exchange_summary.to_csv(
        TYPE_EXCHANGE_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    type_samples.to_csv(
        TYPE_SAMPLES_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("")
    print("========================================")
    print("HOAN TAT")
    print("========================================")

    print(f"Tong ma duy nhat: {result[symbol_column].nunique()}")
    print(f"Da luu: {ALL_SYMBOLS_FILE}")
    print(f"Da luu: {TYPE_SUMMARY_FILE}")
    print(f"Da luu: {TYPE_EXCHANGE_FILE}")
    print(f"Da luu: {TYPE_SAMPLES_FILE}")


if __name__ == "__main__":
    main()
