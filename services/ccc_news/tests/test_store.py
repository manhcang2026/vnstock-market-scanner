from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.ccc_news.models import NewsItem
from services.ccc_news.store import NewsStore


def _item(*, title: str = "HPG co tin moi", summary: str = "Tom tat") -> NewsItem:
    return NewsItem(
        source="CafeF",
        category="MARKET",
        feed_url="https://cafef.vn/thi-truong-chung-khoan.rss",
        title=title,
        summary=summary,
        url="https://cafef.vn/hpg-example.chn",
        published_at="2026-10-04T09:30:00+07:00",
        guid="cafef-1",
        image_url="https://img.example/hpg.jpg",
        image_origin="DESCRIPTION_HTML",
    )


class NewsStoreTests(unittest.TestCase):
    def test_first_write_inserts_and_second_identical_write_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ccc_news.db"
            with NewsStore(path) as store:
                first = store.upsert_many([_item()], fetched_at="2026-10-04T03:00:00+00:00")
                second = store.upsert_many([_item()], fetched_at="2026-10-04T04:00:00+00:00")

                self.assertEqual((first.inserted, first.updated, first.unchanged), (1, 0, 0))
                self.assertEqual((second.inserted, second.updated, second.unchanged), (0, 0, 1))
                self.assertEqual(store.count(), 1)
                [row] = store.latest(limit=5)
                self.assertEqual(row["first_fetched_at"], "2026-10-04T03:00:00+00:00")
                self.assertEqual(row["last_fetched_at"], "2026-10-04T04:00:00+00:00")

    def test_same_url_with_changed_content_updates_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ccc_news.db"
            with NewsStore(path) as store:
                store.upsert_many([_item()], fetched_at="2026-10-04T03:00:00+00:00")
                stats = store.upsert_many(
                    [_item(title="HPG cap nhat tin moi", summary="Tom tat da sua")],
                    fetched_at="2026-10-04T04:00:00+00:00",
                )

                self.assertEqual((stats.inserted, stats.updated, stats.unchanged), (0, 1, 0))
                self.assertEqual(store.count(), 1)
                [row] = store.latest(limit=5)
                self.assertEqual(row["title"], "HPG cap nhat tin moi")
                self.assertEqual(row["summary"], "Tom tat da sua")

    def test_store_is_persistent_across_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ccc_news.db"
            with NewsStore(path) as store:
                store.upsert_many([_item()])
            with NewsStore(path) as reopened:
                self.assertEqual(reopened.count(), 1)
                self.assertEqual(reopened.latest(limit=1)[0]["source"], "CafeF")


if __name__ == "__main__":
    unittest.main()
