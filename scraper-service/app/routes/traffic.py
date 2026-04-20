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
            entry = enrichment.get(url, {})
            stage1 = entry.get("stage1", {}) or {"stage1_score": entry.get("stage1_score", 0)}
            market = entry.get("marketplace", {}) or {"marketplace_verdict": entry.get("marketplace_verdict", "NOT_LISTED")}
            score = compute_priority_score(stage1, trend, market)
            verdict = map_verdict(score)
            summary = (
                f"Traffic {trend['decline_rate_pct']}% over 6m. {trend['trend']}."
                if traffic
                else "No traffic data."
            )
            out.append(TrafficResult(
                url=url,
                traffic_6m=traffic,
                trend=trend["trend"],
                decline_rate_pct=trend["decline_rate_pct"],
                priority_score=score,
                stage2_verdict=verdict,
                summary=summary,
            ))
        except Exception as e:
            log.exception("stage2 failed", extra={"url": url, "stage": 2})
            out.append(TrafficResult(
                url=url,
                traffic_6m=[],
                trend="unknown",
                decline_rate_pct=0.0,
                priority_score=0,
                stage2_verdict="ERROR",
                summary="error",
                error=str(e),
            ))
    return out
