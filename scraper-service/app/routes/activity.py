import asyncio
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
from app.utils.logger import get_logger

router = APIRouter()
log = get_logger(__name__)

MAX_CONCURRENCY = 5


async def _process(url: str) -> dict:
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
            # Spec §8.1 step 4: no blog → auto-CANDIDATE with score 100
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

        return {
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
    except Exception as e:
        log.exception("stage1 failed", extra={"url": url, "stage": 1})
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


@router.post("/check-activity", response_model=list[ActivityResult])
async def check_activity(req: CheckRequest):
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def guarded(u: str):
        async with sem:
            return await _process(u)

    return await asyncio.gather(*[guarded(u) for u in req.urls])
