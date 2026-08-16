from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from time import monotonic, sleep
from typing import Any

import pandas as pd
import requests
from vnai.beam.auth import authenticator
from vnstock.api.quote import Quote

from common import load_watchlist, now_vn, records

PRIMARY_SOURCE = "VCI"
FALLBACK_SOURCE = "KBS"
# Neu nguon chinh co phien cu hon run_date qua nguong nay, thu nguon du phong.
# 4 ngay van bao phu cuoi tuan + 1 ngay nghi le lien ke, tranh hoi KBS vo ich.
SOURCE_STALE_AFTER_DAYS = 4
MA_SESSIONS = 200
MA10_SESSIONS = 10
AVG_VOLUME_SESSIONS = 10
LOOKBACK_DAYS = 500

# VNStock Community: 60 request/phut.
# VCI la nguon chinh; KBS chi duoc goi khi VCI loi/empty/qua cu.
# 1.25 giay/request ~= 48 request/phut, de lai bien an toan.
REQUEST_INTERVAL_SECONDS = 1.25
SOURCE_MAX_RETRIES = 3
RATE_LIMIT_WAIT_SECONDS = 65

# Sau luot dau, chi retry cac ma loi. Tong cong: 1 luot dau + 3 luot retry.
SYMBOL_RETRY_ROUNDS = 3
SYMBOL_RETRY_DELAYS_SECONDS = (15, 30, 60)

# Ghi Supabase tung phan de khong mat ket qua neu workflow bi dung giua chung.
SUPABASE_BATCH_SIZE = 25
SUPABASE_MAX_ATTEMPTS = 4
SUPABASE_RETRY_DELAYS_SECONDS = (2, 5, 10)
SUPABASE_TIMEOUT_SECONDS = 60

SHEET_BACKUP_TIMEOUT_SECONDS = 30


def backup_sheet_best_effort(rows: list[dict[str, Any]], run_log: dict[str, Any]) -> tuple[bool, str]:
    """
    Gui backup sang GAS dung mot lan voi timeout ngan.

    Sheet chi la backup trong giai doan chuyen tiep, nen loi/timeout tai day
    khong duoc lam workflow Daily Baseline that bai khi Supabase da luu xong.
    """
    gas_url = os.getenv("GAS_WEB_APP_URL", "").strip()
    gas_secret = os.getenv("GAS_API_SECRET", "").strip()

    if not gas_url or not gas_secret:
        return False, "Sheet backup skipped: thieu GAS_WEB_APP_URL hoac GAS_API_SECRET"

    body = {
        "secret": gas_secret,
        "action": "replace_daily_baseline",
        "rows": rows,
        "run_log": run_log,
    }

    try:
        response = requests.post(
            gas_url,
            json=body,
            timeout=SHEET_BACKUP_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()

        try:
            result = response.json()
        except ValueError:
            return False, (
                "Sheet backup warning: GAS khong tra JSON hop le; "
                f"HTTP {response.status_code}"
            )

        if not result.get("ok"):
            return False, f"Sheet backup warning: GAS bao loi: {result.get('error')}"

        return True, f"Sheet backup OK: {result}"
    except requests.RequestException as exc:
        return False, (
            "Sheet backup warning: "
            f"{type(exc).__name__}: {exc}"
        )


SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SECRET_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)

_last_request_started_at: float | None = None


def verify_vnstock_api_access() -> None:
    """Dung som neu GitHub Actions chua nhan API key Community."""
    if not os.getenv("VNSTOCK_API_KEY", "").strip():
        raise RuntimeError(
            "Thieu VNSTOCK_API_KEY. Hay tao GitHub Actions secret "
            "VNSTOCK_API_KEY de mo gioi han Community 60 request/phut."
        )

    tier = authenticator.get_tier(force_refresh=True)
    limits = authenticator.get_limits(tier)
    per_minute = int(limits.get("min", 0))
    if per_minute < 60:
        raise RuntimeError(
            f"VNSTOCK_API_KEY chua duoc nhan: tier={tier}, "
            f"limit={per_minute} request/phut."
        )

    print(
        f"VNStock API: tier={tier}, limit={per_minute} request/phut; "
        "job tu gioi han 48 request/phut."
    )


