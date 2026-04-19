import time
from pathlib import Path
from app.utils.cache import TTLCache

def test_set_and_get(tmp_path):
    c = TTLCache(tmp_path, ttl_seconds=60)
    c.set("foo", {"n": 1})
    assert c.get("foo") == {"n": 1}

def test_expired_returns_none(tmp_path):
    c = TTLCache(tmp_path, ttl_seconds=0)
    c.set("foo", {"n": 1})
    time.sleep(0.01)
    assert c.get("foo") is None

def test_missing_key_returns_none(tmp_path):
    c = TTLCache(tmp_path, ttl_seconds=60)
    assert c.get("nope") is None

def test_survives_restart(tmp_path):
    c1 = TTLCache(tmp_path, ttl_seconds=60)
    c1.set("foo", [1, 2, 3])
    c2 = TTLCache(tmp_path, ttl_seconds=60)
    assert c2.get("foo") == [1, 2, 3]
