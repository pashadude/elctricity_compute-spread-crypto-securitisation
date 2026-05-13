"""Crypto adapter — paper-fills at live Coinbase ask.

No real order is placed. We snapshot the live ask (for longs) or bid
(for shorts) at the moment the candidate is wrapped, then build the
deliverable hash from that. Phase 5 reconciliation reads the latest
ticker at settle time and writes realized PnL.
"""
from __future__ import annotations

import hashlib
import time

from feeds.coinbase import fetch_ticker


def paper_fill(symbol: str, direction: str, notional_usdc: float) -> dict:
    quote = fetch_ticker(symbol)
    px = quote.ask if direction == "long" else quote.bid
    if px <= 0:
        px = quote.last
    fill_ts = time.time()
    fill_id_seed = f"{symbol}|{direction}|{notional_usdc}|{fill_ts}"
    return {
        "surface": "crypto",
        "instrument": symbol,
        "direction": direction,
        "notional_usdc": float(notional_usdc),
        "entry_price": float(px),
        "qty": float(notional_usdc) / float(px) if px > 0 else 0.0,
        "fill_ts": fill_ts,
        "fill_id": hashlib.sha256(fill_id_seed.encode()).hexdigest()[:16],
        "raw_response_hash": hashlib.sha256(str(quote).encode()).hexdigest(),
        "stub": False,
    }
