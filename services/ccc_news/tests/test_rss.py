from __future__ import annotations

import unittest

from services.ccc_news.models import FeedSpec
from services.ccc_news.rss import parse_feed


class RSSParserTests(unittest.TestCase):
    def test_cafef_style_description_extracts_text_and_image(self) -> None:
        spec = FeedSpec("CafeF", "MARKET", "https://example.test/cafef.rss")
        payload = b'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><item>
<title><![CDATA[HPG cong bo ket qua kinh doanh]]></title>
<link>https://cafef.vn/hpg-example.chn</link>
<guid>cafef-1</guid>
<description><![CDATA[<img src="https://img.example/hpg.jpg"/>Hoa Phat cong bo ket qua quy moi.]]></description>
<pubDate>Sat, 03 Oct 2026 10:30:00 +0700</pubDate>
</item></channel></rss>'''
        [item] = parse_feed(payload, spec)
        self.assertEqual(item.title, "HPG cong bo ket qua kinh doanh")
        self.assertEqual(item.summary, "Hoa Phat cong bo ket qua quy moi.")
        self.assertEqual(item.image_url, "https://img.example/hpg.jpg")
        self.assertEqual(item.image_origin, "DESCRIPTION_HTML")
        self.assertEqual(item.image_usage_status, "UNREVIEWED")
        self.assertEqual(item.published_at, "2026-10-03T10:30:00+07:00")

    def test_vietstock_media_thumbnail_is_discovered(self) -> None:
        spec = FeedSpec("Vietstock", "DIVIDEND", "https://example.test/vietstock.rss")
        payload = b'''<?xml version="1.0" encoding="utf-8"?>
<rss xmlns:media="http://search.yahoo.com/mrss/" version="2.0"><channel><item>
<title>Doanh nghiep chot quyen co tuc</title>
<link>https://vietstock.vn/example.htm</link>
<description>Thong tin co tuc moi nhat.</description>
<media:thumbnail url="https://img.example/dividend.jpg" />
<pubDate>Sat, 03 Oct 2026 08:15:00 +0700</pubDate>
</item></channel></rss>'''
        [item] = parse_feed(payload, spec)
        self.assertEqual(item.image_url, "https://img.example/dividend.jpg")
        self.assertEqual(item.image_origin, "RSS_MEDIA")
        self.assertEqual(item.summary, "Thong tin co tuc moi nhat.")

    def test_enclosure_image_is_supported(self) -> None:
        spec = FeedSpec("CafeF", "BUSINESS", "https://example.test/business.rss")
        payload = b'''<rss version="2.0"><channel><item>
<title>FPT co tin moi</title><link>https://example.test/fpt</link>
<description>Tom tat.</description>
<enclosure url="https://img.example/fpt.webp" type="image/webp" />
</item></channel></rss>'''
        [item] = parse_feed(payload, spec)
        self.assertEqual(item.image_origin, "RSS_ENCLOSURE")
        self.assertEqual(item.image_url, "https://img.example/fpt.webp")

    def test_item_without_title_or_outbound_link_is_dropped(self) -> None:
        spec = FeedSpec("CafeF", "MARKET", "https://example.test/invalid.rss")
        payload = b'''<rss version="2.0"><channel>
<item><title>Missing link</title></item>
<item><link>https://example.test/missing-title</link></item>
</channel></rss>'''
        self.assertEqual(parse_feed(payload, spec), [])

    def test_atom_link_and_iso_date_are_supported(self) -> None:
        spec = FeedSpec("Future", "MARKET", "https://example.test/atom.xml")
        payload = b'''<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom item</title><link href="https://example.test/atom-item"/>
<summary>Atom summary</summary><updated>2026-10-03T03:00:00Z</updated></entry>
</feed>'''
        [item] = parse_feed(payload, spec)
        self.assertEqual(item.url, "https://example.test/atom-item")
        self.assertEqual(item.published_at, "2026-10-03T03:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
