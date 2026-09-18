"""Stable frontend serializer and read-only current-state readers."""

from __future__ import annotations

import json
import sqlite3
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

from .signal_config import SignalConfig, load_signal_config


PUBLIC_CONTRACT_KEYS = (
    "contract_version", "symbol", "exchange", "trading_date", "event_at",
    "last_price", "ref_price", "change_pct", "total_volume", "session_type",
    "day_rvol", "rvol15", "rvol30", "price5_pct", "price15_pct",
    "ma10", "ma200", "distance_ma10_pct", "distance_ma200_pct",
    "ato_volume", "ato_avg_volume_10", "ato_rvol",
    "ato_baseline_sessions_used", "ato_baseline_quality",
    "atc_volume", "atc_avg_volume_10", "atc_rvol",
    "atc_baseline_sessions_used", "atc_baseline_quality", "atc_price_impact_pct",
    "baseline_sessions_used", "baseline_target_sessions", "baseline_coverage_pct",
    "signal_state", "signal_level", "signal_direction", "reason_codes",
    "signal_summary_vi", "previous_signal_state", "state_changed_at",
    "feed_status", "quality_status", "metrics_trusted",
    "engine_version", "config_version",
)


def _as_mapping(row: sqlite3.Row | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    return row


def serialize_stock_state(
    row: sqlite3.Row | Mapping[str, Any], *, config: SignalConfig | None = None
) -> dict[str, Any]:
    source = _as_mapping(row)
    cfg = config or load_signal_config()
    try:
        reasons = json.loads(source.get("reason_codes_json") or "[]")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("reason_codes_json must contain valid JSON") from exc
    if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
        raise ValueError("reason_codes_json must contain an array of strings")
    values: dict[str, Any] = {
        "contract_version": cfg.contract_version,
        **{key: source.get(key) for key in PUBLIC_CONTRACT_KEYS if key != "contract_version"},
    }
    values["reason_codes"] = reasons
    values["metrics_trusted"] = bool(source.get("metrics_trusted"))
    return OrderedDict((key, values[key]) for key in PUBLIC_CONTRACT_KEYS)


def _fetch_mapping(cursor: sqlite3.Cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    if row is None:
        return None
    names = [item[0] for item in cursor.description or ()]
    return dict(zip(names, row))


def get_current_state(
    connection: sqlite3.Connection, symbol: str, *, config: SignalConfig | None = None
) -> dict[str, Any] | None:
    cursor = connection.execute(
        "SELECT * FROM stock_state_current WHERE symbol = ?",
        (str(symbol or "").strip().upper(),),
    )
    row = _fetch_mapping(cursor)
    return None if row is None else serialize_stock_state(row, config=config)


def list_current_states(
    connection: sqlite3.Connection, *, config: SignalConfig | None = None
) -> list[dict[str, Any]]:
    cursor = connection.execute(
        "SELECT * FROM stock_state_current "
        "ORDER BY signal_level DESC, signal_state, symbol"
    )
    names = [item[0] for item in cursor.description or ()]
    return [
        serialize_stock_state(dict(zip(names, row)), config=config)
        for row in cursor.fetchall()
    ]
