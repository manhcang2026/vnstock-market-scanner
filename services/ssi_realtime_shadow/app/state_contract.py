"""Stable frontend contract keys and canonical state serializers."""

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
