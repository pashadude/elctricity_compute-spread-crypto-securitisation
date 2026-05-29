import time
import sqlite3
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


def test_corrupt_cache_db_is_quarantined(tmp_path, monkeypatch):
    db = tmp_path / "_feed_cache.sqlite"
    db.write_text("not sqlite")
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "_CACHE_DB", db)
    monkeypatch.setattr(cache, "_db_init_done", False)
    cache._mem.clear()

    assert cache.get("ns", "k") is None
    cache.put("ns", "k", {"ok": True}, ttl_seconds=60)

    assert cache.get("ns", "k") == {"ok": True}
    assert list(tmp_path.glob("_feed_cache.sqlite.corrupt.*"))


def test_put_degrades_to_memory_when_disk_cache_is_readonly(monkeypatch):
    monkeypatch.setattr(cache, "_db", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("readonly")))
    cache._mem.clear()

    cache.put("ns-readonly", "k", {"ok": True}, ttl_seconds=60)

    assert cache.get("ns-readonly", "k") == {"ok": True}
