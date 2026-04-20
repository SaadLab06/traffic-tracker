from datetime import datetime, timedelta
from app.services.pattern_analyzer import analyze_blog_pattern


def _dates(gaps_days: list[int], anchor=datetime(2025, 3, 10)) -> list[datetime]:
    out = [anchor]
    for g in gaps_days:
        anchor = anchor - timedelta(days=g)
        out.append(anchor)
    return out


def test_insufficient_data_flags_broken():
    d = analyze_blog_pattern([datetime(2025, 3, 1)])
    assert d["blog_pattern"] == "insufficient_data"
    assert d["pattern_broken"] is True
    assert d["stage1_score_contrib"] == 35


def test_weekly_pattern_detected():
    dates = _dates([7, 7, 7, 7, 7, 7, 7])
    d = analyze_blog_pattern(dates)
    assert d["blog_pattern"] == "weekly"


def test_daily_pattern_detected():
    dates = _dates([1, 1, 1, 1, 1, 1, 1])
    d = analyze_blog_pattern(dates)
    assert d["blog_pattern"] == "daily"


def test_monthly_pattern_detected():
    dates = _dates([30, 30, 30, 30, 30])
    d = analyze_blog_pattern(dates)
    assert d["blog_pattern"] == "monthly"
