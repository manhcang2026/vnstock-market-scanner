"""Read-only canonical adapter for frontend current-state API routes."""

from __future__ import annotations

import sqlite3
from collections import OrderedDict
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .market_session import VN_TZ, classify_market_session
from .signal_config import SignalConfig, load_signal_config
from .state_contract import (
    RADAR_STATES,
    SCANNER_CCC_KEYS,
    SCANNER_PUBLIC_KEYS,
    serialize_ccc_intelligence,
    serialize_public_stock_detail,
    serialize_stock_state,
)


def _row_mapping(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else {key: row[key] for key in row.keys()}


PUBLIC_CURRENT_COLUMNS = (
    "symbol", "exchange", "trading_date", "minute", "ma10", "ma200",
    "distance_ma10_pct", "distance_ma200_pct", "quality_status",
)
PUBLIC_QUOTE_COLUMNS = (
    "symbol", "trading_date", "event_time", "last_price", "ref_price",
    "ratio_change", "total_volume", "exchange",
)
PROTECTED_CURRENT_COLUMNS = (
    "symbol", "trading_date", "day_rvol", "rvol15", "rvol30", "price5_pct",
    "price15_pct", "baseline_sessions_used", "reason_codes_json",
)
SIGNAL_COLUMNS = (
    "symbol", "trading_date", "signal_state", "signal_level",
    "signal_direction", "reason_codes_json", "signal_summary_vi",
    "previous_signal_state", "state_changed_at", "metrics_trusted",
    "engine_version", "config_version",
)
AUCTION_COLUMNS = (
    "symbol", "trading_date", "auction_type", "provider_session",
    "auction_volume", "source", "quality_status", "finalized",
)


class CanonicalStateReader:
    """Merge canonical engine, quote, signal, and exact auction facts."""

    def __init__(
        self,
        *,
        market_dir: str | Path,
        engine_path: str | Path,
        config: SignalConfig | None = None,
    ) -> None:
        self.market_dir = Path(market_dir)
        self.engine_path = Path(engine_path)
        self.config = config or load_signal_config()

    @staticmethod
    def _connect_readonly(path: Path) -> sqlite3.Connection:
        if not path.is_file():
            raise FileNotFoundError(path)
        connection = sqlite3.connect(
            f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=5
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _market_path(self, trading_date: str) -> Path:
        year = datetime.fromisoformat(trading_date).year
        return self.market_dir / f"ccc_market_{year}.db"

    @staticmethod
    def _event_at(quote: Mapping[str, Any] | None) -> str | None:
        if quote is None or not quote.get("event_time"):
            return None
        trading_date = str(quote.get("trading_date") or "")
        raw = str(quote["event_time"])
        try:
            event = datetime.fromisoformat(
                raw if "T" in raw else f"{trading_date}T{raw}"
            )
        except ValueError:
            return None
        if event.tzinfo is None:
            event = event.replace(tzinfo=VN_TZ)
        return event.astimezone(VN_TZ).isoformat()

    @staticmethod
    def _derived_session_type(current: Mapping[str, Any]) -> str | None:
        trading_date = current.get("trading_date")
        minute = current.get("minute")
        exchange = current.get("exchange")
        if not trading_date or not minute or not exchange:
            return None
        try:
            observed = datetime.fromisoformat(
                f"{trading_date}T{str(minute)[:5]}:00"
            ).replace(tzinfo=VN_TZ)
            return classify_market_session(str(exchange), observed).session_type.value
        except ValueError:
            return None

    @staticmethod
    def _trusted_auction_volume(
        row: Mapping[str, Any] | None, *, auction_type: str
    ) -> int | None:
        if row is None:
            return None
        if (
            row.get("auction_type") != auction_type
            or row.get("provider_session") != auction_type
            or row.get("source") != "SSI_STREAM"
            or row.get("quality_status") != "TRUSTED"
            or row.get("finalized") != 1
        ):
            return None
        volume = row.get("auction_volume")
        return (
            volume
            if isinstance(volume, int) and not isinstance(volume, bool)
            else None
        )

    def _merge_public(
        self,
        current: Mapping[str, Any],
        quote: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "symbol": current.get("symbol"),
            "exchange": (
                quote.get("exchange") if quote is not None else None
            ) or current.get("exchange"),
            "trading_date": current.get("trading_date"),
            "event_at": self._event_at(quote),
            "last_price": quote.get("last_price") if quote is not None else None,
            "ref_price": quote.get("ref_price") if quote is not None else None,
            "change_pct": quote.get("ratio_change") if quote is not None else None,
            "total_volume": quote.get("total_volume") if quote is not None else None,
            "session_type": self._derived_session_type(current),
            "ma10": current.get("ma10"),
            "ma200": current.get("ma200"),
            "distance_ma10_pct": current.get("distance_ma10_pct"),
            "distance_ma200_pct": current.get("distance_ma200_pct"),
            "feed_status": None,
            "quality_status": current.get("quality_status"),
        }

    def _merge_protected(
        self,
        current: Mapping[str, Any],
        quote: Mapping[str, Any] | None,
        signal: Mapping[str, Any] | None,
        auctions: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        baseline_used = current.get("baseline_sessions_used")
        target = self.config.continuous_target_sessions
        coverage = (
            float(baseline_used) * 100.0 / target
            if baseline_used is not None and target > 0
            else None
        )
        ato = auctions.get("ATO")
        atc = auctions.get("ATC")
        reason_codes_json = (
            signal.get("reason_codes_json") if signal is not None else None
        ) or current.get("reason_codes_json") or "[]"
        merged = self._merge_public(current, quote)
        merged.update({
            "day_rvol": current.get("day_rvol"),
            "rvol15": current.get("rvol15"),
            "rvol30": current.get("rvol30"),
            "price5_pct": current.get("price5_pct"),
            "price15_pct": current.get("price15_pct"),
            "ato_volume": self._trusted_auction_volume(ato, auction_type="ATO"),
            "ato_avg_volume_10": None,
            "ato_rvol": None,
            "ato_baseline_sessions_used": None,
            "ato_baseline_quality": None,
            "atc_volume": self._trusted_auction_volume(atc, auction_type="ATC"),
            "atc_avg_volume_10": None,
            "atc_rvol": None,
            "atc_baseline_sessions_used": None,
            "atc_baseline_quality": None,
            "atc_price_impact_pct": None,
            "baseline_sessions_used": baseline_used,
            "baseline_target_sessions": target,
            "baseline_coverage_pct": coverage,
            "signal_state": signal.get("signal_state") if signal else None,
            "signal_level": signal.get("signal_level") if signal else None,
            "signal_direction": signal.get("signal_direction") if signal else None,
            "reason_codes_json": reason_codes_json,
            "signal_summary_vi": signal.get("signal_summary_vi") if signal else None,
            "previous_signal_state": (
                signal.get("previous_signal_state") if signal else None
            ),
            "state_changed_at": signal.get("state_changed_at") if signal else None,
            "metrics_trusted": signal.get("metrics_trusted") if signal else None,
            "engine_version": signal.get("engine_version") if signal else None,
            "config_version": signal.get("config_version") if signal else None,
        })
        return merged

    def _protected_symbol_components(
        self, symbol: str
    ) -> tuple[
        Mapping[str, Any],
        Mapping[str, Any] | None,
        Mapping[str, Any] | None,
        dict[str, Mapping[str, Any]],
    ] | None:
        canonical_symbol = str(symbol or "").strip().upper()
        with self._connect_readonly(self.engine_path) as engine:
            current = _row_mapping(
                engine.execute(
                    f"""SELECT {', '.join(PUBLIC_CURRENT_COLUMNS + PROTECTED_CURRENT_COLUMNS[2:])}
                        FROM current_state
                        WHERE symbol=?
                          AND trading_date=(SELECT MAX(trading_date)
                                            FROM current_state
                                            WHERE trading_date IS NOT NULL)""",
                    (canonical_symbol,),
                ).fetchone()
            )
            if current is None:
                return None
            snapshot_date = str(current["trading_date"])
            signal = _row_mapping(
                engine.execute(
                    f"""SELECT {', '.join(SIGNAL_COLUMNS)}
                       FROM signal_state_current
                       WHERE symbol=? AND trading_date=?""",
                    (canonical_symbol, snapshot_date),
                ).fetchone()
            )
        with self._connect_readonly(self._market_path(snapshot_date)) as market:
            quote = _row_mapping(
                market.execute(
                    f"""SELECT {', '.join(PUBLIC_QUOTE_COLUMNS)}
                       FROM latest_quotes
                       WHERE symbol=? AND trading_date=?""",
                    (canonical_symbol, snapshot_date),
                ).fetchone()
            )
            auction_rows = market.execute(
                f"""SELECT {', '.join(AUCTION_COLUMNS)}
                   FROM auction_sessions
                   WHERE symbol=? AND trading_date=? AND finalized=1""",
                (canonical_symbol, snapshot_date),
            ).fetchall()
        auctions = {
            str(row["auction_type"]): _row_mapping(row) or {} for row in auction_rows
        }
        return current, quote, signal, auctions

    def public_stock_detail(self, symbol: str) -> dict[str, Any] | None:
        canonical_symbol = str(symbol or "").strip().upper()
        with self._connect_readonly(self.engine_path) as engine:
            current = _row_mapping(
                engine.execute(
                    f"""SELECT {', '.join(PUBLIC_CURRENT_COLUMNS)}
                        FROM current_state
                        WHERE symbol=?
                          AND trading_date=(SELECT MAX(trading_date)
                                            FROM current_state
                                            WHERE trading_date IS NOT NULL)""",
                    (canonical_symbol,),
                ).fetchone()
            )
        if current is None:
            return None
        snapshot_date = str(current["trading_date"])
        with self._connect_readonly(self._market_path(snapshot_date)) as market:
            quote = _row_mapping(
                market.execute(
                    f"""SELECT {', '.join(PUBLIC_QUOTE_COLUMNS)}
                        FROM latest_quotes
                        WHERE symbol=? AND trading_date=?""",
                    (canonical_symbol, snapshot_date),
                ).fetchone()
            )
        return serialize_public_stock_detail(
            self._merge_public(current, quote), config=self.config
        )

    def ccc_intelligence(self, symbol: str) -> dict[str, Any] | None:
        components = self._protected_symbol_components(symbol)
        if components is None:
            return None
        return serialize_ccc_intelligence(
            self._merge_protected(*components), config=self.config
        )

    @staticmethod
    def _scope_filter(
        trading_date: str, symbols: set[str] | None
    ) -> tuple[str, tuple[str, ...]]:
        if symbols is None:
            return "trading_date=?", (trading_date,)
        ordered = tuple(sorted(symbols))
        placeholders = ",".join("?" for _ in ordered)
        return (
            f"trading_date=? AND symbol IN ({placeholders})",
            (trading_date, *ordered),
        )

    def scanner_projection(
        self,
        *,
        visible_symbols: set[str] | frozenset[str] | None = None,
        full_market: bool = False,
    ) -> dict[str, Any]:
        visible = {str(symbol).strip().upper() for symbol in (visible_symbols or ())}
        protected_symbols = None if full_market else visible
        include_protected = full_market or bool(visible)
        with self._connect_readonly(self.engine_path) as engine:
            current_rows = engine.execute(
                f"""SELECT {', '.join(PUBLIC_CURRENT_COLUMNS)} FROM current_state
                   WHERE trading_date=(SELECT MAX(trading_date) FROM current_state
                                       WHERE trading_date IS NOT NULL)
                   ORDER BY symbol"""
            ).fetchall()
            if not current_rows:
                return {"contract_version": "ccc-scanner-v1", "count": 0, "rows": []}
            snapshot_date = str(current_rows[0]["trading_date"])
            protected_rows: list[sqlite3.Row] = []
            signal_rows: list[sqlite3.Row] = []
            if include_protected:
                scope_sql, scope_params = self._scope_filter(
                    snapshot_date, protected_symbols
                )
                protected_rows = engine.execute(
                    f"""SELECT {', '.join(PROTECTED_CURRENT_COLUMNS)}
                        FROM current_state WHERE {scope_sql}""",
                    scope_params,
                ).fetchall()
                signal_rows = engine.execute(
                    f"""SELECT {', '.join(SIGNAL_COLUMNS)}
                        FROM signal_state_current WHERE {scope_sql}""",
                    scope_params,
                ).fetchall()
        with self._connect_readonly(self._market_path(snapshot_date)) as market:
            quote_rows = market.execute(
                f"""SELECT {', '.join(PUBLIC_QUOTE_COLUMNS)}
                    FROM latest_quotes WHERE trading_date=?""",
                (snapshot_date,),
            ).fetchall()
            auction_rows: list[sqlite3.Row] = []
            if include_protected:
                scope_sql, scope_params = self._scope_filter(
                    snapshot_date, protected_symbols
                )
                auction_rows = market.execute(
                    f"""SELECT {', '.join(AUCTION_COLUMNS)}
                        FROM auction_sessions
                        WHERE {scope_sql} AND finalized=1""",
                    scope_params,
                ).fetchall()
        quotes = {str(row["symbol"]): _row_mapping(row) or {} for row in quote_rows}
        protected = {
            str(row["symbol"]): _row_mapping(row) or {} for row in protected_rows
        }
        signals = {str(row["symbol"]): _row_mapping(row) or {} for row in signal_rows}
        auctions: dict[str, dict[str, Mapping[str, Any]]] = {}
        for row in auction_rows:
            auctions.setdefault(str(row["symbol"]), {})[
                str(row["auction_type"])
            ] = _row_mapping(row) or {}
        rows: list[dict[str, Any]] = []
        for raw_current in current_rows:
            current = _row_mapping(raw_current) or {}
            symbol = str(current["symbol"])
            public = self._merge_public(current, quotes.get(symbol))
            row = OrderedDict((key, public.get(key)) for key in SCANNER_PUBLIC_KEYS)
            if full_market or symbol in visible:
                protected_current = {**current, **protected.get(symbol, {})}
                merged = self._merge_protected(
                    protected_current,
                    quotes.get(symbol),
                    signals.get(symbol),
                    auctions.get(symbol, {}),
                )
                canonical = serialize_stock_state(merged, config=self.config)
                row["ccc"] = OrderedDict(
                    (key, canonical.get(key)) for key in SCANNER_CCC_KEYS
                )
            else:
                row["ccc"] = None
            rows.append(row)
        return {
            "contract_version": "ccc-scanner-v1",
            "count": len(rows),
            "rows": rows,
        }

    def radar_projection(
        self,
        *,
        visible_symbols: set[str] | None = None,
        full_market: bool = False,
    ) -> dict[str, Any]:
        visible = {str(symbol).strip().upper() for symbol in (visible_symbols or set())}
        placeholders = ",".join("?" for _ in RADAR_STATES)
        with self._connect_readonly(self.engine_path) as engine:
            rows = engine.execute(
                f"""SELECT s.symbol,COALESCE(s.exchange,c.exchange) AS exchange,
                            s.updated_at AS event_at,s.state_changed_at,
                            s.signal_state,s.signal_level,s.signal_direction
                     FROM signal_state_current AS s
                     JOIN current_state AS c ON c.symbol=s.symbol
                     WHERE c.trading_date=(SELECT MAX(trading_date) FROM current_state
                                           WHERE trading_date IS NOT NULL)
                       AND s.trading_date=c.trading_date
                       AND s.signal_state IN ({placeholders})
                     ORDER BY s.signal_level DESC,
                              COALESCE(s.state_changed_at,s.updated_at) DESC,
                              s.symbol""",
                RADAR_STATES,
            ).fetchall()
        grouped = {
            state: {"state": state, "total": 0, "items": [], "hidden": 0}
            for state in RADAR_STATES
        }
        for raw in rows:
            row = _row_mapping(raw) or {}
            group = grouped[str(row["signal_state"])]
            group["total"] += 1
            symbol = str(row["symbol"])
            if full_market or symbol in visible:
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
        return {"contract_version": "ccc-radar-v1", "groups": list(grouped.values())}
