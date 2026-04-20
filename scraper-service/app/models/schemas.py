from typing import Literal, Optional
from pydantic import BaseModel, Field, HttpUrl

class CheckRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=200)
    enrichment: dict[str, dict] | None = None

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