def verify_supabase_config() -> None:
    if not SUPABASE_URL:
        raise RuntimeError("Thieu GitHub Secret SUPABASE_URL")
    if not SUPABASE_KEY:
        raise RuntimeError(
            "Thieu GitHub Secret SUPABASE_SECRET_KEY "
            "(hoac SUPABASE_SERVICE_ROLE_KEY cu)"
        )


def is_rate_limit(error: BaseException) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in ("rate limit", "too many requests", "429", "requests/minute")
    )


def wait_for_request_slot() -> None:
    """Giu khoang cach toi thieu giua hai request vnstock thuc te."""
    global _last_request_started_at

    now = monotonic()
    if _last_request_started_at is not None:
        remaining = REQUEST_INTERVAL_SECONDS - (now - _last_request_started_at)
        if remaining > 0:
            sleep(remaining)

    _last_request_started_at = monotonic()


def prepare_history(data: pd.DataFrame, run_date: date) -> pd.DataFrame:
    required = {"time", "close", "volume"}
    missing = required.difference(data.columns)
    if missing:
        raise RuntimeError(f"History thieu cot {sorted(missing)}")

    df = data.copy()
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df.dropna(subset=["time", "close", "volume"])
    df = df[(df["close"] > 0) & (df["volume"] >= 0)]

    # Baseline chi dung cac phien da ket thuc TRUOC ngay chay.
    # Vi du: sang thu Bay lay phien chot thu Sau.
    df = df[df["time"].dt.date < run_date]
    df = (
        df.sort_values("time")
        .drop_duplicates("time", keep="last")
        .reset_index(drop=True)
    )
    if df.empty:
        raise RuntimeError(f"Khong co phien da ket thuc truoc {run_date.isoformat()}")
    return df


def normalize_price_unit(history: pd.DataFrame) -> pd.DataFrame:
    df = history.copy()
    # Lich su ngay cua vnstock thuong tra gia theo nghin dong,
    # trong khi bang gia intraday dung don vi dong.
    sample_size = min(20, len(df))
    if sample_size > 0 and float(df["close"].tail(sample_size).median()) < 1000:
        df["close"] = df["close"] * 1000
    return df


def fetch_source_history(
    symbol: str,
    source: str,
    start: str,
    end: str,
    run_date: date,
) -> pd.DataFrame:
    last_error = "empty"

    for attempt in range(1, SOURCE_MAX_RETRIES + 1):
        try:
            wait_for_request_slot()
            data = Quote(symbol=symbol, source=source).history(
                start=start,
                end=end,
                interval="1D",
            )
            if data is None or data.empty:
                raise RuntimeError("empty")
            return normalize_price_unit(prepare_history(data, run_date))
        except (Exception, SystemExit) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if is_rate_limit(exc) and attempt < SOURCE_MAX_RETRIES:
                print(
                    f"  -> {source} cham rate limit; cho "
                    f"{RATE_LIMIT_WAIT_SECONDS}s roi thu lai "
                    f"({attempt}/{SOURCE_MAX_RETRIES})"
                )
                sleep(RATE_LIMIT_WAIT_SECONDS)
                continue
            break

    raise RuntimeError(f"{source}: {last_error}")


def source_is_too_stale(history: pd.DataFrame, run_date: date) -> bool:
    latest_date = history.iloc[-1]["time"].date()
    age_days = (run_date - latest_date).days
    return age_days > SOURCE_STALE_AFTER_DAYS


def get_history(
    symbol: str,
    start: str,
    end: str,
    run_date: date,
) -> tuple[pd.DataFrame, str]:
    """
    Uu tien VCI de giam gan mot nua so request.

    - VCI hop le va khong qua cu: dung ngay, KHONG goi KBS.
    - VCI loi/empty: goi KBS fallback.
    - VCI co du lieu nhung qua cu: thu KBS; neu KBS khong tot hon thi van giu VCI.
    """
    primary_history: pd.DataFrame | None = None
    primary_error: str | None = None

    try:
        primary_history = fetch_source_history(
            symbol, PRIMARY_SOURCE, start, end, run_date
        )
        primary_date = primary_history.iloc[-1]["time"].date()

        if not source_is_too_stale(primary_history, run_date):
            return primary_history, PRIMARY_SOURCE

        print(
            f"  -> {PRIMARY_SOURCE} co du lieu cu {primary_date.isoformat()}; "
            f"thu {FALLBACK_SOURCE} fallback"
        )
    except Exception as exc:
        primary_error = str(exc)
        print(
            f"  -> {PRIMARY_SOURCE} khong dung duoc; "
            f"thu {FALLBACK_SOURCE} fallback"
        )

    try:
        fallback_history = fetch_source_history(
            symbol, FALLBACK_SOURCE, start, end, run_date
        )
        fallback_date = fallback_history.iloc[-1]["time"].date()

        if primary_history is None:
            return fallback_history, FALLBACK_SOURCE

        primary_date = primary_history.iloc[-1]["time"].date()
        if fallback_date > primary_date:
            return fallback_history, FALLBACK_SOURCE

        # KBS khong moi hon: giu VCI de tranh thay doi nguon khong can thiet.
        return primary_history, PRIMARY_SOURCE
    except Exception as fallback_exc:
        if primary_history is not None:
            return primary_history, PRIMARY_SOURCE

        raise RuntimeError(
            f"{PRIMARY_SOURCE}: {primary_error or 'unknown'} | "
            f"{FALLBACK_SOURCE}: {fallback_exc}"
        ) from fallback_exc


