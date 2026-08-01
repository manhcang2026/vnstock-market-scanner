from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Any

import pandas as pd

from common import gas_request


VN_TZ = timezone(timedelta(hours=7))


def now_vn() -> datetime:
    return datetime.now(VN_TZ)


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def build_test_rows(baseline_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Tạo dữ liệu kiểm thử Dashboard từ Daily_Baseline.

    Dữ liệu này không phải tín hiệu thị trường thật.
    Mục tiêu là tạo đủ trường hợp 0/4 đến 4/4 để làm giao diện.
    """
    generated_at = now_vn()
    trading_date = generated_at.date().isoformat()
    time_slot = generated_at.strftime("%H:%M")

    output: list[dict[str, Any]] = []

    for index, row in enumerate(baseline_rows):
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue

        exchange = str(row.get("exchange", "")).strip().upper()

        previous_close = safe_float(row.get("previous_close"))
        ma200 = safe_float(row.get("ma200"))
        avg_volume_10 = safe_float(row.get("avg_volume_10"))

        ma200_sessions = int(safe_float(row.get("ma200_sessions")) or 0)
        avg_volume_sessions = int(
            safe_float(row.get("avg_volume_sessions")) or 0
        )

        if previous_close is None or previous_close <= 0:
            continue

        # Luân phiên tạo các trường hợp:
        # 0: 4/4
        # 1: 3/4
        # 2: 2/4
        # 3: 1/4, RVOL30 cảnh báo sớm
        # 4: 0/4
        scenario = index % 5

        if scenario == 0:
            price_change_pct = 4.50
            daily_volume_pct = 240.0
            above_ma200 = True
            rvol30_pct = 320.0

        elif scenario == 1:
            price_change_pct = 3.40
            daily_volume_pct = 225.0
            above_ma200 = True
            rvol30_pct = 145.0

        elif scenario == 2:
            price_change_pct = 1.20
            daily_volume_pct = 215.0
            above_ma200 = True
            rvol30_pct = 155.0

        elif scenario == 3:
            price_change_pct = 0.80
            daily_volume_pct = 90.0
            above_ma200 = False
            rvol30_pct = 280.0

        else:
            price_change_pct = -1.10
            daily_volume_pct = 75.0
            above_ma200 = False
            rvol30_pct = 85.0

        current_price = previous_close * (1 + price_change_pct / 100)

        if ma200 is None or ma200 <= 0:
            ma200 = previous_close * 1.03

        if above_ma200:
            current_price = max(current_price, ma200 * 1.025)
        else:
            current_price = min(current_price, ma200 * 0.975)

        if avg_volume_10 is None or avg_volume_10 <= 0:
            avg_volume_10 = 100_000.0

        volume_accumulated = avg_volume_10 * daily_volume_pct / 100
        avg_volume_30m_10 = max(avg_volume_10 * 0.12, 1.0)
        volume_30m = avg_volume_30m_10 * rvol30_pct / 100

        actual_price_change_pct = (
            (current_price / previous_close - 1) * 100
        )

        ma200_distance_pct = (
            (current_price / ma200 - 1) * 100
            if ma200
            else None
        )

        signal_price_3pct = actual_price_change_pct >= 3.0
        signal_daily_volume_200pct = daily_volume_pct >= 200.0
        signal_above_ma200 = current_price > ma200
        signal_rvol30_200pct = rvol30_pct >= 200.0

        signal_count = sum(
            [
                signal_price_3pct,
                signal_daily_volume_200pct,
                signal_above_ma200,
                signal_rvol30_200pct,
            ]
        )

        output.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "current_price": round(current_price, 3),
                "previous_close": round(previous_close, 3),
                "price_change_pct": round(actual_price_change_pct, 2),
                "volume_accumulated": int(volume_accumulated),
                "avg_volume_10": int(avg_volume_10),
                "avg_volume_sessions": avg_volume_sessions,
                "daily_volume_pct": round(daily_volume_pct, 2),
                "ma200": round(ma200, 3),
                "ma200_sessions": ma200_sessions,
                "ma200_distance_pct": (
                    round(ma200_distance_pct, 2)
                    if ma200_distance_pct is not None
                    else None
                ),
                "volume_30m": int(volume_30m),
                "avg_volume_30m_10": int(avg_volume_30m_10),
                "rvol30_pct": round(rvol30_pct, 2),
                "rvol30_sessions": 10,
                "signal_price_3pct": signal_price_3pct,
                "signal_daily_volume_200pct": (
                    signal_daily_volume_200pct
                ),
                "signal_above_ma200": signal_above_ma200,
                "signal_rvol30_200pct": signal_rvol30_200pct,
                "signal_count": signal_count,
                "trading_date": trading_date,
                "time_slot": time_slot,
                "updated_at": generated_at.isoformat(),
                "data_status": "TEST_DEMO",
            }
        )

    return output


def build_test_snapshots(
    dashboard_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "trading_date": row["trading_date"],
            "time_slot": row["time_slot"],
            "symbol": row["symbol"],
            "exchange": row["exchange"],
            "current_price": row["current_price"],
            "volume_accumulated": row["volume_accumulated"],
            "updated_at": row["updated_at"],
            "data_status": "TEST_DEMO",
        }
        for row in dashboard_rows
    ]


def main() -> None:
    started_at = now_vn()

    response = gas_request("get_daily_baseline")
    baseline_rows = response.get("rows", [])

    if not baseline_rows:
        raise RuntimeError(
            "Daily_Baseline đang trống hoặc GAS không trả dữ liệu."
        )

    dashboard_rows = build_test_rows(baseline_rows)
    snapshot_rows = build_test_snapshots(dashboard_rows)

    if not dashboard_rows:
        raise RuntimeError("Không tạo được dữ liệu Dashboard test.")

    finished_at = now_vn()

    payload = {
        "dashboard_rows": dashboard_rows,
        "snapshot_rows": snapshot_rows,
        "run_log": {
            "run_id": started_at.strftime("%Y%m%d-%H%M%S-test"),
            "job_type": "INTRADAY_TEST",
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": "SUCCESS",
            "symbols_requested": len(baseline_rows),
            "symbols_success": len(dashboard_rows),
            "symbols_failed": len(baseline_rows) - len(dashboard_rows),
            "message": "Generated demo data for Dashboard testing",
        },
    }

    result = gas_request("write_intraday_test", payload=payload)

    print(
        f"Đã tạo {len(dashboard_rows)} dòng Dashboard_Test.",
        flush=True,
    )
    print(result, flush=True)


if __name__ == "__main__":
    main()
