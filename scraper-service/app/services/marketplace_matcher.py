import re
from urllib.parse import urlparse
from typing import Any, Optional

def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")

def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) >= 4}

def match_url_to_listings(url: str, listings: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    domain = _domain(url)
    if not domain:
        return None
    core = domain.split(".")[0]
    core_tokens = _tokens(core)
    for listing in listings:
        hint = (listing.get("domain_hint") or "").lower()
        hint_tokens = _tokens(hint)
        if core in hint or core_tokens & hint_tokens:
            return listing
    return None
