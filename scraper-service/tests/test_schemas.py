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
