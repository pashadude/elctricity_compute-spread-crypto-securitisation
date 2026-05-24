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


def _coerce_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= price <= 1.0:
        return price
    return None


def _maybe_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return decoded if isinstance(decoded, list) else []
    return []


def _extract_yes_prices(event: dict) -> list[float]:
    """Extract YES-side prices from the common Gamma event shapes.

    Tests use simple `markets[].outcomePrice` rows; live Gamma responses can
    also carry JSON-encoded `outcomePrices` arrays. Keep this parser
    conservative: unparseable prices are skipped, not guessed.
    """
    prices: list[float] = []
    for raw in event.get("markets") or []:
        if not isinstance(raw, dict):
            continue
        for key in ("outcomePrice", "lastPrice", "price"):
            price = _coerce_price(raw.get(key))
            if price is not None:
                prices.append(price)
                break
        else:
            outcome_prices = _maybe_json_list(raw.get("outcomePrices"))
            outcomes = _maybe_json_list(raw.get("outcomes"))
            if outcome_prices:
                yes_idx = 0
                for idx, outcome in enumerate(outcomes):
                    if str(outcome).strip().lower() == "yes":
                        yes_idx = idx
                        break
                if yes_idx < len(outcome_prices):
                    price = _coerce_price(outcome_prices[yes_idx])
                    if price is not None:
                        prices.append(price)
    return prices


def classify_and_gate(events: list[dict], *, include_rejected: bool = False) -> list[dict]:
    """Classify energy events and run the premium gate.

    By default this returns only scorer-accepted events. Runtime uses
    `include_rejected=True` so premium failures still reach the judge and
    become auditable REJECT rows, while off-template events remain dropped
    before scoring/judging.
    """
    out: list[dict] = []
    for ev in events:
        title = ev.get("title") or ev.get("slug") or ""
        description = ev.get("description") or ""
        template = classify_energy(title=title, description=description)
        if template is None:
            continue
        yes_prices = _extract_yes_prices(ev)
        if len(yes_prices) < 2:
            continue
        # Sum-of-YES heuristic. Use the first market as "candidate", rest as event_avg.
        evg_avg = sum(yes_prices[1:]) / (len(yes_prices) - 1) if len(yes_prices) > 1 else 0.0
        gate = score_candidate(price=yes_prices[0], event_avg_yes_price=evg_avg)
        if not gate.passes_gate and not include_rejected:
            continue
        out.append({
            "id": ev.get("id") or ev.get("slug"),
            "slug": ev.get("slug"),
            "title": title,
            "description": description,
            "end_date": ev.get("endDate") or ev.get("end_date") or ev.get("endDateIso"),
            "start_date": ev.get("startDate") or ev.get("start_date") or ev.get("startDateIso"),
            "volume": ev.get("volume") or ev.get("volumeNum"),
            "liquidity": ev.get("liquidity") or ev.get("liquidityNum"),
            "yes_prices": yes_prices,
            "energy_template_id": template,
            "premium": gate.premium,
            "scorer_result": {
                "passes_gate": gate.passes_gate,
                "premium": gate.premium,
                "rejection_reason": gate.rejection_reason,
                "raw": gate.raw,
            },
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
