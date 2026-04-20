from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.blog_fetcher import get_post_dates_from_html

HTML_WITH_TIMES = """
<html><body>
<article><time datetime="2025-03-10T10:00:00Z">10 mars 2025</time></article>
<article><time datetime="2025-03-03T10:00:00Z">3 mars 2025</time></article>
<article><time datetime="2025-02-25T10:00:00Z">25 février 2025</time></article>
</body></html>
"""

@pytest.mark.asyncio
async def test_html_fallback_extracts_dates_from_time_tags():
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.cleaned_html = HTML_WITH_TIMES
    mock_crawler = MagicMock()
    mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
    mock_crawler.__aexit__ = AsyncMock(return_value=False)
    mock_crawler.arun = AsyncMock(return_value=mock_result)
    with patch("app.services.blog_fetcher.AsyncWebCrawler", return_value=mock_crawler):
        dates = await get_post_dates_from_html("https://example.fr")
    assert dates is not None
    assert len(dates) >= 3

@pytest.mark.asyncio
async def test_html_fallback_empty_returns_none():
    mock_result = MagicMock()
    mock_result.success = False
    mock_crawler = MagicMock()
    mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
    mock_crawler.__aexit__ = AsyncMock(return_value=False)
    mock_crawler.arun = AsyncMock(return_value=mock_result)
    with patch("app.services.blog_fetcher.AsyncWebCrawler", return_value=mock_crawler):
        dates = await get_post_dates_from_html("https://example.fr")
    assert dates is None
