"""Polymarket adapter — READ-ONLY.

Per TASK.md §6 anti-goals: order placement stays on `@beldghik`. This
adapter (1) reads live events from the Gamma API, (2) filters by the
energy classifier, (3) runs each through the upstream scorer's premium
gate, and (4) returns gated candidates' deliverable hashes for the
wrap. It NEVER calls Polymarket's order placement endpoints.

The runtime's `simulate_gated_fill()` is a convenience that returns a
FillReport-shaped dict so the wrapping logic doesn't need a special case
for "Polymarket has no fill, just a hash."
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import requests

from agent.scorer_bridge import score_candidate
from feeds import cache
from templates.energy.classifier import classify_energy

_GAMMA_BASE = "https://gamma-api.polymarket.com"


def fetch_events(limit: int = 50, only_active: bool = True, ttl: float = 60.0) -> list[dict]:
    """Lightweight Gamma /events fetch with caching. Returns raw events."""
    key = f"limit={limit}|active={only_active}"
    hit = cache.get("polymarket_events", key)
    if hit is not None:
        return hit
    params: dict[str, Any] = {"limit": limit}
    if only_active:
        params["active"] = "true"
        params["closed"] = "false"
    try:
        resp = requests.get(f"{_GAMMA_BASE}/events", params=params, timeout=15)
        resp.raise_for_status()
        events = resp.json()
        cache.put("polymarket_events", key, events, ttl_seconds=ttl)
        return events
    except requests.RequestException as exc:
        # Gamma is rate-limited and sometimes flaky; surface the error but
        # don't kill the whole runtime — return empty.
        print(f"[polymarket] gamma fetch failed: {exc}")
        return []


def classify_and_gate(events: list[dict]) -> list[dict]:
    """Filter to energy-classified events with positive premium per the scorer."""
    out: list[dict] = []
    for ev in events:
        title = ev.get("title") or ev.get("slug") or ""
        description = ev.get("description") or ""
        template = classify_energy(title=title, description=description)
        if template is None:
            continue
        markets = ev.get("markets") or []
        yes_prices = []
        for m in markets:
            p = m.get("outcomePrice") or m.get("lastPrice") or m.get("price")
            try:
                yes_prices.append(float(p))
            except (TypeError, ValueError):
                continue
        if len(yes_prices) < 2:
            continue
        # Sum-of-YES heuristic. Use the first market as "candidate", rest as event_avg.
        evg_avg = sum(yes_prices[1:]) / (len(yes_prices) - 1) if len(yes_prices) > 1 else 0.0
        gate = score_candidate(price=yes_prices[0], event_avg_yes_price=evg_avg)
        if not gate.passes_gate:
            continue
        out.append({
            "id": ev.get("id") or ev.get("slug"),
            "slug": ev.get("slug"),
            "title": title,
            "yes_prices": yes_prices,
            "energy_template_id": template,
            "premium": gate.premium,
        })
    return out


def simulate_gated_fill(instrument: str, yes_prices: list[float]) -> dict:
    """Construct a deterministic FillReport-shaped dict for the polymarket surface.

    No real order is placed. The "fill" is the snapshot of the YES prices
    at the moment the candidate was wrapped; the deliverable hash later
    binds this snapshot on-chain.
    """
    snapshot = {
        "surface": "polymarket",
        "instrument": instrument,
        "yes_prices_at_open": list(yes_prices),
        "premium_at_open": (sum(yes_prices) - 1.0) if yes_prices else 0.0,
        "fill_ts": time.time(),
        "fill_id": hashlib.sha256(
            (instrument + str(yes_prices) + str(time.time())).encode()
        ).hexdigest()[:16],
    }
    return snapshot
