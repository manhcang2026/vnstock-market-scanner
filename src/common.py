from __future__ import annotations

import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
WATCHLIST_FILE = Path("config/watchlist.csv")
GAS_WEB_APP_URL = os.getenv("GAS_WEB_APP_URL", "").strip()
GAS_API_SECRET = os.getenv("GAS_API_SECRET", "").strip()

MORNING_START = time(9, 0)
MORNING_END = time(11, 30)
AFTERNOON_START = time(13, 0)
AFTERNOON_END = time(15, 0)


def normalize_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.upper()


def load_watchlist() -> pd.DataFrame:
    if not WATCHLIST_FILE.exists():
        raise FileNotFoundError(f"Khong tim thay {WATCHLIST_FILE}")
    df = pd.read_csv(WATCHLIST_FILE)
    required = {"symbol", "exchange"}
    missing = required.difference(df.columns)
    if missing:
        raise RuntimeError(f"Watchlist thieu cot: {sorted(missing)}")
    df = df.copy()
    df["symbol"] = normalize_text(df["symbol"])
    df["exchange"] = normalize_text(df["exchange"]).replace({"HSX": "HOSE"})
    return (
        df[df["symbol"] != ""]
        .drop_duplicates("symbol", keep="first")
        .sort_values(["exchange", "symbol"])
        .reset_index(drop=True)
    )


def clean_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {str(k): clean_value(v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def gas_request(action: str, **payload: Any) -> dict[str, Any]:
    if not GAS_WEB_APP_URL or not GAS_API_SECRET:
        raise RuntimeError("Thieu GAS_WEB_APP_URL hoac GAS_API_SECRET")
    body = {"secret": GAS_API_SECRET, "action": action, **payload}
    response = requests.post(
        GAS_WEB_APP_URL,
        json=body,
        timeout=180,
        allow_redirects=True,
    )
    response.raise_for_status()
    try:
        result = response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GAS khong tra JSON: {response.text[:1000]}") from exc
    if not result.get("ok"):
        raise RuntimeError(f"GAS bao loi: {result.get('error')}")
    return result


def now_vn() -> datetime:
    return datetime.now(TIMEZONE)


def floor_slot(dt: datetime) -> str:
    minute = (dt.minute // 10) * 10
    return dt.replace(minute=minute, second=0, microsecond=0).strftime("%H:%M")


def is_market_slot(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    current = dt.time()
    return MORNING_START <= current <= MORNING_END or AFTERNOON_START <= current <= AFTERNOON_END


def rvol_window_slots(dt: datetime) -> tuple[str | None, str | None]:
    """Return current slot and start slot 30 trading minutes earlier, never crossing lunch."""
    slot_dt = dt.replace(minute=(dt.minute // 10) * 10, second=0, microsecond=0)
    current = slot_dt.time()
    if MORNING_START <= current <= MORNING_END:
        if slot_dt < slot_dt.replace(hour=9, minute=30):
            return floor_slot(slot_dt), None
        return floor_slot(slot_dt), floor_slot(slot_dt - timedelta(minutes=30))
    if AFTERNOON_START <= current <= AFTERNOON_END:
        if slot_dt < slot_dt.replace(hour=13, minute=30):
            return floor_slot(slot_dt), None
        return floor_slot(slot_dt), floor_slot(slot_dt - timedelta(minutes=30))
    return floor_slot(slot_dt), None


def safe_pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = pd.to_numeric(denominator, errors="coerce")
    numerator = pd.to_numeric(numerator, errors="coerce")
    return numerator.div(denominator.where(denominator > 0)).mul(100)
