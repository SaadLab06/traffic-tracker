import os
import httpx
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.utils.cache import TTLCache
from app.utils.logger import get_logger

log = get_logger(__name__)
SEMRUSH_ENDPOINT = "https://api.semrush.com/analytics/v1/"


class SemrushRetryable(Exception):
    pass


@retry(
    retry=retry_if_exception_type(SemrushRetryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _call_semrush(domain: str, api_key: str) -> dict:
    params = {
        "type": "domain_organic",
        "key": api_key,
        "domain": domain,
        "database": "fr",
        "display_limit": 6,
    }
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(SEMRUSH_ENDPOINT, params=params)
        if r.status_code == 429 or r.status_code >= 500:
            raise SemrushRetryable(str(r.status_code))
        r.raise_for_status()
        return r.json()


async def get_traffic_6m(domain: str, cache_dir: Path | str = ".cache/semrush") -> list[int]:
    api_key = os.getenv("SEMRUSH_API_KEY", "")
    if not api_key or api_key == "changeme":
        log.warning("semrush api key missing", extra={"domain": domain})
        return []
    ttl = int(os.getenv("SEMRUSH_CACHE_TTL", "86400"))
    cache = TTLCache(cache_dir, ttl_seconds=ttl)
    key = f"traffic:{domain}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        data = await _call_semrush(domain, api_key)
        traffic = list(data.get("monthly_organic_traffic", []))[:6]
        cache.set(key, traffic)
        return traffic
    except Exception:
        log.warning("semrush failed", extra={"domain": domain})
        return []
