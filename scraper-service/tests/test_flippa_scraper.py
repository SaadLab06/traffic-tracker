from unittest.mock import AsyncMock, patch
import pytest
from app.services.flippa_scraper import fetch_flippa_listings

SAMPLE = """
<html><body>
<div class="ListingResults__item">
  <a class="ListingResults__link" href="/12345">visit</a>
  <div class="Card__title">french-cbd-store.fr</div>
  <div class="niche">CBD</div>
  <div class="Price__value">€35,000</div>
</div>
</body></html>
"""

@pytest.mark.asyncio
async def test_flippa_parses_listings(tmp_path):
    with patch("app.services.flippa_scraper.fetch_with_retry", AsyncMock(return_value=SAMPLE)):
        out = await fetch_flippa_listings(cache_dir=tmp_path)
    assert len(out) == 1
    assert "french-cbd-store" in out[0]["domain_hint"]

@pytest.mark.asyncio
async def test_flippa_cached(tmp_path):
    fetch = AsyncMock(return_value=SAMPLE)
    with patch("app.services.flippa_scraper.fetch_with_retry", fetch):
        await fetch_flippa_listings(cache_dir=tmp_path)
        await fetch_flippa_listings(cache_dir=tmp_path)
    assert fetch.await_count == 1
