from app.services.marketplace_matcher import match_url_to_listings

LISTINGS = [
    {"url":"https://dotmarket.eu/listing/12345","niche":"CBD",
     "domain_hint":"CBD boutique française duverger","asking_price_eur":45000,
     "traffic_range":"5000-10000"},
    {"url":"https://dotmarket.eu/listing/67890","niche":"Mode",
     "domain_hint":"Boutique vêtements","asking_price_eur":120000,
     "traffic_range":"20000-50000"},
]

def test_direct_domain_hint_match():
    m = match_url_to_listings("https://duverger-nb.com", LISTINGS)
    assert m is not None
    assert m["asking_price_eur"] == 45000

def test_no_match_returns_none():
    m = match_url_to_listings("https://unrelated-site.fr", LISTINGS)
    assert m is None

def test_case_insensitive():
    m = match_url_to_listings("https://DUVERGER-NB.com", LISTINGS)
    assert m is not None
