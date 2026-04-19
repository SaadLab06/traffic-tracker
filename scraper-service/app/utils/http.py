import os
import random
import httpx
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

def _user_agent() -> str:
    return os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; AcquisitionBot/2.0)")

def jittered_delay_seconds() -> float:
    lo = int(os.getenv("SCRAPE_DELAY_MIN_MS", "2000")) / 1000
    hi = int(os.getenv("SCRAPE_DELAY_MAX_MS", "7000")) / 1000
    if lo > hi:
        lo, hi = hi, lo
    return random.uniform(lo, hi)

class RetryableHTTPError(Exception):
    pass

@retry(
    retry=retry_if_exception_type(RetryableHTTPError),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=False,
)
async def _fetch(url: str, timeout: float) -> str:
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        max_redirects=3,
        headers={"User-Agent": _user_agent()},
    ) as client:
        r = await client.get(url)
        if r.status_code >= 500 or r.status_code == 429:
            raise RetryableHTTPError(f"{r.status_code}")
        r.raise_for_status()
        return r.text

async def fetch_with_retry(url: str, timeout: float = 10.0) -> Optional[str]:
    try:
        return await _fetch(url, timeout=timeout)
    except Exception:
        return None
