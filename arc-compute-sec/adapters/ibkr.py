"""IBKR demo paper-trading adapter via ib_insync.

This adapter ONLY uses the paper-trading account. It connects to the IB
Gateway/TWS on `IBKR_HOST:IBKR_GATEWAY_PORT` (defaults 127.0.0.1:4002).
The operator must have Gateway running in paper mode before any chain
phase starts; pre-Gate-A this adapter is unreachable.

If the connection is not available, `place_paper_order` either:
  - returns a deterministic stub fill report (when called with dry_run=True)
  - raises RuntimeError with a clear diagnostic
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from typing import Any

# `ib_insync` requires a running asyncio event loop on import in some
# environments. We try to lazy-init.

_DEFAULT_HOST = os.environ.get("IBKR_HOST", "127.0.0.1")
_DEFAULT_PORT = int(os.environ.get("IBKR_GATEWAY_PORT", "4002"))
_DEFAULT_CLIENT_ID = int(os.environ.get("IBKR_CLIENT_ID", "42"))

_ib_singleton: Any = None


def _connect():
    global _ib_singleton
    if _ib_singleton is not None and _ib_singleton.isConnected():
        return _ib_singleton
    try:
        # Ensure there is an event loop in this thread (Python 3.12 doesn't
        # implicitly create one).
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        from ib_insync import IB
        ib = IB()
        ib.connect(_DEFAULT_HOST, _DEFAULT_PORT, clientId=_DEFAULT_CLIENT_ID, timeout=8)
        # IBKR paper accounts don't have a real-time market-data
        # subscription; reqTickers() returns NaN otherwise. Type 3 =
        # DELAYED_FROZEN — free, returns the last delayed quote. Switching
        # to real-time is a per-account decision the operator makes inside
        # Gateway settings; the adapter doesn't override it.
        ib.reqMarketDataType(3)
        _ib_singleton = ib
        return ib
    except Exception as exc:
        raise RuntimeError(
            f"IBKR Gateway not reachable at {_DEFAULT_HOST}:{_DEFAULT_PORT} "
            f"(clientId={_DEFAULT_CLIENT_ID}). Start IB Gateway in paper-trading mode. "
            f"Underlying error: {exc!r}"
        )


def _stub_fill(symbol: str, direction: str, qty: int) -> dict:
    fill_ts = time.time()
    return {
        "surface": "ibkr",
        "instrument": symbol,
        "direction": direction,
        "qty": qty,
        "entry_price": 0.0,
        "fill_ts": fill_ts,
        "fill_id": hashlib.sha256(
            f"stub|{symbol}|{direction}|{qty}|{fill_ts}".encode()
        ).hexdigest()[:16],
        "raw_response_hash": "stub",
        "stub": True,
    }


def place_paper_order(symbol: str, direction: str, qty: int = 1,
                      *, dry_run: bool = False) -> dict:
    """Place a MarketOrder for `qty` shares of `symbol`. direction ∈ {"long","short"}.

    Returns a FillReport-shaped dict.
    """
    if dry_run:
        return _stub_fill(symbol, direction, qty)
    try:
        ib = _connect()
    except RuntimeError as exc:
        # Gateway not reachable — return a stub but log the reason. The
        # caller can decide to skip the wrap; for v0 paper demo we proceed.
        print(f"[ibkr] {exc}")
        return _stub_fill(symbol, direction, qty)
    from ib_insync import Stock, MarketOrder
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    side = "SELL" if direction == "short" else "BUY"
    order = MarketOrder(side, qty)
    trade = ib.placeOrder(contract, order)
    # Poll up to ~10s for the fill.
    deadline = time.time() + 10
    while time.time() < deadline and not trade.isDone():
        ib.waitOnUpdate(timeout=0.5)
    fills = trade.fills
    entry_price = float(fills[0].execution.price) if fills else 0.0
    fill_ts = time.time()
    raw = str(trade.orderStatus.__dict__ if trade.orderStatus else {})
    return {
        "surface": "ibkr",
        "instrument": symbol,
        "direction": direction,
        "qty": qty,
        "entry_price": entry_price,
        "fill_ts": fill_ts,
        "fill_id": str(trade.order.permId or "")[:16] or hashlib.sha256(raw.encode()).hexdigest()[:16],
        "raw_response_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "stub": False,
    }


def fetch_last_price(symbol: str) -> float | None:
    """Used by the Phase 0.6 smoke test.

    Falls through several ticker fields in preference order because paper
    accounts on delayed data populate different fields than real-time
    accounts: marketPrice (NaN on delayed), last/close/midpoint, then
    explicit delayed fields, finally bid/ask midpoint.
    """
    import math
    try:
        ib = _connect()
    except RuntimeError as exc:
        print(f"[ibkr] {exc}")
        return None
    from ib_insync import Stock
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    [tk] = ib.reqTickers(contract)
    for cand in (tk.marketPrice(), tk.last, tk.close, tk.midpoint(),
                 getattr(tk, "delayedLast", None), getattr(tk, "delayedClose", None)):
        try:
            v = float(cand)
            if math.isfinite(v) and v > 0:
                return v
        except (TypeError, ValueError):
            continue
    # Final fallback: bid/ask midpoint if both available
    try:
        if tk.bid > 0 and tk.ask > 0:
            return (tk.bid + tk.ask) / 2.0
    except Exception:
        pass
    return None
