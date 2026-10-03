from __future__ import annotations

from ..models import FeedSpec

# Official CafeF RSS directory: https://cafef.vn/index.rss
CAFEF_FEEDS: tuple[FeedSpec, ...] = (
    FeedSpec("CafeF", "MARKET", "https://cafef.vn/thi-truong-chung-khoan.rss"),
    FeedSpec("CafeF", "BUSINESS", "https://cafef.vn/doanh-nghiep.rss"),
    FeedSpec("CafeF", "FINANCE_BANKING", "https://cafef.vn/tai-chinh-ngan-hang.rss"),
    FeedSpec("CafeF", "SMART_MONEY", "https://cafef.vn/smart-money.rss"),
)
