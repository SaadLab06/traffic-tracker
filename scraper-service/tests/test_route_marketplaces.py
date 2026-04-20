from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

DM = [{"url":"https://dotmarket.eu/l/1","niche":"CBD",
       "domain_hint":"duverger cbd","asking_price_eur":45000,"traffic_range":"5k-10k"}]
FL = [{"url":"https://flippa.com/1","niche":"CBD",
       "domain_hint":"example","asking_price_eur":30000}]

def test_marketplace_hits_dotmarket_once_for_many_urls():
    client = TestClient(app)
    dm_fetch = AsyncMock(return_value=DM)
    fl_fetch = AsyncMock(return_value=FL)
    with patch("app.routes.marketplaces.fetch_dotmarket_listings", dm_fetch), \
         patch("app.routes.marketplaces.fetch_flippa_listings", fl_fetch):
        r = client.post("/check-marketplaces", json={
            "urls": ["https://duverger-nb.com", "https://other.fr", "https://example.fr"]
        })
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    # catalog fetched once per marketplace even for 3 URLs
    assert dm_fetch.await_count == 1
    assert fl_fetch.await_count == 1
    # duverger matches
    duv = next(x for x in body if x["url"] == "https://duverger-nb.com")
    assert duv["listed_on_dotmarket"] is True
    assert duv["marketplace_verdict"] == "FOR_SALE"
    # example matches flippa
    ex = next(x for x in body if x["url"] == "https://example.fr")
    assert ex["listed_on_flippa"] is True

def test_marketplace_no_match_says_not_listed():
    client = TestClient(app)
    with patch("app.routes.marketplaces.fetch_dotmarket_listings", AsyncMock(return_value=[])), \
         patch("app.routes.marketplaces.fetch_flippa_listings", AsyncMock(return_value=[])):
        r = client.post("/check-marketplaces", json={"urls":["https://nope.fr"]})
    assert r.json()[0]["marketplace_verdict"] == "NOT_LISTED"
