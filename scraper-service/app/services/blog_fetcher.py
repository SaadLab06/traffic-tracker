from datetime import datetime
from typing import Optional
import feedparser

COMMON_FEED_PATHS = [
    "/feed", "/rss", "/atom.xml", "/feed/", "/rss.xml",
    "/blog/feed", "/blog/rss", "/news/feed",
    "/feed.xml", "/blog/feed/", "/actualites/feed",
]

async def get_post_dates_from_feed(base_url: str) -> Optional[list[datetime]]:
    base = base_url.rstrip("/")
    for path in COMMON_FEED_PATHS:
        feed = feedparser.parse(base + path)
        if feed.entries and len(feed.entries) >= 3:
            dates = [
                datetime(*e.published_parsed[:6])
                for e in feed.entries
                if getattr(e, "published_parsed", None)
            ]
            if len(dates) >= 3:
                return dates
    return None
