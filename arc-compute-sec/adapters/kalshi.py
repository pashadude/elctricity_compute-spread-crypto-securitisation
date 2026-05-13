"""Kalshi adapter — STUB. v0 does not wire Kalshi (see session decision).

The interface mirrors the other paper-fill adapters so the runtime
doesn't need a special case. Calling `paper_fill` returns a deterministic
stub report flagged with `stub=True`. v1 wires the real Kalshi API.
"""
from __future__ import annotations

import hashlib
import time


def paper_fill(instrument: str, direction: str, notional_usdc: float) -> dict:
    fill_ts = time.time()
    seed = f"kalshi-stub|{instrument}|{direction}|{notional_usdc}|{fill_ts}"
    return {
        "surface": "kalshi",
        "instrument": instrument,
        "direction": direction,
        "notional_usdc": float(notional_usdc),
        "entry_price": 0.0,
        "fill_ts": fill_ts,
        "fill_id": hashlib.sha256(seed.encode()).hexdigest()[:16],
        "raw_response_hash": "stub-v0-no-kalshi",
        "stub": True,
        "note": "Kalshi out-of-scope for v0; this is a deterministic stub.",
    }
