from datetime import datetime
from typing import Optional
import re
import feedparser
from lxml import etree
from app.utils.http import fetch_with_retry
from app.utils.french_dates import extract_dates_from_html

try:
    from crawl4ai import AsyncWebCrawler
except ImportError:
    # Stub for environments without crawl4ai — production deploy must ensure it's installed.
    class AsyncWebCrawler:  # type: ignore
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def arun(self, url: str):
            class _R:
                success = False
                cleaned_html = ""
            return _R()

COMMON_FEED_PATHS = [
    "/feed", "/rss", "/atom.xml", "/feed/", "/rss.xml",
    "/blog/feed", "/blog/rss", "/news/feed",
    "/feed.xml", "/blog/feed/", "/actualites/feed",
]

async def get_post_dates_from_feed(base_url: str) -> Optional[list[datetime]]:
    base = base_url.rstrip("/")
    for path in COMMON_FEED_PATHS:
        # Fetch async (non-blocking, 10s timeout) then parse content string — feedparser.parse(str) does no I/O
        content = await fetch_with_retry(base + path)
        if not content:
            continue
        feed = feedparser.parse(content)
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


BLOG_PATHS_HTML = ["/blog", "/actualites", "/news", "/magazine", "/blog/fr", "/fr/blog"]

async def get_post_dates_from_html(base_url: str) -> Optional[list[datetime]]:
    base = base_url.rstrip("/")
    async with AsyncWebCrawler() as crawler:
        for path in BLOG_PATHS_HTML:
            result = await crawler.arun(url=f"{base}{path}")
            if getattr(result, "success", False):
                dates = extract_dates_from_html(result.cleaned_html or "")
                if len(dates) >= 3:
                    return dates
    return None


async def fetch_post_dates(base_url: str) -> Optional[list[datetime]]:
    dates = await get_post_dates_from_feed(base_url)
    if dates:
        return dates
    dates = await get_post_dates_from_sitemap(base_url)
    if dates:
        return dates
    dates = await get_post_dates_from_html(base_url)
    return dates
