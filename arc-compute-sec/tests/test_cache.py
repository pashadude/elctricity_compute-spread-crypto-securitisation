import time
from feeds import cache


def test_put_get_roundtrip():
    cache.put("ns", "k", {"a": 1}, ttl_seconds=10)
    assert cache.get("ns", "k") == {"a": 1}


def test_get_after_expiry_returns_none():
    cache.put("ns", "k", {"a": 1}, ttl_seconds=0.01)
    time.sleep(0.05)
    assert cache.get("ns", "k") is None


def test_clear_namespace():
    cache.put("ns1", "k", {"a": 1}, ttl_seconds=60)
    cache.put("ns2", "k", {"a": 2}, ttl_seconds=60)
    cache.clear("ns1")
    assert cache.get("ns1", "k") is None
    assert cache.get("ns2", "k") == {"a": 2}
