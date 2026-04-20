from fastapi import APIRouter
from app.models.schemas import CheckRequest, MarketplaceResult
from app.services.dotmarket_scraper import fetch_dotmarket_listings
from app.services.flippa_scraper import fetch_flippa_listings
from app.services.marketplace_matcher import match_url_to_listings
from app.utils.logger import get_logger

router = APIRouter()
log = get_logger(__name__)


@router.post("/check-marketplaces", response_model=list[MarketplaceResult])
async def check_marketplaces(req: CheckRequest):
    dm_listings = await fetch_dotmarket_listings()
    fl_listings = await fetch_flippa_listings()
    if not dm_listings and not fl_listings:
        log.warning("both marketplace catalogs empty — all URLs will be NOT_LISTED", extra={"stage": "0.5"})
    out: list[MarketplaceResult] = []
    for url in req.urls:
        dm = match_url_to_listings(url, dm_listings)
        fl = match_url_to_listings(url, fl_listings)
        listed = dm is not None or fl is not None
        out.append(MarketplaceResult(
            url=url,
            listed_on_dotmarket=dm is not None,
            dotmarket_url=(dm or {}).get("url"),
            listed_on_flippa=fl is not None,
            flippa_url=(fl or {}).get("url"),
            asking_price_eur=(dm or fl or {}).get("asking_price_eur"),
            marketplace_verdict="FOR_SALE" if listed else "NOT_LISTED",
        ))
    return out
