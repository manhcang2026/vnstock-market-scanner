"""CCC News ingestion service.

News is an optional content layer and must remain isolated from canonical market data.
"""

from .models import FeedSpec, NewsItem

__all__ = ["FeedSpec", "NewsItem"]
