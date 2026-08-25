from __future__ import annotations

import multiprocessing as mp
import os
from datetime import date, datetime, time, timedelta
from time import monotonic, sleep
from typing import Any

import pandas as pd
import requests
from vnai.beam.auth import authenticator
from vnstock.api.quote import Quote

from common import load_watchlist, now_vn

PRIMARY_SOURCE = "KBS"
FALLBACK_SOURCE = "VCI"

TARGET_SESSIONS = 250
MIN_REQUIRED_SESSIONS = 200
LOOKBACK_WINDOWS_DAYS = (500, 1200, 2400)
SOURCE_STALE_AFTER_DAYS = 4

REQUEST_INTERVAL_SECONDS = 1.25
SOURCE_MAX_RETRIES = 3
RATE_LIMIT_WAIT_SECONDS = 65

HISTORY_HARD_TIMEOUT_SECONDS = 15
SOURCE_BREAKER_TIMEOUT_THRESHOLD = 3
SOURCE_BREAKER_COOLDOWN_SECONDS = 300

SUPABASE_MAX_ATTEMPTS = 4
SUPABASE_RETRY_DELAYS_SECONDS = (2, 5, 10)
SUPABASE_TIMEOUT_SECONDS = 60
SUPABASE_WRITE_BATCH_SIZE = 100

MARKET_PROTECTION_START = time(8, 20)
MARKET_PROTECTION_END = time(15, 10)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SECRET_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)

_last_request_started_at: float | None = None
_source_timeout_streak: dict[str, int] = {}
_source_breaker_until: dict[str, float] = {}


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_nonnegative_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} phai la so nguyen >= 0; hien tai={raw!r}") from exc
    if value < 0:
        raise RuntimeError(f"{name} phai >= 0; hien tai={value}")
    return value


def verify_vnstock_api_access() -> None:
    if not os.getenv("VNSTOCK_API_KEY", "").strip():
        raise RuntimeError("Thieu VNSTOCK_API_KEY")

    tier = authenticator.get_tier(force_refresh=True)
    limits = authenticator.get_limits(tier)
    per_minute = int(limits.get("min", 0))
    if per_minute < 60:
        raise RuntimeError(
            f"VNSTOCK_API_KEY chua duoc nhan: tier={tier}, "
            f"limit={per_minute} request/phut"
        )

    print(
        f"VNStock API: tier={tier}, limit={per_minute} request/phut; "
        "backfill tu gioi han ~48 request/phut."
    )


def verify_supabase_config() -> None:
    if not SUPABASE_URL:
        raise RuntimeError("Thieu SUPABASE_URL")
    if not SUPABASE_KEY:
        raise RuntimeError(
            "Thieu SUPABASE_SECRET_KEY hoac SUPABASE_SERVICE_ROLE_KEY"
        )


def supabase_headers() -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    if not SUPABASE_KEY.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return headers


