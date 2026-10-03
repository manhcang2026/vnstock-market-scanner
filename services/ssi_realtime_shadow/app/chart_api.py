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
from .canonical_market_reader import QUOTE_COLUMNS, CanonicalMarketReader
from .canonical_state_reader import CanonicalStateReader


def _bool_arg(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not SYMBOL_RE.fullmatch(normalized):
        raise ValueError("invalid symbol")
    return normalized


def _fetch_latest_quote(
    market_dir: Path, symbol: str, *, as_of_year: int | None = None
) -> dict | None:
    """Read the newest current/previous-year canonical quote."""
    symbol = _normalize_symbol(symbol)
    return CanonicalMarketReader(market_dir).latest_quote(
        symbol, as_of_year=as_of_year
    )


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
    def state_reader(self) -> CanonicalStateReader:
        return self.server.state_reader  # type: ignore[attr-defined]

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
                quote = _fetch_latest_quote(self.store.market_dir, symbol)
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
            except ValueError as exc:
                _response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"error": "INVALID_REQUEST", "message": str(exc)},
                )
                return
            try:
                payload = self.state_reader.public_stock_detail(symbol)
            except (sqlite3.Error, OSError, ValueError) as exc:
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
                payload = self.state_reader.ccc_intelligence(symbol)
            except (sqlite3.Error, OSError, ValueError) as exc:
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
                payload = self.state_reader.radar_projection(
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

        # Public scanner fields use public-only set-based reads. Resolve optional
        # technical scope once; failed authorization reads no protected state.
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
                payload = self.state_reader.scanner_projection(
                    visible_symbols=visible_symbols,
                    full_market=full_market,
                )
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
        canonical_market_dir: Path | None = None,
        canonical_engine_path: Path | None = None,
        state_reader: CanonicalStateReader | None = None,
    ):
        self.store = store
        self.access_client = access_client or SupabaseEntitlementClient()
        self.state_reader = state_reader or CanonicalStateReader(
            market_dir=canonical_market_dir
            or Path(os.getenv("CANONICAL_MARKET_DIR", "/app/data")),
            engine_path=canonical_engine_path
            or Path(os.getenv("CANONICAL_ENGINE_PATH", "/app/data/ccc_engine.db")),
        )
        super().__init__(address, handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CCC local chart-data HTTP API")
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
        "--canonical-market-dir",
        type=Path,
        default=Path(os.getenv("CANONICAL_MARKET_DIR", "/app/data")),
    )
    parser.add_argument(
        "--canonical-engine",
        type=Path,
        default=Path(os.getenv("CANONICAL_ENGINE_PATH", "/app/data/ccc_engine.db")),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ChartDataStore(args.canonical_market_dir)
    server = ChartHTTPServer(
        (args.host, args.port),
        ChartAPIHandler,
        store,
        SupabaseEntitlementClient(),
        args.canonical_market_dir,
        args.canonical_engine,
    )
    print(
        f"CCC Chart API listening on {args.host}:{args.port} "
        f"canonical_market_dir={args.canonical_market_dir}",
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