def calculate_symbol(
    symbol: str,
    exchange: str,
    start: str,
    end: str,
    run_date: date,
    updated_at: datetime,
) -> dict[str, Any]:
    history, source = get_history(symbol, start, end, run_date)
    session_count = len(history)
    ma_sessions = min(session_count, MA_SESSIONS)
    ma10_sessions = min(session_count, MA10_SESSIONS)
    volume_sessions = min(session_count, AVG_VOLUME_SESSIONS)
    latest = history.iloc[-1]
    trading_date = latest["time"].date()

    if trading_date >= run_date:
        raise RuntimeError(
            f"Baseline khong an toan: trading_date={trading_date}, "
            f"run_date={run_date}"
        )

    return {
        "symbol": symbol,
        "exchange": exchange,
        "trading_date": trading_date.isoformat(),
        "previous_close": round(float(latest["close"]), 4),
        "ma200": round(float(history["close"].tail(ma_sessions).mean()), 4),
        "ma200_sessions": ma_sessions,
        "avg_volume_10": round(
            float(history["volume"].tail(volume_sessions).mean()), 4
        ),
        "avg_volume_sessions": volume_sessions,
        "source": source,
        "updated_at": updated_at.isoformat(),
        "data_status": "OK",
        "ma10": round(float(history["close"].tail(ma10_sessions).mean()), 4),
        "ma10_sessions": ma10_sessions,
    }


def supabase_headers() -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }

    # Key moi sb_secret_* phai gui qua apikey header.
    # Legacy service_role la JWT thi van dung Authorization Bearer.
    if not SUPABASE_KEY.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"

    return headers


def supabase_retry_delay(attempt: int) -> int:
    index = min(max(attempt - 1, 0), len(SUPABASE_RETRY_DELAYS_SECONDS) - 1)
    return SUPABASE_RETRY_DELAYS_SECONDS[index]


def supabase_request(
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    payload: Any = None,
    prefer: str | None = None,
) -> requests.Response:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = supabase_headers()
    if prefer:
        headers["Prefer"] = prefer

    last_error: Exception | None = None

    for attempt in range(1, SUPABASE_MAX_ATTEMPTS + 1):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                json=payload,
                timeout=SUPABASE_TIMEOUT_SECONDS,
            )

            if response.status_code in {408, 425, 429, 500, 502, 503, 504}:
                if attempt < SUPABASE_MAX_ATTEMPTS:
                    delay = supabase_retry_delay(attempt)
                    print(
                        f"Supabase tam loi HTTP {response.status_code}; "
                        f"thu lai sau {delay}s ({attempt}/{SUPABASE_MAX_ATTEMPTS})"
                    )
                    sleep(delay)
                    continue

            response.raise_for_status()
            return response
        except requests.HTTPError as exc:
            last_error = exc
            status = exc.response.status_code if exc.response is not None else None

            # 4xx nhu 401/403 la loi config/quyen co dinh; retry khong giup gi.
            if status is not None and 400 <= status < 500 and status not in {408, 425, 429}:
                body = (exc.response.text or "").strip()[:300] if exc.response else ""
                raise RuntimeError(
                    f"Supabase HTTP {status} tai {table}; khong retry. {body}"
                ) from exc

            if attempt >= SUPABASE_MAX_ATTEMPTS:
                break
            delay = supabase_retry_delay(attempt)
            print(
                f"Supabase HTTP loi {status}; "
                f"thu lai sau {delay}s ({attempt}/{SUPABASE_MAX_ATTEMPTS})"
            )
            sleep(delay)
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= SUPABASE_MAX_ATTEMPTS:
                break
            delay = supabase_retry_delay(attempt)
            print(
                f"Supabase request loi {type(exc).__name__}; "
                f"thu lai sau {delay}s ({attempt}/{SUPABASE_MAX_ATTEMPTS})"
            )
            sleep(delay)

    raise RuntimeError(
        f"Supabase request that bai sau {SUPABASE_MAX_ATTEMPTS} lan: {last_error}"
    ) from last_error


