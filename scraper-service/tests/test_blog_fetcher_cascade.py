from unittest.mock import AsyncMock, patch
from datetime import datetime
import pytest
from app.services.blog_fetcher import fetch_post_dates

SAMPLE = [datetime(2025,3,10), datetime(2025,3,3), datetime(2025,2,25), datetime(2025,2,18)]

@pytest.mark.asyncio
async def test_cascade_stops_at_feed():
    with patch("app.services.blog_fetcher.get_post_dates_from_feed", AsyncMock(return_value=SAMPLE)) as mf, \
         patch("app.services.blog_fetcher.get_post_dates_from_sitemap", AsyncMock()) as ms:
        dates = await fetch_post_dates("https://x.fr")
    assert dates == SAMPLE
    mf.assert_awaited_once()
    ms.assert_not_awaited()

@pytest.mark.asyncio
async def test_cascade_falls_through_to_sitemap():
    with patch("app.services.blog_fetcher.get_post_dates_from_feed", AsyncMock(return_value=None)), \
         patch("app.services.blog_fetcher.get_post_dates_from_sitemap", AsyncMock(return_value=SAMPLE)) as ms:
        dates = await fetch_post_dates("https://x.fr")
    assert dates == SAMPLE
    ms.assert_awaited_once()

@pytest.mark.asyncio
async def test_cascade_all_fail_returns_none():
    with patch("app.services.blog_fetcher.get_post_dates_from_feed", AsyncMock(return_value=None)), \
         patch("app.services.blog_fetcher.get_post_dates_from_sitemap", AsyncMock(return_value=None)):
        dates = await fetch_post_dates("https://x.fr")
    assert dates is None
