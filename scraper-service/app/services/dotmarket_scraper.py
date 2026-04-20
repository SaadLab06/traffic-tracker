import os
from pathlib import Path
from typing import Any
from bs4 import BeautifulSoup
from app.utils.http import fetch_with_retry
from app.utils.cache import TTLCache

DOTMARKET_URL = "https://dotmarket.eu/annonces"

async def fetch_dotmarket_listings(cache_dir: Path | str = ".cache/dotmarket") -> list[dict[str, Any]]:
    ttl = int(os.getenv("MARKETPLACE_CACHE_TTL", "21600"))
    cache = TTLCache(cache_dir, ttl_seconds=ttl)
    cached = cache.get("listings")
    if cached is not None:
        return cached

    html = await fetch_with_retry(DOTMARKET_URL, timeout=15.0)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    for card in soup.select(".listing"):
        def txt(cls: str) -> str:
            el = card.select_one(f".{cls}")
            return el.get_text(strip=True) if el else ""
        try:
            price = int(txt("price")) if txt("price").isdigit() else None
        except ValueError:
            price = None
        out.append({
            "url": card.get("data-url") or "",
            "niche": txt("niche"),
            "traffic_range": txt("traffic"),
            "revenue_range": txt("revenue"),
            "asking_price_eur": price,
            "domain_hint": txt("domain-hint"),
        })
    cache.set("listings", out)
    return out
