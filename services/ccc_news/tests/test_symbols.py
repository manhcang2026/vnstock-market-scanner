from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.ccc_news.models import NewsItem
from services.ccc_news.symbols import StockIdentity, SymbolMapper, load_stock_identities


def _item(title: str, summary: str = "", category: str = "MARKET") -> NewsItem:
    return NewsItem(
        source="CafeF",
        category=category,
        feed_url="https://feed.test/rss",
        title=title,
        summary=summary,
        url="https://news.test/item",
        published_at="2026-10-04T09:30:00+07:00",
        guid=None,
        image_url=None,
        image_origin=None,
    )


class SymbolMapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapper = SymbolMapper(
            [
                StockIdentity("HPG", "HOSE", "CTCP Tập đoàn Hòa Phát"),
                StockIdentity("PNJ", "HOSE", "CTCP Vàng bạc Đá quý Phú Nhuận"),
                StockIdentity("MWG", "HOSE", "CTCP Đầu tư Thế Giới Di Động"),
                StockIdentity("SHS", "HNX", "CTCP Chứng khoán Sài Gòn - Hà Nội"),
                StockIdentity("HDB", "HOSE", "Ngân hàng TMCP Phát triển Thành phố Hồ Chí Minh"),
                StockIdentity("DGW", "HOSE", "CTCP Thế Giới Số"),
                StockIdentity("CEO", "HNX", "CTCP Tập đoàn C.E.O"),
                StockIdentity("VUA", "UPCOM", "CTCP Vua Việt Nam"),
                StockIdentity("TRA", "HOSE", "CTCP Traphaco"),
            ]
        )

    def test_company_name_maps_without_ticker(self) -> None:
        matches = self.mapper.match(_item("Hòa Phát công bố kế hoạch kinh doanh mới", category="BUSINESS"))
        self.assertEqual([(m.symbol, m.match_type) for m in matches], [("HPG", "NAME")])

    def test_market_ticker_list_maps_when_stock_context_is_present(self) -> None:
        matches = self.mapper.match(_item('Lịch chốt quyền cổ tức: MWG, SHS, HDB, DGW đồng loạt "lăn chốt"'))
        self.assertEqual([m.symbol for m in matches], ["DGW", "HDB", "MWG", "SHS"])

    def test_generic_ceo_word_does_not_map_ceo_ticker_in_banking_story(self) -> None:
        matches = self.mapper.match(_item("CEO Techcombank: Cuộc đua AI không nằm ở công nghệ", category="FINANCE_BANKING"))
        self.assertEqual(matches, [])

    def test_vietnamese_vua_word_does_not_turn_into_vua_ticker(self) -> None:
        matches = self.mapper.match(
            _item("PNJ nêu lý do khiến cổ phiếu giảm sàn", "Giá cổ phiếu trong giai đoạn vừa qua biến động mạnh.")
        )
        self.assertEqual([m.symbol for m in matches], ["PNJ"])

    def test_vietnamese_tra_word_does_not_turn_into_tra_ticker(self) -> None:
        matches = self.mapper.match(
            _item("Lịch chốt quyền cổ tức: MWG", "Doanh nghiệp trả cổ tức bằng tiền mặt.")
        )
        self.assertEqual([m.symbol for m in matches], ["MWG"])

    def test_generic_uppercase_ceo_is_blocked_even_with_market_context(self) -> None:
        matches = self.mapper.match(
            _item("CEO Techcombank nói về cổ phiếu ngân hàng")
        )
        self.assertEqual(matches, [])

    def test_ticker_without_market_context_is_not_guessed(self) -> None:
        matches = self.mapper.match(_item("PNJ tổ chức một hoạt động cộng đồng", category="BUSINESS"))
        self.assertEqual(matches, [])

    def test_utf8_bom_watchlist_csv_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watchlist.csv"
            path.write_text(
                "\ufeffsymbol,exchange,organ_name,en_organ_name,type,id\n"
                "HPG,HOSE,CTCP Tập đoàn Hòa Phát,Hoa Phat Group,STOCK,1\n",
                encoding="utf-8",
            )
            [identity] = load_stock_identities(path)
            self.assertEqual(identity.symbol, "HPG")
            self.assertEqual(identity.organ_name, "CTCP Tập đoàn Hòa Phát")

    def test_ambiguous_name_alias_is_discarded(self) -> None:
        mapper = SymbolMapper(
            [
                StockIdentity("AAA", "HOSE", "CTCP Tập đoàn Mặt Trời"),
                StockIdentity("BBB", "HNX", "CTCP Mặt Trời"),
            ]
        )
        self.assertEqual(mapper.match(_item("Mặt Trời công bố kế hoạch mới", category="BUSINESS")), [])


if __name__ == "__main__":
    unittest.main()
