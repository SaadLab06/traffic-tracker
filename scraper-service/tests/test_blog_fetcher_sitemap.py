from pathlib import Path
import pytest
import respx
import httpx
from app.services.blog_fetcher import get_post_dates_from_sitemap

FIXTURES = Path(__file__).parent / "fixtures" / "sample_sitemaps"

@pytest.mark.asyncio
@respx.mock
async def test_sitemap_extracts_blog_urls_only():
    xml = (FIXTURES / "blog.xml").read_text()
    respx.get("https://example.fr/sitemap.xml").mock(return_value=httpx.Response(200, text=xml))
    for p in ["/sitemap_index.xml", "/blog-sitemap.xml", "/news-sitemap.xml"]:
        respx.get(f"https://example.fr{p}").mock(return_value=httpx.Response(404))
    dates = await get_post_dates_from_sitemap("https://example.fr")
    assert dates is not None
    # Only /blog/ and /actualites/ entries count, not /produit/
    assert len(dates) == 3

@pytest.mark.asyncio
@respx.mock
async def test_sitemap_all_404_returns_none():
    for p in ["/sitemap.xml", "/sitemap_index.xml", "/blog-sitemap.xml", "/news-sitemap.xml"]:
        respx.get(f"https://example.fr{p}").mock(return_value=httpx.Response(404))
    dates = await get_post_dates_from_sitemap("https://example.fr")
    assert dates is None
