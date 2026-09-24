from __future__ import annotations

import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urljoin
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

# GAS time-driven trigger thuong tre 1-2 phut. Cho phep mot khoang grace ngan
# de run 11:31 duoc ghi vao slot 11:30 va run 15:01 vao slot 15:00.
MARKET_CLOSE_GRACE_MINUTES = 4
INTRADAY_SLOT_MINUTES = 5

READ_ONLY_GAS_ACTIONS = frozenset(
    {
        "get_daily_baseline",
        "get_rvol_reference",
    }
)
RETRYABLE_HTTP_STATUS = frozenset(
    {
        404,
        408,
        425,
        429,
        500,
        502,
        503,
        504,
    }
)
GAS_MAX_ATTEMPTS = 4
GAS_RETRY_DELAYS_SECONDS = (2, 5, 10)
GAS_TIMEOUT_SECONDS = 180


def normalize_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.upper()


def normalize_exchange_value(value: Any) -> str:
    exchange = str(value or "").strip().upper()
    return {
        "HSX": "HOSE",
        "UPCO": "UPCOM",
        "UPCOM": "UPCOM",
    }.get(exchange, exchange)


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
    df["exchange"] = (
        normalize_text(df["exchange"])
        .replace({"HSX": "HOSE", "UPCO": "UPCOM"})
    )
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


def retry_delay(attempt: int) -> int:
    index = min(
        max(attempt - 1, 0),
        len(GAS_RETRY_DELAYS_SECONDS) - 1,
    )
    return GAS_RETRY_DELAYS_SECONDS[index]


def response_preview(response: requests.Response) -> str:
    text = (response.text or "").strip().replace("\n", " ")
    return text[:500]


def fetch_redirect_response(redirect_url: str, action: str) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, GAS_MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                redirect_url,
                timeout=GAS_TIMEOUT_SECONDS,
                allow_redirects=True,
            )
            if (
                response.status_code in RETRYABLE_HTTP_STATUS
                and attempt < GAS_MAX_ATTEMPTS
            ):
                delay = retry_delay(attempt)
                print(
                    f"GAS redirect tam loi HTTP {response.status_code} "
                    f"cho action={action}; thu lai GET sau {delay}s "
                    f"({attempt}/{GAS_MAX_ATTEMPTS})."
                )
                sleep(delay)
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= GAS_MAX_ATTEMPTS:
                break
            delay = retry_delay(attempt)
            print(
                f"Khong tai duoc GAS redirect cho action={action}: "
                f"{type(exc).__name__}; thu lai GET sau {delay}s "
                f"({attempt}/{GAS_MAX_ATTEMPTS})."
            )
            sleep(delay)
    raise RuntimeError(
        f"Khong lay duoc phan hoi GAS sau {GAS_MAX_ATTEMPTS} lan GET "
        f"cho action={action}: {last_error}"
    ) from last_error


