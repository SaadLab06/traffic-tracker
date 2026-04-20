from fastapi.testclient import TestClient
from app.main import app


def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_exposes_all_three_endpoints():
    r = TestClient(app).get("/openapi.json")
    paths = r.json()["paths"]
    for p in ["/check-marketplaces", "/check-activity", "/check-traffic", "/health"]:
        assert p in paths
