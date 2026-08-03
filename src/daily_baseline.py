from __future__ import annotations

from datetime import date, timedelta
from time import sleep

import pandas as pd
from vnstock.api.quote import Quote

from common import gas_request, load_watchlist, now_vn, records

SOURCES = ("VCI", "KBS")
MA_SESSIONS = 200
AVG_VOLUME_SESSIONS = 10
LOOKBACK_DAYS = 500
REQUEST_INTERVAL_SECONDS = 3.3
MAX_RETRIES = 3
RATE_LIMIT_WAIT_SECONDS = 65


def is_rate_limit(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in ("rate limit", "too many requests", "429", "requests/minute")
    )


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

    # Baseline chi duoc dung cac phien da ket thuc truoc ngay chay.
    # Vi du:
    # - Chay trong ngay 03/08/2026 -> lay toi da phien 31/07/2026.
    # - Chay luc 01:00 ngay 04/08/2026 -> lay toi da phien 03/08/2026.
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

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = Quote(symbol=symbol, source=source).history(
                start=start,
                end=end,
                interval="1D",
            )
            if data is None or data.empty:
                raise RuntimeError("empty")
            return normalize_price_unit(prepare_history(data, run_date))
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if is_rate_limit(exc) and attempt < MAX_RETRIES:
                sleep(RATE_LIMIT_WAIT_SECONDS)
                continue
            break

    raise RuntimeError(f"{source}: {last_error}")


def get_history(
    symbol: str,
    start: str,
    end: str,
    run_date: date,
) -> tuple[pd.DataFrame, str]:
    candidates: list[tuple[date, int, pd.DataFrame, str]] = []
    errors: list[str] = []

    # Doc ca VCI va KBS, sau do chon nguon co phien moi nhat.
    # Neu hai nguon cung ngay, uu tien VCI vi VCI dung truoc trong SOURCES.
    for priority, source in enumerate(SOURCES):
        try:
            history = fetch_source_history(symbol, source, start, end, run_date)
            latest_date = history.iloc[-1]["time"].date()
            candidates.append((latest_date, -priority, history, source))
        except Exception as exc:
            errors.append(str(exc))

    if not candidates:
        raise RuntimeError(" | ".join(errors))

    _, _, history, source = max(candidates, key=lambda item: (item[0], item[1]))
    return history, source


def main() -> None:
    run_at = now_vn()
    run_date = run_at.date()
    watchlist = load_watchlist()
    end = run_date.isoformat()
    start = (run_date - timedelta(days=LOOKBACK_DAYS)).isoformat()
    rows: list[dict] = []
    failed = 0

    for index, item in watchlist.iterrows():
        symbol = item["symbol"]
        print(f"[{index + 1}/{len(watchlist)}] {symbol}")

        try:
            history, source = get_history(symbol, start, end, run_date)
            session_count = len(history)
            ma_sessions = min(session_count, MA_SESSIONS)
            volume_sessions = min(session_count, AVG_VOLUME_SESSIONS)
            latest = history.iloc[-1]
            trading_date = latest["time"].date()

            if trading_date >= run_date:
                raise RuntimeError(
                    f"Baseline khong an toan: trading_date={trading_date}, "
                    f"run_date={run_date}"
                )

            rows.append(
                {
                    "symbol": symbol,
                    "exchange": item["exchange"],
                    "trading_date": trading_date.isoformat(),
                    "previous_close": round(float(latest["close"]), 4),
                    "ma200": round(
                        float(history["close"].tail(ma_sessions).mean()), 4
                    ),
                    "ma200_sessions": ma_sessions,
                    "avg_volume_10": round(
                        float(history["volume"].tail(volume_sessions).mean()), 4
                    ),
                    "avg_volume_sessions": volume_sessions,
                    "source": source,
                    "updated_at": run_at.isoformat(),
                    "data_status": "OK",
                }
            )
            print(f"  -> {source} | baseline {trading_date.isoformat()}")
        except Exception as exc:
            failed += 1
            rows.append(
                {
                    "symbol": symbol,
                    "exchange": item["exchange"],
                    "trading_date": None,
                    "previous_close": None,
                    "ma200": None,
                    "ma200_sessions": 0,
                    "avg_volume_10": None,
                    "avg_volume_sessions": 0,
                    "source": None,
                    "updated_at": run_at.isoformat(),
                    "data_status": f"ERROR: {exc}"[:500],
                }
            )
            print(f"  -> ERROR: {exc}")

        sleep(REQUEST_INTERVAL_SECONDS)

    result = pd.DataFrame(rows)
    success = len(watchlist) - failed
    response = gas_request(
        "replace_daily_baseline",
        rows=records(result),
        run_log={
            "run_id": run_at.strftime("daily-%Y%m%d-%H%M%S"),
            "job_type": "DAILY_BASELINE",
            "started_at": run_at.isoformat(),
            "finished_at": now_vn().isoformat(),
            "status": "SUCCESS" if failed == 0 else "PARTIAL",
            "symbols_requested": len(watchlist),
            "symbols_success": success,
            "symbols_failed": failed,
            "message": (
                f"Daily baseline completed: {success}/{len(watchlist)} symbols"
            ),
        },
    )
    print(response)


if __name__ == "__main__":
    main()