def gas_post_once(action: str, body: dict[str, Any]) -> requests.Response:
    response = requests.post(
        GAS_WEB_APP_URL,
        json=body,
        timeout=GAS_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    if response.is_redirect or response.is_permanent_redirect:
        location = response.headers.get("Location", "").strip()
        if not location:
            raise RuntimeError(
                f"GAS chuyen huong nhung thieu Location cho action={action}"
            )
        return fetch_redirect_response(urljoin(GAS_WEB_APP_URL, location), action)
    response.raise_for_status()
    return response


def gas_request(action: str, **payload: Any) -> dict[str, Any]:
    if not GAS_WEB_APP_URL or not GAS_API_SECRET:
        raise RuntimeError("Thieu GAS_WEB_APP_URL hoac GAS_API_SECRET")

    body = {"secret": GAS_API_SECRET, "action": action, **payload}
    read_only = action in READ_ONLY_GAS_ACTIONS
    response: requests.Response | None = None

    for attempt in range(1, GAS_MAX_ATTEMPTS + 1):
        try:
            response = gas_post_once(action, body)
            break
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else None
            retryable = status is None or status in RETRYABLE_HTTP_STATUS
            if not read_only:
                raise RuntimeError(
                    f"GAS write action={action} that bai; khong POST lai "
                    "de tranh ghi trung. Hay kiem tra Sheet/Run_Log truoc "
                    f"khi chay lai. Chi tiet: {exc}"
                ) from exc
            if not retryable or attempt >= GAS_MAX_ATTEMPTS:
                raise
            delay = retry_delay(attempt)
            print(
                f"GAS read action={action} tam loi"
                f"{f' HTTP {status}' if status else ''}; "
                f"thu lai POST sau {delay}s ({attempt}/{GAS_MAX_ATTEMPTS})."
            )
            sleep(delay)
        except RuntimeError:
            if not read_only or attempt >= GAS_MAX_ATTEMPTS:
                raise
            delay = retry_delay(attempt)
            print(
                f"GAS read action={action} chua co phan hoi hop le; "
                f"thu lai POST sau {delay}s ({attempt}/{GAS_MAX_ATTEMPTS})."
            )
            sleep(delay)

    if response is None:
        raise RuntimeError(f"Khong nhan duoc phan hoi GAS cho action={action}")
    try:
        result = response.json()
    except (json.JSONDecodeError, requests.exceptions.JSONDecodeError) as exc:
        raise RuntimeError(
            f"GAS khong tra JSON cho action={action}: {response_preview(response)}"
        ) from exc
    if not result.get("ok"):
        raise RuntimeError(f"GAS bao loi: {result.get('error')}")
    return result


def now_vn() -> datetime:
    return datetime.now(TIMEZONE)


def floor_slot(dt: datetime, minutes: int = INTRADAY_SLOT_MINUTES) -> str:
    minute = (dt.minute // minutes) * minutes
    return dt.replace(minute=minute, second=0, microsecond=0).strftime("%H:%M")


def market_snapshot_slot(dt: datetime) -> str:
    """Slot raw de luu snapshot, co clamp cac run tre sau gio dong cua."""
    current_minutes = dt.hour * 60 + dt.minute
    morning_close = 11 * 60 + 30
    afternoon_close = 15 * 60

    if morning_close < current_minutes <= morning_close + MARKET_CLOSE_GRACE_MINUTES:
        return "11:30"
    if afternoon_close < current_minutes <= afternoon_close + MARKET_CLOSE_GRACE_MINUTES:
        return "15:00"
    return floor_slot(dt)


def is_market_slot(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    minutes = dt.hour * 60 + dt.minute
    in_morning = 9 * 60 <= minutes <= 11 * 60 + 30 + MARKET_CLOSE_GRACE_MINUTES
    in_afternoon = 13 * 60 <= minutes <= 15 * 60 + MARKET_CLOSE_GRACE_MINUTES
    return in_morning or in_afternoon


def _slot_datetime(dt: datetime, slot: str) -> datetime:
    hour, minute = [int(part) for part in slot.split(":", 1)]
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)


def rvol_window_slots(
    dt: datetime,
    exchange: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Tra ve (end_slot, start_slot) cua RVOL30.

    - 5 phut/slot.
    - Khong vuot qua gio nghi trua.
    - Sau 14:45, HOSE/HNX khoa block cuoi tai 14:15->14:45.
    - UPCOM tiep tuc rolling den block cuoi 14:30->15:00.
    - Run tre 11:31/15:01 duoc clamp ve 11:30/15:00.
    """
    snapshot_slot = market_snapshot_slot(dt)
    slot_dt = _slot_datetime(dt, snapshot_slot)
    current = slot_dt.time()

    if MORNING_START <= current <= MORNING_END:
        if current < time(9, 30):
            return snapshot_slot, None
        return snapshot_slot, floor_slot(slot_dt - timedelta(minutes=30))

    if AFTERNOON_START <= current <= AFTERNOON_END:
        normalized_exchange = normalize_exchange_value(exchange)
        close_slot = "14:45" if normalized_exchange in {"HOSE", "HNX"} else "15:00"
        close_dt = _slot_datetime(dt, close_slot)
        effective_dt = min(slot_dt, close_dt)
        effective_slot = effective_dt.strftime("%H:%M")
        if effective_dt.time() < time(13, 30):
            return effective_slot, None
        return effective_slot, floor_slot(effective_dt - timedelta(minutes=30))

    return snapshot_slot, None


def safe_pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = pd.to_numeric(denominator, errors="coerce")
    numerator = pd.to_numeric(numerator, errors="coerce")
    return numerator.div(denominator.where(denominator > 0)).mul(100)
