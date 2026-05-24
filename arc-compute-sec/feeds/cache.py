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


def _quarantine_db() -> None:
    """Move aside a corrupt runtime cache so scans can continue.

    The feed cache is non-canonical data. Canonical venue state is stored in
    append-only logs and hashes elsewhere, so recreating this DB is safe.
    """
    global _db_init_done
    _db_init_done = False
    _mem.clear()
    if not _CACHE_DB.exists():
        return
    target = _CACHE_DB.with_name(f"{_CACHE_DB.name}.corrupt.{time.time_ns()}")
    try:
        _CACHE_DB.replace(target)
    except OSError:
        try:
            _CACHE_DB.unlink()
        except OSError:
            pass


def _db() -> sqlite3.Connection:
    global _db_init_done
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    last_exc: sqlite3.DatabaseError | None = None
    for _ in range(2):
        conn = sqlite3.connect(str(_CACHE_DB), timeout=10)
        try:
            if not _db_init_done:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS cache "
                    "(ns TEXT, key TEXT, expires_at REAL, value TEXT, PRIMARY KEY (ns, key))"
                )
                conn.commit()
                _db_init_done = True
            return conn
        except sqlite3.DatabaseError as exc:
            last_exc = exc
            conn.close()
            _quarantine_db()
    raise last_exc or sqlite3.DatabaseError("cache open failed")


def _fetch_row(ns: str, key: str) -> tuple[float, str] | None:
    conn = _db()
    try:
        return conn.execute(
            "SELECT expires_at, value FROM cache WHERE ns = ? AND key = ?",
            (ns, key),
        ).fetchone()
    finally:
        conn.close()


def get(ns: str, key: str) -> Any | None:
    """Return decoded JSON value, or None if missing/expired."""
    now = time.time()
    with _lock:
        hit = _mem.get((ns, key))
        if hit and hit[0] > now:
            return json.loads(hit[1])
        try:
            row = _fetch_row(ns, key)
        except sqlite3.DatabaseError:
            _quarantine_db()
            row = None
        if row and row[0] > now:
            _mem[(ns, key)] = (row[0], row[1])
            return json.loads(row[1])
    return None


def put(ns: str, key: str, value: Any, ttl_seconds: float = 60.0) -> None:
    expires = time.time() + ttl_seconds
    encoded = json.dumps(value, default=str)
    with _lock:
        _mem[(ns, key)] = (expires, encoded)
        for attempt in range(2):
            conn = _db()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (ns, key, expires_at, value) VALUES (?, ?, ?, ?)",
                    (ns, key, expires, encoded),
                )
                conn.commit()
                return
            except sqlite3.DatabaseError:
                if attempt == 1:
                    raise
                _quarantine_db()
            finally:
                conn.close()


def clear(ns: str | None = None) -> None:
    """Clear cache, optionally only one namespace. Used in tests."""
    with _lock:
        if ns is None:
            _mem.clear()
        else:
            for k in [k for k in _mem if k[0] == ns]:
                _mem.pop(k, None)
        try:
            conn = _db()
            if ns is None:
                conn.execute("DELETE FROM cache")
            else:
                conn.execute("DELETE FROM cache WHERE ns = ?", (ns,))
            conn.commit()
            conn.close()
        except sqlite3.DatabaseError:
            _quarantine_db()
