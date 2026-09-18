"""Offline TEST/DEMO export for the stable CCC current-state contract."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from typing import Any

from .signal_config import SignalConfig, load_signal_config
from .signal_engine import TechnicalState, classify_signal
from .state_contract import serialize_stock_state


DEMO_AT = "2026-09-18T10:30:00+07:00"


def _technical(**overrides: Any) -> TechnicalState:
    values: dict[str, Any] = {
        "session_type": "AM_CONTINUOUS",
        "last_price": 101.0,
        "day_rvol": 1.0,
        "rvol15": 1.0,
        "rvol30": 1.0,
        "price5_pct": 0.0,
        "price15_pct": 0.0,
        "ma10": 100.0,
        "ma200": 95.0,
        "distance_ma10_pct": 1.0,
        "distance_ma200_pct": 6.315789,
        "baseline_sessions_used": 10,
        "metrics_trusted": True,
    }
    values.update(overrides)
    return TechnicalState(**values)


DEMO_CASES = (
    ("DMN", None, {}),
    ("DWT", None, {"day_rvol": 1.30}),
    ("DFA", None, {"day_rvol": 1.20, "rvol15": 1.80, "rvol30": 1.80, "price5_pct": 0.50, "price15_pct": 0.80}),
    ("DFC", None, {"day_rvol": 1.40, "rvol15": 1.20, "rvol30": 2.00, "price5_pct": 0.20, "price15_pct": 1.20}),
    ("DMM", "FLOW_PRICE_CONFIRMED", {"day_rvol": 1.10, "rvol15": 1.10, "rvol30": 1.40, "price5_pct": 0.10, "price15_pct": 0.0}),
    ("DMW", "FLOW_PRICE_CONFIRMED", {"day_rvol": 1.10, "rvol15": 1.10, "rvol30": 1.20, "price5_pct": -0.50, "price15_pct": -0.80}),
    ("DSP", None, {"day_rvol": 1.20, "rvol15": 1.80, "rvol30": 1.80, "price5_pct": -0.80, "price15_pct": -1.20}),
)


def build_demo_items(config: SignalConfig | None = None) -> list[dict[str, Any]]:
    """Return seven deterministic frontend records; never reads production data."""
    cfg = config or load_signal_config()
    items: list[dict[str, Any]] = []
    for symbol, previous, overrides in DEMO_CASES:
        technical = _technical(**overrides)
        decision = classify_signal(technical, previous, cfg)
        row = {
            "symbol": symbol,
            "exchange": "HOSE",
            "trading_date": "2026-09-18",
            "event_at": DEMO_AT,
            "last_price": technical.last_price,
            "ref_price": 100.0,
            "change_pct": technical.price15_pct,
            "total_volume": 1_000_000,
            "session_type": technical.session_type,
            "day_rvol": technical.day_rvol,
            "rvol15": technical.rvol15,
            "rvol30": technical.rvol30,
            "price5_pct": technical.price5_pct,
            "price15_pct": technical.price15_pct,
            "ma10": technical.ma10,
            "ma200": technical.ma200,
            "distance_ma10_pct": technical.distance_ma10_pct,
            "distance_ma200_pct": technical.distance_ma200_pct,
            "ato_volume": None,
            "ato_avg_volume_10": None,
            "ato_rvol": None,
            "ato_baseline_sessions_used": 0,
            "ato_baseline_quality": "UNAVAILABLE",
            "atc_volume": None,
            "atc_avg_volume_10": None,
            "atc_rvol": None,
            "atc_baseline_sessions_used": 0,
            "atc_baseline_quality": "UNAVAILABLE",
            "atc_price_impact_pct": None,
            "baseline_sessions_used": 10,
            "baseline_target_sessions": 10,
            "baseline_coverage_pct": 100.0,
            "signal_state": decision.signal_state,
            "signal_level": decision.signal_level,
            "signal_direction": decision.signal_direction,
            "reason_codes_json": json.dumps(list(decision.reason_codes)),
            "signal_summary_vi": decision.signal_summary_vi,
            "previous_signal_state": previous,
            "state_changed_at": DEMO_AT,
            "feed_status": "LIVE",
            "quality_status": "TRUSTED",
            "metrics_trusted": 1,
            "engine_version": cfg.engine_version,
            "config_version": cfg.config_version,
        }
        items.append(serialize_stock_state(row, config=cfg))
    return items


def build_demo_payload(config: SignalConfig | None = None) -> dict[str, Any]:
    cfg = config or load_signal_config()
    items = build_demo_items(cfg)
    return {"contract_version": cfg.contract_version, "count": len(items), "items": items}


@dataclass(frozen=True, slots=True)
class AuctionDemo:
    sessions_used: int
    baseline_quality: str
    avg_volume: float
    current_volume: int
    rvol: float
    price_impact_pct: float | None = None


def build_auction_demo() -> dict[str, dict[str, Any]]:
    """Clearly synthetic exact-10 examples used only in tests/reports."""
    return {
        "ATO": asdict(AuctionDemo(10, "PROVEN", 400_000.0, 1_000_000, 2.5)),
        "ATC": asdict(AuctionDemo(10, "MIXED", 500_000.0, 1_250_000, 2.5, -1.6)),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("TEST/DEMO ONLY — deterministic synthetic fixtures; no production data")
    print(json.dumps(build_demo_payload(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
