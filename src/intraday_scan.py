from __future__ import annotations

import os
from datetime import timedelta
from time import monotonic, sleep
from typing import Any

import pandas as pd
import requests
from vnstock import Trading

from common import (
    is_market_slot,
    load_watchlist,
    market_snapshot_slot,
    normalize_exchange_value,
    now_vn,
    records,
    rvol_window_slots,
    safe_pct,
)

PRIMARY_SOURCE = "KBS"
FALLBACK_SOURCE = "VCI"

PRICE_BOARD_BATCH_SIZE = 50
PRIMARY_MAX_ATTEMPTS = 2
PRIMARY_RETRY_DELAY_SECONDS = 3
FALLBACK_MAX_ATTEMPTS = 1

# Cadence moi la 5 phut. Neu nguon gia co su co, uu tien ket thuc truoc job ke tiep.
PRICE_FETCH_BUDGET_SECONDS = 210
TOTAL_RUNTIME_BUDGET_SECONDS = 270
MIN_PRICE_BOARD_SUCCESS_RATIO = 0.80

PRICE_THRESHOLD_PCT = 3.0
DAILY_VOLUME_THRESHOLD_PCT = 200.0
RVOL30_THRESHOLD_PCT = 200.0

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SECRET_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
)
SUPABASE_MAX_ATTEMPTS = 4
SUPABASE_RETRY_DELAYS_SECONDS = (2, 5, 10)
SUPABASE_TIMEOUT_SECONDS = 60
SUPABASE_WRITE_BATCH_SIZE = 100

SHEET_BACKUP_TIMEOUT_SECONDS = 30
RVOL_LOOKBACK_DAYS = 35
RVOL_PAGE_SIZE = 1000
RVOL_MAX_PAGES = 20

PRICE_BOARD_COLUMNS = [
    "symbol",
    "close_price",
    "volume_accumulated",
    "exchange",
]

RVOL_COLUMNS = [
    "volume_30m",
    "avg_volume_30m_10",
    "rvol30_pct",
    "rvol30_sessions",
]

DASHBOARD_COLUMNS = [
    "symbol",
    "exchange",
    "current_price",
    "previous_close",
    "price_change_pct",
    "volume_accumulated",
    "avg_volume_10",
    "avg_volume_sessions",
    "daily_volume_pct",
    "ma200",
    "ma200_sessions",
    "ma200_distance_pct",
    "volume_30m",
    "avg_volume_30m_10",
    "rvol30_pct",
    "rvol30_sessions",
    "signal_price_3pct",
    "signal_daily_volume_200pct",
    "signal_above_ma200",
    "signal_rvol30_200pct",
    "signal_count",
    "trading_date",
    "time_slot",
    "updated_at",
    "data_status",
    "ma10",
    "ma10_sessions",
    "ma10_distance_pct",
]

SNAPSHOT_COLUMNS = [
    "trading_date",
    "time_slot",
    "symbol",
    "exchange",
    "current_price",
    "volume_accumulated",
    "updated_at",
    "data_status",
]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def verify_supabase_config() -> None:
    if not SUPABASE_URL:
        raise RuntimeError("Thieu GitHub Secret SUPABASE_URL")
    if not SUPABASE_KEY:
        raise RuntimeError(
            "Thieu GitHub Secret SUPABASE_SECRET_KEY "
            "(hoac SUPABASE_SERVICE_ROLE_KEY cu)"
        )


def supabase_headers() -> dict[str, str]:
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
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
            if status is not None and 400 <= status < 500 and status not in {408, 425, 429}:
                body = (exc.response.text or "").strip()[:300] if exc.response else ""
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
                f"Supabase request loi {type(exc).__name__}; thu lai sau {delay}s "
                f"({attempt}/{SUPABASE_MAX_ATTEMPTS})"
            )
            sleep(delay)

    raise RuntimeError(
        f"Supabase request that bai sau {SUPABASE_MAX_ATTEMPTS} lan: {last_error}"
    ) from last_error


