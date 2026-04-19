# French E-com Acquisition Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Dockerized FastAPI scraper service + n8n workflow that filters ~1400 French CBD/ecom stores through a 4-stage funnel (pre-qual → marketplace check → activity/pattern → Semrush traffic) to produce 20–50 priority-scored acquisition targets per run under 200 Semrush API calls.

**Architecture:** n8n on Hostinger VPS orchestrates Google Sheets I/O and calls a single FastAPI container over Traefik-routed HTTPS. The container exposes three POST endpoints (`/check-marketplaces`, `/check-activity`, `/check-traffic`) plus `/health`. Each stage is a thin service module wrapping a battle-tested library (`feedparser`, `ruptures`, `trustpilot-scraper`, `crawl4ai`, `scipy`) — **we wrap, we don't reimplement**. File-based caches prevent per-URL fan-out of marketplace catalog fetches and Semrush API calls.

**Tech Stack:** Python 3.11, FastAPI, httpx, feedparser, ruptures (PELT), trustpilot-scraper, crawl4ai (Playwright), dateparser, scipy, pydantic v2, tenacity, Docker, Docker Compose, Traefik, n8n.

---

## Ground Rules (read before Task 1)

1. **TDD is rigid here.** For every task: write the failing test FIRST, watch it fail, then minimal implementation, then make it pass, then commit. Skipping the "watch it fail" step hides fixture-import bugs later.
2. **All tests are offline.** No test hits a real URL, DotMarket, Flippa, Trustpilot, or Semrush. Use `respx` for httpx, fixtures for feeds/sitemaps, and monkeypatch for `feedparser.parse` and `trustpilot_scraper.scraper.scrape_trustpilot_reviews`.
3. **One module = one service file = one test file.** Keep the 1:1:1 mapping in the spec's file structure.
4. **Commit after every green test.** Small commits make bisecting regressions cheap.
5. **Never import a library in tests that you haven't added to `requirements.txt` first.** Task 1 locks dependencies; later tasks only consume them.
6. **Windows dev environment note:** The primary OS is Windows but the production target is Linux (Hostinger VPS). Use forward slashes in Python paths and `pathlib.Path`. Do not write batch scripts.

---

## Task 1: Scaffold project structure and lock dependencies

**Files:**
- Create: `scraper-service/requirements.txt`
- Create: `scraper-service/.env.example`
- Create: `scraper-service/.gitignore`
- Create: `scraper-service/pytest.ini`
- Create: `scraper-service/app/__init__.py`
- Create: `scraper-service/app/routes/__init__.py`
- Create: `scraper-service/app/services/__init__.py`
- Create: `scraper-service/app/models/__init__.py`
- Create: `scraper-service/app/utils/__init__.py`
- Create: `scraper-service/tests/__init__.py`
- Create: `scraper-service/tests/fixtures/.gitkeep`

**Step 1: Write `requirements.txt`**

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
httpx>=0.26.0
feedparser>=6.0.11
ruptures>=1.1.9
trustpilot-scraper>=0.10
crawl4ai>=0.5.0
dateparser>=1.2.0
beautifulsoup4>=4.12.3
lxml>=5.1.0
pydantic>=2.5.0
scipy>=1.12.0
numpy>=1.26.0
python-dotenv>=1.0.0
tenacity>=8.2.3

# dev
pytest>=8.0.0
pytest-asyncio>=0.23.0
respx>=0.20.0
```

**Step 2: Write `.env.example`**

```
SEMRUSH_API_KEY=changeme
USER_AGENT=Mozilla/5.0 (compatible; AcquisitionBot/2.0)
ENABLE_SOCIAL_CHECK=false
MARKETPLACE_CACHE_TTL=21600
SEMRUSH_CACHE_TTL=86400
LOG_LEVEL=INFO
MAX_CONCURRENT_WORKERS=5
SCRAPE_DELAY_MIN_MS=2000
SCRAPE_DELAY_MAX_MS=7000
```

**Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.env
.cache/
logs/
*.egg-info/
.venv/
venv/
```

**Step 4: Write `pytest.ini`**

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
addopts = -v --tb=short
```

**Step 5: Create a virtual env and install**

Run:
```bash
cd scraper-service
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt  # Windows dev
# On Linux VPS: .venv/bin/pip install -r requirements.txt
python -m playwright install chromium
```
Expected: clean install, no errors.

**Step 6: Verify pytest can discover tests**

Run: `pytest --collect-only`
Expected: `collected 0 items` — no tests yet, but pytest works.

**Step 7: Commit**

```bash
git add scraper-service/
git commit -m "feat(scaffold): initialize scraper-service skeleton with locked deps"
```

---

## Task 2: Pydantic request/response schemas

**Files:**
- Create: `scraper-service/app/models/schemas.py`
- Test: `scraper-service/tests/test_schemas.py`

**Step 1: Write failing test**

```python
# tests/test_schemas.py
from app.models.schemas import (
    CheckRequest, MarketplaceResult, ActivityResult, TrafficResult,
)

def test_check_request_accepts_url_list():
    req = CheckRequest(urls=["https://example.fr", "https://duverger-nb.com"])
    assert len(req.urls) == 2

def test_marketplace_result_not_listed_defaults():
    r = MarketplaceResult(url="https://example.fr")
    assert r.listed_on_dotmarket is False
    assert r.listed_on_flippa is False
    assert r.marketplace_verdict == "NOT_LISTED"

def test_activity_result_round_trip():
    r = ActivityResult(
        url="https://x.fr", stage1_verdict="CANDIDATE", stage1_score=74,
        blog_pattern="weekly", avg_gap_days=7.2, days_since_last_post=24,
        change_points_detected=1, change_point_date="2024-11-12",
        pattern_broken=True, recent_reviews_14d=0, recent_reviews_30d=1,
        social_active=False, summary="blog: weekly pattern broken"
    )
    assert r.model_dump()["stage1_verdict"] == "CANDIDATE"

def test_traffic_result_validates_verdict_enum():
    r = TrafficResult(
        url="https://x.fr", traffic_6m=[1,2,3,4,5,6],
        trend="declining_strong", decline_rate_pct=-85.4,
        priority_score=87, stage2_verdict="HIGH PRIORITY",
        summary="Traffic -85%"
    )
    assert r.priority_score == 87
```

**Step 2: Run to fail**

Run: `pytest tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: app.models.schemas`.

**Step 3: Implement**

```python
# app/models/schemas.py
from typing import Literal, Optional
from pydantic import BaseModel, Field, HttpUrl

class CheckRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=200)

class MarketplaceResult(BaseModel):
    url: str
    listed_on_dotmarket: bool = False
    dotmarket_url: Optional[str] = None
    listed_on_flippa: bool = False
    flippa_url: Optional[str] = None
    asking_price_eur: Optional[int] = None
    marketplace_verdict: Literal["FOR_SALE", "NOT_LISTED"] = "NOT_LISTED"

class ActivityResult(BaseModel):
    url: str
    stage1_verdict: Literal["CANDIDATE", "ELIMINATED", "ERROR"]
    stage1_score: int = Field(..., ge=0, le=100)
    blog_pattern: Literal["daily","weekly","biweekly","monthly","irregular","none","insufficient_data"]
    avg_gap_days: Optional[float] = None
    days_since_last_post: Optional[int] = None
    change_points_detected: int = 0
    change_point_date: Optional[str] = None
    pattern_broken: bool = False
    recent_reviews_14d: int = 0
    recent_reviews_30d: int = 0
    social_active: Optional[bool] = None
    summary: str = ""
    error: Optional[str] = None

class TrafficResult(BaseModel):
    url: str
    traffic_6m: list[int] = Field(default_factory=list)
    trend: Literal["declining_strong","declining_moderate","stable","recovering","unknown"]
    decline_rate_pct: float
    priority_score: int = Field(..., ge=0, le=100)
    stage2_verdict: Literal["HIGH PRIORITY","MEDIUM PRIORITY","LOW / SKIP","ERROR"]
    summary: str = ""
    error: Optional[str] = None
```

**Step 4: Run to pass**

Run: `pytest tests/test_schemas.py -v`
Expected: 4 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/models/schemas.py scraper-service/tests/test_schemas.py
git commit -m "feat(models): add pydantic schemas for all 3 endpoints"
```

---

## Task 3: HTTP utility with httpx + tenacity + randomized delay

**Files:**
- Create: `scraper-service/app/utils/http.py`
- Test: `scraper-service/tests/test_http.py`

**Step 1: Write failing test**

```python
# tests/test_http.py
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
```

**Step 2: Run to fail**

Run: `pytest tests/test_http.py -v`
Expected: FAIL — module not found.

**Step 3: Implement**

```python
# app/utils/http.py
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
```

**Step 4: Run to pass**

Run: `pytest tests/test_http.py -v`
Expected: 4 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/utils/http.py scraper-service/tests/test_http.py
git commit -m "feat(utils): httpx client with tenacity retry and jittered delay"
```

---

## Task 4: French date parser wrapper

**Files:**
- Create: `scraper-service/app/utils/french_dates.py`
- Test: `scraper-service/tests/test_french_dates.py`

**Step 1: Write failing test**

```python
# tests/test_french_dates.py
from datetime import datetime
from app.utils.french_dates import parse_fr_date, extract_dates_from_html

def test_parse_absolute_french_date():
    d = parse_fr_date("1 janvier 2025")
    assert d and d.year == 2025 and d.month == 1 and d.day == 1

def test_parse_relative_french_date():
    d = parse_fr_date("il y a 3 jours")
    assert d is not None

def test_parse_invalid_returns_none():
    assert parse_fr_date("pas une date") is None

def test_extract_dates_from_html_time_tag():
    html = '<article><time datetime="2024-11-12T10:00:00Z">12 novembre 2024</time></article>'
    dates = extract_dates_from_html(html)
    assert any(d.year == 2024 and d.month == 11 for d in dates)

def test_extract_dates_from_jsonld():
    html = '''
    <script type="application/ld+json">
    {"@type":"Article","datePublished":"2025-02-10T09:00:00Z"}
    </script>
    '''
    dates = extract_dates_from_html(html)
    assert any(d.year == 2025 and d.month == 2 for d in dates)
```

**Step 2: Run to fail**

Run: `pytest tests/test_french_dates.py -v`
Expected: FAIL.

**Step 3: Implement**

```python
# app/utils/french_dates.py
import json
import re
from datetime import datetime
from typing import Optional
import dateparser
from bs4 import BeautifulSoup

def parse_fr_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    return dateparser.parse(text, languages=["fr", "en"])

def extract_dates_from_html(html: str) -> list[datetime]:
    soup = BeautifulSoup(html, "lxml")
    out: list[datetime] = []

    # <time datetime="...">
    for t in soup.find_all("time"):
        val = t.get("datetime") or t.get_text(strip=True)
        d = parse_fr_date(val)
        if d:
            out.append(d)

    # JSON-LD datePublished
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "{}")
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if isinstance(obj, dict) and obj.get("datePublished"):
                d = parse_fr_date(obj["datePublished"])
                if d:
                    out.append(d)

    # Fallback: regex scan of visible text for "12 novembre 2024" etc.
    text = soup.get_text(" ", strip=True)
    for m in re.finditer(r"\b\d{1,2}\s+(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\s+\d{4}\b", text, flags=re.I):
        d = parse_fr_date(m.group(0))
        if d:
            out.append(d)

    return out
```

**Step 4: Run to pass**

Run: `pytest tests/test_french_dates.py -v`
Expected: 5 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/utils/french_dates.py scraper-service/tests/test_french_dates.py
git commit -m "feat(utils): French date parser with HTML extraction (time/JSON-LD/regex)"
```

