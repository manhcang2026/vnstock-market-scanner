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

from .chart_data import ChartDataStore, SYMBOL_RE


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
    server_version = "CCCChartAPI/1.1"

    @property
    def store(self) -> ChartDataStore:
        return self.server.store  # type: ignore[attr-defined]

    def log_message(self, format: str, *args) -> None:
        super().log_message(format, *args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            _response(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "history_db": str(self.store.history_path),
                    "realtime_db": str(self.store.realtime_path),
                },
            )
            return

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

        prefix = "/v1/chart/"
        if not parsed.path.startswith(prefix):
            _response(self, HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
            return

        symbol = parsed.path[len(prefix) :].strip().upper()
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

    def __init__(self, address, handler, store: ChartDataStore):
        self.store = store
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ChartDataStore(args.history, args.realtime)
    server = ChartHTTPServer((args.host, args.port), ChartAPIHandler, store)
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
