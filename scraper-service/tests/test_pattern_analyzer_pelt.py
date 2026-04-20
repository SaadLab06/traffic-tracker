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
    # No catastrophic break — one of these two must hold
    assert d["stage1_score_contrib"] == 0 or d["pattern_broken"] is False

def test_stale_blog_flagged_even_without_change_point():
    # 5 weekly posts ending a year ago
    dates = [datetime(2024, 1, 1) + timedelta(days=7*i) for i in range(5)]
    d = analyze_blog_pattern(dates)
    assert d["pattern_broken"] is True