---

## Task 5: File-based TTL cache

**Files:**
- Create: `scraper-service/app/utils/cache.py`
- Test: `scraper-service/tests/test_cache.py`

**Step 1: Write failing test**

```python
# tests/test_cache.py
import time
from pathlib import Path
from app.utils.cache import TTLCache

def test_set_and_get(tmp_path):
    c = TTLCache(tmp_path, ttl_seconds=60)
    c.set("foo", {"n": 1})
    assert c.get("foo") == {"n": 1}

def test_expired_returns_none(tmp_path):
    c = TTLCache(tmp_path, ttl_seconds=0)
    c.set("foo", {"n": 1})
    time.sleep(0.01)
    assert c.get("foo") is None

def test_missing_key_returns_none(tmp_path):
    c = TTLCache(tmp_path, ttl_seconds=60)
    assert c.get("nope") is None

def test_survives_restart(tmp_path):
    c1 = TTLCache(tmp_path, ttl_seconds=60)
    c1.set("foo", [1, 2, 3])
    c2 = TTLCache(tmp_path, ttl_seconds=60)
    assert c2.get("foo") == [1, 2, 3]
```

**Step 2: Run to fail**

Run: `pytest tests/test_cache.py -v`
Expected: FAIL.

**Step 3: Implement**

```python
# app/utils/cache.py
import json
import time
import hashlib
from pathlib import Path
from typing import Any, Optional

class TTLCache:
    def __init__(self, directory: Path | str, ttl_seconds: int):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds

    def _path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.dir / f"{h}.json"

    def get(self, key: str) -> Optional[Any]:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        if time.time() - data["ts"] > self.ttl:
            return None
        return data["value"]

    def set(self, key: str, value: Any) -> None:
        p = self._path(key)
        p.write_text(json.dumps({"ts": time.time(), "value": value}), encoding="utf-8")
```

**Step 4: Run to pass**

Run: `pytest tests/test_cache.py -v`
Expected: 4 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/utils/cache.py scraper-service/tests/test_cache.py
git commit -m "feat(utils): file-based TTL cache for marketplace and semrush data"
```

---

## Task 6: Structured JSON logger

**Files:**
- Create: `scraper-service/app/utils/logger.py`
- Test: `scraper-service/tests/test_logger.py`

**Step 1: Write failing test**

```python
# tests/test_logger.py
import json
import logging
from app.utils.logger import get_logger

def test_logger_emits_json(caplog):
    log = get_logger("test")
    with caplog.at_level(logging.INFO):
        log.info("hello", extra={"url": "https://x.fr", "stage": 1})
    record = caplog.records[-1]
    # our formatter produces JSON strings
    payload = json.loads(record.getMessage()) if record.getMessage().startswith("{") else {"message": record.message}
    # we at least want the message recoverable
    assert "hello" in caplog.text
