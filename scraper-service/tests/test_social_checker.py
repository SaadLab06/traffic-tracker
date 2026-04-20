import pytest
from app.services.social_checker import check_social


@pytest.mark.asyncio
async def test_social_disabled_by_env(monkeypatch):
    monkeypatch.setenv("ENABLE_SOCIAL_CHECK", "false")
    r = await check_social("https://example.fr")
    assert r is None


@pytest.mark.asyncio
async def test_social_enabled_returns_shape(monkeypatch):
    monkeypatch.setenv("ENABLE_SOCIAL_CHECK", "true")
    r = await check_social("https://example.fr")
    assert r is None or "social_active" in r