def supabase_retry_delay(attempt: int) -> int:
    index = min(
        max(attempt - 1, 0),
        len(SUPABASE_RETRY_DELAYS_SECONDS) - 1,
    )
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
            if (
                status is not None
                and 400 <= status < 500
                and status not in {408, 425, 429}
            ):
                body = (
                    (exc.response.text or "").strip()[:300]
                    if exc.response is not None
                    else ""
                )
                raise RuntimeError(
                    f"Supabase HTTP {status} tai {table}; khong retry. {body}"
                ) from exc
            if attempt >= SUPABASE_MAX_ATTEMPTS:
                break
            delay = supabase_retry_delay(attempt)
            print(
                f"Supabase HTTP loi {status}; thu lai sau {delay}s "
                f"({attempt}/{SUPABASE_MAX_ATTEMPTS})"
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


def upsert_rows(
    table: str,
    rows: list[dict[str, Any]],
    conflict: str,
    *,
    batch_size: int = SUPABASE_WRITE_BATCH_SIZE,
) -> None:
    if not rows:
        return

    for offset in range(0, len(rows), batch_size):
        batch = rows[offset:offset + batch_size]
        supabase_request(
            "POST",
            table,
            params={"on_conflict": conflict},
            payload=batch,
            prefer="resolution=merge-duplicates,return=minimal",
        )


def load_sync_state() -> dict[str, dict[str, Any]]:
    response = supabase_request(
        "GET",
        "daily_history_sync_state",
        params={
            "select": "*",
            "order": "symbol.asc",
            "limit": "1000",
        },
    )
    rows = response.json()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol:
            result[symbol] = row
    return result


def load_baseline_profiles() -> dict[str, dict[str, Any]]:
    """
    H1.2 lay "checkpoint su that" tu Daily Baseline production.

    Backfill seed phai tai tao dung trading_date + MA10 + MA200 + KLTB10
    dang duoc production su dung. Nhu vay khac biet semantics KBS/VCI
    khong bi am tham dua vao kho lich su moi.
    """
    response = supabase_request(
        "GET",
        "latest_daily_baseline",
        params={
            "select": (
                "symbol,trading_date,previous_close,"
                "ma10,ma10_sessions,ma200,ma200_sessions,"
                "avg_volume_10,avg_volume_sessions,source"
            ),
            "order": "symbol.asc",
            "limit": "1000",
        },
    )

    result: dict[str, dict[str, Any]] = {}
    for row in response.json():
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue

        trading_date_raw = str(row.get("trading_date") or "").strip()
        if not trading_date_raw:
            continue

        try:
            trading_date = date.fromisoformat(trading_date_raw)
            ma200_sessions = int(row.get("ma200_sessions") or 0)
            ma10_sessions = int(row.get("ma10_sessions") or 0)
            volume_sessions = int(row.get("avg_volume_sessions") or 0)
            previous_close = float(row.get("previous_close"))
            ma10 = float(row.get("ma10"))
            ma200 = float(row.get("ma200"))
            avg_volume_10 = float(row.get("avg_volume_10"))
        except (TypeError, ValueError):
            continue

        if ma200_sessions <= 0 or ma10_sessions <= 0 or volume_sessions <= 0:
            continue

        source = str(row.get("source") or "").strip().upper()
        if source not in {PRIMARY_SOURCE, FALLBACK_SOURCE}:
            source = PRIMARY_SOURCE

        result[symbol] = {
            "trading_date": trading_date,
            "source": source,
            "previous_close": previous_close,
            "ma10": ma10,
            "ma10_sessions": ma10_sessions,
            "ma200": ma200,
            "ma200_sessions": min(MIN_REQUIRED_SESSIONS, ma200_sessions),
            "avg_volume_10": avg_volume_10,
            "avg_volume_sessions": volume_sessions,
        }

    return result


def upsert_state(
    *,
    symbol: str,
    exchange: str,
    status: str,
    run_at: datetime,
    history_exclusive_date: date,
    sessions_loaded: int = 0,
    oldest_trading_date: date | None = None,
    latest_trading_date: date | None = None,
    source: str | None = None,
    last_error: str | None = None,
    completed: bool = False,
) -> None:
    row = {
        "symbol": symbol,
        "exchange": exchange,
        "target_sessions": TARGET_SESSIONS,
        "sessions_loaded": sessions_loaded,
        "oldest_trading_date": (
            oldest_trading_date.isoformat() if oldest_trading_date else None
        ),
        "latest_trading_date": (
            latest_trading_date.isoformat() if latest_trading_date else None
        ),
        "history_exclusive_date": history_exclusive_date.isoformat(),
        "source": source,
        "status": status,
        "last_error": last_error,
        "last_run_at": run_at.isoformat(),
        "completed_at": run_at.isoformat() if completed else None,
        "updated_at": run_at.isoformat(),
    }
    upsert_rows(
        "daily_history_sync_state",
        [row],
        "symbol",
        batch_size=1,
    )


def is_rate_limit(error: BaseException) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in ("rate limit", "too many requests", "429", "requests/minute")
    )


def wait_for_request_slot() -> None:
    global _last_request_started_at

    now = monotonic()
    if _last_request_started_at is not None:
        remaining = REQUEST_INTERVAL_SECONDS - (now - _last_request_started_at)
        if remaining > 0:
            sleep(remaining)

    _last_request_started_at = monotonic()


