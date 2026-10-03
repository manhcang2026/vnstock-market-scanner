from __future__ import annotations

import unittest

from services.ccc_news.collector import collect
from services.ccc_news.models import FeedSpec, NewsItem


class CollectorTests(unittest.TestCase):
    def test_one_feed_failure_is_fail_open_and_urls_are_deduped(self) -> None:
        feeds = (
            FeedSpec("CafeF", "MARKET", "https://feed.test/a"),
            FeedSpec("Vietstock", "STOCKS", "https://feed.test/b"),
        )

        duplicate = NewsItem(
            source="CafeF",
            category="MARKET",
            feed_url=feeds[0].url,
            title="Same",
            summary="Summary",
            url="https://news.test/same",
            published_at="2026-10-03T10:00:00+07:00",
            guid="1",
            image_url=None,
            image_origin=None,
        )

        def fake_fetch(spec: FeedSpec, *, timeout: float):
            if spec.source == "Vietstock":
                raise TimeoutError("test timeout")
            return [duplicate, duplicate]

        items, errors = collect(feeds, fetcher=fake_fetch)
        self.assertEqual(len(items), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("Vietstock/STOCKS", errors[0])


if __name__ == "__main__":
    unittest.main()