def load_latest_baseline() -> pd.DataFrame:
    response = supabase_request(
        "GET",
        "latest_daily_baseline",
        params={
            "select": (
                "symbol,previous_close,ma10,ma10_sessions,ma200,ma200_sessions,"
                "avg_volume_10,avg_volume_sessions,trading_date,data_status"
            ),
            "order": "symbol.asc",
            "limit": "1000",
        },
    )
    baseline = pd.DataFrame(response.json())
    if baseline.empty:
        raise RuntimeError(
            "Supabase latest_daily_baseline dang rong. Hay chay Daily Baseline truoc."
        )

    required = {
        "symbol", "previous_close", "ma10", "ma10_sessions", "ma200",
        "ma200_sessions", "avg_volume_10", "avg_volume_sessions",
    }
    missing = sorted(required.difference(baseline.columns))
    if missing:
        raise RuntimeError(f"Supabase latest_daily_baseline thieu cot: {missing}")

    baseline["symbol"] = (
        baseline["symbol"].fillna("").astype(str).str.strip().str.upper()
    )
    baseline = baseline.drop_duplicates("symbol", keep="first")
    for column in [
        "previous_close", "ma10", "ma200", "avg_volume_10", "ma200_sessions",
        "avg_volume_sessions", "ma10_sessions",
    ]:
        baseline[column] = pd.to_numeric(baseline[column], errors="coerce")

    print(f"Supabase baseline: {len(baseline)} ma.")
    return baseline[
        [
            "symbol", "previous_close", "ma10", "ma10_sessions", "ma200",
            "ma200_sessions", "avg_volume_10", "avg_volume_sessions",
        ]
    ].copy()


def load_rvol_reference(
    scan_at,
    current_slot: str,
    start_slot: str | None,
) -> list[dict[str, Any]]:
    if not start_slot:
        return []

    start_date = (scan_at.date() - timedelta(days=RVOL_LOOKBACK_DAYS)).isoformat()
    today = scan_at.date().isoformat()
    slots = f"in.({start_slot},{current_slot})"
    rows: list[dict[str, Any]] = []

    for page in range(RVOL_MAX_PAGES):
        offset = page * RVOL_PAGE_SIZE
        response = supabase_request(
            "GET",
            "intraday_snapshots",
            params={
                "select": "trading_date,time_slot,symbol,volume_accumulated",
                "trading_date": f"gte.{start_date}",
                "time_slot": slots,
                "order": "trading_date.desc,time_slot.asc,symbol.asc",
                "limit": str(RVOL_PAGE_SIZE),
                "offset": str(offset),
            },
        )
        page_rows = response.json()
        if not isinstance(page_rows, list):
            raise RuntimeError("Supabase RVOL reference khong tra ve danh sach rows")
        rows.extend(page_rows)
        print(
            f"Supabase RVOL page {page + 1}: {len(page_rows)} rows; offset={offset}."
        )
        if len(page_rows) < RVOL_PAGE_SIZE:
            break
    else:
        raise RuntimeError(
            "Supabase RVOL reference vuot gioi han an toan "
            f"{RVOL_PAGE_SIZE * RVOL_MAX_PAGES} rows"
        )

    rows = [
        row for row in rows
        if str(row.get("trading_date") or "") <= today
    ]
    print(
        f"Supabase RVOL reference FULL: {len(rows)} rows; "
        f"slots={start_slot}->{current_slot}."
    )
    return rows


def upsert_rows(table: str, rows: list[dict[str, Any]], conflict: str) -> None:
    if not rows:
        return
    total = len(rows)
    for offset in range(0, total, SUPABASE_WRITE_BATCH_SIZE):
        batch = rows[offset:offset + SUPABASE_WRITE_BATCH_SIZE]
        supabase_request(
            "POST",
            table,
            params={"on_conflict": conflict},
            payload=batch,
            prefer="resolution=merge-duplicates,return=minimal",
        )
    print(f"Supabase {table}: upsert {total} rows OK.")


def upsert_scan_run(run_log: dict[str, Any]) -> None:
    upsert_rows("scan_runs", [run_log], "run_id")


