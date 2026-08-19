from __future__ import annotations

from datetime import time, timedelta
from time import sleep

import pandas as pd

import daily_baseline as base
from common import now_vn, records

# Cho cac san/GAS co vai phut hoan tat du lieu cuoi phien.
# Tu 15:05 tro di, phien cung ngay duoc xem la da dong va duoc phep
# tham gia Daily Baseline.
AFTER_MARKET_CLOSE = time(15, 5)


def history_exclusive_date(run_at):
    """
    Ngay cat DU LIEU theo kieu exclusive (< date).

    Vi du:
    - 19/08 14:00  -> 19/08: chi dung den 18/08.
    - 19/08 20:00  -> 20/08: cho phep dung den 19/08.
    - 20/08 01:00  -> 20/08: cho phep dung den 19/08.
    """
    if run_at.weekday() < 5 and run_at.time() >= AFTER_MARKET_CLOSE:
        return run_at.date() + timedelta(days=1)
    return run_at.date()


def checkpoint_start(run_at):
    """
    Sau dong cua, khong tai su dung checkpoint tao truoc 15:05 cung ngay,
    vi checkpoint do co the moi chi dung den phien hom truoc.
    """
    if run_at.weekday() < 5 and run_at.time() >= AFTER_MARKET_CLOSE:
        return run_at.replace(hour=15, minute=5, second=0, microsecond=0)
    return run_at.replace(hour=0, minute=0, second=0, microsecond=0)


def same_cutoff_already_completed(history_cutoff, symbols_requested: int):
    """
    Neu da co mot DAILY_BASELINE SUCCESS cho cung history_exclusive_date
    va cung so ma, khong can scan lai toan bo sau nua dem.

    Vi du:
    - chay tay 19/08 20:00 thanh cong, cutoff=20/08;
    - GAS goi lai 20/08 01:00, cutoff van=20/08;
    => bo qua scan Daily lan hai, workflow van tiep tuc refresh RVOL.
    """
    cutoff_text = history_cutoff.isoformat()
    response = base.supabase_request(
        "GET",
        "scan_runs",
        params={
            "select": "run_id,finished_at,status,symbols_requested,message",
            "job_type": "eq.DAILY_BASELINE",
            "status": "eq.SUCCESS",
            "symbols_requested": f"eq.{symbols_requested}",
            "message": f"like.*history_exclusive_date={cutoff_text}*",
            "order": "finished_at.desc",
            "limit": "1",
        },
    )
    rows = response.json()
    return rows[0] if isinstance(rows, list) and rows else None


def load_resume_checkpoints(run_at):
    start_at = checkpoint_start(run_at).isoformat()
    response = base.supabase_request(
        "GET",
        "daily_baseline",
        params={
            "select": "*",
            "updated_at": f"gte.{start_at}",
            "data_status": "eq.OK",
            "order": "updated_at.desc",
            "limit": "1000",
        },
    )
    rows = response.json()
    result = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol and symbol not in result:
            result[symbol] = row
    return result