```

**Step 2: Run to fail**

Run: `pytest tests/test_logger.py -v`
Expected: FAIL.

**Step 3: Implement**

```python
# app/utils/logger.py
import json
import logging
import os
import sys

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("url", "stage", "domain", "duration_ms", "cache_hit"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

_configured = False

def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(JsonFormatter())
        root = logging.getLogger()
        root.handlers = [h]
        root.setLevel(os.getenv("LOG_LEVEL", "INFO"))
        _configured = True
    return logging.getLogger(name)
```

**Step 4: Run to pass**

Run: `pytest tests/test_logger.py -v`
Expected: PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/utils/logger.py scraper-service/tests/test_logger.py
git commit -m "feat(utils): structured JSON logger"
```

---

## Task 7: Blog fetcher — RSS/Atom feed stage (feedparser)

**Files:**
- Create: `scraper-service/app/services/blog_fetcher.py`
- Test: `scraper-service/tests/test_blog_fetcher_feed.py`
- Create: `scraper-service/tests/fixtures/sample_feeds/wordpress.xml`

**Step 1: Create fixture `tests/fixtures/sample_feeds/wordpress.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Blog CBD</title>
<item><title>Post 1</title><pubDate>Mon, 10 Mar 2025 10:00:00 +0000</pubDate></item>
<item><title>Post 2</title><pubDate>Mon, 03 Mar 2025 10:00:00 +0000</pubDate></item>
<item><title>Post 3</title><pubDate>Mon, 24 Feb 2025 10:00:00 +0000</pubDate></item>
<item><title>Post 4</title><pubDate>Mon, 17 Feb 2025 10:00:00 +0000</pubDate></item>
</channel></rss>
```

**Step 2: Write failing test**

```python
# tests/test_blog_fetcher_feed.py
from pathlib import Path
import pytest
from app.services.blog_fetcher import get_post_dates_from_feed

FIXTURES = Path(__file__).parent / "fixtures" / "sample_feeds"

@pytest.mark.asyncio
async def test_feedparser_happy_path(monkeypatch):
    import feedparser
    raw = (FIXTURES / "wordpress.xml").read_text()
    monkeypatch.setattr(feedparser, "parse", lambda url: feedparser.parse(raw))
    dates = await get_post_dates_from_feed("https://example.fr")
    assert dates is not None
    assert len(dates) == 4
    assert dates[0].year == 2025

@pytest.mark.asyncio
async def test_feedparser_empty_feed_returns_none(monkeypatch):
    import feedparser
    monkeypatch.setattr(feedparser, "parse", lambda url: feedparser.parse("<rss><channel></channel></rss>"))
    dates = await get_post_dates_from_feed("https://example.fr")
    assert dates is None

@pytest.mark.asyncio
async def test_feedparser_too_few_entries_returns_none(monkeypatch):
    import feedparser
    short = '<rss version="2.0"><channel><item><title>x</title><pubDate>Mon, 10 Mar 2025 10:00:00 +0000</pubDate></item></channel></rss>'
    monkeypatch.setattr(feedparser, "parse", lambda url: feedparser.parse(short))
    dates = await get_post_dates_from_feed("https://example.fr")
    assert dates is None
```

**Step 3: Run to fail**

Run: `pytest tests/test_blog_fetcher_feed.py -v`
Expected: FAIL — module not found.

**Step 4: Implement**

```python
# app/services/blog_fetcher.py
from datetime import datetime
from typing import Optional
import feedparser

COMMON_FEED_PATHS = [
    "/feed", "/rss", "/atom.xml", "/feed/", "/rss.xml",
    "/blog/feed", "/blog/rss", "/news/feed",
    "/feed.xml", "/blog/feed/", "/actualites/feed",
]

async def get_post_dates_from_feed(base_url: str) -> Optional[list[datetime]]:
    base = base_url.rstrip("/")
    for path in COMMON_FEED_PATHS:
        feed = feedparser.parse(base + path)
        if feed.entries and len(feed.entries) >= 3:
            dates = [
                datetime(*e.published_parsed[:6])
                for e in feed.entries
                if getattr(e, "published_parsed", None)
            ]
            if len(dates) >= 3:
                return dates
    return None
```

**Step 5: Run to pass**

Run: `pytest tests/test_blog_fetcher_feed.py -v`
Expected: 3 PASSED.

**Step 6: Commit**

```bash
git add scraper-service/app/services/blog_fetcher.py scraper-service/tests/test_blog_fetcher_feed.py scraper-service/tests/fixtures/sample_feeds/
git commit -m "feat(blog): RSS/Atom feed stage via feedparser"
```

---

## Task 8: Blog fetcher — Sitemap stage

**Files:**
- Modify: `scraper-service/app/services/blog_fetcher.py`
- Test: `scraper-service/tests/test_blog_fetcher_sitemap.py`
- Create: `scraper-service/tests/fixtures/sample_sitemaps/blog.xml`

**Step 1: Create fixture `tests/fixtures/sample_sitemaps/blog.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.fr/blog/article-1</loc><lastmod>2025-03-10</lastmod></url>
  <url><loc>https://example.fr/blog/article-2</loc><lastmod>2025-03-03</lastmod></url>
  <url><loc>https://example.fr/actualites/news-1</loc><lastmod>2025-02-25</lastmod></url>
  <url><loc>https://example.fr/produit/cbd-oil</loc><lastmod>2025-03-01</lastmod></url>
</urlset>
```

**Step 2: Write failing test**

```python
# tests/test_blog_fetcher_sitemap.py
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
    # other candidates 404
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
```

**Step 3: Run to fail**

Run: `pytest tests/test_blog_fetcher_sitemap.py -v`
Expected: FAIL — `get_post_dates_from_sitemap` missing.

**Step 4: Append to `app/services/blog_fetcher.py`**

```python
import re
from lxml import etree
from app.utils.http import fetch_with_retry

BLOG_URL_PATTERN = re.compile(r"/(blog|article|actualites|news|magazine)/", re.IGNORECASE)

async def get_post_dates_from_sitemap(base_url: str) -> Optional[list[datetime]]:
    base = base_url.rstrip("/")
    candidates = ["/sitemap.xml", "/sitemap_index.xml", "/blog-sitemap.xml", "/news-sitemap.xml"]
    for path in candidates:
        text = await fetch_with_retry(base + path)
        if not text:
            continue
        try:
            root = etree.fromstring(text.encode("utf-8"))
        except etree.XMLSyntaxError:
            continue
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        dates: list[datetime] = []
        for url in root.findall(".//s:url", ns):
            loc = (url.findtext("s:loc", namespaces=ns) or "")
            lastmod = url.findtext("s:lastmod", namespaces=ns)
            if lastmod and BLOG_URL_PATTERN.search(loc):
                try:
                    dates.append(datetime.fromisoformat(lastmod.replace("Z", "+00:00").split("T")[0]))
                except ValueError:
                    continue
        if len(dates) >= 3:
            return dates
    return None
```

**Step 5: Run to pass**

Run: `pytest tests/test_blog_fetcher_sitemap.py -v`
Expected: 2 PASSED.

**Step 6: Commit**

```bash
git add scraper-service/app/services/blog_fetcher.py scraper-service/tests/test_blog_fetcher_sitemap.py scraper-service/tests/fixtures/sample_sitemaps/
git commit -m "feat(blog): sitemap stage filters blog/article/actualites paths"
```

---

## Task 9: Blog fetcher — HTML fallback via crawl4ai

**Files:**
- Modify: `scraper-service/app/services/blog_fetcher.py`
- Test: `scraper-service/tests/test_blog_fetcher_html.py`

**Step 1: Write failing test (mocks crawl4ai to stay offline)**

```python
# tests/test_blog_fetcher_html.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.blog_fetcher import get_post_dates_from_html

HTML_WITH_TIMES = """
<html><body>
<article><time datetime="2025-03-10T10:00:00Z">10 mars 2025</time></article>
<article><time datetime="2025-03-03T10:00:00Z">3 mars 2025</time></article>
<article><time datetime="2025-02-25T10:00:00Z">25 février 2025</time></article>
</body></html>
"""

@pytest.mark.asyncio
async def test_html_fallback_extracts_dates_from_time_tags():
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.cleaned_html = HTML_WITH_TIMES
    mock_crawler = MagicMock()
    mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
    mock_crawler.__aexit__ = AsyncMock(return_value=False)
    mock_crawler.arun = AsyncMock(return_value=mock_result)
    with patch("app.services.blog_fetcher.AsyncWebCrawler", return_value=mock_crawler):
        dates = await get_post_dates_from_html("https://example.fr")
    assert dates is not None
    assert len(dates) >= 3

@pytest.mark.asyncio
async def test_html_fallback_empty_returns_none():
    mock_result = MagicMock()
    mock_result.success = False
    mock_crawler = MagicMock()
    mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
    mock_crawler.__aexit__ = AsyncMock(return_value=False)
    mock_crawler.arun = AsyncMock(return_value=mock_result)
    with patch("app.services.blog_fetcher.AsyncWebCrawler", return_value=mock_crawler):
        dates = await get_post_dates_from_html("https://example.fr")
    assert dates is None
```

**Step 2: Run to fail**

Run: `pytest tests/test_blog_fetcher_html.py -v`
Expected: FAIL.

**Step 3: Append to `app/services/blog_fetcher.py`**

```python
from crawl4ai import AsyncWebCrawler
from app.utils.french_dates import extract_dates_from_html

BLOG_PATHS_HTML = ["/blog", "/actualites", "/news", "/magazine", "/blog/fr", "/fr/blog"]

async def get_post_dates_from_html(base_url: str) -> Optional[list[datetime]]:
    base = base_url.rstrip("/")
    async with AsyncWebCrawler() as crawler:
        for path in BLOG_PATHS_HTML:
            result = await crawler.arun(url=f"{base}{path}")
            if getattr(result, "success", False):
                dates = extract_dates_from_html(result.cleaned_html or "")
                if len(dates) >= 3:
                    return dates
    return None
```

**Step 4: Run to pass**

Run: `pytest tests/test_blog_fetcher_html.py -v`
Expected: 2 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/services/blog_fetcher.py scraper-service/tests/test_blog_fetcher_html.py
git commit -m "feat(blog): HTML fallback stage via crawl4ai"
```

---

## Task 10: Blog fetcher — cascade orchestrator

**Files:**
- Modify: `scraper-service/app/services/blog_fetcher.py`
- Test: `scraper-service/tests/test_blog_fetcher_cascade.py`

**Step 1: Write failing test**

```python
# tests/test_blog_fetcher_cascade.py
from unittest.mock import AsyncMock, patch
from datetime import datetime
import pytest
from app.services.blog_fetcher import fetch_post_dates

SAMPLE = [datetime(2025,3,10), datetime(2025,3,3), datetime(2025,2,25), datetime(2025,2,18)]

@pytest.mark.asyncio
async def test_cascade_stops_at_feed():
    with patch("app.services.blog_fetcher.get_post_dates_from_feed", AsyncMock(return_value=SAMPLE)) as mf, \
         patch("app.services.blog_fetcher.get_post_dates_from_sitemap", AsyncMock()) as ms, \
         patch("app.services.blog_fetcher.get_post_dates_from_html", AsyncMock()) as mh:
        dates = await fetch_post_dates("https://x.fr")
    assert dates == SAMPLE
    mf.assert_awaited_once()
    ms.assert_not_awaited()
    mh.assert_not_awaited()

@pytest.mark.asyncio
async def test_cascade_falls_through_to_sitemap():
    with patch("app.services.blog_fetcher.get_post_dates_from_feed", AsyncMock(return_value=None)), \
         patch("app.services.blog_fetcher.get_post_dates_from_sitemap", AsyncMock(return_value=SAMPLE)) as ms, \
         patch("app.services.blog_fetcher.get_post_dates_from_html", AsyncMock()) as mh:
        dates = await fetch_post_dates("https://x.fr")
    assert dates == SAMPLE
    ms.assert_awaited_once()
    mh.assert_not_awaited()

@pytest.mark.asyncio
async def test_cascade_falls_through_to_html():
    with patch("app.services.blog_fetcher.get_post_dates_from_feed", AsyncMock(return_value=None)), \
         patch("app.services.blog_fetcher.get_post_dates_from_sitemap", AsyncMock(return_value=None)), \
         patch("app.services.blog_fetcher.get_post_dates_from_html", AsyncMock(return_value=SAMPLE)) as mh:
        dates = await fetch_post_dates("https://x.fr")
    assert dates == SAMPLE
    mh.assert_awaited_once()

@pytest.mark.asyncio
async def test_cascade_all_fail_returns_none():
    with patch("app.services.blog_fetcher.get_post_dates_from_feed", AsyncMock(return_value=None)), \
         patch("app.services.blog_fetcher.get_post_dates_from_sitemap", AsyncMock(return_value=None)), \
         patch("app.services.blog_fetcher.get_post_dates_from_html", AsyncMock(return_value=None)):
        dates = await fetch_post_dates("https://x.fr")
    assert dates is None
```

**Step 2: Run to fail**

Run: `pytest tests/test_blog_fetcher_cascade.py -v`
Expected: FAIL.

**Step 3: Append to `app/services/blog_fetcher.py`**

```python
async def fetch_post_dates(base_url: str) -> Optional[list[datetime]]:
    dates = await get_post_dates_from_feed(base_url)
    if dates:
        return dates
    dates = await get_post_dates_from_sitemap(base_url)
    if dates:
        return dates
    dates = await get_post_dates_from_html(base_url)
    return dates
```

**Step 4: Run to pass**

Run: `pytest tests/test_blog_fetcher_cascade.py -v`
Expected: 4 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/services/blog_fetcher.py scraper-service/tests/test_blog_fetcher_cascade.py
git commit -m "feat(blog): cascade orchestrator (feed → sitemap → crawl4ai)"
```

---

## Task 11: Pattern analyzer — median gap classification

**Files:**
- Create: `scraper-service/app/services/pattern_analyzer.py`
- Test: `scraper-service/tests/test_pattern_analyzer_classify.py`

**Step 1: Write failing test**

```python
# tests/test_pattern_analyzer_classify.py
from datetime import datetime, timedelta
from app.services.pattern_analyzer import analyze_blog_pattern

def _dates(gaps_days: list[int], anchor=datetime(2025,3,10)) -> list[datetime]:
    out = [anchor]
    for g in gaps_days:
        anchor = anchor - timedelta(days=g)
        out.append(anchor)
    return out

def test_insufficient_data_flags_broken():
    d = analyze_blog_pattern([datetime(2025,3,1)])
    assert d["blog_pattern"] == "insufficient_data"
    assert d["pattern_broken"] is True
    assert d["stage1_score_contrib"] == 35

def test_weekly_pattern_detected():
    dates = _dates([7,7,7,7,7,7,7])
    d = analyze_blog_pattern(dates)
    assert d["blog_pattern"] == "weekly"

def test_daily_pattern_detected():
    dates = _dates([1,1,1,1,1,1,1])
    d = analyze_blog_pattern(dates)
    assert d["blog_pattern"] == "daily"

def test_monthly_pattern_detected():
    dates = _dates([30,30,30,30,30])
    d = analyze_blog_pattern(dates)
    assert d["blog_pattern"] == "monthly"
```

**Step 2: Run to fail**

Run: `pytest tests/test_pattern_analyzer_classify.py -v`
Expected: FAIL.

**Step 3: Implement**

```python
# app/services/pattern_analyzer.py
from datetime import datetime
from typing import Any
import numpy as np
import ruptures as rpt

def analyze_blog_pattern(post_dates: list[datetime]) -> dict[str, Any]:
    if len(post_dates) < 5:
        return {
            "blog_pattern": "insufficient_data",
            "avg_gap_days": None,
            "days_since_last_post": (datetime.now() - max(post_dates)).days if post_dates else None,
            "change_points_detected": 0,
            "change_point_date": None,
            "pattern_broken": True,
            "stage1_score_contrib": 35,
        }

    sorted_dates = sorted(post_dates)
    gaps = np.array([
        (sorted_dates[i+1] - sorted_dates[i]).total_seconds() / 86400
        for i in range(len(sorted_dates) - 1)
    ])
    median_gap = float(np.median(gaps))
    if   median_gap < 2:  pattern = "daily"
    elif median_gap < 10: pattern = "weekly"
    elif median_gap < 20: pattern = "biweekly"
    elif median_gap < 45: pattern = "monthly"
    else:                 pattern = "irregular"

    signal = gaps.reshape(-1, 1)
    try:
        algo = rpt.Pelt(model="rbf").fit(signal)
        change_points = [cp for cp in algo.predict(pen=10) if cp < len(signal)]
    except Exception:
        change_points = []

    pattern_broken = False
    change_point_date: str | None = None
    if change_points:
        last_cp = change_points[-1]
        gaps_before = gaps[:last_cp]
        gaps_after = gaps[last_cp:]
        if len(gaps_after) and len(gaps_before) and np.mean(gaps_after) > np.mean(gaps_before) * 2:
            pattern_broken = True
            change_point_date = sorted_dates[last_cp + 1].isoformat()

    days_since_last = (datetime.now() - sorted_dates[-1]).days
    if days_since_last > median_gap * 3:
        pattern_broken = True

    return {
        "blog_pattern": pattern,
        "avg_gap_days": round(median_gap, 1),
        "days_since_last_post": days_since_last,
        "change_points_detected": len(change_points),
        "change_point_date": change_point_date,
        "pattern_broken": pattern_broken,
        "stage1_score_contrib": 40 if pattern_broken else 0,
    }
```

**Step 4: Run to pass**

Run: `pytest tests/test_pattern_analyzer_classify.py -v`
Expected: 4 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/services/pattern_analyzer.py scraper-service/tests/test_pattern_analyzer_classify.py
git commit -m "feat(pattern): median-gap classification daily/weekly/biweekly/monthly/irregular"
```

---

## Task 12: Pattern analyzer — PELT change-point detection

**Files:**
- Test: `scraper-service/tests/test_pattern_analyzer_pelt.py`

**Step 1: Write failing test (calibration test for PELT penalty)**

```python
# tests/test_pattern_analyzer_pelt.py
from datetime import datetime, timedelta
from app.services.pattern_analyzer import analyze_blog_pattern

def test_weekly_then_silence_detects_change_point():
    # 10 weekly posts, then 3 giant gaps (stopped posting) — should flag pattern_broken
    dates = []
    anchor = datetime(2024, 1, 1)
    for i in range(10):
        dates.append(anchor + timedelta(days=7 * i))
    # then big silence: 80-day gaps
    for i in range(3):
        dates.append(dates[-1] + timedelta(days=80))
    d = analyze_blog_pattern(dates)
    assert d["pattern_broken"] is True
    assert d["change_points_detected"] >= 1
    assert d["change_point_date"] is not None

def test_consistent_pattern_no_break():
    # 20 posts, exactly weekly, all the way to recent
    dates = []
    anchor = datetime.now() - timedelta(days=7 * 19)
    for i in range(20):
        dates.append(anchor + timedelta(days=7 * i))
    d = analyze_blog_pattern(dates)
    # Recent post → days_since_last should be small
    assert d["days_since_last_post"] < 14
    # No catastrophic break
    assert d["stage1_score_contrib"] == 0 or d["pattern_broken"] is False

def test_stale_blog_flagged_even_without_change_point():
    # 5 weekly posts ending a year ago
    dates = [datetime(2024, 1, 1) + timedelta(days=7*i) for i in range(5)]
    d = analyze_blog_pattern(dates)
    assert d["pattern_broken"] is True
```

**Step 2: Run to fail, then pass**

Run: `pytest tests/test_pattern_analyzer_pelt.py -v`
Expected: PASS (implementation from Task 11 already handles this). If any fail, **do not weaken the test** — re-tune `pen=10` in `pattern_analyzer.py` and document the new value in a comment with justification.

**Step 3: Commit**

```bash
git add scraper-service/tests/test_pattern_analyzer_pelt.py
git commit -m "test(pattern): PELT calibration tests (change-point + stale detection)"
```

---

## Task 13: Review scraper — Trustpilot wrapper

**Files:**
- Create: `scraper-service/app/services/review_scraper.py`
- Test: `scraper-service/tests/test_review_scraper.py`

**Step 1: Write failing test**

```python
# tests/test_review_scraper.py
from unittest.mock import patch
from datetime import datetime, timedelta
from app.services.review_scraper import check_trustpilot_velocity

def _mk(n_14: int, n_30: int):
    """Return fake reviews list with n_14 reviews in last 14d and (n_30-n_14) extra in 14-30d window."""
    now = datetime.now()
    revs = []
    for i in range(n_14):
        revs.append({"Date": (now - timedelta(days=3)).strftime("%Y-%m-%d")})
    for i in range(max(0, n_30 - n_14)):
        revs.append({"Date": (now - timedelta(days=20)).strftime("%Y-%m-%d")})
    return revs

def test_trustpilot_active_shop():
    with patch("app.services.review_scraper.scrape_trustpilot_reviews", return_value=_mk(7, 12)):
        r = check_trustpilot_velocity("example.fr")
    assert r["trustpilot_found"] is True
    assert r["recent_reviews_14d"] == 7
    assert r["recent_reviews_30d"] == 12

def test_trustpilot_silent_shop():
    with patch("app.services.review_scraper.scrape_trustpilot_reviews", return_value=[]):
        r = check_trustpilot_velocity("example.fr")
    assert r["recent_reviews_14d"] == 0
    assert r["recent_reviews_30d"] == 0

def test_trustpilot_404_graceful():
    with patch("app.services.review_scraper.scrape_trustpilot_reviews", side_effect=Exception("404")):
        r = check_trustpilot_velocity("notfound.fr")
    assert r["trustpilot_found"] is False
    assert r["recent_reviews_14d"] == 0
    assert r["recent_reviews_30d"] == 0
```

**Step 2: Run to fail**

Run: `pytest tests/test_review_scraper.py -v`
Expected: FAIL.

**Step 3: Implement**

```python
# app/services/review_scraper.py
from datetime import datetime, timedelta
from typing import Any
try:
    from trustpilot_scraper.scraper import scrape_trustpilot_reviews
except ImportError:  # pragma: no cover
    def scrape_trustpilot_reviews(url: str):
        raise RuntimeError("trustpilot-scraper not installed")

def check_trustpilot_velocity(domain: str) -> dict[str, Any]:
    try:
        reviews = scrape_trustpilot_reviews(f"https://www.trustpilot.com/review/{domain}")
    except Exception:
        return {"trustpilot_found": False, "recent_reviews_14d": 0, "recent_reviews_30d": 0}

    now = datetime.now()
    c14, c30 = 0, 0
    for r in (reviews or [])[:50]:
        try:
            rev_date = datetime.strptime(r["Date"], "%Y-%m-%d")
        except (KeyError, ValueError, TypeError):
            continue
        if rev_date >= now - timedelta(days=14): c14 += 1
        if rev_date >= now - timedelta(days=30): c30 += 1
    return {"trustpilot_found": True, "recent_reviews_14d": c14, "recent_reviews_30d": c30}
```

**Step 4: Run to pass**

Run: `pytest tests/test_review_scraper.py -v`
Expected: 3 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/services/review_scraper.py scraper-service/tests/test_review_scraper.py
git commit -m "feat(reviews): Trustpilot wrapper with graceful 404 handling"
```

---

## Task 14: Social checker (toggleable)

**Files:**
- Create: `scraper-service/app/services/social_checker.py`
- Test: `scraper-service/tests/test_social_checker.py`

**Step 1: Write failing test**

```python
# tests/test_social_checker.py
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
```

**Step 2: Run to fail**

Run: `pytest tests/test_social_checker.py -v`
Expected: FAIL.

**Step 3: Implement (v1 stub — spec says default off)**

```python
# app/services/social_checker.py
import os
from typing import Any, Optional

async def check_social(base_url: str) -> Optional[dict[str, Any]]:
    if os.getenv("ENABLE_SOCIAL_CHECK", "false").lower() != "true":
        return None
    # v1: placeholder returns None; v2 will extract IG/FB from footer and
    # parse last-post date from open-graph meta without API calls.
    return None
```

**Step 4: Run to pass**

Run: `pytest tests/test_social_checker.py -v`
Expected: 2 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/services/social_checker.py scraper-service/tests/test_social_checker.py
git commit -m "feat(social): toggleable stub deferred to v2 per spec section 8.4"
```

---

## Task 15: Stage 1 scoring formula

**Files:**
- Modify: `scraper-service/app/services/pattern_analyzer.py` (add `compute_stage1_score`)
- Test: `scraper-service/tests/test_stage1_score.py`

**Step 1: Write failing test**

```python
# tests/test_stage1_score.py
from app.services.pattern_analyzer import compute_stage1_score

def test_no_blog_max_out_at_75():
    s = compute_stage1_score(
        {"blog_pattern": "none", "stage1_score_contrib": 40},
        {"recent_reviews_30d": 0},
        None,
    )
    # 40 (broken) + 35 (none) + 20 (zero reviews) = 95
    assert s == 95

def test_healthy_active_shop_below_threshold():
    s = compute_stage1_score(
        {"blog_pattern": "weekly", "stage1_score_contrib": 0},
        {"recent_reviews_30d": 12},
        None,
    )
    assert s == 0

def test_verdict_threshold_boundary():
    from app.services.pattern_analyzer import stage1_verdict
    assert stage1_verdict(40) == "CANDIDATE"
    assert stage1_verdict(39) == "ELIMINATED"

def test_social_boost_applies():
    s = compute_stage1_score(
        {"blog_pattern": "weekly", "stage1_score_contrib": 0},
        {"recent_reviews_30d": 1},
        {"social_active": False},
    )
    # 10 (≤2 reviews) + 15 (social dead) = 25
    assert s == 25

def test_score_capped_at_100():
    s = compute_stage1_score(
        {"blog_pattern": "none", "stage1_score_contrib": 40},
        {"recent_reviews_30d": 0},
        {"social_active": False},
    )
    # would be 40+35+20+15 = 110 → cap 100
    assert s == 100
```

**Step 2: Run to fail**

Run: `pytest tests/test_stage1_score.py -v`
Expected: FAIL.

**Step 3: Append to `app/services/pattern_analyzer.py`**

```python
def compute_stage1_score(blog_data: dict, review_data: dict, social_data: dict | None) -> int:
    score = 0
    score += blog_data.get("stage1_score_contrib", 0)
    if blog_data.get("blog_pattern") == "none":
        score += 35
    r30 = review_data.get("recent_reviews_30d", 0)
    if r30 == 0:
        score += 20
    elif r30 <= 2:
        score += 10
    if social_data and social_data.get("social_active") is False:
        score += 15
    return min(100, score)

def stage1_verdict(score: int) -> str:
    return "CANDIDATE" if score >= 40 else "ELIMINATED"
```

**Step 4: Run to pass**

Run: `pytest tests/test_stage1_score.py -v`
Expected: 5 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/services/pattern_analyzer.py scraper-service/tests/test_stage1_score.py
git commit -m "feat(stage1): scoring formula + CANDIDATE verdict at ≥40"
```

---

## Task 16: `/check-activity` route

**Files:**
- Create: `scraper-service/app/routes/activity.py`
- Test: `scraper-service/tests/test_route_activity.py`

**Step 1: Write failing test**

```python
# tests/test_route_activity.py
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def _weekly(n=10):
    anchor = datetime.now() - timedelta(days=7*(n-1))
    return [anchor + timedelta(days=7*i) for i in range(n)]

def test_activity_returns_candidate_for_broken_pattern(client):
    stale = [datetime(2024,1,1) + timedelta(days=7*i) for i in range(6)]
    with patch("app.routes.activity.fetch_post_dates", AsyncMock(return_value=stale)), \
         patch("app.routes.activity.check_trustpilot_velocity", return_value={"trustpilot_found":True,"recent_reviews_14d":0,"recent_reviews_30d":0}), \
         patch("app.routes.activity.check_social", AsyncMock(return_value=None)):
        r = client.post("/check-activity", json={"urls":["https://x.fr"]})
    assert r.status_code == 200
    data = r.json()
    assert data[0]["stage1_verdict"] == "CANDIDATE"
    assert data[0]["stage1_score"] >= 40
    assert data[0]["pattern_broken"] is True

def test_activity_returns_eliminated_for_active_shop(client):
    with patch("app.routes.activity.fetch_post_dates", AsyncMock(return_value=_weekly(20))), \
         patch("app.routes.activity.check_trustpilot_velocity", return_value={"trustpilot_found":True,"recent_reviews_14d":8,"recent_reviews_30d":15}), \
         patch("app.routes.activity.check_social", AsyncMock(return_value=None)):
        r = client.post("/check-activity", json={"urls":["https://x.fr"]})
    assert r.json()[0]["stage1_verdict"] == "ELIMINATED"

def test_activity_handles_no_blog(client):
    with patch("app.routes.activity.fetch_post_dates", AsyncMock(return_value=None)), \
         patch("app.routes.activity.check_trustpilot_velocity", return_value={"trustpilot_found":False,"recent_reviews_14d":0,"recent_reviews_30d":0}), \
         patch("app.routes.activity.check_social", AsyncMock(return_value=None)):
        r = client.post("/check-activity", json={"urls":["https://x.fr"]})
    data = r.json()[0]
    assert data["blog_pattern"] == "none"
    assert data["stage1_verdict"] == "CANDIDATE"

def test_activity_per_url_error_does_not_break_batch(client):
    async def flaky(url):
        if "bad" in url: raise RuntimeError("boom")
        return _weekly(10)
    with patch("app.routes.activity.fetch_post_dates", AsyncMock(side_effect=flaky)), \
         patch("app.routes.activity.check_trustpilot_velocity", return_value={"trustpilot_found":True,"recent_reviews_14d":0,"recent_reviews_30d":0}), \
         patch("app.routes.activity.check_social", AsyncMock(return_value=None)):
        r = client.post("/check-activity", json={"urls":["https://ok.fr","https://bad.fr"]})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert any(row.get("error") for row in data)
```

**Step 2: Run to fail**

Run: `pytest tests/test_route_activity.py -v`
Expected: FAIL — neither `app.main` nor `app.routes.activity` exist yet.

**Step 3: Implement `app/routes/activity.py`**

```python
# app/routes/activity.py
import asyncio
from urllib.parse import urlparse
from fastapi import APIRouter
from app.models.schemas import CheckRequest, ActivityResult
from app.services.blog_fetcher import fetch_post_dates
from app.services.pattern_analyzer import (
    analyze_blog_pattern, compute_stage1_score, stage1_verdict,
)
from app.services.review_scraper import check_trustpilot_velocity
from app.services.social_checker import check_social
from app.utils.logger import get_logger

router = APIRouter()
log = get_logger(__name__)

MAX_CONCURRENCY = 5

async def _process(url: str) -> dict:
    try:
        dates = await fetch_post_dates(url)
        if dates is None:
            blog = {"blog_pattern": "none", "avg_gap_days": None,
                    "days_since_last_post": None, "change_points_detected": 0,
                    "change_point_date": None, "pattern_broken": True,
                    "stage1_score_contrib": 0}
        else:
            blog = analyze_blog_pattern(dates)

        domain = urlparse(url).hostname or ""
        reviews = check_trustpilot_velocity(domain.removeprefix("www."))
        social = await check_social(url)

        score = compute_stage1_score(blog, reviews, social)
        verdict = stage1_verdict(score) if blog["blog_pattern"] != "none" or reviews["recent_reviews_30d"] > 0 else "CANDIDATE"
        # If truly no blog → spec says auto-CANDIDATE with score=100
        if blog["blog_pattern"] == "none":
            score = 100
            verdict = "CANDIDATE"

        summary_bits = []
        if blog["blog_pattern"] == "none":
            summary_bits.append("no blog detected")
        else:
            state = "broken" if blog["pattern_broken"] else "active"
            summary_bits.append(f"blog: {blog['blog_pattern']} {state}")
        summary_bits.append(f"{reviews['recent_reviews_30d']} reviews 30d")
        if social and social.get("social_active") is False:
            summary_bits.append("social dead")

        return {
            "url": url,
            "stage1_verdict": verdict,
            "stage1_score": score,
            **{k: blog[k] for k in ("blog_pattern","avg_gap_days","days_since_last_post",
                                     "change_points_detected","change_point_date","pattern_broken")},
            "recent_reviews_14d": reviews["recent_reviews_14d"],
            "recent_reviews_30d": reviews["recent_reviews_30d"],
            "social_active": (social or {}).get("social_active"),
            "summary": " | ".join(summary_bits),
        }
    except Exception as e:
        log.exception("stage1 failed", extra={"url": url, "stage": 1})
        return {
            "url": url, "stage1_verdict": "ERROR", "stage1_score": 0,
            "blog_pattern": "insufficient_data", "pattern_broken": False,
            "recent_reviews_14d": 0, "recent_reviews_30d": 0,
            "summary": "error", "error": str(e),
        }

@router.post("/check-activity", response_model=list[ActivityResult])
async def check_activity(req: CheckRequest):
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    async def guarded(u: str):
        async with sem:
            return await _process(u)
    return await asyncio.gather(*[guarded(u) for u in req.urls])
```

**Step 4: Create stub `app/main.py`**

```python
# app/main.py
from fastapi import FastAPI
from app.routes import activity

app = FastAPI(title="Acquisition Scraper Service")
app.include_router(activity.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 5: Run to pass**

Run: `pytest tests/test_route_activity.py -v`
Expected: 4 PASSED.

**Step 6: Commit**

```bash
git add scraper-service/app/routes/activity.py scraper-service/app/main.py scraper-service/tests/test_route_activity.py
git commit -m "feat(route): /check-activity with concurrency guard and per-URL error isolation"
```

---

## Task 17: DotMarket scraper with once-per-run cache

**Files:**
- Create: `scraper-service/app/services/dotmarket_scraper.py`
- Test: `scraper-service/tests/test_dotmarket_scraper.py`
- Create: `scraper-service/tests/fixtures/sample_dotmarket.html`

**Step 1: Create fixture `tests/fixtures/sample_dotmarket.html`** (a minimal listing page)

```html
<html><body>
<div class="listing" data-url="https://dotmarket.eu/listing/12345">
  <span class="niche">CBD</span>
  <span class="traffic">5000-10000</span>
  <span class="revenue">2000-5000</span>
  <span class="price">45000</span>
  <span class="domain-hint">CBD boutique française</span>
</div>
<div class="listing" data-url="https://dotmarket.eu/listing/67890">
  <span class="niche">Mode</span>
  <span class="traffic">20000-50000</span>
  <span class="revenue">5000-15000</span>
  <span class="price">120000</span>
  <span class="domain-hint">Boutique vêtements</span>
</div>
</body></html>
```

**Step 2: Write failing test**

```python
# tests/test_dotmarket_scraper.py
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from app.services.dotmarket_scraper import fetch_dotmarket_listings

FIXTURE = (Path(__file__).parent / "fixtures" / "sample_dotmarket.html").read_text()

@pytest.mark.asyncio
async def test_parse_listings(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKETPLACE_CACHE_TTL", "60")
    with patch("app.services.dotmarket_scraper.fetch_with_retry", AsyncMock(return_value=FIXTURE)):
        listings = await fetch_dotmarket_listings(cache_dir=tmp_path)
    assert len(listings) == 2
    assert listings[0]["niche"] == "CBD"
    assert listings[0]["asking_price_eur"] == 45000

@pytest.mark.asyncio
async def test_cache_is_used_on_second_call(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKETPLACE_CACHE_TTL", "60")
    fetch = AsyncMock(return_value=FIXTURE)
    with patch("app.services.dotmarket_scraper.fetch_with_retry", fetch):
        await fetch_dotmarket_listings(cache_dir=tmp_path)
        await fetch_dotmarket_listings(cache_dir=tmp_path)
        await fetch_dotmarket_listings(cache_dir=tmp_path)
    # HTTP called exactly once across 3 calls
    assert fetch.await_count == 1
```

**Step 3: Run to fail**

Run: `pytest tests/test_dotmarket_scraper.py -v`
Expected: FAIL.

**Step 4: Implement**

```python
# app/services/dotmarket_scraper.py
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
```

**Step 5: Run to pass**

Run: `pytest tests/test_dotmarket_scraper.py -v`
Expected: 2 PASSED.

**Step 6: Commit**

```bash
git add scraper-service/app/services/dotmarket_scraper.py scraper-service/tests/test_dotmarket_scraper.py scraper-service/tests/fixtures/sample_dotmarket.html
git commit -m "feat(marketplace): DotMarket scraper with 6h TTL cache (fetched once per run)"
```

---

## Task 18: Flippa scraper (geography=fr)

**Files:**
- Create: `scraper-service/app/services/flippa_scraper.py`
- Test: `scraper-service/tests/test_flippa_scraper.py`

**Step 1: Write failing test**

```python
# tests/test_flippa_scraper.py
from unittest.mock import AsyncMock, patch
import pytest
from app.services.flippa_scraper import fetch_flippa_listings

SAMPLE = """
<html><body>
<div class="ListingResults__item">
  <a class="ListingResults__link" href="/12345">visit</a>
  <div class="Card__title">french-cbd-store.fr</div>
  <div class="niche">CBD</div>
  <div class="Price__value">€35,000</div>
</div>
</body></html>
"""

@pytest.mark.asyncio
async def test_flippa_parses_listings(tmp_path):
    with patch("app.services.flippa_scraper.fetch_with_retry", AsyncMock(return_value=SAMPLE)):
        out = await fetch_flippa_listings(cache_dir=tmp_path)
    assert len(out) == 1
    assert "french-cbd-store" in out[0]["domain_hint"]

@pytest.mark.asyncio
async def test_flippa_cached(tmp_path):
    fetch = AsyncMock(return_value=SAMPLE)
    with patch("app.services.flippa_scraper.fetch_with_retry", fetch):
        await fetch_flippa_listings(cache_dir=tmp_path)
        await fetch_flippa_listings(cache_dir=tmp_path)
    assert fetch.await_count == 1
```

**Step 2: Run to fail**

Run: `pytest tests/test_flippa_scraper.py -v`
Expected: FAIL.

**Step 3: Implement**

```python
# app/services/flippa_scraper.py
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
```

**Step 4: Run to pass**

Run: `pytest tests/test_flippa_scraper.py -v`
Expected: 2 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/services/flippa_scraper.py scraper-service/tests/test_flippa_scraper.py
git commit -m "feat(marketplace): Flippa FR listings scraper with TTL cache"
```

---

## Task 19: Marketplace matcher (domain fuzzy match)

**Files:**
- Create: `scraper-service/app/services/marketplace_matcher.py`
- Test: `scraper-service/tests/test_marketplace_matcher.py`

**Step 1: Write failing test**

```python
# tests/test_marketplace_matcher.py
from app.services.marketplace_matcher import match_url_to_listings

LISTINGS = [
    {"url":"https://dotmarket.eu/listing/12345","niche":"CBD",
     "domain_hint":"CBD boutique française duverger","asking_price_eur":45000,
     "traffic_range":"5000-10000"},
    {"url":"https://dotmarket.eu/listing/67890","niche":"Mode",
     "domain_hint":"Boutique vêtements","asking_price_eur":120000,
     "traffic_range":"20000-50000"},
]

def test_direct_domain_hint_match():
    m = match_url_to_listings("https://duverger-nb.com", LISTINGS)
    assert m is not None
    assert m["asking_price_eur"] == 45000

def test_no_match_returns_none():
    m = match_url_to_listings("https://unrelated-site.fr", LISTINGS)
    assert m is None

def test_case_insensitive():
    m = match_url_to_listings("https://DUVERGER-NB.com", LISTINGS)
    assert m is not None
```

**Step 2: Run to fail**

Run: `pytest tests/test_marketplace_matcher.py -v`
Expected: FAIL.

**Step 3: Implement**

```python
# app/services/marketplace_matcher.py
import re
from urllib.parse import urlparse
from typing import Any, Optional

def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")

def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) >= 4}

def match_url_to_listings(url: str, listings: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    domain = _domain(url)
    if not domain:
        return None
    # Use the left-most label of the domain as the primary fingerprint
    core = domain.split(".")[0]
    core_tokens = _tokens(core)
    for listing in listings:
        hint = (listing.get("domain_hint") or "").lower()
        hint_tokens = _tokens(hint)
        if core in hint or core_tokens & hint_tokens:
            return listing
    return None
```

**Step 4: Run to pass**

Run: `pytest tests/test_marketplace_matcher.py -v`
Expected: 3 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/services/marketplace_matcher.py scraper-service/tests/test_marketplace_matcher.py
git commit -m "feat(marketplace): fuzzy URL→listing matcher on core-domain tokens"
```

---

## Task 20: `/check-marketplaces` route

**Files:**
- Create: `scraper-service/app/routes/marketplaces.py`
- Modify: `scraper-service/app/main.py` (register router)
- Test: `scraper-service/tests/test_route_marketplaces.py`

**Step 1: Write failing test**

```python
# tests/test_route_marketplaces.py
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

DM = [{"url":"https://dotmarket.eu/l/1","niche":"CBD",
       "domain_hint":"duverger cbd","asking_price_eur":45000,"traffic_range":"5k-10k"}]
FL = [{"url":"https://flippa.com/1","niche":"CBD",
       "domain_hint":"example","asking_price_eur":30000}]

def test_marketplace_hits_dotmarket_once_for_many_urls():
    client = TestClient(app)
    dm_fetch = AsyncMock(return_value=DM)
    fl_fetch = AsyncMock(return_value=FL)
    with patch("app.routes.marketplaces.fetch_dotmarket_listings", dm_fetch), \
         patch("app.routes.marketplaces.fetch_flippa_listings", fl_fetch):
        r = client.post("/check-marketplaces", json={
            "urls": ["https://duverger-nb.com", "https://other.fr", "https://example.fr"]
        })
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    # catalog fetched once per marketplace even for 3 URLs
    assert dm_fetch.await_count == 1
    assert fl_fetch.await_count == 1
    # duverger matches
    duv = next(x for x in body if x["url"] == "https://duverger-nb.com")
    assert duv["listed_on_dotmarket"] is True
    assert duv["marketplace_verdict"] == "FOR_SALE"
    # example matches flippa
    ex = next(x for x in body if x["url"] == "https://example.fr")
    assert ex["listed_on_flippa"] is True

def test_marketplace_no_match_says_not_listed():
    client = TestClient(app)
    with patch("app.routes.marketplaces.fetch_dotmarket_listings", AsyncMock(return_value=[])), \
         patch("app.routes.marketplaces.fetch_flippa_listings", AsyncMock(return_value=[])):
        r = client.post("/check-marketplaces", json={"urls":["https://nope.fr"]})
    assert r.json()[0]["marketplace_verdict"] == "NOT_LISTED"
```

**Step 2: Run to fail**

Run: `pytest tests/test_route_marketplaces.py -v`
Expected: FAIL.

**Step 3: Implement `app/routes/marketplaces.py`**

```python
# app/routes/marketplaces.py
from fastapi import APIRouter
from app.models.schemas import CheckRequest, MarketplaceResult
from app.services.dotmarket_scraper import fetch_dotmarket_listings
from app.services.flippa_scraper import fetch_flippa_listings
from app.services.marketplace_matcher import match_url_to_listings

router = APIRouter()

@router.post("/check-marketplaces", response_model=list[MarketplaceResult])
async def check_marketplaces(req: CheckRequest):
    # Catalogs fetched once per run (cache TTL enforced in each scraper)
    dm_listings = await fetch_dotmarket_listings()
    fl_listings = await fetch_flippa_listings()
    out: list[MarketplaceResult] = []
    for url in req.urls:
        dm = match_url_to_listings(url, dm_listings)
        fl = match_url_to_listings(url, fl_listings)
        listed = dm is not None or fl is not None
        out.append(MarketplaceResult(
            url=url,
            listed_on_dotmarket=dm is not None,
            dotmarket_url=(dm or {}).get("url"),
            listed_on_flippa=fl is not None,
            flippa_url=(fl or {}).get("url"),
            asking_price_eur=(dm or fl or {}).get("asking_price_eur"),
            marketplace_verdict="FOR_SALE" if listed else "NOT_LISTED",
        ))
    return out
```

**Step 4: Register in `app/main.py`**

```python
from app.routes import marketplaces
app.include_router(marketplaces.router)
```

**Step 5: Run to pass**

Run: `pytest tests/test_route_marketplaces.py -v`
Expected: 2 PASSED.

**Step 6: Commit**

```bash
git add scraper-service/app/routes/marketplaces.py scraper-service/app/main.py scraper-service/tests/test_route_marketplaces.py
git commit -m "feat(route): /check-marketplaces fetches catalogs once, matches per URL"
```

---

## Task 21: Semrush client with tenacity + 24h cache

**Files:**
- Create: `scraper-service/app/services/semrush_client.py`
- Test: `scraper-service/tests/test_semrush_client.py`

**Step 1: Write failing test**

```python
# tests/test_semrush_client.py
from unittest.mock import AsyncMock, patch
import pytest
from app.services.semrush_client import get_traffic_6m

FAKE_RESPONSE = {"monthly_organic_traffic": [8200,6100,4800,3200,2100,1200]}

@pytest.mark.asyncio
async def test_get_traffic_returns_6_months(tmp_path, monkeypatch):
    monkeypatch.setenv("SEMRUSH_API_KEY", "k")
    with patch("app.services.semrush_client._call_semrush", AsyncMock(return_value=FAKE_RESPONSE)):
        traffic = await get_traffic_6m("example.fr", cache_dir=tmp_path)
    assert traffic == [8200,6100,4800,3200,2100,1200]

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
```

**Step 2: Run to fail**

Run: `pytest tests/test_semrush_client.py -v`
Expected: FAIL.

**Step 3: Implement**

```python
# app/services/semrush_client.py
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
    except Exception as e:
        log.warning("semrush failed", extra={"domain": domain})
        return []
```

**Step 4: Run to pass**

Run: `pytest tests/test_semrush_client.py -v`
Expected: 4 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/services/semrush_client.py scraper-service/tests/test_semrush_client.py
git commit -m "feat(semrush): API client with tenacity retry + 24h cache + missing-key fallback"
```

---

## Task 22: Trend analyzer (scipy linregress)

**Files:**
- Create: `scraper-service/app/services/trend_analyzer.py`
- Test: `scraper-service/tests/test_trend_analyzer.py`

**Step 1: Write failing test**

```python
# tests/test_trend_analyzer.py
from app.services.trend_analyzer import classify_trend, compute_priority_score, map_verdict

def test_strong_decline():
    r = classify_trend([8200,6100,4800,3200,2100,1200])
    assert r["trend"] == "declining_strong"
    assert r["decline_rate_pct"] < -50

def test_moderate_decline():
    r = classify_trend([1000,950,900,850,800,750])
    assert r["trend"] == "declining_moderate"

def test_stable():
    r = classify_trend([1000,1000,1000,1000,1000,1000])
    assert r["trend"] == "stable"

def test_recovering():
    r = classify_trend([500,600,700,800,900,1000])
    assert r["trend"] == "recovering"

def test_all_zeros_unknown():
    r = classify_trend([0,0,0,0,0,0])
    assert r["trend"] == "unknown"

def test_too_few_unknown():
    r = classify_trend([100,200])
    assert r["trend"] == "unknown"

def test_priority_score_high_when_decline_strong():
    s = compute_priority_score(
        {"stage1_score": 70},
        {"trend": "declining_strong"},
        {"marketplace_verdict": "NOT_LISTED"},
    )
    # base 50 + 14 (70*0.2) + 25 (strong) = 89
    assert s == 89

def test_priority_score_marketplace_boost():
    s = compute_priority_score(
        {"stage1_score": 0},
        {"trend": "stable"},
        {"marketplace_verdict": "FOR_SALE"},
    )
    # base 50 + 40 (market) + 0 + -5 (stable) = 85
    assert s == 85

def test_priority_recovering_penalized():
    s = compute_priority_score(
        {"stage1_score": 40},
        {"trend": "recovering"},
        {"marketplace_verdict": "NOT_LISTED"},
    )
    # base 50 + 8 - 30 = 28
    assert s == 28

def test_verdict_mapping():
    assert map_verdict(90) == "HIGH PRIORITY"
    assert map_verdict(80) == "HIGH PRIORITY"
    assert map_verdict(79) == "MEDIUM PRIORITY"
    assert map_verdict(50) == "MEDIUM PRIORITY"
    assert map_verdict(49) == "LOW / SKIP"
```

**Step 2: Run to fail**

Run: `pytest tests/test_trend_analyzer.py -v`
Expected: FAIL.

**Step 3: Implement**

```python
# app/services/trend_analyzer.py
import numpy as np
from scipy.stats import linregress
from typing import Any

def classify_trend(monthly_visits: list[int]) -> dict[str, Any]:
    if len(monthly_visits) < 6 or all(v == 0 for v in monthly_visits):
        return {"trend": "unknown", "decline_rate_pct": 0.0, "slope": 0.0}

    y = np.array(list(reversed(monthly_visits)), dtype=float)  # oldest → newest
    x = np.arange(len(y), dtype=float)
    slope, *_ = linregress(x, y)

    decline_rate = ((y[-1] - y[0]) / y[0] * 100) if y[0] > 0 else 0.0

    if decline_rate < -50:   trend = "declining_strong"
    elif decline_rate < -15: trend = "declining_moderate"
    elif decline_rate < 5:   trend = "stable"
    else:                    trend = "recovering"

    return {"trend": trend, "decline_rate_pct": round(float(decline_rate), 1), "slope": round(float(slope), 2)}

def compute_priority_score(stage1_data: dict, trend_data: dict, marketplace_data: dict) -> int:
    score = 50
    if marketplace_data.get("marketplace_verdict") == "FOR_SALE":
        score += 40
    score += int(stage1_data.get("stage1_score", 0) * 0.2)
    t = trend_data.get("trend")
    if   t == "declining_strong":   score += 25
    elif t == "declining_moderate": score += 10
    elif t == "recovering":         score -= 30
    elif t == "stable":             score -= 5
    return max(0, min(100, int(score)))

def map_verdict(score: int) -> str:
    if score >= 80: return "HIGH PRIORITY"
    if score >= 50: return "MEDIUM PRIORITY"
    return "LOW / SKIP"
```

**Step 4: Run to pass**

Run: `pytest tests/test_trend_analyzer.py -v`
Expected: 10 PASSED.

**Step 5: Commit**

```bash
git add scraper-service/app/services/trend_analyzer.py scraper-service/tests/test_trend_analyzer.py
git commit -m "feat(stage2): trend classification + priority scoring + verdict mapping"
```

---

## Task 23: `/check-traffic` route

**Files:**
- Create: `scraper-service/app/routes/traffic.py`
- Modify: `scraper-service/app/main.py` (register)
- Test: `scraper-service/tests/test_route_traffic.py`

**Step 1: Write failing test**

```python
# tests/test_route_traffic.py
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

def test_traffic_happy_path():
    c = TestClient(app)
    with patch("app.routes.traffic.get_traffic_6m", AsyncMock(return_value=[8200,6100,4800,3200,2100,1200])):
        r = c.post("/check-traffic", json={"urls":["https://duverger-nb.com"]})
    assert r.status_code == 200
    body = r.json()[0]
    assert body["trend"] == "declining_strong"
    assert body["priority_score"] >= 80
    assert body["stage2_verdict"] == "HIGH PRIORITY"

def test_traffic_missing_data_returns_unknown():
    c = TestClient(app)
    with patch("app.routes.traffic.get_traffic_6m", AsyncMock(return_value=[])):
        r = c.post("/check-traffic", json={"urls":["https://x.fr"]})
    body = r.json()[0]
    assert body["trend"] == "unknown"
    # priority uses base (50) minus nothing = 50 → MEDIUM
    assert body["stage2_verdict"] in ("MEDIUM PRIORITY", "LOW / SKIP")

def test_traffic_accepts_optional_stage1_and_marketplace_payload():
    c = TestClient(app)
    with patch("app.routes.traffic.get_traffic_6m", AsyncMock(return_value=[8000,4000,2000,1000,500,200])):
        r = c.post("/check-traffic", json={
            "urls":["https://x.fr"],
            "enrichment": {"https://x.fr": {"stage1_score": 70, "marketplace_verdict":"FOR_SALE"}}
        })
    body = r.json()[0]
    # base 50 + 40 (marketplace) + 14 (stage1*0.2) + 25 (strong) = 129 → capped 100
    assert body["priority_score"] == 100
```

**Step 2: Run to fail**

Run: `pytest tests/test_route_traffic.py -v`
Expected: FAIL.

**Step 3: Extend `CheckRequest` in `app/models/schemas.py`**

```python
# Add to CheckRequest:
class CheckRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=200)
    enrichment: dict[str, dict] | None = None
```

**Step 4: Implement `app/routes/traffic.py`**

```python
# app/routes/traffic.py
from urllib.parse import urlparse
from fastapi import APIRouter
from app.models.schemas import CheckRequest, TrafficResult
from app.services.semrush_client import get_traffic_6m
from app.services.trend_analyzer import classify_trend, compute_priority_score, map_verdict
from app.utils.logger import get_logger

router = APIRouter()
log = get_logger(__name__)

@router.post("/check-traffic", response_model=list[TrafficResult])
async def check_traffic(req: CheckRequest):
    out: list[TrafficResult] = []
    enrichment = req.enrichment or {}
    for url in req.urls:
        domain = (urlparse(url).hostname or "").removeprefix("www.")
        try:
            traffic = await get_traffic_6m(domain)
            trend = classify_trend(traffic)
            stage1 = enrichment.get(url, {}).get("stage1", {}) or {"stage1_score": enrichment.get(url, {}).get("stage1_score", 0)}
            market = enrichment.get(url, {}).get("marketplace", {}) or {"marketplace_verdict": enrichment.get(url, {}).get("marketplace_verdict", "NOT_LISTED")}
            score = compute_priority_score(stage1, trend, market)
            verdict = map_verdict(score)
            summary = f"Traffic {trend['decline_rate_pct']}% over 6m. {trend['trend']}." if traffic else "No traffic data."
            out.append(TrafficResult(
                url=url, traffic_6m=traffic, trend=trend["trend"],
                decline_rate_pct=trend["decline_rate_pct"],
                priority_score=score, stage2_verdict=verdict, summary=summary,
            ))
        except Exception as e:
            log.exception("stage2 failed", extra={"url": url, "stage": 2})
            out.append(TrafficResult(
                url=url, traffic_6m=[], trend="unknown",
                decline_rate_pct=0.0, priority_score=0,
                stage2_verdict="ERROR", summary="error", error=str(e),
            ))
    return out
```

**Step 5: Register in `app/main.py`**

```python
from app.routes import traffic
app.include_router(traffic.router)
```

**Step 6: Run to pass**

Run: `pytest tests/test_route_traffic.py -v`
Expected: 3 PASSED.

**Step 7: Commit**

```bash
git add scraper-service/app/routes/traffic.py scraper-service/app/main.py scraper-service/app/models/schemas.py scraper-service/tests/test_route_traffic.py
git commit -m "feat(route): /check-traffic with enrichment-aware priority scoring"
```

---

## Task 24: Health endpoint test + full app smoke test

**Files:**
- Test: `scraper-service/tests/test_health.py`

**Step 1: Write test**

```python
# tests/test_health.py
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
```

**Step 2: Run, expect pass**

Run: `pytest tests/test_health.py -v`
Expected: 2 PASSED.

**Step 3: Commit**

```bash
git add scraper-service/tests/test_health.py
git commit -m "test(health): /health endpoint + OpenAPI coverage guard"
```

---

## Task 25: Dockerfile

**Files:**
- Create: `scraper-service/Dockerfile`
- Create: `scraper-service/.dockerignore`

**Step 1: Write `.dockerignore`**

```
.git
.venv
venv
__pycache__
*.pyc
.pytest_cache
.cache
logs
tests/fixtures/*.html
.env
```

**Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps for lxml + Playwright (crawl4ai)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libxml2-dev libxslt1-dev curl \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -u 1000 scraper

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN python -m playwright install chromium

COPY app ./app

RUN mkdir -p /app/.cache /app/logs && chown -R scraper:scraper /app
USER scraper

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 3: Local build smoke test**

Run: `docker build -t scraper-service:dev scraper-service/`
Expected: build succeeds (may take 3–5 min for playwright download).

**Step 4: Run container and probe health**

Run:
```bash
docker run -d --name scraper-dev -p 8000:8000 -e SEMRUSH_API_KEY=test scraper-service:dev
sleep 10
curl http://localhost:8000/health
docker logs scraper-dev
docker rm -f scraper-dev
```
Expected: `{"status":"ok"}`.

**Step 5: Commit**

```bash
git add scraper-service/Dockerfile scraper-service/.dockerignore
git commit -m "build(docker): python:3.11-slim + playwright + non-root + healthcheck"
```

---

## Task 26: docker-compose.yml with Traefik labels

**Files:**
- Create: `scraper-service/docker-compose.yml`

**Step 1: Write compose file**

```yaml
services:
  scraper:
    build: .
    container_name: scraper-service
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./.cache:/app/.cache
      - ./logs:/app/logs
    networks:
      - web
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=web"
      - "traefik.http.routers.scraper.rule=Host(`${SCRAPER_DOMAIN}`)"
      - "traefik.http.routers.scraper.entrypoints=websecure"
      - "traefik.http.routers.scraper.tls.certresolver=le"
      - "traefik.http.services.scraper.loadbalancer.server.port=8000"
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

networks:
  web:
    external: true
```

**Step 2: Validate compose syntax**

Run: `docker compose -f scraper-service/docker-compose.yml config`
Expected: parsed output, no errors (assumes SCRAPER_DOMAIN in .env; set a placeholder for local).

**Step 3: Commit**

```bash
git add scraper-service/docker-compose.yml
git commit -m "build(compose): Traefik-routed scraper service with health + persistent volumes"
```

---

## Task 27: README + Traefik deployment notes

**Files:**
- Create: `scraper-service/README.md`

**Step 1: Write README**

```markdown
# Acquisition Scraper Service

FastAPI service used by n8n to filter French ecom stores through a 4-stage acquisition funnel.

## Endpoints

- `POST /check-marketplaces` — Stage 0.5: DotMarket + Flippa cross-reference
- `POST /check-activity`     — Stage 1: blog freshness + Trustpilot velocity
- `POST /check-traffic`      — Stage 2: Semrush 6-month trend
- `GET  /health`             — container healthcheck

## Local development

```bash
python -m venv .venv
.venv/Scripts/activate           # or .venv/bin/activate on Linux
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
uvicorn app.main:app --reload --port 8000
pytest
```

## Deploy to Hostinger VPS

Assumes Traefik (network `web`) and n8n already running.

```bash
scp -r scraper-service/ user@vps:/srv/scraper-service/
ssh user@vps
cd /srv/scraper-service
cp .env.example .env     # then fill in SEMRUSH_API_KEY + SCRAPER_DOMAIN
docker compose up -d --build
docker compose logs -f scraper
curl -H "Host: scraper.yourdomain.com" https://scraper.yourdomain.com/health
```

### Traefik snippet

If Traefik is configured via a static file, no additions are needed — the compose labels register the router automatically. For the dynamic file config variant:

```yaml
http:
  routers:
    scraper:
      rule: "Host(`scraper.yourdomain.com`)"
      entryPoints: [websecure]
      tls:
        certResolver: le
      service: scraper@docker
```

## Re-run / tuning runbook

- **Clear marketplace cache**: `rm -r scraper-service/.cache/dotmarket scraper-service/.cache/flippa`
- **Clear Semrush cache**: `rm -r scraper-service/.cache/semrush`
- **Tune PELT penalty**: `pen=10` in `app/services/pattern_analyzer.py`. Raise to reduce false breaks, lower to detect gentler slowdowns. Run `pytest tests/test_pattern_analyzer_pelt.py` after any change.
- **Tune stage1 threshold**: `stage1_verdict` cutoff in `app/services/pattern_analyzer.py` (default 40). Raising narrows the funnel.

## Library wrapping contracts

| Module | Wraps | Test file |
|---|---|---|
| `blog_fetcher` | `feedparser` + `lxml` + `crawl4ai` | `test_blog_fetcher_*.py` |
| `pattern_analyzer` | `ruptures.Pelt(model="rbf")` | `test_pattern_analyzer_*.py` |
| `review_scraper` | `trustpilot-scraper` | `test_review_scraper.py` |
| `trend_analyzer` | `scipy.stats.linregress` | `test_trend_analyzer.py` |
| `semrush_client` | HTTP + `tenacity` + `TTLCache` | `test_semrush_client.py` |

Do **not** replace these libraries without updating both code and tests together.
```

**Step 2: Commit**

```bash
git add scraper-service/README.md
git commit -m "docs(readme): deployment + Traefik + library wrapping contracts"
```

---

## Task 28: n8n workflow JSON

**Files:**
- Create: `n8n/workflow.json`
- Create: `n8n/README.md`

**Step 1: Write `n8n/workflow.json`**

This is the n8n export format. Use the template below; import into n8n and wire credentials (Google Sheets OAuth2, Telegram Bot token, scraper service base URL).

```json
{
  "name": "FR Ecom Acquisition Pipeline",
  "nodes": [
    {
      "parameters": { "rule": { "interval": [ { "field": "hours", "hoursInterval": 24 } ] } },
      "id": "n-schedule",
      "name": "Nightly 02:00",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.1,
      "position": [ 100, 300 ]
    },
    {
      "parameters": {
        "documentId": { "__rl": true, "mode": "list", "value": "SHEET_ID" },
        "sheetName": { "__rl": true, "mode": "list", "value": "Sheet1" }
      },
      "id": "n-read",
      "name": "Read Sheet",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4,
      "position": [ 300, 300 ]
    },
    {
      "parameters": {
        "jsCode": "const rows = $input.all();\nconst seen = new Set();\nreturn rows.map(row => {\n  const d = row.json;\n  const types = (d['Types']||'').toLowerCase();\n  const statut = (d['Statut scraping']||'').trim();\n  const site = (d['Site web']||'').trim();\n  const avis = parseInt(d['Nb Avis'])||0;\n  const note = parseFloat(d['Note Google'])||0;\n  let domain = null;\n  try { domain = new URL(site).hostname.replace(/^www\\./,''); } catch {}\n  if (statut && !statut.startsWith('S0:')) return { json: { ...d, skip:true, reason:'already processed' } };\n  if (!types.includes('ecommerce')) return { json: { ...d, skip:true, reason:'physical only' } };\n  if (!site || !site.startsWith('http') || !domain) return { json: { ...d, skip:true, reason:'no website' } };\n  if (avis > 500 && note > 4.5) return { json: { ...d, skip:true, reason:'obviously healthy' } };\n  if (seen.has(domain)) return { json: { ...d, skip:true, reason:'duplicate domain' } };\n  seen.add(domain);\n  return { json: { ...d, skip:false, domain, reason:'qualified' } };\n});"
      },
      "id": "n-stage0",
      "name": "Stage 0 Pre-qual",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [ 500, 300 ]
    },
    {
      "parameters": {
        "conditions": { "conditions": [ { "leftValue": "={{$json.skip}}", "rightValue": false, "operator": { "type": "boolean", "operation": "equals" } } ] }
      },
      "id": "n-filter0",
      "name": "Keep Qualified",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [ 700, 300 ]
    },
    {
      "parameters": {
        "aggregate": "aggregateIndividualFields",
        "fieldsToAggregate": { "fieldToAggregate": [ { "fieldToAggregate": "={{$json['Site web']}}", "renameField": "urls" } ] }
      },
      "id": "n-aggregate",
      "name": "Collect URLs",
      "type": "n8n-nodes-base.aggregate",
      "typeVersion": 1,
      "position": [ 900, 260 ]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "={{$env.SCRAPER_BASE}}/check-marketplaces",
        "sendBody": true, "contentType": "json",
        "jsonBody": "={\n  \"urls\": {{$json.urls}}\n}"
      },
      "id": "n-market",
      "name": "Stage 0.5 Marketplaces",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [ 1100, 260 ]
    },
    {
      "parameters": { "batchSize": 10 },
      "id": "n-split",
      "name": "Batch 10",
      "type": "n8n-nodes-base.splitInBatches",
      "typeVersion": 3,
      "position": [ 1300, 260 ]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "={{$env.SCRAPER_BASE}}/check-activity",
        "sendBody": true, "contentType": "json",
        "jsonBody": "={\n  \"urls\": {{$json.urls}}\n}"
      },
      "id": "n-activity",
      "name": "Stage 1 Activity",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [ 1500, 260 ]
    },
    {
      "parameters": {
        "conditions": { "conditions": [
          { "leftValue": "={{$json.stage1_verdict}}", "rightValue": "CANDIDATE", "operator": { "type": "string", "operation": "equals" } }
        ] }
      },
      "id": "n-filter1",
      "name": "Keep Candidates",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [ 1700, 260 ]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "={{$env.SCRAPER_BASE}}/check-traffic",
        "sendBody": true, "contentType": "json",
        "jsonBody": "={\n  \"urls\": [{{$json.url}}],\n  \"enrichment\": {\n    \"{{$json.url}}\": {\n      \"stage1_score\": {{$json.stage1_score}},\n      \"marketplace_verdict\": \"{{$json.marketplace_verdict || 'NOT_LISTED'}}\"\n    }\n  }\n}"
      },
      "id": "n-traffic",
      "name": "Stage 2 Traffic",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [ 1900, 260 ]
    },
    {
      "parameters": {
        "documentId": { "__rl": true, "mode": "list", "value": "SHEET_ID" },
        "sheetName": { "__rl": true, "mode": "list", "value": "Sheet1" },
        "operation": "update",
        "columns": { "mappingMode": "defineBelow",
          "value": {
            "Site web": "={{$json.url}}",
            "Statut scraping": "={{ $json.stage1_verdict === 'ERROR' ? ('ERROR: ' + ($json.error || 'unknown')) : ('S1: ' + $json.stage1_verdict + ' (' + $json.stage1_score + ')') }}",
            "Check Semrush (intéressant pour racheter?)": "={{ $json.priority_score >= 50 ? ('Oui (' + $json.priority_score + ') — ' + ($json.priority_score>=80?'HIGH':'MED')) : 'Non' }}",
            "Commentaire": "={{$json.summary}}"
          }
        }
      },
      "id": "n-write",
      "name": "Write Back",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4,
      "position": [ 2100, 260 ]
    },
    {
      "parameters": {
        "conditions": { "conditions": [
          { "leftValue": "={{$json.priority_score}}", "rightValue": 50, "operator": { "type": "number", "operation": "gte" } }
        ] }
      },
      "id": "n-filter2",
      "name": "Keep Priority ≥50",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [ 2300, 260 ]
    },
    {
      "parameters": {
        "chatId": "={{$env.TELEGRAM_CHAT_ID}}",
        "text": "=Top candidate: {{$json.url}}\nScore: {{$json.priority_score}} — {{$json.stage2_verdict}}\n{{$json.summary}}"
      },
      "id": "n-telegram",
      "name": "Telegram Notify",
      "type": "n8n-nodes-base.telegram",
      "typeVersion": 1.2,
      "position": [ 2500, 260 ]
    }
  ],
  "connections": {
    "Nightly 02:00": { "main": [ [ { "node": "Read Sheet", "type": "main", "index": 0 } ] ] },
    "Read Sheet": { "main": [ [ { "node": "Stage 0 Pre-qual", "type": "main", "index": 0 } ] ] },
    "Stage 0 Pre-qual": { "main": [ [ { "node": "Keep Qualified", "type": "main", "index": 0 } ] ] },
    "Keep Qualified": { "main": [ [ { "node": "Collect URLs", "type": "main", "index": 0 } ], [] ] },
    "Collect URLs": { "main": [ [ { "node": "Stage 0.5 Marketplaces", "type": "main", "index": 0 } ] ] },
    "Stage 0.5 Marketplaces": { "main": [ [ { "node": "Batch 10", "type": "main", "index": 0 } ] ] },
    "Batch 10": { "main": [ [ { "node": "Stage 1 Activity", "type": "main", "index": 0 } ] ] },
    "Stage 1 Activity": { "main": [ [ { "node": "Keep Candidates", "type": "main", "index": 0 } ] ] },
    "Keep Candidates": { "main": [ [ { "node": "Stage 2 Traffic", "type": "main", "index": 0 } ], [] ] },
    "Stage 2 Traffic": { "main": [ [ { "node": "Write Back", "type": "main", "index": 0 } ] ] },
    "Write Back": { "main": [ [ { "node": "Keep Priority ≥50", "type": "main", "index": 0 } ] ] },
    "Keep Priority ≥50": { "main": [ [ { "node": "Telegram Notify", "type": "main", "index": 0 } ], [] ] }
  },
  "settings": { "executionOrder": "v1" }
}
```

**Step 2: Write `n8n/README.md`**

```markdown
# n8n workflow

## Import
1. In n8n UI → **Workflows** → **Import from file** → upload `workflow.json`.
2. Replace `SHEET_ID` in both Google Sheets nodes with the real sheet ID.
3. Set environment variables in n8n:
   - `SCRAPER_BASE` = `https://scraper.yourdomain.com`
   - `TELEGRAM_CHAT_ID` = your chat/group ID
4. Attach credentials:
   - Google Sheets OAuth2
   - Telegram Bot (API token)
5. Activate the workflow.

## Test with 10 rows
Manually trigger (Execute Workflow). Confirm Stage 0 tags propagate to the sheet before leaving it running nightly.

## Error branches
Both IF nodes have a `false` branch left dangling — n8n will stop the item silently there. To persist failures, extend `Write Back` to accept `ERROR: <reason>` by listening on the `false` branch of `Keep Candidates` and writing `Statut scraping = "ERROR: stage1 eliminated"`.
```

**Step 3: Commit**

```bash
git add n8n/
git commit -m "feat(n8n): acquisition pipeline workflow.json + import/setup readme"
```

---

## Task 29: Sample rows fixture + end-to-end integration test

**Files:**
- Create: `scraper-service/tests/fixtures/sample_rows.json`
- Test: `scraper-service/tests/test_e2e_pipeline.py`

**Step 1: Create `tests/fixtures/sample_rows.json`** (5 realistic rows)

```json
[
  {
    "Nom": "DUVERGER CBD", "Types": "Boutique Physique, Ecommerce",
    "Site web": "https://duverger-nb.com", "Note Google": 4.8, "Nb Avis": 170,
    "Statut scraping": ""
  },
  {
    "Nom": "CBD Dormant", "Types": "Ecommerce",
    "Site web": "https://dormant-cbd.fr", "Note Google": 4.2, "Nb Avis": 35,
    "Statut scraping": ""
  },
  {
    "Nom": "Obviously Healthy", "Types": "Ecommerce",
    "Site web": "https://big-cbd.fr", "Note Google": 4.9, "Nb Avis": 1200,
    "Statut scraping": ""
  },
  {
    "Nom": "Physical Only", "Types": "Boutique Physique",
    "Site web": "https://shop-only.fr", "Note Google": 4.5, "Nb Avis": 80,
    "Statut scraping": ""
  },
  {
    "Nom": "No Website", "Types": "Ecommerce",
    "Site web": "", "Note Google": 4.0, "Nb Avis": 10,
    "Statut scraping": ""
  }
]
```

**Step 2: Write e2e test**

```python
# tests/test_e2e_pipeline.py
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

ROWS = json.loads((Path(__file__).parent / "fixtures" / "sample_rows.json").read_text())

def _qualified_urls(rows):
    # Mirrors Stage 0 JS logic
    seen = set()
    out = []
    for d in rows:
        types = d["Types"].lower()
        if not d.get("Statut scraping","").strip():
            if "ecommerce" not in types: continue
            site = d["Site web"]
            if not site.startswith("http"): continue
            if d["Nb Avis"] > 500 and d["Note Google"] > 4.5: continue
            from urllib.parse import urlparse
            dom = urlparse(site).hostname.replace("www.","")
            if dom in seen: continue
            seen.add(dom)
            out.append(site)
    return out

def test_stage0_filters_to_two_urls():
    urls = _qualified_urls(ROWS)
    assert len(urls) == 2
    assert "https://duverger-nb.com" in urls
    assert "https://dormant-cbd.fr" in urls

def test_e2e_happy_path():
    c = TestClient(app)
    urls = _qualified_urls(ROWS)
    # Stage 0.5: one match
    dm = [{"url":"https://dotmarket.eu/1","niche":"CBD",
           "domain_hint":"dormant cbd","asking_price_eur":25000,"traffic_range":"3k-5k"}]
    with patch("app.routes.marketplaces.fetch_dotmarket_listings", AsyncMock(return_value=dm)), \
         patch("app.routes.marketplaces.fetch_flippa_listings", AsyncMock(return_value=[])):
        r1 = c.post("/check-marketplaces", json={"urls": urls})
    market = {row["url"]: row for row in r1.json()}
    assert market["https://dormant-cbd.fr"]["marketplace_verdict"] == "FOR_SALE"

    # Stage 1
    from datetime import datetime, timedelta
    stale = [datetime(2024,1,1) + timedelta(days=7*i) for i in range(6)]
    with patch("app.routes.activity.fetch_post_dates", AsyncMock(return_value=stale)), \
         patch("app.routes.activity.check_trustpilot_velocity", return_value={"trustpilot_found":True,"recent_reviews_14d":0,"recent_reviews_30d":1}), \
         patch("app.routes.activity.check_social", AsyncMock(return_value=None)):
        r2 = c.post("/check-activity", json={"urls": urls})
    assert all(row["stage1_verdict"] in ("CANDIDATE", "ERROR") for row in r2.json())

    # Stage 2 with enrichment
    with patch("app.routes.traffic.get_traffic_6m", AsyncMock(return_value=[8200,6100,4800,3200,2100,1200])):
        r3 = c.post("/check-traffic", json={
            "urls": urls,
            "enrichment": {
                u: {"stage1_score": 70, "marketplace_verdict": market[u]["marketplace_verdict"]}
                for u in urls
            }
        })
    # FOR_SALE row should hit HIGH PRIORITY
    dormant = next(x for x in r3.json() if x["url"] == "https://dormant-cbd.fr")
    assert dormant["stage2_verdict"] == "HIGH PRIORITY"
```

**Step 3: Run**

Run: `pytest tests/test_e2e_pipeline.py -v`
Expected: 2 PASSED.

**Step 4: Commit**

```bash
git add scraper-service/tests/test_e2e_pipeline.py scraper-service/tests/fixtures/sample_rows.json
git commit -m "test(e2e): 5-row fixture + full pipeline integration test"
```

---

## Task 30: Final full-suite run + cleanup

**Step 1: Run the complete suite**

Run: `pytest -v`
Expected: **all tests pass**, ~50+ tests collected across 15+ files.

**Step 2: Sanity-check acceptance criteria (manual)**

Verify each item from spec §12:
- [ ] `docker compose up` starts and `/health` returns 200
- [ ] `feedparser` handles all 3 fixture feeds (WordPress, empty, too-short)
- [ ] `ruptures.Pelt` detects the weekly→silence change point (Task 12)
- [ ] `trustpilot-scraper` 404 returns gracefully (Task 13)
- [ ] DotMarket catalog fetched once per run (Task 17)
- [ ] `/check-activity` handles 50 URLs without crashing — add ad-hoc load test:
  ```bash
  curl -X POST http://localhost:8000/check-activity \
       -H 'Content-Type: application/json' \
       -d "{\"urls\": [$(python -c 'print(",".join([chr(34)+"https://example"+str(i)+".fr"+chr(34) for i in range(50)]))')]}"
  ```
- [ ] Semrush client retries on 429 via tenacity (Task 21)
- [ ] Sheet write-back preserves other columns (n8n update mode uses `Site web` as match key — verify in n8n UI)
- [ ] Randomized 2–7s delay — confirm in structured logs when scraping live sites

**Step 3: Tag the milestone**

```bash
git tag v0.1.0-plan-complete
```

**Step 4: Commit any lingering docs**

```bash
git add -A
git commit -m "chore: v0.1.0 implementation complete per docs/plans/2026-04-19-french-ecom-acquisition-pipeline.md"
```

---

## Open Questions (must resolve before production deploy)

1. **Semrush API tier** — confirm call volume covers 200 domains/run at €50 budget. The plan assumes Semrush's `domain_organic` endpoint; if a different tier/SKU is licensed, `semrush_client.py::_call_semrush` params need updating.
2. **Social check** — spec defaults OFF (Task 14). Flip `ENABLE_SOCIAL_CHECK=true` in v2 and implement IG/FB footer extraction.
3. **Notification channel** — plan uses Telegram (Task 28). Swap to email by replacing `Telegram Notify` node with `Send Email` and providing SMTP creds.
4. **Marketplace scraping legality** — review DotMarket and Flippa ToS before enabling the `/check-marketplaces` endpoint on the VPS. If disallowed, gate the endpoint behind an env flag `ENABLE_MARKETPLACE_SCRAPING=false` and skip Stage 0.5.

---

## Out of Scope (v1)

Spec §16: no outreach automation, no longitudinal v2 tracking, no multi-language, no UI dashboard, no Ubersuggest/Similarweb fallback.
