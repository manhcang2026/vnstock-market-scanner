from __future__ import annotations

import argparse
import os
from datetime import date
from typing import Any

import pandas as pd

import backfill_daily_history as backfill
from common import load_watchlist, now_vn


# Only end-of-day snapshots are eligible for repair overlays.
# Current scanner produces the canonical final slot at 15:00.
MIN_EOD_TIME_SLOT = "15:00:00"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_symbols(raw: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in raw.replace(";", ",").split(","):
        symbol = item.strip().upper()
        if symbol and symbol not in seen:
            result.append(symbol)
            seen.add(symbol)
    return result


def load_existing_rows(symbol: str, anchor_date: date) -> list[dict[str, Any]]:
    response = backfill.supabase_request(
        "GET",
        "daily_history",
        params={
            "select": "symbol,exchange,trading_date,close,volume,source,updated_at",
            "symbol": f"eq.{symbol}",
            "trading_date": f"lte.{anchor_date.isoformat()}",
            "order": "trading_date.asc",
            "limit": "1000",
        },
    )
    return response.json()


def rows_to_history(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["time", "close", "volume"])

    df = pd.DataFrame(
        {
            "time": [row.get("trading_date") for row in rows],
            "close": [row.get("close") for row in rows],
            "volume": [row.get("volume") for row in rows],
        }
    )
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df.dropna(subset=["time", "close", "volume"])
    return (
        df[(df["close"] > 0) & (df["volume"] >= 0)]
        .sort_values("time")
        .drop_duplicates("time", keep="last")
        .reset_index(drop=True)
    )


def load_final_intraday_snapshots(
    symbol: str,
    anchor_date: date,
) -> dict[date, tuple[float, float, str]]:
    response = backfill.supabase_request(
        "GET",
        "intraday_snapshots",
        params={
            "select": (
                "trading_date,time_slot,current_price,"
                "volume_accumulated,data_status"
            ),
            "symbol": f"eq.{symbol}",
            "trading_date": f"lte.{anchor_date.isoformat()}",
            "current_price": "gt.0",
            "volume_accumulated": "gte.0",
            "data_status": "eq.OK",
            "time_slot": f"gte.{MIN_EOD_TIME_SLOT}",
            "order": "trading_date.asc,time_slot.asc",
            "limit": "5000",
        },
    )

    final_by_date: dict[date, tuple[float, float, str]] = {}
    for row in response.json():
        try:
            trading_date = date.fromisoformat(str(row["trading_date"]))
            price = float(row["current_price"])
            volume = float(row["volume_accumulated"])
            time_slot = str(row.get("time_slot") or "")
        except (KeyError, TypeError, ValueError):
            continue
        if price > 0 and volume >= 0:
            # Query already excludes pre-EOD slots; among eligible rows,
            # the last valid row wins for each date.
            final_by_date[trading_date] = (price, volume, time_slot)
    return final_by_date


def overlay_snapshots(
    history: pd.DataFrame,
    snapshots: dict[date, tuple[float, float, str]],
    mode: str,
    anchor_date: date,
) -> tuple[pd.DataFrame, list[date]]:
    available_dates = [
        pd.Timestamp(value).date()
        for value in history["time"].tolist()
        if pd.Timestamp(value).date() in snapshots
    ]
    if mode == "anchor":
        selected = [anchor_date] if anchor_date in available_dates else []
    elif mode == "recent10":
        selected = available_dates[-10:]
    elif mode == "all":
        selected = available_dates
    else:
        raise ValueError(f"Overlay mode khong hop le: {mode}")

    if not selected:
        return history.copy(), []

    selected_set = set(selected)
    result = history.copy()
    for index, row in result.iterrows():
        trading_date = pd.Timestamp(row["time"]).date()
        if trading_date not in selected_set:
            continue
        price, volume, _slot = snapshots[trading_date]
        result.at[index, "close"] = price
        result.at[index, "volume"] = volume

    return result, sorted(selected_set)


def candidate_from_sources(
    symbol: str,
    profile: dict[str, Any],
    run_date: date,
) -> tuple[pd.DataFrame, str, str, list[date]]:
    required_sessions = int(profile["ma200_sessions"])
    anchor_date: date = profile["trading_date"]
    preferred = str(profile["source"])
    fallback = (
        backfill.FALLBACK_SOURCE
        if preferred == backfill.PRIMARY_SOURCE
        else backfill.PRIMARY_SOURCE
    )
    snapshots = load_final_intraday_snapshots(symbol, anchor_date)
    attempts: list[str] = []

    for source in (preferred, fallback):
        try:
            history = backfill.fetch_source_history_adaptive(
                symbol,
                source,
                run_date,
                required_sessions,
                anchor_date,
            )
        except Exception as exc:
            attempts.append(f"{source}: fetch {type(exc).__name__}: {exc}")
            continue

        if len(history) < required_sessions:
            attempts.append(
                f"{source}: chi co {len(history)}/{required_sessions} phien"
            )
            continue

        exact, detail = backfill.compare_with_production(history, profile)
        if exact:
            return history, source, "provider_exact", []
        attempts.append(f"{source}/provider: {detail}")

        # Escalate conservatively: anchor only -> recent 10 -> all snapshots.
        for mode in ("anchor", "recent10", "all"):
            overlaid, used_dates = overlay_snapshots(
                history,
                snapshots,
                mode,
                anchor_date,
            )
            if not used_dates:
                continue

            exact, detail = backfill.compare_with_production(overlaid, profile)
            if exact:
                return overlaid, source, f"intraday_{mode}", used_dates
            attempts.append(
                f"{source}/intraday_{mode}({len(used_dates)}d): {detail}"
            )

    raise RuntimeError(
        "Khong tao duoc history EXACT sau provider + intraday overlay: "
        + " | ".join(attempts)
    )


def find_conflicts(
    existing_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> list[str]:
    candidate_by_date = {
        str(row["trading_date"]): row for row in candidate_rows
    }
    conflicts: list[str] = []
    for existing in existing_rows:
        trading_date = str(existing.get("trading_date") or "")
        candidate = candidate_by_date.get(trading_date)
        if candidate is None:
            continue
        try:
            same_close = abs(
                float(existing["close"]) - float(candidate["close"])
            ) <= 0.0001
            same_volume = abs(
                float(existing["volume"]) - float(candidate["volume"])
            ) <= 0.0001
        except (KeyError, TypeError, ValueError):
            conflicts.append(trading_date)
            continue
        if not (same_close and same_volume):
            conflicts.append(trading_date)
    return conflicts


def insert_missing_rows(rows: list[dict[str, Any]]) -> None:
    for offset in range(0, len(rows), backfill.SUPABASE_WRITE_BATCH_SIZE):
        batch = rows[offset:offset + backfill.SUPABASE_WRITE_BATCH_SIZE]
        backfill.supabase_request(
            "POST",
            "daily_history",
            params={"on_conflict": "symbol,trading_date"},
            payload=batch,
            prefer="resolution=ignore-duplicates,return=minimal",
        )


def verify_stored_history(
    symbol: str,
    profile: dict[str, Any],
) -> tuple[bool, str, pd.DataFrame]:
    rows = load_existing_rows(symbol, profile["trading_date"])
    history = rows_to_history(rows).tail(backfill.TARGET_SESSIONS).reset_index(
        drop=True
    )
    required_sessions = int(profile["ma200_sessions"])
    if len(history) < required_sessions:
        return False, f"stored={len(history)}/{required_sessions}", history

    latest = pd.Timestamp(history.iloc[-1]["time"]).date()
    if latest != profile["trading_date"]:
        return (
            False,
            f"latest={latest} != baseline={profile['trading_date']}",
            history,
        )

    exact, detail = backfill.compare_with_production(history, profile)
    return exact, detail, history


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair daily_history cho backfill ERROR. Mac dinh dry-run; "
            "khong DELETE va khong overwrite row hien co."
        )
    )
    parser.add_argument(
        "--symbols",
        default=os.getenv("REPAIR_SYMBOLS", ""),
        help="Danh sach ma phan tach bang dau phay.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        default=env_bool("REPAIR_WRITE", False),
        help="Cho phep insert missing-only va cap nhat sync state.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = parse_symbols(args.symbols)
    if not symbols:
        raise RuntimeError(
            "REPAIR_SYMBOLS/--symbols bat buoc; khong repair ca universe mu."
        )

    backfill.verify_vnstock_api_access()
    backfill.verify_supabase_config()

    run_at = now_vn()
    run_date = run_at.date()
    if backfill.in_market_protection_window(run_at):
        raise RuntimeError(
            "SAFETY STOP 08:20-15:10: khong tranh quota voi intraday."
        )

    watchlist = load_watchlist()
    exchanges = {
        str(row.symbol).strip().upper(): str(row.exchange).strip().upper()
        for row in watchlist.itertuples(index=False)
    }
    profiles = backfill.load_baseline_profiles()

    repaired = 0
    already_exact = 0
    unresolved: list[tuple[str, str]] = []

    print(
        f"Daily History Repair: symbols={len(symbols)}, "
        f"write={args.write}, run_date={run_date}."
    )

    for index, symbol in enumerate(symbols, start=1):
        profile = profiles.get(symbol)
        exchange = exchanges.get(symbol)
        if profile is None or not exchange:
            reason = "Khong co baseline profile/exchange hop le"
            unresolved.append((symbol, reason))
            print(f"[{index}] {symbol} -> UNRESOLVED: {reason}")
            continue

        existing_rows = load_existing_rows(symbol, profile["trading_date"])
        stored_exact, stored_detail, stored_history = verify_stored_history(
            symbol,
            profile,
        )
        if stored_exact:
            already_exact += 1
            print(
                f"[{index}] {symbol} -> ALREADY EXACT "
                f"({len(stored_history)} rows); no-op."
            )
            continue

        print(
            f"[{index}] {symbol} ({exchange}) "
            f"baseline={profile['trading_date']}, existing={len(existing_rows)}, "
            f"stored_gate={stored_detail}"
        )

        try:
            history, source, mode, overlay_dates = candidate_from_sources(
                symbol,
                profile,
                run_date,
            )
            candidate_rows = backfill.history_rows(
                symbol,
                exchange,
                history,
                source,
                run_at,
            )

            # Preserve row-level provenance. Only dates actually replaced by
            # a final intraday snapshot are labelled INTRADAY_EOD; provider
            # rows keep their original KBS/VCI source.
            overlay_date_strings = {value.isoformat() for value in overlay_dates}
            for candidate_row in candidate_rows:
                if candidate_row["trading_date"] in overlay_date_strings:
                    candidate_row["source"] = "INTRADAY_EOD"

            conflicts = find_conflicts(existing_rows, candidate_rows)
            if conflicts:
                raise RuntimeError(
                    "Existing rows conflict voi candidate tai: "
                    + ",".join(conflicts[:20])
                )

            existing_dates = {
                str(row.get("trading_date") or "")
                for row in existing_rows
                if row.get("trading_date")
            }
            missing_rows = [
                row
                for row in candidate_rows
                if row["trading_date"] not in existing_dates
            ]

            print(
                f"  -> CANDIDATE EXACT source={source}, mode={mode}, "
                f"rows={len(candidate_rows)}, missing={len(missing_rows)}, "
                f"overlay_days={len(overlay_dates)}"
            )
            if overlay_dates:
                print(
                    "  -> overlay="
                    + ",".join(value.isoformat() for value in overlay_dates)
                )

            if not args.write:
                print("  -> DRY-RUN: Supabase unchanged.")
                continue

            insert_missing_rows(missing_rows)
            exact, detail, stored_after = verify_stored_history(symbol, profile)
            if not exact:
                message = f"Post-write EXACT gate fail: {detail}"
                if not stored_after.empty:
                    dates = [
                        pd.Timestamp(value).date()
                        for value in stored_after["time"].tolist()
                    ]
                else:
                    dates = []
                backfill.upsert_state(
                    symbol=symbol,
                    exchange=exchange,
                    status="ERROR",
                    run_at=run_at,
                    history_exclusive_date=run_date,
                    sessions_loaded=len(stored_after),
                    oldest_trading_date=min(dates) if dates else None,
                    latest_trading_date=max(dates) if dates else None,
                    source=source,
                    last_error=message,
                )
                raise RuntimeError(message)

            dates = [
                pd.Timestamp(value).date()
                for value in stored_after["time"].tolist()
            ]
            backfill.upsert_state(
                symbol=symbol,
                exchange=exchange,
                status="COMPLETE",
                run_at=run_at,
                history_exclusive_date=run_date,
                sessions_loaded=len(stored_after),
                oldest_trading_date=min(dates),
                latest_trading_date=max(dates),
                source=source if mode == "provider_exact" else f"{source}+INTRADAY",
                completed=True,
            )
            repaired += 1
            print(
                f"  -> REPAIRED COMPLETE: stored={len(stored_after)}, "
                f"source={source}, mode={mode}"
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            unresolved.append((symbol, message))
            print(f"  -> UNRESOLVED {symbol}: {message}")

    print(
        f"Repair summary: requested={len(symbols)}, repaired={repaired}, "
        f"already_exact={already_exact}, unresolved={len(unresolved)}, "
        f"write={args.write}."
    )
    for symbol, reason in unresolved:
        print(f"  - {symbol}: {reason[:700]}")

    # Dry-run is an audit and should stay green even when some symbols
    # remain unresolved. A write run fails if anything could not be repaired.
    if args.write and unresolved:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
