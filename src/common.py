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


def retry_delay(attempt: int) -> int:
    index = min(
        max(attempt - 1, 0),
        len(GAS_RETRY_DELAYS_SECONDS) - 1,
    )
    return GAS_RETRY_DELAYS_SECONDS[index]


def response_preview(response: requests.Response) -> str:
    text = (response.text or "").strip().replace("\n", " ")
    return text[:500]


def fetch_redirect_response(
    redirect_url: str,
    action: str,
) -> requests.Response:
    """
    Tai phan hoi tu URL chuyen huong cua GAS.

    Viec lap lai GET nay an toan cho ca lenh doc va lenh ghi vi
    khong gui lai POST da thuc thi Apps Script.
    """
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
    """Gui POST dung mot lan, sau do tu xu ly URL chuyen huong."""
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
        return fetch_redirect_response(
            urljoin(GAS_WEB_APP_URL, location),
            action,
        )

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
            status = (
                exc.response.status_code
                if exc.response is not None
                else None
            )
            retryable = status is None or status in RETRYABLE_HTTP_STATUS

            # Lenh ghi khong duoc POST lai: GAS co the da nhan du lieu
            # nhung phan hoi bi mat, gui lai co the tao snapshot/log trung.
            if not read_only:
                raise RuntimeError(
                    f"GAS write action={action} that bai; khong POST lai "
                    "de tranh ghi trung. Hay kiem tra Sheet/Run_Log truoc "
                    f"khi chay lai. Chi tiet: {exc}"
                ) from exc

            if (
                not retryable
                or attempt >= GAS_MAX_ATTEMPTS
            ):
                raise

            delay = retry_delay(attempt)
            print(
                f"GAS read action={action} tam loi"
                f"{f' HTTP {status}' if status else ''}; "
                f"thu lai POST sau {delay}s "
                f"({attempt}/{GAS_MAX_ATTEMPTS})."
            )
            sleep(delay)
        except RuntimeError:
            # Loi sau khi POST (vi du URL redirect hong) khong duoc
            # POST lai doi voi lenh ghi. Lenh doc co the thu lai an toan.
            if not read_only or attempt >= GAS_MAX_ATTEMPTS:
                raise
            delay = retry_delay(attempt)
            print(
                f"GAS read action={action} chua co phan hoi hop le; "
                f"thu lai POST sau {delay}s "
                f"({attempt}/{GAS_MAX_ATTEMPTS})."
            )
            sleep(delay)

    if response is None:
        raise RuntimeError(
            f"Khong nhan duoc phan hoi GAS cho action={action}"
        )

    try:
        result = response.json()
    except (json.JSONDecodeError, requests.exceptions.JSONDecodeError) as exc:
        raise RuntimeError(
            f"GAS khong tra JSON cho action={action}: "
            f"{response_preview(response)}"
        ) from exc

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