def backup_sheet_best_effort(
    snapshots: list[dict[str, Any]],
    dashboard: list[dict[str, Any]],
    run_log: dict[str, Any],
) -> tuple[bool, str]:
    gas_url = os.getenv("GAS_WEB_APP_URL", "").strip()
    gas_secret = os.getenv("GAS_API_SECRET", "").strip()
    if not gas_url or not gas_secret:
        return False, "Sheet backup skipped: thieu GAS_WEB_APP_URL hoac GAS_API_SECRET"

    body = {
        "secret": gas_secret,
        "action": "update_intraday_scan",
        "snapshots": snapshots,
        "dashboard": dashboard,
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
        return False, f"Sheet backup warning: {type(exc).__name__}: {exc}"


def normalize_price_board(data: pd.DataFrame) -> pd.DataFrame:
    if data is None or not isinstance(data, pd.DataFrame) or data.empty:
        raise RuntimeError("Price board rong hoac khong hop le")

    df = data.copy()

    # VCI co the tra MultiIndex neu khong flatten. Day la lop bao ve thu hai.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join(
                str(part)
                for part in col
                if str(part) not in {"", "None"}
            )
            for col in df.columns.to_flat_index()
        ]

    # Chuan hoa schema KBS/VCI ve schema noi bo cua scanner.
    aliases = {
        "listing_symbol": "symbol",
        "listing_ticker": "symbol",
        "match_match_price": "close_price",
        "match_price": "close_price",
        "match_accumulated_volume": "volume_accumulated",
        "accumulated_volume": "volume_accumulated",
        "listing_exchange": "exchange",
        "listing_board": "exchange",
    }
    for source_col, target_col in aliases.items():
        if target_col not in df.columns and source_col in df.columns:
            df = df.rename(columns={source_col: target_col})

    required = {"symbol", "close_price", "volume_accumulated"}
    missing = required.difference(df.columns)
    if missing:
        raise RuntimeError(
            f"Price board thieu cot {sorted(missing)}; hien co {list(df.columns)}"
        )

    if "exchange" not in df.columns:
        df["exchange"] = pd.NA

    df["symbol"] = df["symbol"].fillna("").astype(str).str.strip().str.upper()
    df["close_price"] = pd.to_numeric(df["close_price"], errors="coerce")
    df["volume_accumulated"] = pd.to_numeric(
        df["volume_accumulated"], errors="coerce"
    )
    df["exchange"] = (
        df["exchange"].fillna("").astype(str).str.upper()
        .replace({"HSX": "HOSE", "UPCO": "UPCOM"})
    )

    return (
        df[PRICE_BOARD_COLUMNS]
        .loc[df["symbol"] != ""]
        .drop_duplicates("symbol", keep="last")
        .reset_index(drop=True)
    )


def seconds_left(deadline: float) -> float:
    return max(0.0, deadline - monotonic())


def fetch_price_board_once(symbols: list[str], source: str) -> pd.DataFrame:
    trading = Trading(source=source)

    # VCI mac dinh co the tra MultiIndex; yeu cau vnstock flatten ngay tu nguon.
    if source.upper() == "VCI":
        data = trading.price_board(
            symbols_list=symbols,
            flatten_columns=True,
        )
    else:
        data = trading.price_board(symbols_list=symbols)

    return normalize_price_board(data)


def collect_valid_rows(part: pd.DataFrame, target: dict[str, dict[str, Any]]) -> None:
    for row in part.to_dict(orient="records"):
        symbol = str(row.get("symbol") or "").strip().upper()
        if (
            symbol
            and pd.notna(row.get("close_price"))
            and pd.notna(row.get("volume_accumulated"))
        ):
            target[symbol] = row


