from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from app.services.dotmarket_scraper import fetch_dotmarket_listings

FIXTURE = (Path(__file__).parent / "fixtures" / "sample_dotmarket.html").read_text()

@pytest.mark.asyncio
async def test_parse_listings(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKETPLACE_CACHE_TTL", "60")
    with patch("app.services.dotmarket_scraper.fetch_with_retry", AsyncMock(return_value=FIXTURE)):
        listings = await fetch_dotmarket_listings(cache_dir=tmp_path)
    assert len(listings) == 2
    assert listings[0]["niche"] == "CBD"
    assert listings[0]["asking_price_eur"] == 45000

@pytest.mark.asyncio
async def test_cache_is_used_on_second_call(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKETPLACE_CACHE_TTL", "60")
    fetch = AsyncMock(return_value=FIXTURE)
    with patch("app.services.dotmarket_scraper.fetch_with_retry", fetch):
        await fetch_dotmarket_listings(cache_dir=tmp_path)
        await fetch_dotmarket_listings(cache_dir=tmp_path)
        await fetch_dotmarket_listings(cache_dir=tmp_path)
    # HTTP called exactly once across 3 calls
    assert fetch.await_count == 1
