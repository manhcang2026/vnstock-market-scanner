from __future__ import annotations

import math
import os
from datetime import datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import quote as urlquote
from zoneinfo import ZoneInfo

import pandas as pd
import requests

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
TIMEOUT = 15
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SECRET_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)
UA = "Mozilla/5.0 CCC-Market-Pulse/1.1"


def n(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(str(v).replace(",", ""))
        return x if math.isfinite(x) else None
    except Exception:
        return None


def iso(v: Any, tz=timezone.utc) -> str | None:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)):
            d = datetime.fromtimestamp(int(v), timezone.utc)
        else:
            d = pd.to_datetime(v, errors="raise").to_pydatetime()
        if d.tzinfo is None:
            d = d.replace(tzinfo=tz)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def change(price, prev):
    if price is None or prev in (None, 0):
        return None, None
    delta = price - prev
    return delta, delta / prev * 100


def sb_headers():
    if not SUPABASE_URL:
        raise RuntimeError("Thieu SUPABASE_URL")
    if not SUPABASE_KEY:
        raise RuntimeError("Thieu SUPABASE_SECRET_KEY/SERVICE_ROLE_KEY")
    h = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    if not SUPABASE_KEY.startswith("sb_secret_"):
        h["Authorization"] = "Bearer " + SUPABASE_KEY
    return h


