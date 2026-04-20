from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app


def test_traffic_happy_path():
    c = TestClient(app)
    with patch("app.routes.traffic.get_traffic_6m", AsyncMock(return_value=[8200, 6100, 4800, 3200, 2100, 1200])):
        r = c.post("/check-traffic", json={"urls": ["https://duverger-nb.com"]})
    assert r.status_code == 200
    body = r.json()[0]
    assert body["trend"] == "declining_strong"
    # Task 22 formula with no enrichment: base 50 + 25 (strong decline) = 75
    assert body["priority_score"] >= 75
    assert body["stage2_verdict"] == "MEDIUM PRIORITY"


def test_traffic_missing_data_returns_unknown():
    c = TestClient(app)
    with patch("app.routes.traffic.get_traffic_6m", AsyncMock(return_value=[])):
        r = c.post("/check-traffic", json={"urls": ["https://x.fr"]})
    body = r.json()[0]
    assert body["trend"] == "unknown"
    # priority uses base (50) minus nothing = 50 -> MEDIUM
    assert body["stage2_verdict"] in ("MEDIUM PRIORITY", "LOW / SKIP")


def test_traffic_accepts_optional_stage1_and_marketplace_payload():
    c = TestClient(app)
    with patch("app.routes.traffic.get_traffic_6m", AsyncMock(return_value=[8000, 4000, 2000, 1000, 500, 200])):
        r = c.post("/check-traffic", json={
            "urls": ["https://x.fr"],
            "enrichment": {"https://x.fr": {"stage1_score": 70, "marketplace_verdict": "FOR_SALE"}},
        })
    body = r.json()[0]
    # base 50 + 40 (marketplace) + 14 (stage1*0.2) + 25 (strong) = 129 -> capped 100
    assert body["priority_score"] == 100
