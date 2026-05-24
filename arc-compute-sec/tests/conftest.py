"""Pytest config — adds the project root to sys.path so `agent`, `feeds`,
`adapters`, etc. resolve regardless of cwd. Also clears the feed cache
between tests so each test starts hermetic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True)
def _clear_feed_cache(monkeypatch):
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    monkeypatch.setenv("POLYMARKET_DIRECT_EVENT_FETCH", "0")
    from feeds import cache
    cache.clear()
    yield
    cache.clear()
