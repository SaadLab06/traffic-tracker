import os
from pathlib import Path
from typing import Any
from bs4 import BeautifulSoup
from app.utils.http import fetch_with_retry
from app.utils.cache import TTLCache

FLIPPA_URL = "https://flippa.com/search?property_type%5B%5D=website&status=open&geography%5B%5D=fr"

async def fetch_flippa_listings(cache_dir: Path | str = ".cache/flippa") -> list[dict[str, Any]]:
    ttl = int(os.getenv("MARKETPLACE_CACHE_TTL", "21600"))
    cache = TTLCache(cache_dir, ttl_seconds=ttl)
    cached = cache.get("listings")
    if cached is not None:
        return cached

    html = await fetch_with_retry(FLIPPA_URL, timeout=15.0)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    for card in soup.select(".ListingResults__item"):
        title = card.select_one(".Card__title")
        link = card.select_one(".ListingResults__link")
        price_el = card.select_one(".Price__value")
        niche_el = card.select_one(".niche")
        href = link.get("href") if link else None
        out.append({
            "url": f"https://flippa.com{href}" if href and href.startswith("/") else (href or ""),
            "niche": niche_el.get_text(strip=True) if niche_el else "",
            "domain_hint": title.get_text(strip=True) if title else "",
            "asking_price_eur": _parse_euros(price_el.get_text(strip=True) if price_el else ""),
        })
    cache.set("listings", out)
    return out

def _parse_euros(s: str) -> int | None:
    import re
    m = re.search(r"[\d,]+", s)
    if not m:
        return None
    try:
        return int(m.group(0).replace(",", ""))
    except ValueError:
        return None