def main() -> None:
    base.verify_vnstock_api_access()
    base.verify_supabase_config()

    run_at = now_vn()
    actual_run_date = run_at.date()
    history_cutoff = history_exclusive_date(run_at)

    run_id = run_at.strftime("daily-%Y%m%d-%H%M%S")
    watchlist = base.load_watchlist()
    watchlist_map = {
        str(row["symbol"]).strip().upper(): str(row["exchange"]).strip().upper()
        for _, row in watchlist.iterrows()
    }

    # Sau dong cua 19/08 -> history_cutoff=20/08.
    # 01:00 20/08       -> history_cutoff=20/08.
    end = history_cutoff.isoformat()
    start = (history_cutoff - timedelta(days=base.LOOKBACK_DAYS)).isoformat()

    print(
        "Daily Baseline cutoff: "
        f"run_at={run_at.isoformat()} | "
        f"history_exclusive_date={history_cutoff.isoformat()} | "
        f"same_day_close_included={history_cutoff > actual_run_date}"
    )

    completed = same_cutoff_already_completed(
        history_cutoff,
        len(watchlist_map),
    )
    if completed:
        print(
            "SKIP DAILY SCAN: cutoff nay da SUCCESS truoc do; "
            f"run_id={completed.get('run_id')}. "
            "Khong goi lai VNStock; workflow se tiep tuc buoc Refresh RVOL30."
        )
        return

    checkpoint_rows = load_resume_checkpoints(run_at)
    success_rows = {
        symbol: row
        for symbol, row in checkpoint_rows.items()
        if symbol in watchlist_map
    }

    if success_rows:
        print(
            f"Resume: Supabase da co {len(success_rows)}/{len(watchlist_map)} "
            "ma OK trong cung cua so chay; se bo qua cac ma nay."
        )

    pending_symbols = [
        symbol for symbol in watchlist_map if symbol not in success_rows
    ]
    last_errors: dict[str, str] = {}

    total_rounds = 1 + base.SYMBOL_RETRY_ROUNDS
    for round_index in range(total_rounds):
        if not pending_symbols:
            break

        if round_index > 0:
            delay = base.SYMBOL_RETRY_DELAYS_SECONDS[
                min(round_index - 1, len(base.SYMBOL_RETRY_DELAYS_SECONDS) - 1)
            ]
            print(
                f"\nRetry round {round_index}/{base.SYMBOL_RETRY_ROUNDS}: "
                f"{len(pending_symbols)} ma loi; cho {delay}s truoc khi retry."
            )
            sleep(delay)
        else:
            print(f"Bat dau Daily Baseline: {len(pending_symbols)} ma can scan.")

        failed_this_round: list[str] = []
        batch: list[dict] = []

        for index, symbol in enumerate(pending_symbols, start=1):
            exchange = watchlist_map[symbol]
            print(
                f"[round {round_index + 1}/{total_rounds}] "
                f"[{index}/{len(pending_symbols)}] {symbol}"
            )

            try:
                row = base.calculate_symbol(
                    symbol=symbol,
                    exchange=exchange,
                    start=start,
                    end=end,
                    run_date=history_cutoff,
                    updated_at=run_at,
                )
                success_rows[symbol] = row
                last_errors.pop(symbol, None)
                batch.append(row)
                print(
                    f"  -> {row['source']} | baseline {row['trading_date']} | OK"
                )

                if len(batch) >= base.SUPABASE_BATCH_SIZE:
                    base.flush_batch(batch)
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                last_errors[symbol] = message
                failed_this_round.append(symbol)
                print(f"  -> ERROR: {message}")

        base.flush_batch(batch)
        pending_symbols = failed_this_round

    final_failed = list(pending_symbols)
    success_count = len(watchlist_map) - len(final_failed)
    finished_at = now_vn()

    sheet_rows: list[dict] = []
    for symbol, exchange in watchlist_map.items():
        if symbol in success_rows:
            sheet_rows.append(success_rows[symbol])
        else:
            sheet_rows.append(
                base.stale_row_from_previous(
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

    message = (
        f"Daily baseline completed: {success_count}/{len(watchlist_map)} symbols; "
        f"history_exclusive_date={history_cutoff.isoformat()}"
    )
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
    base.upsert_scan_run(run_log)

    # Daily Sheet backup van giu tam thoi; Intraday da ngat Sheet.
    sheet_ok, sheet_message = base.backup_sheet_best_effort(
        records(pd.DataFrame(sheet_rows)),
        run_log,
    )
    print(sheet_message)

    if not sheet_ok:
        run_log["finished_at"] = now_vn().isoformat()
        run_log["message"] = f"{message}; {sheet_message}"[:1000]
        base.upsert_scan_run(run_log)

    if final_failed:
        raise RuntimeError(
            f"Con {len(final_failed)} ma loi sau "
            f"{base.SYMBOL_RETRY_ROUNDS} luot retry: {failed_text}. "
            "Chay lai workflow se chi retry checkpoint phu hop voi cua so chay."
        )

    print(
        f"DONE: {success_count}/{len(watchlist_map)} ma OK; "
        f"history_exclusive_date={history_cutoff.isoformat()}; "
        f"Supabase primary; Sheet backup={'OK' if sheet_ok else 'WARNING'}."
    )


if __name__ == "__main__":
    main()
