from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,12}$")

APPROVED_SOURCE_IMAGE_STATUSES = frozenset(
    {"SOURCE_APPROVED", "CCC_APPROVED", "APPROVED"}
)

# Broad lifestyle/business feeds are stored for optional future use, but they
# do not enter Overview unless deterministic symbol mapping proves relevance.
OVERVIEW_ALWAYS_CATEGORIES = frozenset(
    {
        "MARKET",
        "STOCKS",
        "INSIDER_TRADING",
        "LISTING",
        "DIVIDEND",
        "CAPITAL_MA",
        "FINANCE_BANKING",
    }
)


def normalize_symbol(value: str) -> str:
    symbol = str(value or "").strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError("invalid symbol")
    return symbol


def _safe_source_image(url: object, status: object) -> str | None:
    raw = str(url or "").strip()
    approved = str(status or "").strip().upper()
    if not raw or approved not in APPROVED_SOURCE_IMAGE_STATUSES:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return raw


def _public_article(row: sqlite3.Row, symbols: list[str]) -> dict[str, object]:
    source_image = _safe_source_image(row["image_url"], row["image_usage_status"])
    if source_image:
        thumbnail_mode = "SOURCE"
        thumbnail_url = source_image
        thumbnail_symbol = symbols[0] if symbols else None
    elif symbols:
        thumbnail_mode = "SYMBOL"
        thumbnail_url = None
        thumbnail_symbol = symbols[0]
    else:
        thumbnail_mode = "CATEGORY"
        thumbnail_url = None
        thumbnail_symbol = None

    return {
        "id": int(row["id"]),
        "source": row["source"],
        "category": row["category"],
        "title": row["title"],
        "summary": row["summary"],
        "url": row["url"],
        "published_at": row["published_at"],
        "symbols": symbols,
        "thumbnail_mode": thumbnail_mode,
        "thumbnail_url": thumbnail_url,
        "thumbnail_symbol": thumbnail_symbol,
        "thumbnail_category": row["category"],
    }


class NewsReader:
    """Read-only public projection of the isolated CCC news database."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    @property
    def available(self) -> bool:
        return self.path.is_file()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self.path}?mode=ro",
            uri=True,
            timeout=5,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @staticmethod
    def _bounded_limit(limit: int) -> int:
        return max(1, min(50, int(limit)))

    @staticmethod
    def _symbols_by_article(
        connection: sqlite3.Connection, article_ids: list[int]
    ) -> dict[int, list[str]]:
        if not article_ids:
            return {}
        placeholders = ",".join("?" for _ in article_ids)
        rows = connection.execute(
            f"""
            SELECT article_id, symbol
            FROM news_article_symbols
            WHERE article_id IN ({placeholders})
            ORDER BY article_id, symbol
            """,
            article_ids,
        ).fetchall()
        result: dict[int, list[str]] = defaultdict(list)
        for row in rows:
            result[int(row["article_id"])].append(str(row["symbol"]))
        return dict(result)

    def _project(
        self,
        connection: sqlite3.Connection,
        rows: list[sqlite3.Row],
    ) -> list[dict[str, object]]:
        article_ids = [int(row["id"]) for row in rows]
        symbol_map = self._symbols_by_article(connection, article_ids)
        return [
            _public_article(row, symbol_map.get(int(row["id"]), []))
            for row in rows
        ]

    def latest(self, *, limit: int = 20) -> list[dict[str, object]]:
        if not self.available:
            return []
        placeholders = ",".join("?" for _ in OVERVIEW_ALWAYS_CATEGORIES)
        categories = tuple(sorted(OVERVIEW_ALWAYS_CATEGORIES))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT a.id, a.source, a.category, a.title, a.summary, a.url,
                       a.published_at, a.image_url, a.image_usage_status
                FROM news_articles a
                WHERE a.category IN ({placeholders})
                   OR EXISTS (
                       SELECT 1
                       FROM news_article_symbols s
                       WHERE s.article_id = a.id
                   )
                ORDER BY a.published_at DESC, a.id DESC
                LIMIT ?
                """,
                (*categories, self._bounded_limit(limit)),
            ).fetchall()
            return self._project(connection, rows)

    def for_symbol(
        self, symbol: str, *, limit: int = 20
    ) -> list[dict[str, object]]:
        normalized = normalize_symbol(symbol)
        if not self.available:
            return []
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT a.id, a.source, a.category, a.title, a.summary, a.url,
                       a.published_at, a.image_url, a.image_usage_status
                FROM news_article_symbols requested
                JOIN news_articles a ON a.id = requested.article_id
                WHERE requested.symbol = ?
                ORDER BY a.published_at DESC, a.id DESC
                LIMIT ?
                """,
                (normalized, self._bounded_limit(limit)),
            ).fetchall()
            return self._project(connection, rows)
