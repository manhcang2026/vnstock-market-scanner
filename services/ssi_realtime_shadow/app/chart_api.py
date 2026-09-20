from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .access_control import (
    AuthenticationRequired,
    EntitlementServiceUnavailable,
    SupabaseEntitlementClient,
    TechnicalAccessDecision,
    extract_bearer_token,
)
from .chart_data import ChartDataStore, SYMBOL_RE
from .state_contract import (
    build_radar_projection,
    build_scanner_projection,
    get_ccc_intelligence,
    get_public_stock_detail,
)


QUOTE_COLUMNS = (
    "symbol",
    "trading_date",
    "event_time",
    "last_price",
    "total_volume",
    "ref_price",
    "open",
    "high",
    "low",
    "close",
    "bid_price1",
    "bid_vol1",
    "ask_price1",
    "ask_vol1",
    "change",
    "ratio_change",
    "exchange",
    "trading_session",
    "trading_status",
    "updated_at",
)


def _bool_arg(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not SYMBOL_RE.fullmatch(normalized):
        raise ValueError("invalid symbol")
    return normalized


def _fetch_latest_quote(path: Path, symbol: str) -> dict | None:
    """Read one current quote from the realtime SQLite DB in read-only mode."""
    symbol = _normalize_symbol(symbol)
    if not path.exists():
        return None

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        row = conn.execute(
            f"SELECT {', '.join(QUOTE_COLUMNS)} FROM latest_quotes WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if row is None:
            return None
        payload = {column: row[column] for column in QUOTE_COLUMNS}
        payload["source"] = "SSI_STREAM"
        return payload
    finally:
        conn.close()


def _response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


class ChartAPIHandler(BaseHTTPRequestHandler):
    server_version = "CCCChartAPI/1.3"

    @property
    def store(self) -> ChartDataStore:
        return self.server.store  # type: ignore[attr-defined]

    @property
    def access_client(self) -> SupabaseEntitlementClient:
        return self.server.access_client  # type: ignore[attr-defined]

    @property
    def state_path(self) -> Path:
        return self.server.state_path  # type: ignore[attr-defined]

    def _state_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self.state_path.resolve()}?mode=ro", uri=True, timeout=5
        )
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def log_message(self, format: str, *args) -> None:
        # Standard access log only; Authorization header is never logged here.
        super().log_message(format, *args)

    def _technical_access(
        self, symbol: str
    ) -> tuple[TechnicalAccessDecision | None, bool]:
        token = extract_bearer_token(self.headers.get("Authorization"))
        if token is None:
            _response(
                self,
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "AUTH_REQUIRED",
                    "message": "Authenticated Supabase session required.",
                },
            )
            return None, False

        try:
            decision = self.access_client.check(token=token, symbol=symbol)
        except AuthenticationRequired:
            _response(
                self,
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "INVALID_OR_EXPIRED_SESSION",
                    "message": "Please sign in again.",
                },
            )
            return None, False
        except EntitlementServiceUnavailable:
            # Fail closed: protected data is not returned if entitlement authority fails.
            _response(
                self,
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "ENTITLEMENT_UNAVAILABLE",
                    "message": "Technical access could not be verified.",
                },
            )
            return None, False

        return decision, True

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        # Private-network health endpoint. Nginx must not rewrite a public URL here.
        if parsed.path == "/health":
            _response(
                self,
                HTTPStatus.OK,
                {"ok": True, "service": "ccc-chart-api"},
            )
            return

        # Public Market Quote: intentionally public by product contract.
        quote_prefix = "/v1/quote/"
        if parsed.path.startswith(quote_prefix):
            try:
                symbol = _normalize_symbol(parsed.path[len(quote_prefix) :])
                quote = _fetch_latest_quote(self.store.realtime_path, symbol)
            except ValueError as exc:
                _response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"error": "INVALID_REQUEST", "message": str(exc)},
                )
                return
            except (sqlite3.Error, OSError) as exc:
                _response(
                    self,
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "INTERNAL_ERROR", "message": type(exc).__name__},
                )
                return

            if quote is None:
                _response(
                    self,
                    HTTPStatus.NOT_FOUND,
                    {"error": "QUOTE_NOT_FOUND", "symbol": symbol},
                )
                return

            _response(self, HTTPStatus.OK, quote)
            return

        # Authenticated entitlement introspection for Stock Detail locked/unlocked state.
        access_prefix = "/v1/access/"
        if parsed.path.startswith(access_prefix):
            try:
                symbol = _normalize_symbol(parsed.path[len(access_prefix) :])
            except ValueError as exc:
                _response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"error": "INVALID_REQUEST", "message": str(exc)},
                )
                return

            decision, authenticated = self._technical_access(symbol)
            if not authenticated or decision is None:
                return

            _response(self, HTTPStatus.OK, decision.to_public_payload())
            return

        # Anonymous Stock Detail context: explicit public fields only.
        public_detail_prefix = "/v1/stock-detail/"
        if parsed.path.startswith(public_detail_prefix):
            try:
                symbol = _normalize_symbol(parsed.path[len(public_detail_prefix) :])
                with self._state_connection() as connection:
                    payload = get_public_stock_detail(connection, symbol)
            except ValueError as exc:
                _response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"error": "INVALID_REQUEST", "message": str(exc)},
                )
                return
            except (sqlite3.Error, OSError) as exc:
                _response(
                    self,
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "STATE_UNAVAILABLE", "message": type(exc).__name__},
                )
                return
            if payload is None:
                _response(
                    self,
                    HTTPStatus.NOT_FOUND,
                    {"error": "STATE_NOT_FOUND", "symbol": symbol},
                )
                return
            _response(self, HTTPStatus.OK, payload)
            return

        # Proprietary current-state projection: authorize before reading/returning.
        ccc_prefix = "/v1/ccc/"
        if parsed.path.startswith(ccc_prefix):
            try:
                symbol = _normalize_symbol(parsed.path[len(ccc_prefix) :])
            except ValueError as exc:
                _response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"error": "INVALID_REQUEST", "message": str(exc)},
                )
                return
            decision, authenticated = self._technical_access(symbol)
            if not authenticated or decision is None:
                return
            if not decision.technical_allowed:
                _response(
                    self,
                    HTTPStatus.FORBIDDEN,
                    {
                        "error": "CCC_ACCESS_DENIED",
                        "symbol": symbol,
                        "reason": decision.reason,
                    },
                )
                return
            try:
                with self._state_connection() as connection:
                    payload = get_ccc_intelligence(connection, symbol)
            except (sqlite3.Error, OSError) as exc:
                _response(
                    self,
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "STATE_UNAVAILABLE", "message": type(exc).__name__},
                )
                return
            if payload is None:
                _response(
                    self,
                    HTTPStatus.NOT_FOUND,
                    {"error": "STATE_NOT_FOUND", "symbol": symbol},
                )
                return
            _response(self, HTTPStatus.OK, payload)
            return

        # Radar counts are public. Identities are added only after one
        # server-side scope resolution; anonymous or failed scope checks receive
        # aggregate counts with every identity omitted.
        if parsed.path == "/v1/radar":
            visible_symbols: set[str] = set()
            full_market = False
            identity_scope = "ANONYMOUS"
            token = extract_bearer_token(self.headers.get("Authorization"))
            if token:
                try:
                    scope = self.access_client.scope(token=token)
                    visible_symbols = set(scope.allowed_symbols)
                    full_market = scope.effective_full_market_access
                    identity_scope = "FULL_MARKET" if full_market else "WATCHLIST"
                except (AuthenticationRequired, EntitlementServiceUnavailable):
                    identity_scope = "UNAVAILABLE"
            try:
                with self._state_connection() as connection:
                    payload = build_radar_projection(
                        connection,
                        visible_symbols=visible_symbols,
                        full_market=full_market,
                    )
            except (sqlite3.Error, OSError) as exc:
                _response(
                    self,
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "STATE_UNAVAILABLE", "message": type(exc).__name__},
                )
                return
            payload["identity_scope"] = identity_scope
            _response(self, HTTPStatus.OK, payload)
            return

        # Public scanner fields come from one read-only current-state query.
        # Resolve optional technical scope once; failed authorization enriches nothing.
        if parsed.path == "/v1/scanner":
            visible_symbols: set[str] = set()
            full_market = False
            technical_scope = "ANONYMOUS"
            authorization = self.headers.get("Authorization")
            if authorization is not None:
                token = extract_bearer_token(authorization)
                if token is None:
                    technical_scope = "UNAVAILABLE"
                else:
                    try:
                        scope = self.access_client.scope(token=token)
                        visible_symbols = set(scope.allowed_symbols)
                        full_market = scope.effective_full_market_access
                        technical_scope = "FULL_MARKET" if full_market else "WATCHLIST"
                    except (AuthenticationRequired, EntitlementServiceUnavailable):
                        technical_scope = "UNAVAILABLE"
            try:
                connection = self._state_connection()
                try:
                    payload = build_scanner_projection(
                        connection,
                        visible_symbols=visible_symbols,
                        full_market=full_market,
                    )
                finally:
                    connection.close()
            except (sqlite3.Error, OSError, ValueError) as exc:
                _response(
                    self,
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "STATE_UNAVAILABLE", "message": type(exc).__name__},
                )
                return
            payload["technical_scope"] = technical_scope
            _response(self, HTTPStatus.OK, payload)
            return

        # Price/volume history contains market bars only and is public.
        chart_prefix = "/v1/chart/"
        if not parsed.path.startswith(chart_prefix):
            _response(self, HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
            return

        try:
            symbol = _normalize_symbol(parsed.path[len(chart_prefix) :])
        except ValueError as exc:
            _response(
                self,
                HTTPStatus.BAD_REQUEST,
                {"error": "INVALID_REQUEST", "message": str(exc)},
            )
            return

        query = parse_qs(parsed.query)
        today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
        date_from = query.get("from", [today])[0]
        date_to = query.get("to", [today])[0]

        try:
            resolution = int(query.get("resolution", ["1"])[0])
            include_invalid = _bool_arg(query.get("include_invalid", ["0"])[0])
            result = self.store.query(
                symbol=symbol,
                date_from=date_from,
                date_to=date_to,
                resolution=resolution,
                include_invalid=include_invalid,
            )
        except (ValueError, TypeError) as exc:
            _response(
                self,
                HTTPStatus.BAD_REQUEST,
                {"error": "INVALID_REQUEST", "message": str(exc)},
            )
            return
        except Exception as exc:
            _response(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "INTERNAL_ERROR", "message": type(exc).__name__},
            )
            return

        payload = {
            "symbol": result.symbol,
            "from": result.date_from,
            "to": result.date_to,
            "resolution": result.resolution,
            "count": len(result.bars),
            "invalid_ohlc_dropped": result.invalid_ohlc_dropped,
            "source_counts": result.source_counts,
            "bars": [asdict(bar) for bar in result.bars],
        }
        _response(self, HTTPStatus.OK, payload)


class ChartHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address,
        handler,
        store: ChartDataStore,
        access_client: SupabaseEntitlementClient | None = None,
        state_path: Path | None = None,
    ):
        self.store = store
        self.access_client = access_client or SupabaseEntitlementClient()
        self.state_path = Path(
            state_path or os.getenv("MARKET_V2_DATABASE_PATH", "/app/data/ccc_market_v2.db")
        )
        super().__init__(address, handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CCC local chart-data HTTP API")
    parser.add_argument(
        "--history",
        type=Path,
        default=Path(os.getenv("CHART_HISTORY_PATH", "/app/data/ssi_history_2026.db")),
    )
    parser.add_argument(
        "--realtime",
        type=Path,
        default=Path(os.getenv("CHART_REALTIME_PATH", "/app/data/ssi_shadow.db")),
    )
    parser.add_argument(
        "--host",
        default=os.getenv("CHART_API_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("CHART_API_PORT", "8787")),
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=Path(
            os.getenv("MARKET_V2_DATABASE_PATH", "/app/data/ccc_market_v2.db")
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ChartDataStore(args.history, args.realtime)
    server = ChartHTTPServer(
        (args.host, args.port),
        ChartAPIHandler,
        store,
        SupabaseEntitlementClient(),
        args.state,
    )
    print(
        f"CCC Chart API listening on {args.host}:{args.port} "
        f"history={args.history} realtime={args.realtime}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