def _history_worker(
    connection,
    symbol: str,
    source: str,
    start: str,
    end: str,
) -> None:
    try:
        data = Quote(symbol=symbol, source=source).history(
            start=start,
            end=end,
            interval="1D",
        )
        connection.send(("ok", data))
    except BaseException as exc:
        try:
            connection.send(("error", f"{type(exc).__name__}: {exc}"))
        except Exception:
            pass
    finally:
        connection.close()


def _breaker_remaining_seconds(source: str) -> float:
    until = _source_breaker_until.get(source, 0.0)
    return max(0.0, until - monotonic())


def _record_source_timeout(source: str) -> None:
    streak = _source_timeout_streak.get(source, 0) + 1
    _source_timeout_streak[source] = streak
    if streak >= SOURCE_BREAKER_TIMEOUT_THRESHOLD:
        _source_breaker_until[source] = (
            monotonic() + SOURCE_BREAKER_COOLDOWN_SECONDS
        )
        _source_timeout_streak[source] = 0
        print(
            f"  -> {source} circuit breaker OPEN "
            f"{SOURCE_BREAKER_COOLDOWN_SECONDS}s sau "
            f"{SOURCE_BREAKER_TIMEOUT_THRESHOLD} hard-timeout lien tiep."
        )


def _record_source_success(source: str) -> None:
    _source_timeout_streak[source] = 0
    _source_breaker_until.pop(source, None)


def fetch_history_with_hard_timeout(
    symbol: str,
    source: str,
    start: str,
    end: str,
) -> pd.DataFrame:
    remaining = _breaker_remaining_seconds(source)
    if remaining > 0:
        raise RuntimeError(
            f"{source} circuit breaker dang OPEN, con {remaining:.0f}s"
        )

    try:
        context = mp.get_context("fork")
    except ValueError:
        context = mp.get_context("spawn")

    recv_conn, send_conn = context.Pipe(duplex=False)
    process = context.Process(
        target=_history_worker,
        args=(send_conn, symbol, source, start, end),
        daemon=True,
    )
    process.start()
    send_conn.close()

    deadline = monotonic() + HISTORY_HARD_TIMEOUT_SECONDS
    result = None

    while monotonic() < deadline:
        if recv_conn.poll(0.2):
            try:
                result = recv_conn.recv()
            except EOFError:
                result = None
            break
        if not process.is_alive():
            break

    if result is None and process.is_alive():
        process.terminate()
        process.join(timeout=2)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=1)
        recv_conn.close()
        _record_source_timeout(source)
        raise TimeoutError(
            f"{source} hard-timeout sau {HISTORY_HARD_TIMEOUT_SECONDS}s"
        )

    process.join(timeout=2)
    if result is None and recv_conn.poll():
        try:
            result = recv_conn.recv()
        except EOFError:
            result = None
    recv_conn.close()

    if result is None:
        raise RuntimeError(
            f"{source} worker ket thuc khong tra ket qua; exit={process.exitcode}"
        )

    status, payload = result
    if status != "ok":
        raise RuntimeError(str(payload))

    _record_source_success(source)
    return payload


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

    # Giu DUNG semantics Daily Baseline production: volume=0 van co the la
    # mot daily bar cua phien thi truong va van tham gia MA/KLTB.
    # H1.2 khong tu y xoa cac bar nay. Thay vao do, tung ma se bi anchor
    # ve trading_date ma production da xac nhan.
    df = df[df["time"].dt.date < run_date]
    df = (
        df.sort_values("time")
        .drop_duplicates("time", keep="last")
        .reset_index(drop=True)
    )
    if df.empty:
        raise RuntimeError(
            f"Khong co phien da ket thuc truoc {run_date.isoformat()}"
        )
    return df


def normalize_price_unit(history: pd.DataFrame) -> pd.DataFrame:
    df = history.copy()
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
            data = fetch_history_with_hard_timeout(
                symbol, source, start, end
            )
            if data is None or data.empty:
                raise RuntimeError("empty")
            return normalize_price_unit(
                prepare_history(data, run_date)
            )
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
    return (run_date - latest_date).days > SOURCE_STALE_AFTER_DAYS


