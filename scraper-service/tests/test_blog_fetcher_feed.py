from pathlib import Path
import pytest
from app.services.blog_fetcher import get_post_dates_from_feed

FIXTURES = Path(__file__).parent / "fixtures" / "sample_feeds"

@pytest.mark.asyncio
async def test_feedparser_happy_path(monkeypatch):
    import feedparser
    original_parse = feedparser.parse
    raw = (FIXTURES / "wordpress.xml").read_text()
    monkeypatch.setattr(feedparser, "parse", lambda url: original_parse(raw))
    dates = await get_post_dates_from_feed("https://example.fr")
    assert dates is not None
    assert len(dates) == 4
    assert dates[0].year == 2025

@pytest.mark.asyncio
async def test_feedparser_empty_feed_returns_none(monkeypatch):
    import feedparser
    original_parse = feedparser.parse
    monkeypatch.setattr(feedparser, "parse", lambda url: original_parse("<rss><channel></channel></rss>"))
    dates = await get_post_dates_from_feed("https://example.fr")
    assert dates is None

@pytest.mark.asyncio
async def test_feedparser_too_few_entries_returns_none(monkeypatch):
    import feedparser
    original_parse = feedparser.parse
    short = '<rss version="2.0"><channel><item><title>x</title><pubDate>Mon, 10 Mar 2025 10:00:00 +0000</pubDate></item></channel></rss>'
    monkeypatch.setattr(feedparser, "parse", lambda url: original_parse(short))
    dates = await get_post_dates_from_feed("https://example.fr")
    assert dates is None
