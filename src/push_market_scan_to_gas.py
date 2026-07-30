import json
import os
from pathlib import Path

import pandas as pd
import requests


MARKET_SCAN_FILE = Path("data/market_scan_latest.csv")
SIGNALS_FILE = Path("data/signals_latest.csv")

GAS_WEB_APP_URL = os.environ.get(
    "GAS_WEB_APP_URL",
    "",
).strip()

GAS_API_SECRET = os.environ.get(
    "GAS_API_SECRET",
    "",
).strip()


def clean_value(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    if hasattr(value, "item"):
        value = value.item()

    return value


def dataframe_to_records(
    dataframe: pd.DataFrame,
) -> list[dict]:
    records = []

    for raw_record in dataframe.to_dict(
        orient="records"
    ):
        clean_record = {
            str(key): clean_value(value)
            for key, value in raw_record.items()
        }

        records.append(clean_record)

    return records


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Khong tim thay file: {path}"
        )

    return pd.read_csv(path)


def main() -> None:
    if not GAS_WEB_APP_URL:
        raise RuntimeError(
            "Thieu bien moi truong GAS_WEB_APP_URL."
        )

    if not GAS_API_SECRET:
        raise RuntimeError(
            "Thieu bien moi truong GAS_API_SECRET."
        )

    latest_df = load_csv(
        MARKET_SCAN_FILE
    )

    signals_df = load_csv(
        SIGNALS_FILE
    )

    payload = {
        "secret": GAS_API_SECRET,
        "action": "update_market_scan",
        "latest": dataframe_to_records(
            latest_df
        ),
        "signals": dataframe_to_records(
            signals_df
        ),
    }

    print(
        f"Dang gui {len(latest_df)} dong latest "
        f"va {len(signals_df)} dong signal sang GAS..."
    )

    response = requests.post(
        GAS_WEB_APP_URL,
        json=payload,
        timeout=120,
        allow_redirects=True,
    )

    print(
        f"HTTP status: {response.status_code}"
    )

    print(
        f"Response: {response.text[:2000]}"
    )

    response.raise_for_status()

    try:
        result = response.json()
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "GAS khong tra ve JSON hop le."
        ) from error

    if not result.get("ok"):
        raise RuntimeError(
            "GAS bao loi: "
            + str(result.get("error"))
        )

    print("Gui du lieu sang GAS thanh cong.")
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
