from app.services.trend_analyzer import classify_trend, compute_priority_score, map_verdict


def test_strong_decline():
    r = classify_trend([8200, 6100, 4800, 3200, 2100, 1200])
    assert r["trend"] == "declining_strong"
    assert r["decline_rate_pct"] < -50


def test_moderate_decline():
    r = classify_trend([1000, 950, 900, 850, 800, 750])
    assert r["trend"] == "declining_moderate"


def test_stable():
    r = classify_trend([1000, 1000, 1000, 1000, 1000, 1000])
    assert r["trend"] == "stable"


def test_recovering():
    r = classify_trend([500, 600, 700, 800, 900, 1000])
    assert r["trend"] == "recovering"


def test_all_zeros_unknown():
    r = classify_trend([0, 0, 0, 0, 0, 0])
    assert r["trend"] == "unknown"


def test_too_few_unknown():
    r = classify_trend([100, 200])
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
