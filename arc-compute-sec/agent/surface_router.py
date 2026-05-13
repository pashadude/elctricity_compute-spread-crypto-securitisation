"""Surface router.

Given an ArbSignal, enumerate candidate positions across the four surfaces
the agent knows about. Each candidate carries enough info for the judge
and the appropriate adapter to act on it.

Direction semantics:
    direction = "compute_expensive"      → mean-reversion means compute
                                             will get cheaper / electricity
                                             will move up. Equity-positive
                                             for hyperscalers (their cost
                                             eased); BTC short on mining
                                             stress; Polymarket-AI: faster
                                             releases more likely.
    direction = "electricity_expensive"  → mining margin compression;
                                             hyperscaler margins compress;
                                             BTC short; AI releases slow.

Per-surface routing rules are deliberately simple. The judge layer
applies the 4-way classifier on top.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Sequence

from agent.arb_identifier import (
    ArbSignal,
    DIRECTION_COMPUTE_EXPENSIVE,
    DIRECTION_ELEC_EXPENSIVE,
)
from agent.pnl_probe import estimate as pnl_estimate, DIRECTION_LONG, DIRECTION_SHORT


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    arb_signal_id: str
    surface: str          # "polymarket" | "ibkr" | "crypto" | "kalshi"
    instrument: str       # e.g. "GOOGL", "BTC/USD", "polymarket:<event_id>:<token_id>"
    direction: str        # "long" | "short" — for predictive markets this maps to YES/NO via adapter
    sizing_usdc: float    # notional in USDC for the on-chain wrap
    conviction: float     # signal |z|
    est_pnl_per_dollar: float
    ttl_hours: int
    metadata: dict        # surface-specific extras (yes_prices, event_id, qty, etc.)


# Hyperscaler universe — keyed by surface direction.
_EQUITY_INSTRUMENTS = ("GOOGL", "AMZN", "MSFT", "BABA")
_MINER_INSTRUMENTS = ("MARA", "RIOT", "CLSK")
_CRYPTO_INSTRUMENTS = ("BTC/USD", "ETH/USD")


def _equity_candidates(
    signal: ArbSignal, sizing_per_name_usdc: float
) -> list[Candidate]:
    # When electricity is expensive, hyperscaler margins compress → short.
    # When compute is expensive, mining stress relaxes → long the hyperscaler
    # cloud beneficiaries less; we keep the v0 rule conservative: short
    # equities only on `electricity_expensive`. `compute_expensive` skips
    # equities (no v0 signal of the right magnitude there).
    if signal.direction != DIRECTION_ELEC_EXPENSIVE:
        return []
    out: list[Candidate] = []
    for sym in _EQUITY_INSTRUMENTS:
        est = pnl_estimate(
            surface="ibkr",
            instrument=sym,
            direction=DIRECTION_SHORT,
            z=signal.z,
        )
        out.append(
            Candidate(
                candidate_id=str(uuid.uuid4())[:12],
                arb_signal_id=signal.signal_id,
                surface="ibkr",
                instrument=sym,
                direction=DIRECTION_SHORT,
                sizing_usdc=sizing_per_name_usdc,
                conviction=signal.conviction,
                est_pnl_per_dollar=est.est_pnl_per_dollar,
                ttl_hours=signal.ttl_hours,
                metadata={"qty_hint": 1, "order_type": "MKT"},
            )
        )
    return out


def _crypto_candidates(signal: ArbSignal, sizing_usdc: float) -> list[Candidate]:
    # Crypto rule: short BTC on either direction's compression of mining
    # margin; v0 simplifies to short BTC on `electricity_expensive`, skip
    # on `compute_expensive`.
    if signal.direction != DIRECTION_ELEC_EXPENSIVE:
        return []
    out: list[Candidate] = []
    for sym in _CRYPTO_INSTRUMENTS:
        est = pnl_estimate(
            surface="crypto",
            instrument=sym,
            direction=DIRECTION_SHORT,
            z=signal.z,
        )
        out.append(
            Candidate(
                candidate_id=str(uuid.uuid4())[:12],
                arb_signal_id=signal.signal_id,
                surface="crypto",
                instrument=sym,
                direction=DIRECTION_SHORT,
                sizing_usdc=sizing_usdc,
                conviction=signal.conviction,
                est_pnl_per_dollar=est.est_pnl_per_dollar,
                ttl_hours=signal.ttl_hours,
                metadata={},
            )
        )
    return out


def _polymarket_candidates(
    signal: ArbSignal,
    events: Sequence[dict],
    sizing_usdc: float,
) -> list[Candidate]:
    """Build candidates from a pre-fetched list of Gamma events.

    The adapter is responsible for fetching events; this router only
    consumes them. Each event dict must contain at least:
      {id, slug, yes_prices: [..], description: ..}
    """
    out: list[Candidate] = []
    for ev in events:
        ypx = ev.get("yes_prices") or []
        if not ypx:
            continue
        try:
            est = pnl_estimate(
                surface="polymarket",
                instrument=f"polymarket:{ev.get('id') or ev.get('slug') or 'unknown'}",
                direction=DIRECTION_SHORT,  # NO-overlay = "shorting" overpriced YES sum
                yes_prices=ypx,
            )
        except ValueError:
            continue
        out.append(
            Candidate(
                candidate_id=str(uuid.uuid4())[:12],
                arb_signal_id=signal.signal_id,
                surface="polymarket",
                instrument=f"polymarket:{ev.get('id') or ev.get('slug')}",
                direction=DIRECTION_SHORT,
                sizing_usdc=sizing_usdc,
                conviction=signal.conviction,
                est_pnl_per_dollar=est.est_pnl_per_dollar,
                ttl_hours=signal.ttl_hours,
                metadata={
                    "event_id": ev.get("id"),
                    "slug": ev.get("slug"),
                    "yes_prices": list(ypx),
                    "energy_template_id": ev.get("energy_template_id"),
                },
            )
        )
    return out


def route(
    signal: ArbSignal,
    polymarket_events: Sequence[dict] = (),
    sizing_per_equity_usdc: float = 1.0,
    sizing_crypto_usdc: float = 1.0,
    sizing_polymarket_usdc: float = 1.0,
) -> list[Candidate]:
    """Top-level routing. Returns a flat list of candidates ranked by est_pnl_per_dollar desc."""
    cands: list[Candidate] = []
    cands.extend(_equity_candidates(signal, sizing_per_equity_usdc))
    cands.extend(_crypto_candidates(signal, sizing_crypto_usdc))
    cands.extend(_polymarket_candidates(signal, polymarket_events, sizing_polymarket_usdc))
    cands.sort(key=lambda c: c.est_pnl_per_dollar, reverse=True)
    return cands
