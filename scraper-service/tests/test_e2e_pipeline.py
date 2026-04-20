import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

ROWS = json.loads((Path(__file__).parent / "fixtures" / "sample_rows.json").read_text())

def _qualified_urls(rows):
    # Mirrors Stage 0 JS logic
    seen = set()
    out = []
    for d in rows:
        types = d["Types"].lower()
        if not d.get("Statut scraping","").strip():
            if "ecommerce" not in types: continue
            site = d["Site web"]
            if not site.startswith("http"): continue
            if d["Nb Avis"] > 500 and d["Note Google"] > 4.5: continue
            from urllib.parse import urlparse
            dom = urlparse(site).hostname.replace("www.","")
            if dom in seen: continue
            seen.add(dom)
            out.append(site)
    return out

def test_stage0_filters_to_two_urls():
    urls = _qualified_urls(ROWS)
    assert len(urls) == 2
    assert "https://duverger-nb.com" in urls
    assert "https://dormant-cbd.fr" in urls

def test_e2e_happy_path():
    c = TestClient(app)
    urls = _qualified_urls(ROWS)
    # Stage 0.5: one match
    dm = [{"url":"https://dotmarket.eu/1","niche":"CBD",
           "domain_hint":"dormant cbd","asking_price_eur":25000,"traffic_range":"3k-5k"}]
    with patch("app.routes.marketplaces.fetch_dotmarket_listings", AsyncMock(return_value=dm)), \
         patch("app.routes.marketplaces.fetch_flippa_listings", AsyncMock(return_value=[])):
        r1 = c.post("/check-marketplaces", json={"urls": urls})
    market = {row["url"]: row for row in r1.json()}
    assert market["https://dormant-cbd.fr"]["marketplace_verdict"] == "FOR_SALE"

    # Stage 1
    from datetime import datetime, timedelta
    stale = [datetime(2024,1,1) + timedelta(days=7*i) for i in range(6)]
    with patch("app.routes.activity.fetch_post_dates", AsyncMock(return_value=stale)), \
         patch("app.routes.activity.check_trustpilot_velocity", return_value={"trustpilot_found":True,"recent_reviews_14d":0,"recent_reviews_30d":1}), \
         patch("app.routes.activity.check_social", AsyncMock(return_value=None)):
        r2 = c.post("/check-activity", json={"urls": urls})
    assert all(row["stage1_verdict"] in ("CANDIDATE", "ERROR") for row in r2.json())

    # Stage 2 with enrichment
    with patch("app.routes.traffic.get_traffic_6m", AsyncMock(return_value=[8200,6100,4800,3200,2100,1200])):
        r3 = c.post("/check-traffic", json={
            "urls": urls,
            "enrichment": {
                u: {"stage1_score": 70, "marketplace_verdict": market[u]["marketplace_verdict"]}
                for u in urls
            }
        })
    # FOR_SALE row should hit HIGH PRIORITY
    dormant = next(x for x in r3.json() if x["url"] == "https://dormant-cbd.fr")
    assert dormant["stage2_verdict"] == "HIGH PRIORITY"
