from __future__ import annotations

import http.client
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from services.ccc_news.api import NewsAPIHandler, NewsHTTPServer


SCHEMA = """
CREATE TABLE news_articles (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    published_at TEXT,
    image_url TEXT,
    image_usage_status TEXT NOT NULL
);
CREATE TABLE news_article_symbols (
    article_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    match_type TEXT NOT NULL,
    matched_text TEXT NOT NULL,
    PRIMARY KEY(article_id, symbol)
);
"""


def _make_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        connection.execute(
            """
            INSERT INTO news_articles VALUES(
                1,'CafeF','MARKET','HPG có tin mới','Tóm tắt ngắn',
                'https://cafef.vn/hpg.chn','2026-10-04T10:00:00+07:00',
                'https://img.cafef.vn/hpg.jpg','UNREVIEWED'
            )
            """
        )
        connection.execute(
            "INSERT INTO news_article_symbols VALUES(1,'HPG','TICKER','HPG')"
        )


@contextmanager
def _server(news_path: Path, *, enabled: bool = True):
    server = NewsHTTPServer(
        ("127.0.0.1", 0),
        NewsAPIHandler,
        news_path=news_path,
        news_enabled=enabled,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(server, path: str):
    connection = http.client.HTTPConnection(*server.server_address, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_public_latest_and_symbol_routes(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    _make_db(db)

    with _server(db) as server:
        latest_status, latest = _get(server, "/v1/news?limit=10")
        symbol_status, symbol = _get(server, "/v1/news/HPG?limit=10")

    assert latest_status == 200
    assert latest["contract_version"] == "ccc-news-v1"
    assert latest["available"] is True
    assert latest["count"] == 1
    assert latest["items"][0]["thumbnail_mode"] == "SYMBOL"
    assert symbol_status == 200
    assert symbol["symbol"] == "HPG"
    assert symbol["count"] == 1


def test_missing_database_fails_open(tmp_path: Path) -> None:
    with _server(tmp_path / "missing.db") as server:
        status, payload = _get(server, "/v1/news")

    assert status == 200
    assert payload["available"] is False
    assert payload["reason"] == "UNAVAILABLE"
    assert payload["items"] == []


def test_disabled_news_fails_open(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    _make_db(db)

    with _server(db, enabled=False) as server:
        status, payload = _get(server, "/v1/news/HPG")

    assert status == 200
    assert payload["available"] is False
    assert payload["reason"] == "DISABLED"
    assert payload["symbol"] == "HPG"


def test_health_is_private_probe_contract(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    _make_db(db)

    with _server(db) as server:
        status, payload = _get(server, "/health")

    assert status == 200
    assert payload["service"] == "ccc-news-api"
    assert payload["database_available"] is True


def test_invalid_request_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    _make_db(db)

    with _server(db) as server:
        symbol_status, symbol = _get(server, "/v1/news/A")
        limit_status, limit = _get(server, "/v1/news?limit=abc")

    assert symbol_status == 400
    assert symbol["error"] == "INVALID_REQUEST"
    assert limit_status == 400
    assert limit["error"] == "INVALID_REQUEST"