def upsert_daily_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    supabase_request(
        "POST",
        "daily_baseline",
        params={"on_conflict": "symbol,trading_date"},
        payload=rows,
        prefer="resolution=merge-duplicates,return=minimal",
    )
    print(f"  -> Supabase da ghi {len(rows)} baseline rows")


def upsert_scan_run(run_log: dict[str, Any]) -> None:
    supabase_request(
        "POST",
        "scan_runs",
        params={"on_conflict": "run_id"},
        payload=[run_log],
        prefer="resolution=merge-duplicates,return=minimal",
    )


def load_today_checkpoints(run_at: datetime) -> dict[str, dict[str, Any]]:
    """
    Lay cac ma da ghi OK trong ngay hien tai.

    Neu workflow bi fail/timeout va chay lai cung ngay, cac ma nay se duoc bo qua,
    chi scan lai nhung ma chua co checkpoint OK.
    """
    day_start = run_at.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    response = supabase_request(
        "GET",
        "daily_baseline",
        params={
            "select": "*",
            "updated_at": f"gte.{day_start}",
            "data_status": "eq.OK",
            "order": "updated_at.desc",
            "limit": "1000",
        },
    )
    rows = response.json()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol and symbol not in result:
            result[symbol] = row
    return result


def load_latest_baseline(symbol: str) -> dict[str, Any] | None:
    response = supabase_request(
        "GET",
        "daily_baseline",
        params={
            "select": "*",
            "symbol": f"eq.{symbol}",
            "order": "trading_date.desc,updated_at.desc",
            "limit": "1",
        },
    )
    rows = response.json()
    return rows[0] if rows else None


def stale_row_from_previous(
    symbol: str,
    exchange: str,
    error_message: str,
    run_at: datetime,
) -> dict[str, Any]:
    previous = load_latest_baseline(symbol)
    if previous:
        row = dict(previous)
        row["exchange"] = exchange
        row["updated_at"] = run_at.isoformat()
        row["data_status"] = f"STALE: {error_message}"[:500]
        return row

    return {
        "symbol": symbol,
        "exchange": exchange,
        "trading_date": None,
        "previous_close": None,
        "ma200": None,
        "ma200_sessions": 0,
        "avg_volume_10": None,
        "avg_volume_sessions": 0,
        "source": None,
        "updated_at": run_at.isoformat(),
        "data_status": f"ERROR: {error_message}"[:500],
        "ma10": None,
        "ma10_sessions": 0,
    }


