import os
from typing import Any, Optional


async def check_social(base_url: str) -> Optional[dict[str, Any]]:
    if os.getenv("ENABLE_SOCIAL_CHECK", "false").lower() != "true":
        return None
    # v1: placeholder returns None; v2 will extract IG/FB from footer and
    # parse last-post date from open-graph meta without API calls.
    return None
