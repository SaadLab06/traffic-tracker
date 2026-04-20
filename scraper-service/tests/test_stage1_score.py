from app.services.pattern_analyzer import compute_stage1_score


def test_no_blog_max_out_at_75():
    s = compute_stage1_score(
        {"blog_pattern": "none", "stage1_score_contrib": 40},
        {"recent_reviews_30d": 0},
        None,
    )
    # 40 (broken) + 35 (none) + 20 (zero reviews) = 95
    assert s == 95


def test_healthy_active_shop_below_threshold():
    s = compute_stage1_score(
        {"blog_pattern": "weekly", "stage1_score_contrib": 0},
        {"recent_reviews_30d": 12},
        None,
    )
    assert s == 0


def test_verdict_threshold_boundary():
    from app.services.pattern_analyzer import stage1_verdict
    assert stage1_verdict(40) == "CANDIDATE"
    assert stage1_verdict(39) == "ELIMINATED"


def test_social_boost_applies():
    s = compute_stage1_score(
        {"blog_pattern": "weekly", "stage1_score_contrib": 0},
        {"recent_reviews_30d": 1},
        {"social_active": False},
    )
    # 10 (≤2 reviews) + 15 (social dead) = 25
    assert s == 25


def test_score_capped_at_100():
    s = compute_stage1_score(
        {"blog_pattern": "none", "stage1_score_contrib": 40},
        {"recent_reviews_30d": 0},
        {"social_active": False},
    )
    # would be 40+35+20+15 = 110 → cap 100
    assert s == 100
