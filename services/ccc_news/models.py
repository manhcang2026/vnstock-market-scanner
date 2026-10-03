from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class FeedSpec:
    source: str
    category: str
    url: str


@dataclass(frozen=True, slots=True)
class NewsItem:
    source: str
    category: str
    feed_url: str
    title: str
    summary: str
    url: str
    published_at: str | None
    guid: str | None
    image_url: str | None
    image_origin: str | None
    # Discovery and usage permission are intentionally separate. An image URL
    # present in RSS must not silently become approved for frontend reuse.
    image_usage_status: str = "UNREVIEWED"

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)
