from pathlib import Path

import pandas as pd
from vnstock import Listing


RAW_FILE = Path("config/watchlist_raw.csv")
CLEAN_FILE = Path("config/watchlist.csv")
REJECTED_FILE = Path("output/watchlist_rejected.csv")

VALID_EXCHANGES = {"HOSE", "HNX", "UPCOM"}


def normalize_symbol_column(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )


def main() -> None:
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Khong tim thay file dau vao: {RAW_FILE}"
        )

    raw = pd.read_csv(RAW_FILE)

    if "symbol" not in raw.columns:
        raise RuntimeError(
            "File watchlist_raw.csv phai co cot symbol."
        )

    raw["symbol"] = normalize_symbol_column(raw["symbol"])

    raw = raw[
        raw["symbol"] != ""
    ].drop_duplicates(
        subset=["symbol"]
    ).reset_index(drop=True)

    print(f"So ma trong danh sach anh: {len(raw)}")

    listing = Listing(source="KBS")
    reference = listing.symbols_by_exchange()

    required_columns = {
        "symbol",
        "exchange",
        "type",
    }

    missing = required_columns.difference(reference.columns)

    if missing:
        raise RuntimeError(
            f"Danh muc Vnstock thieu cot: {sorted(missing)}"
        )

    reference = reference.copy()

    for column in ["symbol", "exchange", "type"]:
        reference[column] = (
            reference[column]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

    reference["exchange"] = reference["exchange"].replace(
        {"HSX": "HOSE"}
    )

    reference = reference.drop_duplicates(
        subset=["symbol"],
        keep="first",
    )

    checked = raw.merge(
        reference,
        how="left",
        on="symbol",
        suffixes=("", "_reference"),
    )

    checked["reject_reason"] = ""

    checked.loc[
        checked["exchange"].isna(),
        "reject_reason",
    ] = "NOT_FOUND"

    checked.loc[
        checked["exchange"].notna()
        & ~checked["exchange"].isin(VALID_EXCHANGES),
        "reject_reason",
    ] = "INVALID_EXCHANGE"

    checked.loc[
        checked["exchange"].notna()
        & checked["exchange"].isin(VALID_EXCHANGES)
        & (checked["type"] != "STOCK"),
        "reject_reason",
    ] = "NOT_STOCK"

    clean = checked[
        checked["reject_reason"] == ""
    ].copy()

    rejected = checked[
        checked["reject_reason"] != ""
    ].copy()

    clean_columns = [
        column
        for column in [
            "symbol",
            "exchange",
            "organ_name",
            "en_organ_name",
            "type",
            "id",
        ]
        if column in clean.columns
    ]

    clean = clean[
        clean_columns
    ].sort_values(
        by=["exchange", "symbol"]
    ).reset_index(drop=True)

    Path("config").mkdir(
        parents=True,
        exist_ok=True,
    )

    Path("output").mkdir(
        parents=True,
        exist_ok=True,
    )

    clean.to_csv(
        CLEAN_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    rejected.to_csv(
        REJECTED_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("")
    print("========================================")
    print("KET QUA WATCHLIST")
    print("========================================")
    print(f"Tong ma dau vao: {len(raw)}")
    print(f"Co phieu hop le: {len(clean)}")
    print(f"Bi loai: {len(rejected)}")

    if not clean.empty:
        print("")
        print("So ma hop le theo san:")
        print(
            clean.groupby("exchange")["symbol"]
            .nunique()
            .sort_index()
            .to_string()
        )

    if not rejected.empty:
        print("")
        print("Danh sach bi loai:")
        print(
            rejected[
                ["symbol", "exchange", "type", "reject_reason"]
            ].to_string(index=False)
        )

    print("")
    print(f"Da luu: {CLEAN_FILE}")
    print(f"Da luu: {REJECTED_FILE}")


if __name__ == "__main__":
    main()
