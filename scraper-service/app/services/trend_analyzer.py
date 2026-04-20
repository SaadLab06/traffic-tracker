import numpy as np
from scipy.stats import linregress
from typing import Any


def classify_trend(monthly_visits: list[int]) -> dict[str, Any]:
    if len(monthly_visits) < 6 or all(v == 0 for v in monthly_visits):
        return {"trend": "unknown", "decline_rate_pct": 0.0, "slope": 0.0}

    y = np.array(monthly_visits, dtype=float)
    x = np.arange(len(y), dtype=float)
    slope, *_ = linregress(x, y)

    decline_rate = ((y[-1] - y[0]) / y[0] * 100) if y[0] > 0 else 0.0

    if decline_rate < -50:
        trend = "declining_strong"
    elif decline_rate < -15:
        trend = "declining_moderate"
    elif decline_rate < 5:
        trend = "stable"
    else:
        trend = "recovering"

    return {
        "trend": trend,
        "decline_rate_pct": round(float(decline_rate), 1),
        "slope": round(float(slope), 2),
    }


def compute_priority_score(
    stage1_data: dict, trend_data: dict, marketplace_data: dict
) -> int:
    score = 50
    if marketplace_data.get("marketplace_verdict") == "FOR_SALE":
        score += 40
    score += int(stage1_data.get("stage1_score", 0) * 0.2)
    t = trend_data.get("trend")
    if t == "declining_strong":
        score += 25
    elif t == "declining_moderate":
        score += 10
    elif t == "recovering":
        score -= 30
    elif t == "stable":
        score -= 5
    return max(0, min(100, int(score)))


def map_verdict(score: int) -> str:
    if score >= 80:
        return "HIGH PRIORITY"
    if score >= 50:
        return "MEDIUM PRIORITY"
    return "LOW / SKIP"
