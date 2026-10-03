from __future__ import annotations

from ..models import FeedSpec

# Official Vietnamese Vietstock RSS directory: https://vietstock.vn/rss
VIETSTOCK_FEEDS: tuple[FeedSpec, ...] = (
    FeedSpec("Vietstock", "STOCKS", "https://vietstock.vn/830/chung-khoan/co-phieu.rss"),
    FeedSpec(
        "Vietstock",
        "INSIDER_TRADING",
        "https://vietstock.vn/739/chung-khoan/giao-dich-noi-bo.rss",
    ),
    FeedSpec("Vietstock", "LISTING", "https://vietstock.vn/741/chung-khoan/niem-yet.rss"),
    FeedSpec(
        "Vietstock",
        "BUSINESS",
        "https://vietstock.vn/737/doanh-nghiep/hoat-dong-kinh-doanh.rss",
    ),
    FeedSpec("Vietstock", "DIVIDEND", "https://vietstock.vn/738/doanh-nghiep/co-tuc.rss"),
    FeedSpec("Vietstock", "CAPITAL_MA", "https://vietstock.vn/764/doanh-nghiep/tang-von-m-a.rss"),
)
