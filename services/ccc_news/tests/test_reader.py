from __future__ import annotations

import sqlite3
from pathlib import Path

from services.ccc_news.reader import NewsReader, normalize_symbol


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
        connection.executemany(
            """
            INSERT INTO news_articles(
                id,source,category,title,summary,url,published_at,
                image_url,image_usage_status
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    1, "CafeF", "MARKET", "Fed giữ nguyên lãi suất",
                    "Tin thị trường chung.", "https://cafef.vn/fed.chn",
                    "2026-10-04T10:00:00+07:00",
                    "https://img.cafef.vn/fed.jpg", "UNREVIEWED",
                ),
                (
                    2, "CafeF", "BUSINESS", "Bóng đá Việt Nam",
                    "Broad business item.", "https://cafef.vn/football.chn",
                    "2026-10-04T09:59:00+07:00", None, "UNREVIEWED",
                ),
                (
                    3, "CafeF", "BUSINESS", "Hòa Phát mở rộng sản xuất",
                    "Doanh nghiệp niêm yết.", "https://cafef.vn/hpg.chn",
                    "2026-10-04T09:58:00+07:00",
                    "https://img.cafef.vn/hpg.jpg", "UNREVIEWED",
                ),
                (
                    4, "CafeF", "SMART_MONEY", "Cho bạn vay 105.000 USD",
                    "Personal finance story.", "https://cafef.vn/loan.chn",
                    "2026-10-04T09:57:00+07:00", None, "UNREVIEWED",
                ),
                (
                    5, "Vietstock", "DIVIDEND", "MWG chốt quyền cổ tức",
                    "Cổ tức MWG.", "https://vietstock.vn/mwg.htm",
                    "2026-10-04T09:56:00+07:00",
                    "https://static.vietstock.vn/mwg.jpg", "SOURCE_APPROVED",
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO news_article_symbols(article_id,symbol,match_type,matched_text)
            VALUES(?,?,?,?)
            """,
            [
                (3, "HPG", "NAME", "HOA PHAT"),
                (5, "MWG", "TICKER", "MWG"),
            ],
        )


def test_latest_keeps_relevant_and_drops_unmapped_broad_feeds(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    _make_db(db)

    items = NewsReader(db).latest(limit=20)

    assert [item["id"] for item in items] == [1, 3, 5]


def test_thumbnail_fallback_and_approved_source_image(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    _make_db(db)
    by_id = {item["id"]: item for item in NewsReader(db).latest(limit=20)}

    assert by_id[1]["thumbnail_mode"] == "CATEGORY"
    assert by_id[1]["thumbnail_url"] is None
    assert by_id[3]["thumbnail_mode"] == "SYMBOL"
    assert by_id[3]["thumbnail_symbol"] == "HPG"
    assert by_id[3]["thumbnail_url"] is None
    assert by_id[5]["thumbnail_mode"] == "SOURCE"
    assert by_id[5]["thumbnail_url"] == "https://static.vietstock.vn/mwg.jpg"


def test_symbol_feed_returns_only_requested_symbol(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    _make_db(db)

    items = NewsReader(db).for_symbol("hpg", limit=10)

    assert len(items) == 1
    assert items[0]["symbols"] == ["HPG"]
    assert items[0]["title"] == "Hòa Phát mở rộng sản xuất"


def test_missing_database_is_optional(tmp_path: Path) -> None:
    reader = NewsReader(tmp_path / "missing.db")
    assert reader.available is False
    assert reader.latest(limit=10) == []


def test_symbol_validation() -> None:
    assert normalize_symbol("hpg") == "HPG"
    try:
        normalize_symbol("A")
    except ValueError:
        pass
    else:
        raise AssertionError("short invalid symbol must be rejected")
