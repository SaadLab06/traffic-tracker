import asyncio
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter

from app.models.schemas import ActivityResult, CheckRequest
from app.services.blog_fetcher import fetch_post_dates
from app.services.pattern_analyzer import (
    analyze_blog_pattern,
    compute_stage1_score,
    stage1_verdict,
)
from app.services.review_scraper import check_trustpilot_velocity
from app.services.social_checker import check_social
from app.utils.cache import TTLCache
from app.utils.logger import get_logger

router = APIRouter()
log = get_logger(__name__)

MAX_CONCURRENCY = 20
ACTIVITY_CACHE_TTL = int(os.getenv("ACTIVITY_CACHE_TTL", "86400"))  # 24h
_activity_cache = TTLCache(Path(".cache/activity"), ttl_seconds=ACTIVITY_CACHE_TTL)


async def _compute(url: str) -> dict:
    t0 = time.perf_counter()
    try:
        dates = await fetch_post_dates(url)
        if dates is None:
            blog = {
                "blog_pattern": "none",
                "avg_gap_days": None,
                "days_since_last_post": None,
                "change_points_detected": 0,
                "change_point_date": None,
                "pattern_broken": True,
                "stage1_score_contrib": 0,
            }
        else:
            blog = analyze_blog_pattern(dates)

        domain = urlparse(url).hostname or ""
        reviews = await check_trustpilot_velocity(domain.removeprefix("www."))
        social = await check_social(url)

        if blog["blog_pattern"] == "none":
            score = 100
            verdict = "CANDIDATE"
        else:
            score = compute_stage1_score(blog, reviews, social)
            verdict = stage1_verdict(score)

        summary_bits: list[str] = []
        if blog["blog_pattern"] == "none":
            summary_bits.append("no blog detected")
        else:
            state = "broken" if blog["pattern_broken"] else "active"
            summary_bits.append(f"blog: {blog['blog_pattern']} {state}")
        summary_bits.append(f"{reviews['recent_reviews_30d']} reviews 30d")
        if social and social.get("social_active") is False:
            summary_bits.append("social dead")

        result = {
            "url": url,
            "stage1_verdict": verdict,
            "stage1_score": score,
            **{
                k: blog[k]
                for k in (
                    "blog_pattern",
                    "avg_gap_days",
                    "days_since_last_post",
                    "change_points_detected",
                    "change_point_date",
                    "pattern_broken",
                )
            },
            "recent_reviews_14d": reviews["recent_reviews_14d"],
            "recent_reviews_30d": reviews["recent_reviews_30d"],
            "social_active": (social or {}).get("social_active"),
            "summary": " | ".join(summary_bits),
        }
        log.info(
            "stage1 ok",
            extra={"url": url, "stage": 1, "duration_ms": int((time.perf_counter() - t0) * 1000), "verdict": verdict},
        )
        return result
    except Exception as e:
        log.exception(
            "stage1 failed",
            extra={"url": url, "stage": 1, "duration_ms": int((time.perf_counter() - t0) * 1000)},
        )
        return {
            "url": url,
            "stage1_verdict": "ERROR",
            "stage1_score": 0,
            "blog_pattern": "insufficient_data",
            "pattern_broken": False,
            "recent_reviews_14d": 0,
            "recent_reviews_30d": 0,
            "summary": "error",
            "error": str(e),
        }


async def _process(url: str) -> dict:
    cache_key = f"activity:{url}"
    cached = _activity_cache.get(cache_key)
    if cached is not None:
        log.info("stage1 cache hit", extra={"url": url, "stage": 1, "cache_hit": True})
        return cached
    result = await _compute(url)
    if result.get("stage1_verdict") != "ERROR":
        _activity_cache.set(cache_key, result)
    return result


@router.post("/check-activity", response_model=list[ActivityResult])
async def check_activity(req: CheckRequest):
    t0 = time.perf_counter()
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def guarded(u: str):
        async with sem:
            return await _process(u)

    results = await asyncio.gather(*[guarded(u) for u in req.urls])
    log.info(
        "check-activity batch done",
        extra={
            "stage": 1,
            "input_url_count": len(req.urls),
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        },
    )
    return results
