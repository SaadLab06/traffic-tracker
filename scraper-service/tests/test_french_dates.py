from datetime import datetime
from app.utils.french_dates import parse_fr_date, extract_dates_from_html

def test_parse_absolute_french_date():
    d = parse_fr_date("1 janvier 2025")
    assert d and d.year == 2025 and d.month == 1 and d.day == 1

def test_parse_relative_french_date():
    d = parse_fr_date("il y a 3 jours")
    assert d is not None

def test_parse_invalid_returns_none():
    assert parse_fr_date("pas une date") is None

def test_extract_dates_from_html_time_tag():
    html = '<article><time datetime="2024-11-12T10:00:00Z">12 novembre 2024</time></article>'
    dates = extract_dates_from_html(html)
    assert any(d.year == 2024 and d.month == 11 for d in dates)

def test_extract_dates_from_jsonld():
    html = '''
    <script type="application/ld+json">
    {"@type":"Article","datePublished":"2025-02-10T09:00:00Z"}
    </script>
    '''
    dates = extract_dates_from_html(html)
    assert any(d.year == 2025 and d.month == 2 for d in dates)

def test_extract_dates_dedupes_same_day_across_sources():
    html = '''
    <article><time datetime="2025-03-10T10:00:00Z">10 mars 2025</time></article>
    <script type="application/ld+json">{"@type":"Article","datePublished":"2025-03-10T10:00:00Z"}</script>
    <p>Article publié le 10 mars 2025</p>
    '''
    dates = extract_dates_from_html(html)
    day_keys = {(d.year, d.month, d.day) for d in dates}
    # All three sources mention 2025-03-10 — result should have exactly one entry for that day
    assert (2025, 3, 10) in day_keys
    count_march_10 = sum(1 for d in dates if (d.year, d.month, d.day) == (2025, 3, 10))
    assert count_march_10 == 1
