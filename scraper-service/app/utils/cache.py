import json
import time
import hashlib
from pathlib import Path
from typing import Any, Optional


class TTLCache:
    def __init__(self, directory: Path | str, ttl_seconds: int):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds

    def _path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.dir / f"{h}.json"

    def get(self, key: str) -> Optional[Any]:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        if time.time() - data["ts"] > self.ttl:
            return None
        return data["value"]

    def set(self, key: str, value: Any) -> None:
        p = self._path(key)
        p.write_text(json.dumps({"ts": time.time(), "value": value}), encoding="utf-8")
