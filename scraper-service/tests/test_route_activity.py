from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _weekly(n=10):
    anchor = datetime.now() - timedelta(days=7 * (n - 1))
    return [anchor + timedelta(days=7 * i) for i in range(n)]


def test_activity_returns_candidate_for_broken_pattern(client):
    stale = [datetime(2024, 1, 1) + timedelta(days=7 * i) for i in range(6)]
    with patch("app.routes.activity.fetch_post_dates", AsyncMock(return_value=stale)), \
         patch("app.routes.activity.check_trustpilot_velocity", return_value={"trustpilot_found": True, "recent_reviews_14d": 0, "recent_reviews_30d": 0}), \
         patch("app.routes.activity.check_social", AsyncMock(return_value=None)):
        r = client.post("/check-activity", json={"urls": ["https://x.fr"]})
    assert r.status_code == 200
    data = r.json()
    assert data[0]["stage1_verdict"] == "CANDIDATE"
    assert data[0]["stage1_score"] >= 40
    assert data[0]["pattern_broken"] is True


def test_activity_returns_eliminated_for_active_shop(client):
    with patch("app.routes.activity.fetch_post_dates", AsyncMock(return_value=_weekly(20))), \
         patch("app.routes.activity.check_trustpilot_velocity", return_value={"trustpilot_found": True, "recent_reviews_14d": 8, "recent_reviews_30d": 15}), \
         patch("app.routes.activity.check_social", AsyncMock(return_value=None)):
        r = client.post("/check-activity", json={"urls": ["https://x.fr"]})
    assert r.json()[0]["stage1_verdict"] == "ELIMINATED"


def test_activity_handles_no_blog(client):
    with patch("app.routes.activity.fetch_post_dates", AsyncMock(return_value=None)), \
         patch("app.routes.activity.check_trustpilot_velocity", return_value={"trustpilot_found": False, "recent_reviews_14d": 0, "recent_reviews_30d": 0}), \
         patch("app.routes.activity.check_social", AsyncMock(return_value=None)):
        r = client.post("/check-activity", json={"urls": ["https://x.fr"]})
    data = r.json()[0]
    assert data["blog_pattern"] == "none"
    assert data["stage1_verdict"] == "CANDIDATE"


def test_activity_per_url_error_does_not_break_batch(client):
    async def flaky(url):
        if "bad" in url:
            raise RuntimeError("boom")
        return _weekly(10)

    with patch("app.routes.activity.fetch_post_dates", AsyncMock(side_effect=flaky)), \
         patch("app.routes.activity.check_trustpilot_velocity", return_value={"trustpilot_found": True, "recent_reviews_14d": 0, "recent_reviews_30d": 0}), \
         patch("app.routes.activity.check_social", AsyncMock(return_value=None)):
        r = client.post("/check-activity", json={"urls": ["https://ok.fr", "https://bad.fr"]})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert any(row.get("error") for row in data)