def fetch_price_board(symbols: list[str], deadline: float) -> pd.DataFrame:
    requested = list(dict.fromkeys(str(symbol).strip().upper() for symbol in symbols))
    requested = [symbol for symbol in requested if symbol]
    if not requested:
        raise RuntimeError("Danh sach ma lay price board dang rong")

    received: dict[str, dict[str, Any]] = {}
    batch_count = (len(requested) + PRICE_BOARD_BATCH_SIZE - 1) // PRICE_BOARD_BATCH_SIZE

    for offset in range(0, len(requested), PRICE_BOARD_BATCH_SIZE):
        batch_number = offset // PRICE_BOARD_BATCH_SIZE + 1
        batch = requested[offset:offset + PRICE_BOARD_BATCH_SIZE]
        pending = [symbol for symbol in batch if symbol not in received]

        if seconds_left(deadline) <= 0:
            print(
                f"HET NGAN SACH lay gia truoc batch {batch_number}/{batch_count}; "
                f"bo qua {len(pending)} ma con lai trong batch nay."
            )
            continue

        last_error = "unknown"
        for attempt in range(1, PRIMARY_MAX_ATTEMPTS + 1):
            if not pending or seconds_left(deadline) <= 0:
                break
            try:
                part = fetch_price_board_once(pending, PRIMARY_SOURCE)
                collect_valid_rows(part, received)
                pending = [symbol for symbol in batch if symbol not in received]
                print(
                    f"{PRIMARY_SOURCE} batch {batch_number}/{batch_count}: "
                    f"{len(batch)-len(pending)}/{len(batch)} ma "
                    f"(lan {attempt}/{PRIMARY_MAX_ATTEMPTS}); "
                    f"con {seconds_left(deadline):.0f}s budget."
                )
                if not pending:
                    break
                last_error = f"thieu {len(pending)} ma: {pending[:10]}"
            except (Exception, SystemExit) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                print(
                    f"{PRIMARY_SOURCE} batch {batch_number}/{batch_count} loi "
                    f"(lan {attempt}/{PRIMARY_MAX_ATTEMPTS}): {last_error}"
                )

            if attempt < PRIMARY_MAX_ATTEMPTS and pending:
                if seconds_left(deadline) > PRIMARY_RETRY_DELAY_SECONDS:
                    print(
                        f"  -> Retry KBS sau {PRIMARY_RETRY_DELAY_SECONDS}s; "
                        f"con {len(pending)} ma."
                    )
                    sleep(PRIMARY_RETRY_DELAY_SECONDS)
                else:
                    break

        if pending and FALLBACK_MAX_ATTEMPTS > 0 and seconds_left(deadline) > 0:
            try:
                fallback_part = fetch_price_board_once(pending, FALLBACK_SOURCE)
                before = len(received)
                collect_valid_rows(fallback_part, received)
                rescued = len(received) - before
                pending = [symbol for symbol in batch if symbol not in received]
                print(
                    f"  -> {FALLBACK_SOURCE} fallback cuu {rescued} ma; "
                    f"batch con thieu {len(pending)} ma; "
                    f"con {seconds_left(deadline):.0f}s budget."
                )
            except (Exception, SystemExit) as exc:
                print(
                    f"  -> {FALLBACK_SOURCE} fallback loi cho {len(pending)} ma: "
                    f"{type(exc).__name__}: {exc}"
                )

        if pending:
            print(
                f"CANH BAO: batch {batch_number}/{batch_count} con thieu "
                f"{len(pending)} ma sau KBS->VCI. KBS cuoi: {last_error}"
            )

    if not received:
        raise RuntimeError("KBS/VCI khong tra duoc ma nao trong ngan sach Intraday")

    result = (
        pd.DataFrame(received.values())
        .drop_duplicates("symbol", keep="last")
        .reset_index(drop=True)
    )
    valid = result[
        result["close_price"].notna() & result["volume_accumulated"].notna()
    ]
    success_ratio = len(valid) / len(requested)
    print(
        f"Price board hop le KBS->VCI: {len(valid)}/{len(requested)} ma "
        f"({success_ratio:.1%})."
    )
    if success_ratio < MIN_PRICE_BOARD_SUCCESS_RATIO:
        raise RuntimeError(
            "Price board khong dat nguong an toan: "
            f"{len(valid)}/{len(requested)} ma ({success_ratio:.1%}), "
            f"yeu cau toi thieu {MIN_PRICE_BOARD_SUCCESS_RATIO:.0%}."
        )
    return result


