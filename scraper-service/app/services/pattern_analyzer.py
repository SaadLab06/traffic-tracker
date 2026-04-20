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
        (sorted_dates[i + 1] - sorted_dates[i]).total_seconds() / 86400
        for i in range(len(sorted_dates) - 1)
    ])
    median_gap = float(np.median(gaps))
    if median_gap < 2:
        pattern = "daily"
    elif median_gap < 10:
        pattern = "weekly"
    elif median_gap < 20:
        pattern = "biweekly"
    elif median_gap < 45:
        pattern = "monthly"
    else:
        pattern = "irregular"

    signal = gaps.reshape(-1, 1)
    try:
        algo = rpt.Pelt(model="rbf").fit(signal)
        # pen tuned to 2 on ruptures 1.0.6 — see tests/test_pattern_analyzer_pelt.py
        change_points = [cp for cp in algo.predict(pen=2) if cp < len(signal)]
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
