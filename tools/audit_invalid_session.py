from __future__ import annotations

import argparse
import os
from typing import Any

import pandas as pd
import requests


def args():
    p = argparse.ArgumentParser(
        description="Read-only audit for a suspected non-trading intraday date."
    )
    p.add_argument("--invalid-date", required=True, help="YYYY-MM-DD")
    p.add_argument("--previous-date", required=True, help="YYYY-MM-DD")
    return p.parse_args()


def config():
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = (
        os.getenv("SUPABASE_SECRET_KEY", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE secret")
    headers = {"apikey": key}
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return url, headers


def get_rows(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    url, headers = config()
    r = requests.get(
        f"{url}/rest/v1/{table}",
        headers=headers,
        params=params,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def main():
    a = args()
    bad = pd.DataFrame(
        get_rows(
            "intraday_snapshots",
            {
                "select": "symbol,current_price,volume_accumulated,time_slot",
                "trading_date": f"eq.{a.invalid_date}",
                "time_slot": "eq.15:00:00",
                "order": "symbol.asc",
                "limit": "1000",
            },
        )
    )
    prev = pd.DataFrame(
        get_rows(
            "intraday_snapshots",
            {
                "select": "symbol,current_price,volume_accumulated,time_slot",
                "trading_date": f"eq.{a.previous_date}",
                "time_slot": "eq.15:00:00",
                "order": "symbol.asc",
                "limit": "1000",
            },
        )
    )

    print(f"invalid_date={a.invalid_date}: {len(bad)} EOD rows")
    print(f"previous_date={a.previous_date}: {len(prev)} EOD rows")
    if bad.empty or prev.empty:
        print("Not enough data to compare.")
        return

    m = bad.merge(prev, on="symbol", suffixes=("_bad", "_prev"))
    same_price = (
        pd.to_numeric(m.current_price_bad, errors="coerce")
        == pd.to_numeric(m.current_price_prev, errors="coerce")
    )
    same_volume = (
        pd.to_numeric(m.volume_accumulated_bad, errors="coerce")
        == pd.to_numeric(m.volume_accumulated_prev, errors="coerce")
    )
    same_both = same_price & same_volume
    print(
        "same price+volume: "
        f"{int(same_both.sum())}/{len(m)} "
        f"({same_both.mean():.2%})"
    )
    print("READ-ONLY AUDIT COMPLETE. Nothing was written or deleted.")


if __name__ == "__main__":
    main()