def fetch_source_history_adaptive(
    symbol: str,
    source: str,
    run_date: date,
    required_sessions: int,
    anchor_date: date,
) -> pd.DataFrame:
    """
    Lay lich su toi da 250 bar va anchor ve trading_date production.

    500 ngay du cho ma thanh khoan binh thuong. Neu chua du buffer thi
    mo rong 1200/2400 ngay. Request end cung bi gioi han sat anchor de
    provider khong chen cac carry-forward bar moi hon checkpoint production.
    """
    request_end_date = min(run_date, anchor_date + timedelta(days=1))
    end = request_end_date.isoformat()
    best: pd.DataFrame | None = None

    for lookback_days in LOOKBACK_WINDOWS_DAYS:
        if (
            best is not None
            and lookback_days == LOOKBACK_WINDOWS_DAYS[-1]
            and len(best) >= required_sessions
        ):
            break

        start = (anchor_date - timedelta(days=lookback_days)).isoformat()
        history = fetch_source_history(
            symbol, source, start, end, run_date
        )
        history = history[
            history["time"].dt.date <= anchor_date
        ].reset_index(drop=True)

        if history.empty:
            raise RuntimeError(
                f"{source}: khong co history <= anchor {anchor_date}"
            )

        best = history
        latest_date = history.iloc[-1]["time"].date()
        print(
            f"  -> {source} lookback={lookback_days}d: "
            f"{len(history)} phien, latest={latest_date}, "
            f"anchor={anchor_date}"
        )

        if len(history) >= TARGET_SESSIONS:
            break

        if lookback_days != LOOKBACK_WINDOWS_DAYS[-1]:
            print(
                f"  -> {source} chua du buffer {TARGET_SESSIONS} phien; "
                "mo rong lookback."
            )

    if best is None:
        raise RuntimeError(f"{source}: khong lay duoc history")
    return best


def calculate_compatibility_metrics(
    history: pd.DataFrame,
    profile: dict[str, Any],
) -> dict[str, Any]:
    ma200_sessions = int(profile["ma200_sessions"])
    ma10_sessions = int(profile["ma10_sessions"])
    volume_sessions = int(profile["avg_volume_sessions"])

    required = max(ma200_sessions, ma10_sessions, volume_sessions)
    if len(history) < required:
        raise RuntimeError(
            f"Chi co {len(history)} phien, can it nhat {required}"
        )

    latest = history.iloc[-1]
    return {
        "trading_date": latest["time"].date(),
        "previous_close": round(float(latest["close"]), 4),
        "ma10": round(
            float(history["close"].tail(ma10_sessions).mean()), 4
        ),
        "ma200": round(
            float(history["close"].tail(ma200_sessions).mean()), 4
        ),
        "avg_volume_10": round(
            float(history["volume"].tail(volume_sessions).mean()), 4
        ),
    }


def compare_with_production(
    history: pd.DataFrame,
    profile: dict[str, Any],
) -> tuple[bool, str]:
    metrics = calculate_compatibility_metrics(history, profile)
    parts: list[str] = []

    date_match = metrics["trading_date"] == profile["trading_date"]
    if not date_match:
        parts.append(
            f"date {metrics['trading_date']} != {profile['trading_date']}"
        )

    for key in ("previous_close", "ma10", "ma200", "avg_volume_10"):
        actual = float(metrics[key])
        expected = float(profile[key])
        diff = round(actual - expected, 4)
        if abs(diff) > 0.0001:
            parts.append(
                f"{key} diff={diff:+.4f} "
                f"(cache={actual:.4f}, prod={expected:.4f})"
            )

    if not parts:
        return True, "EXACT"
    return False, "; ".join(parts)


