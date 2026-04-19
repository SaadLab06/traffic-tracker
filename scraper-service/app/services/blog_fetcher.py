from datetime import datetime
from typing import Optional
import re
import feedparser
from lxml import etree
from app.utils.http import fetch_with_retry

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


BLOG_URL_PATTERN = re.compile(r"/(blog|article|actualites|news|magazine)/", re.IGNORECASE)

async def get_post_dates_from_sitemap(base_url: str) -> Optional[list[datetime]]:
    base = base_url.rstrip("/")
    candidates = ["/sitemap.xml", "/sitemap_index.xml", "/blog-sitemap.xml", "/news-sitemap.xml"]
    for path in candidates:
        text = await fetch_with_retry(base + path)
        if not text:
            continue
        try:
            root = etree.fromstring(text.encode("utf-8"))
        except etree.XMLSyntaxError:
            continue
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        dates: list[datetime] = []
        for url in root.findall(".//s:url", ns):
            loc = (url.findtext("s:loc", namespaces=ns) or "")
            lastmod = url.findtext("s:lastmod", namespaces=ns)
            if lastmod and BLOG_URL_PATTERN.search(loc):
                try:
                    dates.append(datetime.fromisoformat(lastmod.replace("Z", "+00:00").split("T")[0]))
                except ValueError:
                    continue
        if len(dates) >= 3:
            return dates
    return None
