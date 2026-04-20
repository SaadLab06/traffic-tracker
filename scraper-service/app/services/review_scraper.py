from datetime import datetime, timedelta
from typing import Any
try:
    from trustpilot_scraper.scraper import scrape_trustpilot_reviews
except ImportError:  # pragma: no cover
    def scrape_trustpilot_reviews(url: str):
        raise RuntimeError("trustpilot-scraper not installed")

def check_trustpilot_velocity(domain: str) -> dict[str, Any]:
    try:
        reviews = scrape_trustpilot_reviews(f"https://www.trustpilot.com/review/{domain}")
    except Exception:
        return {"trustpilot_found": False, "recent_reviews_14d": 0, "recent_reviews_30d": 0}

    now = datetime.now()
    c14, c30 = 0, 0
    for r in (reviews or [])[:50]:
        try:
            rev_date = datetime.strptime(r["Date"], "%Y-%m-%d")
        except (KeyError, ValueError, TypeError):
            continue
        if rev_date >= now - timedelta(days=14): c14 += 1
        if rev_date >= now - timedelta(days=30): c30 += 1
    return {"trustpilot_found": True, "recent_reviews_14d": c14, "recent_reviews_30d": c30}
