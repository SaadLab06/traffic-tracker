import pytest
from unittest.mock import patch
from datetime import datetime, timedelta
from app.services.review_scraper import check_trustpilot_velocity

def _mk(n_14: int, n_30: int):
    """Return fake reviews list with n_14 reviews in last 14d and (n_30-n_14) extra in 14-30d window."""
    now = datetime.now()
    revs = []
    for i in range(n_14):
        revs.append({"Date": (now - timedelta(days=3)).strftime("%Y-%m-%d")})
    for i in range(max(0, n_30 - n_14)):
        revs.append({"Date": (now - timedelta(days=20)).strftime("%Y-%m-%d")})
    return revs

@pytest.mark.asyncio
async def test_trustpilot_active_shop():
    with patch("app.services.review_scraper.scrape_trustpilot_reviews", return_value=_mk(7, 12)):
        r = await check_trustpilot_velocity("example.fr")
    assert r["trustpilot_found"] is True
    assert r["recent_reviews_14d"] == 7
    assert r["recent_reviews_30d"] == 12

@pytest.mark.asyncio
async def test_trustpilot_silent_shop():
    with patch("app.services.review_scraper.scrape_trustpilot_reviews", return_value=[]):
        r = await check_trustpilot_velocity("example.fr")
    assert r["recent_reviews_14d"] == 0
    assert r["recent_reviews_30d"] == 0

@pytest.mark.asyncio
async def test_trustpilot_404_graceful():
    with patch("app.services.review_scraper.scrape_trustpilot_reviews", side_effect=Exception("404")):
        r = await check_trustpilot_velocity("notfound.fr")
    assert r["trustpilot_found"] is False
    assert r["recent_reviews_14d"] == 0
    assert r["recent_reviews_30d"] == 0
