import asyncio
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

# Wall-clock cap for the whole cascade per URL; prevents one slow site from stalling the batch
PER_URL_TIMEOUT_S = 25.0


def _extract_feed_dates(content: str) -> Optional[list[datetime]]:
    feed = feedparser.parse(content)
    if not feed.entries or len(feed.entries) < 3:
        return None
    dates = [
        datetime(*e.published_parsed[:6])
        for e in feed.entries
        if getattr(e, "published_parsed", None)
    ]
    return dates if len(dates) >= 3 else None


async def _try_feed_path(base: str, path: str) -> Optional[list[datetime]]:
    content = await fetch_with_retry(base + path)
    if not content:
        return None
    return _extract_feed_dates(content)


async def get_post_dates_from_feed(base_url: str) -> Optional[list[datetime]]:
    base = base_url.rstrip("/")
    results = await asyncio.gather(
        *(_try_feed_path(base, p) for p in COMMON_FEED_PATHS),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, list) and r:
            return r
    return None


BLOG_URL_PATTERN = re.compile(r"/(blog|article|actualites|news|magazine)/", re.IGNORECASE)


def _extract_sitemap_dates(text: str) -> Optional[list[datetime]]:
    try:
        root = etree.fromstring(text.encode("utf-8"))
    except etree.XMLSyntaxError:
        return None
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
    return dates if len(dates) >= 3 else None


async def _try_sitemap_path(base: str, path: str) -> Optional[list[datetime]]:
    text = await fetch_with_retry(base + path)
    if not text:
        return None
    return _extract_sitemap_dates(text)


async def get_post_dates_from_sitemap(base_url: str) -> Optional[list[datetime]]:
    base = base_url.rstrip("/")
    candidates = ["/sitemap.xml", "/sitemap_index.xml", "/blog-sitemap.xml", "/news-sitemap.xml"]
    results = await asyncio.gather(
        *(_try_sitemap_path(base, p) for p in candidates),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, list) and r:
            return r
    return None


async def _cascade(base_url: str) -> Optional[list[datetime]]:
    dates = await get_post_dates_from_feed(base_url)
    if dates:
        return dates
    return await get_post_dates_from_sitemap(base_url)


async def fetch_post_dates(base_url: str) -> Optional[list[datetime]]:
    """Return blog post dates, or None if unavailable or cascade exceeds PER_URL_TIMEOUT_S.

    Sites that return None fall into the 'no blog → auto-CANDIDATE score 100' path
    in the Stage 1 route (this is the desired signal — absent blog = neglected site).
    """
    try:
        return await asyncio.wait_for(_cascade(base_url), timeout=PER_URL_TIMEOUT_S)
    except asyncio.TimeoutError:
        return None