def sb(method, table, params=None, payload=None, prefer=None):
    h = sb_headers()
    if prefer:
        h["Prefer"] = prefer
    r = requests.request(
        method,
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=h,
        params=params,
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r


def existing():
    rows = sb("GET", "market_pulse_current", params={"select": "*"}).json()
    return {str(x.get("key", "")).lower(): x for x in rows if x.get("key")}


def vn_status():
    now = datetime.now(VN_TZ)
    if now.weekday() >= 5:
        return "CLOSED"
    t = now.time()
    return "OPEN" if (
        time(9, 0) <= t <= time(11, 30)
        or time(13, 0) <= t <= time(15, 0)
    ) else "CLOSED"


def fetch_vnindex_from_source(source: str):
    """
    Lấy VN-INDEX bằng chính Quote API của vnstock.

    KBS hỗ trợ VNINDEX như một index symbol và history interval 5m.
    Ta lấy các bar 5 phút gần nhất trong 10 ngày, sau đó:
    - price = close của bar mới nhất
    - previous_close = close cuối cùng của phiên giao dịch trước đó

    Cách này phù hợp cadence Market Pulse 5 phút và không dùng Yahoo cho VNINDEX.
    """
    from vnstock import Quote

    today = datetime.now(VN_TZ).date()
    start = (today - timedelta(days=10)).isoformat()
    end = today.isoformat()

    quote = Quote(symbol="VNINDEX", source=source)
    df = quote.history(
        start=start,
        end=end,
        interval="5m",
    )

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        raise RuntimeError(f"{source} VNINDEX 5m history rong")

    required = {"time", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise RuntimeError(
            f"{source} VNINDEX thieu cot {sorted(missing)}; "
            f"co {list(df.columns)}"
        )

    work = df[["time", "close"]].copy()
    work["time"] = pd.to_datetime(work["time"], errors="coerce")
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    work = work.dropna(subset=["time", "close"]).sort_values("time")

    if work.empty:
        raise RuntimeError(f"{source} VNINDEX khong co bar hop le")

    latest = work.iloc[-1]
    latest_time = latest["time"]
    latest_date = latest_time.date()
    price = float(latest["close"])

    previous_sessions = work[work["time"].dt.date < latest_date]
    previous_close = None
    if not previous_sessions.empty:
        previous_close = float(previous_sessions.iloc[-1]["close"])

    delta, pct = change(price, previous_close)

    return {
        "key": "vnindex",
        "display_name": "VN-INDEX",
        "sort_order": 1,
        "price": price,
        "previous_close": previous_close,
        "change_value": delta,
        "change_pct": pct,
        "currency": "POINT",
        "source": f"vnstock/{source}",
        "source_symbol": "VNINDEX",
        "change_basis": "previous_close",
        "market_status": vn_status(),
        "market_time": iso(latest_time, VN_TZ) or datetime.now(timezone.utc).isoformat(),
        "note": (
            f"VNINDEX {source} 5m; "
            f"latest_bar={latest_time}; previous_session_close={previous_close}"
        ),
    }


def fetch_vnindex():
    errors = []
    for source in ("KBS", "VCI"):
        try:
            row = fetch_vnindex_from_source(source)
            if source == "VCI":
                row["source"] = "vnstock/VCI fallback"
                row["note"] = "KBS failed; " + row.get("note", "")
            return row, None
        except Exception as e:
            errors.append(f"{source}: {type(e).__name__}: {e}")

    return {
        "key": "vnindex",
        "display_name": "VN-INDEX",
        "sort_order": 1,
        "currency": "POINT",
        "source": "vnstock/KBS",
        "source_symbol": "VNINDEX",
        "change_basis": "previous_close",
        "market_status": vn_status(),
    }, " || ".join(errors)


def yahoo(key, name, order, symbol, currency):
    errors = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            r = requests.get(
                f"https://{host}/v8/finance/chart/{urlquote(symbol, safe='')}",
                params={"interval": "1m", "range": "1d"},
                headers={"User-Agent": UA, "Accept": "application/json"},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            chart = (r.json() or {}).get("chart") or {}
            if chart.get("error"):
                raise RuntimeError(str(chart["error"]))
            blocks = chart.get("result") or []
            if not blocks:
                raise RuntimeError("Yahoo chart.result rong")
            block = blocks[0]
            meta = block.get("meta") or {}
            price = n(meta.get("regularMarketPrice"))
            prev = n(meta.get("chartPreviousClose")) or n(meta.get("previousClose"))
            if price is None:
                closes = ((((block.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or [])
                vals = [n(x) for x in closes]
                vals = [x for x in vals if x is not None]
                price = vals[-1] if vals else None
            if price is None:
                raise RuntimeError("khong co regularMarketPrice/close")
            delta, pct = change(price, prev)

            period = ((meta.get("currentTradingPeriod") or {}).get("regular") or {})
            now_ts = int(datetime.now(timezone.utc).timestamp())
            start, end = n(period.get("start")), n(period.get("end"))
            status = (
                "OPEN"
                if start is not None and end is not None and int(start) <= now_ts <= int(end)
                else "CLOSED"
            )

            return {
                "key": key,
                "display_name": name,
                "sort_order": order,
                "price": price,
                "previous_close": prev,
                "change_value": delta,
                "change_pct": pct,
                "currency": str(meta.get("currency") or currency),
                "source": "Yahoo Finance",
                "source_symbol": symbol,
                "change_basis": "previous_close",
                "market_status": status,
                "market_time": iso(meta.get("regularMarketTime")) or datetime.now(timezone.utc).isoformat(),
                "note": str(meta.get("exchangeName") or meta.get("fullExchangeName") or ""),
            }, None
        except Exception as e:
            errors.append(f"{host}: {type(e).__name__}: {e}")

    return {
        "key": key,
        "display_name": name,
        "sort_order": order,
        "currency": currency,
        "source": "Yahoo Finance",
        "source_symbol": symbol,
        "change_basis": "previous_close",
        "market_status": "UNKNOWN",
    }, " | ".join(errors)


def btc():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": "bitcoin",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_last_updated_at": "true",
            },
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        b = (r.json() or {}).get("bitcoin") or {}
        price, pct = n(b.get("usd")), n(b.get("usd_24h_change"))
        if price is None:
            raise RuntimeError("khong co bitcoin.usd")
        prev = price / (1 + pct / 100) if pct is not None and pct != -100 else None
        delta, _ = change(price, prev)
        return {
            "key": "btc",
            "display_name": "BTC",
            "sort_order": 7,
            "price": price,
            "previous_close": prev,
            "change_value": delta,
            "change_pct": pct,
            "currency": "USD",
            "source": "CoinGecko",
            "source_symbol": "bitcoin/USD",
            "change_basis": "rolling_24h",
            "market_status": "OPEN_24H",
            "market_time": iso(b.get("last_updated_at")) or datetime.now(timezone.utc).isoformat(),
            "note": "Bien dong 24h",
        }, None
    except Exception as e:
        fb, ferr = yahoo("btc", "BTC", 7, "BTC-USD", "USD")
        if ferr is None:
            fb["source"] = "Yahoo Finance fallback"
            fb["note"] = ((fb.get("note") or "") + " | CoinGecko loi").strip(" |")
            return fb, None
        return {
            "key": "btc",
            "display_name": "BTC",
            "sort_order": 7,
            "currency": "USD",
            "source": "CoinGecko",
            "source_symbol": "bitcoin/USD",
            "change_basis": "rolling_24h",
            "market_status": "OPEN_24H",
        }, f"CoinGecko: {type(e).__name__}: {e}; Yahoo: {ferr}"


def collect():
    return [
        fetch_vnindex(),
        yahoo("sp500", "S&P 500", 2, "^GSPC", "USD"),
        yahoo("hangseng", "HANG SENG", 3, "^HSI", "HKD"),
        yahoo("dxy", "DXY", 4, "DX-Y.NYB", "INDEX"),
        yahoo("gold", "GOLD", 5, "GC=F", "USD"),
        yahoo("wti", "WTI", 6, "CL=F", "USD"),
        btc(),
    ]


def main():
    started = datetime.now(timezone.utc).isoformat()
    old = existing()
    checked = datetime.now(timezone.utc).isoformat()
    rows, failures, ok = [], [], 0

    for data, err in collect():
        key = data["key"]
        prev_row = old.get(key, {})
        if err is None and n(data.get("price")) is not None:
            data["last_success_at"] = checked
            data["checked_at"] = checked
            data["data_status"] = "OK"
            rows.append(data)
            ok += 1
            print(
                f"OK {data['display_name']}: {data.get('price')} "
                f"{data.get('change_pct')}% [{data.get('source')}] "
                f"market_time={data.get('market_time')}"
            )
        else:
            has_old = n(prev_row.get("price")) is not None
            row = dict(prev_row) if prev_row else dict(data)
            row.update({
                "key": key,
                "display_name": data["display_name"],
                "sort_order": data["sort_order"],
                "checked_at": checked,
                "data_status": "STALE" if has_old else "ERROR",
                "note": ("Source fetch failed; kept last good value. " + (err or "unknown"))[:500],
            })
            rows.append(row)
            failures.append(f"{data['display_name']}: {err}")
            print(f"FAIL {data['display_name']}: {err}")

    sb(
        "POST",
        "market_pulse_current",
        params={"on_conflict": "key"},
        payload=rows,
        prefer="resolution=merge-duplicates,return=minimal",
    )

    status = "SUCCESS" if ok == 7 else ("PARTIAL" if ok else "ERROR")
    run = {
        "run_id": datetime.now(timezone.utc).strftime("market-pulse-%Y%m%d-%H%M%S"),
        "job_type": "MARKET_PULSE_SCAN",
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "symbols_requested": 7,
        "symbols_success": ok,
        "symbols_failed": 7 - ok,
        "message": (
            f"market_pulse={ok}/7; "
            + (" | ".join(failures) if failures else "all_sources_ok")
        )[:1000],
    }
    try:
        sb(
            "POST",
            "scan_runs",
            params={"on_conflict": "run_id"},
            payload=[run],
            prefer="resolution=merge-duplicates,return=minimal",
        )
    except Exception as e:
        print(f"WARNING scan_runs: {type(e).__name__}: {e}")

    print(f"DONE Market Pulse: {ok}/7")
    if ok == 0:
        raise RuntimeError("Tat ca Market Pulse sources deu that bai")


if __name__ == "__main__":
    main()
