import json
import re
from datetime import datetime
from typing import Optional
import dateparser
from bs4 import BeautifulSoup

# If lxml installed, use it; else fall back to stdlib html.parser
try:
    import lxml  # noqa: F401
    _BS_PARSER = "lxml"
except ImportError:
    _BS_PARSER = "html.parser"

def parse_fr_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    return dateparser.parse(text, languages=["fr", "en"])

def extract_dates_from_html(html: str) -> list[datetime]:
    soup = BeautifulSoup(html, _BS_PARSER)
    out: list[datetime] = []

    for t in soup.find_all("time"):
        val = t.get("datetime") or t.get_text(strip=True)
        d = parse_fr_date(val)
        if d:
            out.append(d)

    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "{}")
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if isinstance(obj, dict) and obj.get("datePublished"):
                d = parse_fr_date(obj["datePublished"])
                if d:
                    out.append(d)

    text = soup.get_text(" ", strip=True)
    for m in re.finditer(r"\b\d{1,2}\s+(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\s+\d{4}\b", text, flags=re.I):
        d = parse_fr_date(m.group(0))
        if d:
            out.append(d)

    return out
