from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import NewsItem
from .symbols import SymbolMatch

SCHEMA = """
CREATE TABLE IF NOT EXISTS news_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL UNIQUE,
    published_at TEXT,
    guid TEXT,
    image_url TEXT,
    image_origin TEXT,
    image_usage_status TEXT NOT NULL DEFAULT 'UNREVIEWED',
    content_hash TEXT NOT NULL,
    first_fetched_at TEXT NOT NULL,
    last_fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_articles_published
    ON news_articles(published_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_news_articles_source_published
    ON news_articles(source, published_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_news_articles_category_published
    ON news_articles(category, published_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS news_article_symbols (
    article_id INTEGER NOT NULL REFERENCES news_articles(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    match_type TEXT NOT NULL CHECK (match_type IN ('TICKER', 'NAME')),
    matched_text TEXT NOT NULL,
    PRIMARY KEY (article_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_news_article_symbols_symbol
    ON news_article_symbols(symbol, article_id);
"""


@dataclass(frozen=True, slots=True)
class StoreStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.unchanged


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _content_hash(item: NewsItem) -> str:
    # URL is deliberately excluded. If a provider fixes its outbound URL while
    # leaving the article content unchanged, the content comparison stays stable.
    raw = "\x1f".join(
        (
            _clean(item.source),
            _clean(item.category),
            _clean(item.title),
            _clean(item.summary),
            _clean(item.published_at),
            _clean(item.guid),
            _clean(item.image_url),
            _clean(item.image_origin),
            _clean(item.image_usage_status),
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class NewsStore:
    """Small isolated SQLite store for optional CCC news content."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "NewsStore":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def upsert_many(
        self,
        items: list[NewsItem],
        *,
        fetched_at: str | None = None,
    ) -> StoreStats:
        now = fetched_at or _now_iso()
        inserted = updated = unchanged = 0

        with self._conn:
            for item in items:
                url = _clean(item.url)
                if not url:
                    continue
                content_hash = _content_hash(item)
                row = self._conn.execute(
                    "SELECT id, content_hash FROM news_articles WHERE url = ?",
                    (url,),
                ).fetchone()

                if row is None:
                    self._conn.execute(
                        """
                        INSERT INTO news_articles (
                            source, category, feed_url, title, summary, url,
                            published_at, guid, image_url, image_origin,
                            image_usage_status, content_hash,
                            first_fetched_at, last_fetched_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            _clean(item.source),
                            _clean(item.category),
                            _clean(item.feed_url),
                            _clean(item.title),
                            _clean(item.summary),
                            url,
                            item.published_at,
                            item.guid,
                            item.image_url,
                            item.image_origin,
                            _clean(item.image_usage_status) or "UNREVIEWED",
                            content_hash,
                            now,
                            now,
                            now,
                            now,
                        ),
                    )
                    inserted += 1
                    continue

                if row["content_hash"] == content_hash:
                    self._conn.execute(
                        "UPDATE news_articles SET last_fetched_at = ? WHERE id = ?",
                        (now, row["id"]),
                    )
                    unchanged += 1
                    continue

                self._conn.execute(
                    """
                    UPDATE news_articles
                    SET source = ?, category = ?, feed_url = ?, title = ?, summary = ?,
                        published_at = ?, guid = ?, image_url = ?, image_origin = ?,
                        image_usage_status = ?, content_hash = ?,
                        last_fetched_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        _clean(item.source),
                        _clean(item.category),
                        _clean(item.feed_url),
                        _clean(item.title),
                        _clean(item.summary),
                        item.published_at,
                        item.guid,
                        item.image_url,
                        item.image_origin,
                        _clean(item.image_usage_status) or "UNREVIEWED",
                        content_hash,
                        now,
                        now,
                        row["id"],
                    ),
                )
                updated += 1

        return StoreStats(inserted=inserted, updated=updated, unchanged=unchanged)

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS count FROM news_articles").fetchone()
        return int(row["count"])

    def replace_symbols_for_url(self, url: str, matches: list[SymbolMatch]) -> int:
        row = self._conn.execute(
            "SELECT id FROM news_articles WHERE url = ?",
            (_clean(url),),
        ).fetchone()
        if row is None:
            return 0
        article_id = int(row["id"])
        unique = {match.symbol: match for match in matches}
        with self._conn:
            self._conn.execute(
                "DELETE FROM news_article_symbols WHERE article_id = ?",
                (article_id,),
            )
            self._conn.executemany(
                """
                INSERT INTO news_article_symbols (article_id, symbol, match_type, matched_text)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (article_id, match.symbol, match.match_type, match.matched_text)
                    for match in sorted(unique.values(), key=lambda item: item.symbol)
                ],
            )
        return len(unique)

    def for_symbol(self, symbol: str, *, limit: int = 20) -> list[dict[str, object]]:
        rows = self._conn.execute(
            """
            SELECT a.id, a.source, a.category, a.title, a.summary, a.url,
                   a.published_at, a.image_url, a.image_origin,
                   a.image_usage_status, s.match_type, s.matched_text
            FROM news_article_symbols s
            JOIN news_articles a ON a.id = s.article_id
            WHERE s.symbol = ?
            ORDER BY a.published_at DESC, a.id DESC
            LIMIT ?
            """,
            (_clean(symbol).upper(), max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def latest(self, *, limit: int = 20) -> list[dict[str, object]]:
        rows = self._conn.execute(
            """
            SELECT id, source, category, title, summary, url, published_at,
                   image_url, image_origin, image_usage_status,
                   first_fetched_at, last_fetched_at
            FROM news_articles
            ORDER BY published_at DESC, id DESC
            LIMIT ?
            """,
            (max(0, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]
