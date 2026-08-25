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


def load_baseline_requirements() -> dict[str, int]:
    """
    Lay so phien MA200 ma production hien tai thuc su dung cho tung ma.

    Ma moi niem yet co the chua du 200 phien; khi do backfill chi can dat
    dung so phien production dang co, thay vi bat buoc 200 mot cach gia tao.
    """
    response = supabase_request(
        "GET",
        "latest_daily_baseline",
        params={
            "select": "symbol,ma200_sessions",
            "order": "symbol.asc",
            "limit": "1000",
        },
    )
    result: dict[str, int] = {}
    for row in response.json():
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        try:
            sessions = int(row.get("ma200_sessions") or 0)
        except (TypeError, ValueError):
            sessions = 0
        if sessions > 0:
            result[symbol] = min(MIN_REQUIRED_SESSIONS, sessions)
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

    # H1.1: provider co the bo sung dong carry-forward volume=0 o CUOI
    # chuoi sau khi ma da ngung giao dich. Khong cho cac dong nay day
    # trading_date tien len (truong hop BCF/BTW bat duoc o test H1).
    # Van giu volume=0 NAM GIUA lich su de MA200 giu cung semantics voi
    # Daily Baseline production: 200 phien thi truong, khong phai 200 ngay
    # ma co phat sinh khoi luong.
    positive_positions = df.index[df["volume"] > 0]
    if len(positive_positions) == 0:
        raise RuntimeError("History khong co phien volume > 0")
    last_traded_position = int(positive_positions[-1])
    return df.iloc[: last_traded_position + 1].reset_index(drop=True)


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
) -> pd.DataFrame:
    """
    Bat dau 500 ngay de giu request nhe. Neu chua du buffer 250 phien thi
    mo rong 1200 ngay. Chi mo rong tiep 2400 ngay neu van chua dat so phien
    toi thieu ma production hien tai can cho MA200.
    """
    end = run_date.isoformat()
    best: pd.DataFrame | None = None

    for lookback_days in LOOKBACK_WINDOWS_DAYS:
        if (
            best is not None
            and lookback_days == LOOKBACK_WINDOWS_DAYS[-1]
            and len(best) >= required_sessions
        ):
            break

        start = (run_date - timedelta(days=lookback_days)).isoformat()
        history = fetch_source_history(
            symbol, source, start, end, run_date
        )
        best = history
        latest_date = history.iloc[-1]["time"].date()
        print(
            f"  -> {source} lookback={lookback_days}d: "
            f"{len(history)} phien, latest={latest_date}"
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


def history_quality(
    history: pd.DataFrame,
    required_sessions: int,
) -> tuple[int, int, date]:
    return (
        1 if len(history) >= required_sessions else 0,
        min(len(history), TARGET_SESSIONS),
        history.iloc[-1]["time"].date(),
    )


def get_history(
    symbol: str,
    run_date: date,
    required_sessions: int,
) -> tuple[pd.DataFrame, str]:
    """
    KBS van la primary. H1.1 chi goi VCI khi KBS loi/empty, stale, hoac
    chua du buffer 250 phien. Neu ca hai co du lieu, chon nguon dap ung
    MA200 truoc, sau do uu tien nhieu phien hon va trading_date moi hon.
    KBS thang neu chat luong bang nhau.
    """
    primary_history: pd.DataFrame | None = None
    primary_error: str | None = None

    try:
        primary_history = fetch_source_history_adaptive(
            symbol, PRIMARY_SOURCE, run_date, required_sessions
        )
        primary_date = primary_history.iloc[-1]["time"].date()
        if (
            len(primary_history) >= TARGET_SESSIONS
            and not source_is_too_stale(primary_history, run_date)
        ):
            return primary_history, PRIMARY_SOURCE

        reasons: list[str] = []
        if len(primary_history) < TARGET_SESSIONS:
            reasons.append(f"chi co {len(primary_history)} phien")
        if source_is_too_stale(primary_history, run_date):
            reasons.append(f"du lieu cu {primary_date.isoformat()}")
        print(
            f"  -> {PRIMARY_SOURCE} {'; '.join(reasons)}; "
            f"thu {FALLBACK_SOURCE}."
        )
    except Exception as exc:
        primary_error = str(exc)
        print(
            f"  -> {PRIMARY_SOURCE} khong dung duoc; "
            f"thu {FALLBACK_SOURCE}."
        )

    try:
        fallback_history = fetch_source_history_adaptive(
            symbol, FALLBACK_SOURCE, run_date, required_sessions
        )

        if primary_history is None:
            selected_history = fallback_history
            selected_source = FALLBACK_SOURCE
        else:
            primary_quality = history_quality(
                primary_history, required_sessions
            )
            fallback_quality = history_quality(
                fallback_history, required_sessions
            )
            if fallback_quality > primary_quality:
                selected_history = fallback_history
                selected_source = FALLBACK_SOURCE
            else:
                selected_history = primary_history
                selected_source = PRIMARY_SOURCE

        if len(selected_history) < required_sessions:
            raise RuntimeError(
                f"khong nguon nao du {required_sessions} phien: "
                f"{PRIMARY_SOURCE}={len(primary_history) if primary_history is not None else 0}, "
                f"{FALLBACK_SOURCE}={len(fallback_history)}"
            )
        return selected_history, selected_source
    except Exception as fallback_exc:
        if (
            primary_history is not None
            and len(primary_history) >= required_sessions
        ):
            return primary_history, PRIMARY_SOURCE

        primary_detail = (
            primary_error
            or (
                f"{len(primary_history)} phien"
                if primary_history is not None
                else "unknown"
            )
        )
        raise RuntimeError(
            f"{PRIMARY_SOURCE}: {primary_detail} | "
            f"{FALLBACK_SOURCE}: {fallback_exc}"
        ) from fallback_exc


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
    baseline_requirements = load_baseline_requirements()

    completed_before = {
        symbol
        for symbol, state in states.items()
        if str(state.get("status") or "").upper() == "COMPLETE"
        and int(state.get("target_sessions") or 0) == TARGET_SESSIONS
        and int(state.get("sessions_loaded") or 0)
        >= baseline_requirements.get(symbol, MIN_REQUIRED_SESSIONS)
    }

    print(
        f"Daily History Backfill H1.1: universe={len(watchlist)}, "
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

        required_sessions = baseline_requirements.get(
            symbol, MIN_REQUIRED_SESSIONS
        )
        print(
            f"[{attempted}] {symbol} ({exchange}) "
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
                required_sessions,
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

            upsert_rows(
                "daily_history",
                rows,
                "symbol,trading_date",
            )

            dates = [
                date.fromisoformat(str(item["trading_date"]))
                for item in rows
            ]
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
                f"  -> COMPLETE {symbol}: {len(rows)} phien, "
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
