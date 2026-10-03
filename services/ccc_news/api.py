from __future__ import annotations

import argparse
import json
import os
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .reader import NewsReader, normalize_symbol


TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _bool_value(value: object, *, default: bool = True) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError("invalid boolean value")


def _limit(query: dict[str, list[str]]) -> int:
    raw = query.get("limit", ["20"])[0]
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid news limit") from exc
    return max(1, min(50, value))


def _response(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: dict[str, object],
    *,
    cache_control: str = "public, max-age=60",
) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", cache_control)
    handler.end_headers()
    handler.wfile.write(body)


class NewsAPIHandler(BaseHTTPRequestHandler):
    server_version = "CCCNewsAPI/1.0"

    @property
    def reader(self) -> NewsReader:
        return self.server.reader  # type: ignore[attr-defined]

    @property
    def enabled(self) -> bool:
        return self.server.news_enabled  # type: ignore[attr-defined]

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
                    "service": "ccc-news-api",
                    "enabled": self.enabled,
                    "database_available": self.reader.available,
                },
                cache_control="no-store",
            )
            return

        if parsed.path != "/v1/news" and not parsed.path.startswith("/v1/news/"):
            _response(
                self,
                HTTPStatus.NOT_FOUND,
                {"error": "NOT_FOUND"},
                cache_control="no-store",
            )
            return

        symbol: str | None = None
        if parsed.path != "/v1/news":
            try:
                symbol = normalize_symbol(parsed.path[len("/v1/news/") :])
            except ValueError as exc:
                _response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"error": "INVALID_REQUEST", "message": str(exc)},
                    cache_control="no-store",
                )
                return

        try:
            limit = _limit(parse_qs(parsed.query))
        except ValueError as exc:
            _response(
                self,
                HTTPStatus.BAD_REQUEST,
                {"error": "INVALID_REQUEST", "message": str(exc)},
                cache_control="no-store",
            )
            return

        payload: dict[str, object] = {
            "contract_version": "ccc-news-v1",
            "available": False,
            "count": 0,
            "items": [],
        }
        if symbol is not None:
            payload["symbol"] = symbol

        if not self.enabled:
            payload["reason"] = "DISABLED"
            _response(self, HTTPStatus.OK, payload, cache_control="no-store")
            return

        if not self.reader.available:
            payload["reason"] = "UNAVAILABLE"
            _response(self, HTTPStatus.OK, payload, cache_control="no-store")
            return

        try:
            items = (
                self.reader.for_symbol(symbol, limit=limit)
                if symbol is not None
                else self.reader.latest(limit=limit)
            )
        except (sqlite3.Error, OSError, ValueError):
            payload["reason"] = "UNAVAILABLE"
            _response(self, HTTPStatus.OK, payload, cache_control="no-store")
            return

        payload["available"] = True
        payload["count"] = len(items)
        payload["items"] = items
        _response(self, HTTPStatus.OK, payload)


class NewsHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address,
        handler=NewsAPIHandler,
        *,
        news_path: Path | str,
        news_enabled: bool = True,
    ) -> None:
        self.reader = NewsReader(news_path)
        self.news_enabled = bool(news_enabled)
        super().__init__(address, handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CCC standalone public news API")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.getenv("NEWS_DB_PATH", "/opt/ccc-news/data/ccc_news.db")),
    )
    parser.add_argument(
        "--host",
        default=os.getenv("NEWS_API_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("NEWS_API_PORT", "8795")),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        enabled = _bool_value(os.getenv("NEWS_ENABLED", "true"))
    except ValueError as exc:
        raise SystemExit(f"Invalid NEWS_ENABLED: {exc}") from exc

    server = NewsHTTPServer(
        (args.host, args.port),
        news_path=args.db,
        news_enabled=enabled,
    )
    print(
        f"CCC News API listening on {args.host}:{args.port} "
        f"db={args.db} enabled={enabled}",
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