def get_history(
    symbol: str,
    run_date: date,
    profile: dict[str, Any],
) -> tuple[pd.DataFrame, str]:
    """
    H1.2 seed theo source + trading_date production.

    Uu tien dung chinh provider da tao baseline hien tai. Neu provider do
    khong con tai tao EXACT cac chi so, thu provider con lai. Chi ghi cache
    khi mot trong hai nguon tai tao dung previous_close/MA10/MA200/KLTB10.
    Khong am tham chap nhan mot lich su "gan dung".
    """
    required_sessions = int(profile["ma200_sessions"])
    anchor_date = profile["trading_date"]
    preferred_source = str(profile["source"])
    fallback_source = (
        FALLBACK_SOURCE
        if preferred_source == PRIMARY_SOURCE
        else PRIMARY_SOURCE
    )

    attempts: list[str] = []

    for source in (preferred_source, fallback_source):
        try:
            history = fetch_source_history_adaptive(
                symbol,
                source,
                run_date,
                required_sessions,
                anchor_date,
            )

            if len(history) < required_sessions:
                attempts.append(
                    f"{source}: chi co {len(history)}/{required_sessions} phien"
                )
                continue

            exact, detail = compare_with_production(history, profile)
            if exact:
                if source == preferred_source:
                    print(
                        f"  -> {source} EXACT voi Daily Baseline production."
                    )
                else:
                    print(
                        f"  -> {source} fallback EXACT voi Daily Baseline production."
                    )
                return history, source

            attempts.append(f"{source}: {detail}")
            print(
                f"  -> {source} KHONG EXACT voi production; "
                f"thu nguon con lai. {detail}"
            )
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            attempts.append(f"{source}: {detail}")
            print(
                f"  -> {source} khong dung duoc; thu nguon con lai. "
                f"{detail}"
            )

    raise RuntimeError(
        "Khong provider nao tai tao EXACT Daily Baseline production: "
        + " | ".join(attempts)
    )


def delete_symbol_history(symbol: str) -> None:
    """
    Backfill la seed/rebuild. Xoa cache CU cua rieng ma nay truoc khi ghi
    bo 250 bar moi de tranh con sot date tu provider/lan chay truoc.
    Cache chua duoc production doc o H1/H1.2 nen thao tac nay an toan.
    """
    supabase_request(
        "DELETE",
        "daily_history",
        params={"symbol": f"eq.{symbol}"},
        prefer="return=minimal",
    )


def history_rows(
    symbol: str,
    exchange: str,
    history: pd.DataFrame,
    source: str,
    updated_at: datetime,
) -> list[dict[str, Any]]:
    selected = history.tail(TARGET_SESSIONS).copy()
    rows: list[dict[str, Any]] = []

    for row in selected.to_dict(orient="records"):
        rows.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "trading_date": pd.Timestamp(row["time"]).date().isoformat(),
                "close": round(float(row["close"]), 4),
                "volume": round(float(row["volume"]), 4),
                "source": source,
                "updated_at": updated_at.isoformat(),
            }
        )
    return rows