def flush_batch(batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    upsert_daily_rows(batch)
    batch.clear()


def main() -> None:
    verify_vnstock_api_access()
    verify_supabase_config()

    run_at = now_vn()
    run_date = run_at.date()
    run_id = run_at.strftime("daily-%Y%m%d-%H%M%S")
    watchlist = load_watchlist()
    watchlist_map = {
        str(row["symbol"]).strip().upper(): str(row["exchange"]).strip().upper()
        for _, row in watchlist.iterrows()
    }

    end = run_date.isoformat()
    start = (run_date - timedelta(days=LOOKBACK_DAYS)).isoformat()

    checkpoint_rows = load_today_checkpoints(run_at)
    success_rows: dict[str, dict[str, Any]] = {
        symbol: row
        for symbol, row in checkpoint_rows.items()
        if symbol in watchlist_map
    }

    if success_rows:
        print(
            f"Resume: Supabase da co {len(success_rows)}/{len(watchlist_map)} "
            "ma OK trong hom nay; se bo qua cac ma nay."
        )

    pending_symbols = [
        symbol for symbol in watchlist_map if symbol not in success_rows
    ]
    last_errors: dict[str, str] = {}

    total_rounds = 1 + SYMBOL_RETRY_ROUNDS
    for round_index in range(total_rounds):
        if not pending_symbols:
            break

        if round_index > 0:
            delay = SYMBOL_RETRY_DELAYS_SECONDS[
                min(round_index - 1, len(SYMBOL_RETRY_DELAYS_SECONDS) - 1)
            ]
            print(
                f"\nRetry round {round_index}/{SYMBOL_RETRY_ROUNDS}: "
                f"{len(pending_symbols)} ma loi; cho {delay}s truoc khi retry."
            )
            sleep(delay)
        else:
            print(f"Bat dau Daily Baseline: {len(pending_symbols)} ma can scan.")

        failed_this_round: list[str] = []
        batch: list[dict[str, Any]] = []

        for index, symbol in enumerate(pending_symbols, start=1):
            exchange = watchlist_map[symbol]
            print(
                f"[round {round_index + 1}/{total_rounds}] "
                f"[{index}/{len(pending_symbols)}] {symbol}"
            )

            try:
                row = calculate_symbol(
                    symbol=symbol,
                    exchange=exchange,
                    start=start,
                    end=end,
                    run_date=run_date,
                    updated_at=run_at,
                )
                success_rows[symbol] = row
                last_errors.pop(symbol, None)
                batch.append(row)
                print(
                    f"  -> {row['source']} | baseline {row['trading_date']} | OK"
                )

                if len(batch) >= SUPABASE_BATCH_SIZE:
                    flush_batch(batch)
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                last_errors[symbol] = message
                failed_this_round.append(symbol)
                print(f"  -> ERROR: {message}")

        flush_batch(batch)
        pending_symbols = failed_this_round

    final_failed = list(pending_symbols)
    success_count = len(watchlist_map) - len(final_failed)
    finished_at = now_vn()

    # Tao bang 256 ma cho Sheet backup. Ma con loi sau moi retry se dung baseline cu
    # tu Supabase va danh dau STALE, khong xoa du lieu cu.
    sheet_rows: list[dict[str, Any]] = []
    for symbol, exchange in watchlist_map.items():
        if symbol in success_rows:
            sheet_rows.append(success_rows[symbol])
        else:
            sheet_rows.append(
                stale_row_from_previous(
                    symbol=symbol,
                    exchange=exchange,
                    error_message=last_errors.get(symbol, "unknown error"),
                    run_at=run_at,
                )
            )

    status = "SUCCESS" if not final_failed else "PARTIAL"
    failed_text = ", ".join(final_failed[:30])
    if len(final_failed) > 30:
        failed_text += f", ... (+{len(final_failed) - 30})"

    message = f"Daily baseline completed: {success_count}/{len(watchlist_map)} symbols"
    if final_failed:
        message += f"; failed after retries: {failed_text}"

    run_log = {
        "run_id": run_id,
        "job_type": "DAILY_BASELINE",
        "started_at": run_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "status": status,
        "symbols_requested": len(watchlist_map),
        "symbols_success": success_count,
        "symbols_failed": len(final_failed),
        "message": message[:1000],
    }
    upsert_scan_run(run_log)

    # Sheet chi la backup/nguon doc cu trong giai doan chuyen tiep.
    # Backup chi thu dung mot lan, timeout ngan va KHONG lam workflow fail.
    sheet_ok, sheet_message = backup_sheet_best_effort(
        records(pd.DataFrame(sheet_rows)),
        run_log,
    )
    print(sheet_message)

    if not sheet_ok:
        # Giu nguyen SUCCESS/PARTIAL theo ket qua Supabase; chi bo sung canh bao.
        run_log["finished_at"] = now_vn().isoformat()
        run_log["message"] = f"{message}; {sheet_message}"[:1000]
        upsert_scan_run(run_log)

    if final_failed:
        raise RuntimeError(
            f"Con {len(final_failed)} ma loi sau {SYMBOL_RETRY_ROUNDS} luot retry: "
            f"{failed_text}. Chay lai workflow trong cung ngay se chi scan lai "
            "cac ma chua co checkpoint OK."
        )

    print(
        f"DONE: {success_count}/{len(watchlist_map)} ma OK; "
        f"Supabase primary; Sheet backup={'OK' if sheet_ok else 'WARNING'}."
    )


if __name__ == "__main__":
    main()
