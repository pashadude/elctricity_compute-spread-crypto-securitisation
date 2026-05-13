"""Tiny in-memory + on-disk SQLite cache. Avoids hammering EIA / AWS / Coinbase
during a single --scan cycle and across short-interval reruns.

TTLs are per-key. The cache key is (namespace, key) and value is a JSON string.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_CACHE_DIR = Path(__file__).resolve().parent.parent / "logs"
_CACHE_DB = _CACHE_DIR / "_feed_cache.sqlite"

_mem: dict[tuple[str, str], tuple[float, str]] = {}
_lock = threading.Lock()
_db_init_done = False


def _db() -> sqlite3.Connection:
    global _db_init_done
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_CACHE_DB))
    if not _db_init_done:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(ns TEXT, key TEXT, expires_at REAL, value TEXT, PRIMARY KEY (ns, key))"
        )
        conn.commit()
        _db_init_done = True
    return conn


def get(ns: str, key: str) -> Any | None:
    """Return decoded JSON value, or None if missing/expired."""
    now = time.time()
    with _lock:
        hit = _mem.get((ns, key))
        if hit and hit[0] > now:
            return json.loads(hit[1])
        conn = _db()
        row = conn.execute(
            "SELECT expires_at, value FROM cache WHERE ns = ? AND key = ?",
            (ns, key),
        ).fetchone()
        conn.close()
        if row and row[0] > now:
            _mem[(ns, key)] = (row[0], row[1])
            return json.loads(row[1])
    return None


def put(ns: str, key: str, value: Any, ttl_seconds: float = 60.0) -> None:
    expires = time.time() + ttl_seconds
    encoded = json.dumps(value, default=str)
    with _lock:
        _mem[(ns, key)] = (expires, encoded)
        conn = _db()
        conn.execute(
            "INSERT OR REPLACE INTO cache (ns, key, expires_at, value) VALUES (?, ?, ?, ?)",
            (ns, key, expires, encoded),
        )
        conn.commit()
        conn.close()


def clear(ns: str | None = None) -> None:
    """Clear cache, optionally only one namespace. Used in tests."""
    with _lock:
        if ns is None:
            _mem.clear()
        else:
            for k in [k for k in _mem if k[0] == ns]:
                _mem.pop(k, None)
        conn = _db()
        if ns is None:
            conn.execute("DELETE FROM cache")
        else:
            conn.execute("DELETE FROM cache WHERE ns = ?", (ns,))
        conn.commit()
        conn.close()
