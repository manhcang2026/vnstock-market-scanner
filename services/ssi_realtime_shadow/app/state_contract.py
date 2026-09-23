"""Stable frontend serializer and read-only current-state readers."""

from __future__ import annotations

import json
import sqlite3
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

from .signal_config import SignalConfig, load_signal_config


CANONICAL_STATE_KEYS = (
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

# Backward-compatible alias for the internal/canonical state contract.  Despite
# the historical name this payload contains proprietary CCC fields and must not
# be served anonymously.
PUBLIC_CONTRACT_KEYS = CANONICAL_STATE_KEYS

PUBLIC_STOCK_DETAIL_KEYS = (
    "contract_version", "symbol", "exchange", "trading_date", "event_at",
    "last_price", "ref_price", "change_pct", "total_volume", "session_type",
    "ma10", "ma200", "distance_ma10_pct", "distance_ma200_pct",
    "feed_status", "quality_status",
)

PROTECTED_CCC_INTELLIGENCE_KEYS = (
    "contract_version", "symbol", "trading_date", "event_at",
    "day_rvol", "rvol15", "rvol30", "price5_pct", "price15_pct",
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

SCANNER_PUBLIC_KEYS = (
    "symbol", "exchange", "trading_date", "event_at",
    "last_price", "ref_price", "change_pct", "total_volume",
    "session_type", "ma10", "ma200", "distance_ma10_pct",
    "distance_ma200_pct", "feed_status", "quality_status",
)

SCANNER_CCC_KEYS = (
    "day_rvol", "rvol15", "rvol30", "price5_pct", "price15_pct",
    "ato_volume", "ato_avg_volume_10", "ato_rvol",
    "ato_baseline_sessions_used", "ato_baseline_quality",
    "atc_volume", "atc_avg_volume_10", "atc_rvol",
    "atc_baseline_sessions_used", "atc_baseline_quality", "atc_price_impact_pct",
    "baseline_sessions_used", "baseline_target_sessions", "baseline_coverage_pct",
    "signal_state", "signal_level", "signal_direction", "reason_codes",
    "signal_summary_vi", "previous_signal_state", "state_changed_at",
    "metrics_trusted", "engine_version", "config_version",
)

_SCANNER_CCC_DB_COLUMNS = tuple(
    "reason_codes_json" if key == "reason_codes" else key
    for key in SCANNER_CCC_KEYS
)

RADAR_STATES = (
    "WATCHING",
    "FLOW_APPEARING",
    "FLOW_PRICE_CONFIRMED",
    "MOMENTUM_MAINTAINED",
    "MOMENTUM_WEAKENING",
    "SELLING_PRESSURE",
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
        **{key: source.get(key) for key in CANONICAL_STATE_KEYS if key != "contract_version"},
    }
    values["reason_codes"] = reasons
    values["metrics_trusted"] = bool(source.get("metrics_trusted"))
    return OrderedDict((key, values[key]) for key in CANONICAL_STATE_KEYS)


def serialize_public_stock_detail(
    row: sqlite3.Row | Mapping[str, Any], *, config: SignalConfig | None = None
) -> dict[str, Any]:
    """Return the explicit anonymous Stock Detail projection.

    This deliberately excludes RVOL, price momentum, auctions, signal state,
    reasons and engine configuration.
    """
    source = _as_mapping(row)
    cfg = config or load_signal_config()
    values = {
        "contract_version": cfg.contract_version,
        **{
            key: source.get(key)
            for key in PUBLIC_STOCK_DETAIL_KEYS
            if key != "contract_version"
        },
    }
    return OrderedDict((key, values[key]) for key in PUBLIC_STOCK_DETAIL_KEYS)


def serialize_ccc_intelligence(
    row: sqlite3.Row | Mapping[str, Any], *, config: SignalConfig | None = None
) -> dict[str, Any]:
    """Return proprietary CCC intelligence after server authorization."""
    canonical = serialize_stock_state(row, config=config)
    return OrderedDict(
        (key, canonical[key]) for key in PROTECTED_CCC_INTELLIGENCE_KEYS
    )


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


def get_public_stock_detail(
    connection: sqlite3.Connection, symbol: str, *, config: SignalConfig | None = None
) -> dict[str, Any] | None:
    cursor = connection.execute(
        "SELECT * FROM stock_state_current WHERE symbol = ?",
        (str(symbol or "").strip().upper(),),
    )
    row = _fetch_mapping(cursor)
    return None if row is None else serialize_public_stock_detail(row, config=config)


def get_ccc_intelligence(
    connection: sqlite3.Connection, symbol: str, *, config: SignalConfig | None = None
) -> dict[str, Any] | None:
    cursor = connection.execute(
        "SELECT * FROM stock_state_current WHERE symbol = ?",
        (str(symbol or "").strip().upper(),),
    )
    row = _fetch_mapping(cursor)
    return None if row is None else serialize_ccc_intelligence(row, config=config)


def build_scanner_projection(
    connection: sqlite3.Connection,
    *,
    visible_symbols: set[str] | frozenset[str] | None = None,
    full_market: bool = False,
) -> dict[str, Any]:
    """Read current state once and construct only authorized scanner fields."""
    visible = {str(symbol).strip().upper() for symbol in (visible_symbols or ())}
    include_ccc_columns = full_market or bool(visible)
    columns = SCANNER_PUBLIC_KEYS + (_SCANNER_CCC_DB_COLUMNS if include_ccc_columns else ())
    cursor = connection.execute(
        f"SELECT {', '.join(columns)} FROM stock_state_current ORDER BY symbol"
    )
    names = [item[0] for item in cursor.description or ()]
    positions = {name: index for index, name in enumerate(names)}
    rows: list[dict[str, Any]] = []
    for raw_row in cursor.fetchall():
        row = OrderedDict((key, raw_row[positions[key]]) for key in SCANNER_PUBLIC_KEYS)
        entitled = full_market or row["symbol"] in visible
        if entitled:
            source = dict(zip(names, raw_row))
            try:
                reasons = json.loads(source.get("reason_codes_json") or "[]")
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("reason_codes_json must contain valid JSON") from exc
            if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
                raise ValueError("reason_codes_json must contain an array of strings")
            ccc = OrderedDict((key, source.get(key)) for key in SCANNER_CCC_KEYS)
            ccc["reason_codes"] = reasons
            ccc["metrics_trusted"] = bool(source.get("metrics_trusted"))
            row["ccc"] = ccc
        else:
            row["ccc"] = None
        rows.append(row)
    return {
        "contract_version": "ccc-scanner-v1",
        "count": len(rows),
        "rows": rows,
    }


def build_radar_projection(
    connection: sqlite3.Connection,
    *,
    visible_symbols: set[str] | None = None,
    full_market: bool = False,
) -> dict[str, Any]:
    """Build aggregate counts plus an authorization-filtered identity list."""
    normalized_visible = {
        str(symbol).strip().upper() for symbol in (visible_symbols or set())
    }
    placeholders = ",".join("?" for _ in RADAR_STATES)
    cursor = connection.execute(
        f"SELECT symbol,exchange,event_at,state_changed_at,signal_state,"
        f"signal_level,signal_direction FROM stock_state_current "
        f"WHERE signal_state IN ({placeholders}) "
        f"ORDER BY signal_level DESC, COALESCE(state_changed_at,event_at) DESC, symbol",
        RADAR_STATES,
    )
    names = [item[0] for item in cursor.description or ()]
    grouped = {
        state: {"state": state, "total": 0, "items": [], "hidden": 0}
        for state in RADAR_STATES
    }
    for raw_row in cursor.fetchall():
        row = dict(zip(names, raw_row))
        state = str(row.get("signal_state") or "")
        group = grouped.get(state)
        if group is None:
            continue
        group["total"] += 1
        symbol = str(row.get("symbol") or "").upper()
        if full_market or symbol in normalized_visible:
            group["items"].append(
                OrderedDict(
                    (
                        ("symbol", symbol),
                        ("exchange", row.get("exchange")),
                        ("event_at", row.get("event_at")),
                        ("state_changed_at", row.get("state_changed_at")),
                        ("signal_level", row.get("signal_level")),
                        ("signal_direction", row.get("signal_direction")),
                    )
                )
            )
    for group in grouped.values():
        group["hidden"] = group["total"] - len(group["items"])
    return {
        "contract_version": "ccc-radar-v1",
        "groups": list(grouped.values()),
    }


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
