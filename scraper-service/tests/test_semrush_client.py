from unittest.mock import AsyncMock, patch
import pytest
from app.services.semrush_client import get_traffic_6m

FAKE_RESPONSE = {"monthly_organic_traffic": [8200, 6100, 4800, 3200, 2100, 1200]}


@pytest.mark.asyncio
async def test_get_traffic_returns_6_months(tmp_path, monkeypatch):
    monkeypatch.setenv("SEMRUSH_API_KEY", "k")
    with patch("app.services.semrush_client._call_semrush", AsyncMock(return_value=FAKE_RESPONSE)):
        traffic = await get_traffic_6m("example.fr", cache_dir=tmp_path)
    assert traffic == [8200, 6100, 4800, 3200, 2100, 1200]


@pytest.mark.asyncio
async def test_traffic_cached_for_24h(tmp_path, monkeypatch):
    monkeypatch.setenv("SEMRUSH_API_KEY", "k")
    call = AsyncMock(return_value=FAKE_RESPONSE)
    with patch("app.services.semrush_client._call_semrush", call):
        await get_traffic_6m("example.fr", cache_dir=tmp_path)
        await get_traffic_6m("example.fr", cache_dir=tmp_path)
    assert call.await_count == 1


@pytest.mark.asyncio
async def test_traffic_api_failure_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("SEMRUSH_API_KEY", "k")
    with patch("app.services.semrush_client._call_semrush", AsyncMock(side_effect=Exception("429"))):
        traffic = await get_traffic_6m("example.fr", cache_dir=tmp_path)
    assert traffic == []


@pytest.mark.asyncio
async def test_missing_api_key_returns_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("SEMRUSH_API_KEY", raising=False)
    traffic = await get_traffic_6m("example.fr", cache_dir=tmp_path)
    assert traffic == []
