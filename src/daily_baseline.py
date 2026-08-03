from __future__ import annotations

from datetime import date, timedelta
from time import sleep

import pandas as pd
from vnstock.api.quote import Quote

from common import gas_request, load_watchlist, now_vn, records

PRIMARY_SOURCE = "VCI"
FALLBACK_SOURCE = "KBS"
MA_SESSIONS = 200
AVG_VOLUME_SESSIONS = 10
LOOKBACK_DAYS = 500
REQUEST_INTERVAL_SECONDS = 3.3
MAX_RETRIES = 3
RATE_LIMIT_WAIT_SECONDS = 65


def is_rate_limit(error: Exception) -> bool:
    text = str(error).lower()
    return any(x in text for x in ["rate limit", "too many requests", "429", "requests/minute"])


def get_history(symbol: str, start: str, end: str) -> tuple[pd.DataFrame, str]:
    errors: list[str] = []
    for source in [PRIMARY_SOURCE, FALLBACK_SOURCE]:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                data = Quote(symbol=symbol, source=source).history(start=start, end=end, interval="1D")
                if data is not None and not data.empty:
                    return data.copy(), source
                errors.append(f"{source}: empty")
                break
            except Exception as exc:
                errors.append(f"{source}: {type(exc).__name__}: {exc}")
                if is_rate_limit(exc) and attempt < MAX_RETRIES:
                    sleep(RATE_LIMIT_WAIT_SECONDS)
                    continue
                break
    raise RuntimeError(" | ".join(errors))


def prepare(data: pd.DataFrame) -> pd.DataFrame:
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
    return df.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)


def normalize_price_unit(history: pd.DataFrame) -> pd.DataFrame:
    df = history.copy()
    # vnstock daily history is commonly in thousand VND while price board is VND.
    if not df.empty and float(df["close"].tail(min(20, len(df))).median()) < 1000:
        df["close"] = df["close"] * 1000
    return df


def main() -> None:
    run_at = now_vn()
    watchlist = load_watchlist()
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    rows: list[dict] = []
    failed = 0

    for index, item in watchlist.iterrows():
        symbol = item["symbol"]
        print(f"[{index + 1}/{len(watchlist)}] {symbol}")
        try:
            history, source = get_history(symbol, start, end)
            history = normalize_price_unit(prepare(history))
            session_count = len(history)
            ma_sessions = min(session_count, MA_SESSIONS)
            volume_sessions = min(session_count, AVG_VOLUME_SESSIONS)
            latest = history.iloc[-1]
            rows.append({
                "symbol": symbol,
                "exchange": item["exchange"],
                "trading_date": latest["time"].date().isoformat(),
                "previous_close": round(float(latest["close"]), 4),
                "ma200": round(float(history["close"].tail(ma_sessions).mean()), 4),
                "ma200_sessions": ma_sessions,
                "avg_volume_10": round(float(history["volume"].tail(volume_sessions).mean()), 4),
                "avg_volume_sessions": volume_sessions,
                "source": source,
                "updated_at": run_at.isoformat(),
                "data_status": "OK",
            })
        except Exception as exc:
            failed += 1
            rows.append({
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
            })
        sleep(REQUEST_INTERVAL_SECONDS)

    result = pd.DataFrame(rows)
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
            "symbols_success": len(watchlist) - failed,
            "symbols_failed": failed,
            "message": "Daily baseline completed",
        },
    )
    print(response)


if __name__ == "__main__":
    main()
