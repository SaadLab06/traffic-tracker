import asyncio
import pytest
import respx
import httpx
from app.utils.http import fetch_with_retry, jittered_delay_seconds

@pytest.mark.asyncio
@respx.mock
async def test_fetch_with_retry_success():
    respx.get("https://example.fr/feed").mock(return_value=httpx.Response(200, text="<rss/>"))
    text = await fetch_with_retry("https://example.fr/feed")
    assert text == "<rss/>"

@pytest.mark.asyncio
@respx.mock
async def test_fetch_with_retry_retries_on_500_then_succeeds():
    route = respx.get("https://example.fr/feed").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, text="ok")]
    )
    text = await fetch_with_retry("https://example.fr/feed")
    assert text == "ok"
    assert route.call_count == 2

@pytest.mark.asyncio
@respx.mock
async def test_fetch_with_retry_returns_none_on_persistent_failure():
    respx.get("https://example.fr/feed").mock(return_value=httpx.Response(500))
    text = await fetch_with_retry("https://example.fr/feed")
    assert text is None

def test_jittered_delay_within_bounds(monkeypatch):
    monkeypatch.setenv("SCRAPE_DELAY_MIN_MS", "2000")
    monkeypatch.setenv("SCRAPE_DELAY_MAX_MS", "7000")
    for _ in range(50):
        d = jittered_delay_seconds()
        assert 2.0 <= d <= 7.0