def filter_newer_stock_snapshot_rows(
    rows: list[dict[str, Any]], scan_at
) -> list[dict[str, Any]]:
    if not rows:
        return rows
    response = supabase_request(
        "GET",
        "stock_snapshot",
        params={
            "select": "symbol,updated_at",
            "order": "symbol.asc",
            "limit": "1000",
        },
    )
    existing = {}
    for row in response.json():
        symbol = str(row.get("symbol") or "").strip().upper()
        updated = pd.to_datetime(row.get("updated_at"), errors="coerce", utc=True)
        if symbol and pd.notna(updated):
            existing[symbol] = updated

    scan_ts = pd.Timestamp(scan_at).tz_convert("UTC")
    kept = []
    skipped = 0
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol in existing and existing[symbol] > scan_ts:
            skipped += 1
            continue
        kept.append(row)
    if skipped:
        print(f"Bao ve stale overwrite: bo qua {skipped} stock_snapshot rows cu hon.")
    return kept


def build_rvol_reference(
    reference_rows: list[dict],
    start_slot: str,
    current_slot: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ref = pd.DataFrame(reference_rows)
    empty_start = pd.DataFrame(columns=["symbol", "start_volume_today"])
    empty_end = pd.DataFrame(columns=["symbol", "end_volume_today"])
    if ref.empty:
        return empty_start, empty_end, pd.DataFrame()

    required = {"symbol", "trading_date", "time_slot", "volume_accumulated"}
    missing = required.difference(ref.columns)
    if missing:
        print(
            f"CANH BAO: du lieu RVOL tham chieu thieu cot {sorted(missing)}; "
            "tam de RVOL trong."
        )
        return empty_start, empty_end, pd.DataFrame()

    ref["symbol"] = ref["symbol"].fillna("").astype(str).str.strip().str.upper()
    ref["volume_accumulated"] = pd.to_numeric(
        ref["volume_accumulated"], errors="coerce"
    )
    ref["trading_date"] = ref["trading_date"].astype(str)
    ref["time_slot"] = ref["time_slot"].astype(str).str.slice(0, 5)

    today = now_vn().date().isoformat()
    today_rows = ref[ref["trading_date"] == today]
    today_start = (
        today_rows[today_rows["time_slot"] == start_slot][
            ["symbol", "volume_accumulated"]
        ]
        .drop_duplicates("symbol", keep="last")
        .rename(columns={"volume_accumulated": "start_volume_today"})
    )
    today_end = (
        today_rows[today_rows["time_slot"] == current_slot][
            ["symbol", "volume_accumulated"]
        ]
        .drop_duplicates("symbol", keep="last")
        .rename(columns={"volume_accumulated": "end_volume_today"})
    )

    historical = ref[ref["trading_date"] != today].copy()
    if historical.empty:
        return today_start, today_end, pd.DataFrame()

    pivot = historical.pivot_table(
        index=["trading_date", "symbol"],
        columns="time_slot",
        values="volume_accumulated",
        aggfunc="last",
    ).reset_index()
    return today_start, today_end, pivot


def calculate_rvol(
    scan: pd.DataFrame,
    reference_rows: list[dict],
    current_slot: str,
    start_slot: str | None,
    live_snapshot_slot: str,
) -> pd.DataFrame:
    output = scan[["symbol", "volume_accumulated"]].copy()
    output["volume_30m"] = pd.NA
    output["avg_volume_30m_10"] = pd.NA
    output["rvol30_pct"] = pd.NA
    output["rvol30_sessions"] = 0

    if not start_slot:
        return output

    today_start, today_end, pivot = build_rvol_reference(
        reference_rows, start_slot, current_slot
    )
    output = output.merge(today_start, on="symbol", how="left")

    # Neu block RVOL ket thuc dung tai slot dang scan, dung volume live.
    # Neu HOSE/HNX da qua 14:45, dung snapshot 14:45 trong Supabase de khoa block.
    if current_slot == live_snapshot_slot:
        output["end_volume_for_rvol"] = output["volume_accumulated"]
    else:
        output = output.merge(today_end, on="symbol", how="left")
        output["end_volume_for_rvol"] = output["end_volume_today"]

    output["volume_30m"] = (
        output["end_volume_for_rvol"] - output["start_volume_today"]
    )
    output.loc[output["volume_30m"] < 0, "volume_30m"] = pd.NA

    historical_stats = pd.DataFrame(
        columns=["symbol", "avg_volume_30m_10", "historical_sessions"]
    )
    if (
        not pivot.empty
        and current_slot in pivot.columns
        and start_slot in pivot.columns
    ):
        pivot["historical_volume_30m"] = pivot[current_slot] - pivot[start_slot]
        valid = pivot[
            pivot["historical_volume_30m"].notna()
            & (pivot["historical_volume_30m"] >= 0)
        ].copy()

        # Chon toi da 10 PHIEN HOP LE cho tung ma, thay vi cat 10 ngay truoc khi
        # biet ngay nao co du ca 2 endpoint cua block.
        if not valid.empty:
            valid = valid.sort_values(["symbol", "trading_date"])
            valid = valid.groupby("symbol", group_keys=False).tail(10)
            historical_stats = (
                valid.groupby("symbol")["historical_volume_30m"]
                .agg(["mean", "count"])
                .reset_index()
                .rename(
                    columns={
                        "mean": "avg_volume_30m_10",
                        "count": "historical_sessions",
                    }
                )
            )

    output = (
        output.drop(columns=["avg_volume_30m_10", "rvol30_sessions"])
        .merge(historical_stats, on="symbol", how="left")
    )
    output["historical_sessions"] = (
        pd.to_numeric(output["historical_sessions"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    # Session hien thi la so phien du lieu da tich luy, gom ca phien hien tai.
    # Vi vay ngay dau tien cua slot 5-phut moi se hien 1/10.
    # RVOL% van chi dung CAC PHIEN TRUOC de lam baseline; neu chua co phien truoc
    # thi RVOL% de trong, khong tu so sanh phien hien tai voi chinh no.
    current_valid = output["volume_30m"].notna().astype(int)
    output["rvol30_sessions"] = (
        output["historical_sessions"] + current_valid
    ).clip(upper=10).astype(int)

    output["rvol30_pct"] = safe_pct(
        output["volume_30m"], output["avg_volume_30m_10"]
    )

    return output.drop(
        columns=[
            "start_volume_today",
            "end_volume_today",
            "end_volume_for_rvol",
            "historical_sessions",
        ],
        errors="ignore",
    )


def build_empty_rvol(scan: pd.DataFrame) -> pd.DataFrame:
    output = scan[["symbol", "volume_accumulated"]].copy()
    output["volume_30m"] = pd.NA
    output["avg_volume_30m_10"] = pd.NA
    output["rvol30_pct"] = pd.NA
    output["rvol30_sessions"] = 0
    return output


def merge_rvol_columns(result: pd.DataFrame, rvol: pd.DataFrame) -> pd.DataFrame:
    clean_result = result.drop(columns=RVOL_COLUMNS, errors="ignore")
    clean_rvol = rvol.copy()
    defaults = {
        "volume_30m": pd.NA,
        "avg_volume_30m_10": pd.NA,
        "rvol30_pct": pd.NA,
        "rvol30_sessions": 0,
    }
    for column, default in defaults.items():
        if column not in clean_rvol.columns:
            clean_rvol[column] = default
    if "symbol" not in clean_rvol.columns:
        clean_rvol["symbol"] = pd.Series(dtype="object")
    clean_rvol["symbol"] = (
        clean_rvol["symbol"].fillna("").astype(str).str.strip().str.upper()
    )
    clean_rvol = clean_rvol[["symbol", *RVOL_COLUMNS]].drop_duplicates(
        "symbol", keep="last"
    )
    merged = clean_result.merge(
        clean_rvol, on="symbol", how="left", validate="one_to_one"
    )
    merged["rvol30_sessions"] = (
        pd.to_numeric(merged["rvol30_sessions"], errors="coerce")
        .fillna(0)
        .astype(int)
    )
    return merged


def normalize_result_exchange(result: pd.DataFrame) -> pd.DataFrame:
    watchlist_exchange = result.get(
        "exchange_watchlist", pd.Series("", index=result.index)
    ).fillna("").astype(str).map(normalize_exchange_value)
    market_exchange = result.get(
        "exchange_market", pd.Series("", index=result.index)
    ).fillna("").astype(str).map(normalize_exchange_value)

    # Watchlist la nguon phan loai san on dinh hon. Market chi fallback neu thieu.
    result["exchange"] = watchlist_exchange.where(
        watchlist_exchange != "", market_exchange
    )
    return result


def calculate_rvol_by_exchange(
    result: pd.DataFrame,
    scan_at,
    live_snapshot_slot: str,
) -> tuple[pd.DataFrame, dict[str, tuple[str | None, str | None]]]:
    pieces: list[pd.DataFrame] = []
    windows: dict[str, tuple[str | None, str | None]] = {}
    reference_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for exchange, group in result.groupby("exchange", dropna=False, sort=False):
        normalized_exchange = normalize_exchange_value(exchange)
        current_slot, start_slot = rvol_window_slots(scan_at, normalized_exchange)
        windows[normalized_exchange or "UNKNOWN"] = (current_slot, start_slot)

        if not start_slot or not current_slot:
            pieces.append(build_empty_rvol(group))
            continue

        cache_key = (current_slot, start_slot)
        if cache_key not in reference_cache:
            reference_cache[cache_key] = load_rvol_reference(
                scan_at, current_slot, start_slot
            )
        pieces.append(
            calculate_rvol(
                group,
                reference_cache[cache_key],
                current_slot,
                start_slot,
                live_snapshot_slot,
            )
        )

    if not pieces:
        return build_empty_rvol(result), windows
    return pd.concat(pieces, ignore_index=True), windows


def main() -> None:
    verify_supabase_config()
    run_started_monotonic = monotonic()
    scan_at = now_vn()
    force_run = env_bool("FORCE_RUN", default=False)
    in_market = is_market_slot(scan_at)
    forced_outside_session = force_run and not in_market

    if not in_market and not force_run:
        print("Ngoai gio giao dich; bo qua.")
        return
    if forced_outside_session:
        print(
            "FORCE_RUN=true: chay kiem tra ngoai gio. "
            "Khong tinh tin hieu va khong ghi intraday_snapshots."
        )

    watchlist = load_watchlist()
    baseline = load_latest_baseline()
    price_deadline = run_started_monotonic + PRICE_FETCH_BUDGET_SECONDS
    price = fetch_price_board(watchlist["symbol"].tolist(), price_deadline)

    live_snapshot_slot = (
        market_snapshot_slot(scan_at)
        if in_market
        else scan_at.strftime("%H:%M")
    )

    result = watchlist.merge(
        price,
        on="symbol",
        how="left",
        suffixes=("_watchlist", "_market"),
    )
    result = normalize_result_exchange(result)
    result = result.drop(
        columns=["exchange_watchlist", "exchange_market"], errors="ignore"
    )
    result = result.merge(baseline, on="symbol", how="left")

    if in_market:
        rvol, rvol_windows = calculate_rvol_by_exchange(
            result, scan_at, live_snapshot_slot
        )
    else:
        rvol = build_empty_rvol(result)
        rvol_windows = {}

    result = merge_rvol_columns(
        result,
        rvol.drop(columns=["volume_accumulated"], errors="ignore"),
    )

    result["price_change_pct"] = (
        result["close_price"] / result["previous_close"] - 1
    ) * 100
    result["daily_volume_pct"] = safe_pct(
        result["volume_accumulated"], result["avg_volume_10"]
    )
    result["ma200_distance_pct"] = (
        result["close_price"] / result["ma200"] - 1
    ) * 100
    result["ma10_distance_pct"] = (
        result["close_price"] / result["ma10"] - 1
    ) * 100

    signal_columns = [
        "signal_price_3pct",
        "signal_daily_volume_200pct",
        "signal_above_ma200",
        "signal_rvol30_200pct",
    ]

    if in_market:
        result["signal_price_3pct"] = result["price_change_pct"] >= PRICE_THRESHOLD_PCT
        result["signal_daily_volume_200pct"] = (
            result["daily_volume_pct"] >= DAILY_VOLUME_THRESHOLD_PCT
        )
        result["signal_above_ma200"] = result["close_price"] > result["ma200"]
        result["signal_rvol30_200pct"] = (
            result["rvol30_pct"] >= RVOL30_THRESHOLD_PCT
        )
        result[signal_columns] = result[signal_columns].fillna(False).astype(bool)
        result["signal_count"] = result[signal_columns].sum(axis=1).astype(int)
    else:
        for column in signal_columns:
            result[column] = False
        result["signal_count"] = 0

    result["trading_date"] = scan_at.date().isoformat()
    result["time_slot"] = live_snapshot_slot
    result["updated_at"] = scan_at.isoformat()

    has_market_data = (
        result["close_price"].notna() & result["volume_accumulated"].notna()
    )
    if forced_outside_session:
        result["data_status"] = "OUT_OF_SESSION_TEST"
        result.loc[~has_market_data, "data_status"] = "MISSING_MARKET_DATA"
    else:
        result["data_status"] = "MISSING_MARKET_DATA"
        result.loc[has_market_data, "data_status"] = "OK"

    result = result.rename(columns={"close_price": "current_price"})
    for column in DASHBOARD_COLUMNS:
        if column not in result.columns:
            result[column] = None

    dashboard = result[DASHBOARD_COLUMNS].sort_values(
        ["signal_count", "rvol30_pct", "price_change_pct"],
        ascending=[False, False, False],
        na_position="last",
    )

    snapshots = (
        pd.DataFrame(columns=SNAPSHOT_COLUMNS)
        if forced_outside_session
        else dashboard[SNAPSHOT_COLUMNS].copy()
    )

    failed = int((dashboard["data_status"] == "MISSING_MARKET_DATA").sum())
    successful = len(watchlist) - failed
    job_type = "INTRADAY_FORCE_TEST" if forced_outside_session else "INTRADAY_SCAN"
    run_status = "SUCCESS" if failed == 0 else "PARTIAL"

    window_text = ",".join(
        f"{exchange}:{start or '-'}->{end or '-'}"
        for exchange, (end, start) in sorted(rvol_windows.items())
    )
    run_message = (
        "FORCED_OUT_OF_SESSION; signals_disabled=true; snapshots_written=0"
        if forced_outside_session
        else (
            f"slot={live_snapshot_slot}; rvol_windows={window_text}; "
            f"price_board={successful}/{len(watchlist)}; source=KBS->VCI_fallback"
        )
    )

    run_log = {
        "run_id": scan_at.strftime("intraday-%Y%m%d-%H%M%S"),
        "job_type": job_type,
        "started_at": scan_at.isoformat(),
        "finished_at": now_vn().isoformat(),
        "status": run_status,
        "symbols_requested": len(watchlist),
        "symbols_success": successful,
        "symbols_failed": failed,
        "message": run_message,
    }

    dashboard_rows = records(dashboard)
    snapshot_rows = records(snapshots)

    if snapshot_rows:
        upsert_rows(
            "intraday_snapshots",
            snapshot_rows,
            "trading_date,time_slot,symbol",
        )
    safe_dashboard_rows = filter_newer_stock_snapshot_rows(dashboard_rows, scan_at)
    upsert_rows("stock_snapshot", safe_dashboard_rows, "symbol")
    upsert_scan_run(run_log)

    elapsed = monotonic() - run_started_monotonic
    if elapsed >= TOTAL_RUNTIME_BUDGET_SECONDS - SHEET_BACKUP_TIMEOUT_SECONDS:
        sheet_ok = False
        sheet_message = (
            f"Sheet backup skipped: runtime da {elapsed:.0f}s, "
            "uu tien ket thuc truoc slot ke tiep."
        )
    else:
        sheet_ok, sheet_message = backup_sheet_best_effort(
            snapshot_rows, dashboard_rows, run_log
        )
    print(sheet_message)

    if not sheet_ok:
        run_log["finished_at"] = now_vn().isoformat()
        run_log["message"] = f"{run_message}; {sheet_message}"[:1000]
        upsert_scan_run(run_log)

    print(
        f"DONE: {successful}/{len(watchlist)} ma; slot={live_snapshot_slot}; "
        f"Supabase primary; Sheet backup={'OK' if sheet_ok else 'WARNING'}."
    )


if __name__ == "__main__":
    main()