def in_market_protection_window(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    current = dt.time().replace(tzinfo=None)
    return MARKET_PROTECTION_START <= current <= MARKET_PROTECTION_END


def main() -> None:
    verify_vnstock_api_access()
    verify_supabase_config()

    max_symbols = env_nonnegative_int("BACKFILL_MAX_SYMBOLS", 20)
    force = env_bool("BACKFILL_FORCE", False)

    run_at = now_vn()
    run_date = run_at.date()

    if in_market_protection_window(run_at):
        print(
            "SAFETY STOP: dang trong khung 08:20-15:10 ngay giao dich. "
            "Backfill khong goi VNStock de tranh quota voi intraday."
        )
        return

    watchlist = load_watchlist()
    states = load_sync_state()
    baseline_profiles = load_baseline_profiles()

    completed_before: set[str] = set()
    for symbol, state in states.items():
        profile = baseline_profiles.get(symbol)
        if profile is None:
            continue
        if (
            str(state.get("status") or "").upper() == "COMPLETE"
            and int(state.get("target_sessions") or 0) == TARGET_SESSIONS
            and int(state.get("sessions_loaded") or 0)
            >= int(profile["ma200_sessions"])
            and str(state.get("latest_trading_date") or "")
            == profile["trading_date"].isoformat()
        ):
            completed_before.add(symbol)

    print(
        f"Daily History Backfill H1.2: universe={len(watchlist)}, "
        f"profiles={len(baseline_profiles)}, "
        f"target={TARGET_SESSIONS} phien/ma, "
        f"complete_truoc={len(completed_before)}, "
        f"max_symbols={max_symbols}, force={force}."
    )

    attempted = 0
    completed_now = 0
    skipped = 0
    errors: list[tuple[str, str]] = []
    safety_stopped = False

    for row in watchlist.itertuples(index=False):
        symbol = str(row.symbol).strip().upper()
        exchange = str(row.exchange).strip().upper()

        if not force and symbol in completed_before:
            skipped += 1
            continue

        if max_symbols > 0 and attempted >= max_symbols:
            break

        current = now_vn()
        if in_market_protection_window(current):
            print(
                "SAFETY STOP: da toi 08:20-15:10. "
                "Dung backfill, cac checkpoint COMPLETE da duoc giu."
            )
            safety_stopped = True
            break

        attempted += 1
        symbol_run_at = now_vn()
        profile = baseline_profiles.get(symbol)

        if profile is None:
            message = (
                "Khong co Daily Baseline production profile hop le; "
                "khong duoc seed mu."
            )
            errors.append((symbol, message))
            print(f"[{attempted}] {symbol} ({exchange}) -> ERROR: {message}")
            continue

        required_sessions = int(profile["ma200_sessions"])
        anchor_date = profile["trading_date"]
        preferred_source = profile["source"]

        print(
            f"[{attempted}] {symbol} ({exchange}) "
            f"anchor={anchor_date}, baseline_source={preferred_source}, "
            f"required_ma_sessions={required_sessions}"
        )

        try:
            upsert_state(
                symbol=symbol,
                exchange=exchange,
                status="RUNNING",
                run_at=symbol_run_at,
                history_exclusive_date=run_date,
            )

            history, source = get_history(
                symbol,
                run_date,
                profile,
            )
            rows = history_rows(
                symbol,
                exchange,
                history,
                source,
                symbol_run_at,
            )
            if not rows:
                raise RuntimeError("Khong co row hop le de ghi daily_history")
            if len(rows) < required_sessions:
                raise RuntimeError(
                    f"Chi co {len(rows)} phien, can it nhat "
                    f"{required_sessions} phien de tuong thich MA200 production"
                )

            dates = [
                date.fromisoformat(str(item["trading_date"]))
                for item in rows
            ]
            if max(dates) != anchor_date:
                raise RuntimeError(
                    f"Anchor mismatch: cache latest={max(dates)}, "
                    f"production={anchor_date}"
                )

            # Re-check lan cuoi tren chinh history se ghi.
            selected_for_validation = history.tail(TARGET_SESSIONS).copy()
            exact, detail = compare_with_production(
                selected_for_validation,
                profile,
            )
            if not exact:
                raise RuntimeError(
                    f"Compatibility gate fail truoc khi ghi: {detail}"
                )

            # Rebuild rieng ma nay de khong con orphan rows tu provider cu.
            delete_symbol_history(symbol)
            upsert_rows(
                "daily_history",
                rows,
                "symbol,trading_date",
            )

            upsert_state(
                symbol=symbol,
                exchange=exchange,
                status="COMPLETE",
                run_at=symbol_run_at,
                history_exclusive_date=run_date,
                sessions_loaded=len(rows),
                oldest_trading_date=min(dates),
                latest_trading_date=max(dates),
                source=source,
                completed=True,
            )

            completed_now += 1
            print(
                f"  -> COMPLETE EXACT {symbol}: {len(rows)} phien, "
                f"{min(dates)}->{max(dates)}, source={source}"
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            errors.append((symbol, message))
            print(f"  -> ERROR {symbol}: {message}")

            try:
                upsert_state(
                    symbol=symbol,
                    exchange=exchange,
                    status="ERROR",
                    run_at=symbol_run_at,
                    history_exclusive_date=run_date,
                    last_error=message[:1000],
                )
            except Exception as state_exc:
                print(
                    f"  -> WARNING khong ghi duoc sync state cho {symbol}: "
                    f"{type(state_exc).__name__}: {state_exc}"
                )

    print(
        "BACKFILL SUMMARY: "
        f"universe={len(watchlist)}, "
        f"profiles={len(baseline_profiles)}, "
        f"complete_truoc={len(completed_before)}, "
        f"skipped={skipped}, attempted={attempted}, "
        f"completed_now={completed_now}, errors={len(errors)}, "
        f"safety_stopped={safety_stopped}."
    )

    if errors:
        preview = "; ".join(
            f"{symbol}={message}"
            for symbol, message in errors[:10]
        )
        raise RuntimeError(
            f"Backfill co {len(errors)} ma loi. "
            f"Co the rerun de resume. Mau loi: {preview}"
        )


if __name__ == "__main__":
    main()
