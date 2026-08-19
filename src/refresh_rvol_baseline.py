from __future__ import annotations

import os
from datetime import time, timedelta
from time import sleep

import requests

from common import now_vn

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SECRET_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)
TIMEOUT_SECONDS = 180
MAX_ATTEMPTS = 4
RETRY_DELAYS_SECONDS = (2, 5, 10)
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}

AFTER_MARKET_CLOSE = time(15, 5)


def rvol_as_of_date(run_at):
    """
    RPC SQL dung trading_date < p_as_of_date.

    - 19/08 sau 15:05 -> p_as_of_date=20/08 -> lay duoc 19/08.
    - 20/08 luc 01:00 -> p_as_of_date=20/08 -> cung lay den 19/08.
    """
    if run_at.weekday() < 5 and run_at.time() >= AFTER_MARKET_CLOSE:
        return run_at.date() + timedelta(days=1)
    return run_at.date()


def headers() -> dict[str, str]:
    if not SUPABASE_URL:
        raise RuntimeError("Thieu GitHub Secret SUPABASE_URL")
    if not SUPABASE_KEY:
        raise RuntimeError(
            "Thieu GitHub Secret SUPABASE_SECRET_KEY "
            "(hoac SUPABASE_SERVICE_ROLE_KEY cu)"
        )

    result = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    if not SUPABASE_KEY.startswith("sb_secret_"):
        result["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return result


def main() -> None:
    run_at = now_vn()
    as_of_date = rvol_as_of_date(run_at)

    url = f"{SUPABASE_URL}/rest/v1/rpc/refresh_rvol30_baseline"
    payload = {"p_as_of_date": as_of_date.isoformat()}
    last_error: Exception | None = None

    print(
        "RVOL30 refresh cutoff: "
        f"run_at={run_at.isoformat()} | "
        f"p_as_of_date={as_of_date.isoformat()}"
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(
                url,
                headers=headers(),
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )
            if response.status_code in RETRYABLE_STATUS and attempt < MAX_ATTEMPTS:
                delay = RETRY_DELAYS_SECONDS[
                    min(attempt - 1, len(RETRY_DELAYS_SECONDS) - 1)
                ]
                print(
                    f"RVOL baseline RPC tam loi HTTP {response.status_code}; "
                    f"thu lai sau {delay}s ({attempt}/{MAX_ATTEMPTS})."
                )
                sleep(delay)
                continue

            response.raise_for_status()
            result = response.json()
            print(f"RVOL30 baseline refresh OK: {result}")
            return

        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt >= MAX_ATTEMPTS:
                break

            delay = RETRY_DELAYS_SECONDS[
                min(attempt - 1, len(RETRY_DELAYS_SECONDS) - 1)
            ]
            print(
                f"RVOL baseline RPC loi {type(exc).__name__}; "
                f"thu lai sau {delay}s ({attempt}/{MAX_ATTEMPTS})."
            )
            sleep(delay)

    raise RuntimeError(
        f"Khong refresh duoc rvol30_baseline sau "
        f"{MAX_ATTEMPTS} lan: {last_error}"
    ) from last_error


if __name__ == "__main__":
    main()
