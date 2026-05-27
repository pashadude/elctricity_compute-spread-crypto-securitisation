"""Read-only paper-PnL probe — never executes anything.

For every candidate the surface_router emits, attach an `est_pnl_per_dollar`
so the operator can see what the agent would have earned per dollar at
entry. Realized PnL is computed at settle time and reconciled separately
in `logs/pnl_reconciliation.tsv`.

PnL models per surface:

  polymarket       →  sum(yes_prices) - 1                 (NO-overlay arb)
  ibkr_prediction  →  sum(yes_prices) - 1                 (event contract overlay)
  kalshi           →  sum(yes_prices) - 1                 (event contract overlay)
  ibkr             →  |z| * basis_per_z_for_equity        (stock proxy)
  crypto           →  |z| * basis_per_z_for_crypto

Basis-per-z constants are deliberately conservative; the agent's realized
PnL will trail or beat these and the reconciliation table will show drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

# Conservative defaults. These can be tuned once we have live trace.
EQUITY_BASIS_PER_Z = 0.005   # 50 bps per σ of spread dislocation, days–weeks horizon
CRYPTO_BASIS_PER_Z = 0.012   # 120 bps per σ; crypto is higher beta

DIRECTION_LONG = "long"
DIRECTION_SHORT = "short"


@dataclass(frozen=True, slots=True)
class PnLEstimate:
    surface: str
    instrument: str
    direction: str
    est_pnl_per_dollar: float
    inputs: dict


def event_contract_pnl_per_dollar(yes_prices: Sequence[float]) -> float:
    """sum(p_yes_i) − 1. Positive = NO-overlay profitable."""
    if not yes_prices:
        raise ValueError("event_contract_pnl_per_dollar requires at least one yes_price")
    return sum(float(p) for p in yes_prices) - 1.0


def polymarket_pnl_per_dollar(yes_prices: Sequence[float]) -> float:
    return event_contract_pnl_per_dollar(yes_prices)


def equity_pnl_per_dollar(
    z: float,
    direction: str,
    basis_per_z: float = EQUITY_BASIS_PER_Z,
) -> float:
    """Equity mean-reversion expected return. Positive when the agent's
    direction agrees with the mean-reversion of the spread.
    """
    if direction not in (DIRECTION_LONG, DIRECTION_SHORT):
        raise ValueError(f"direction must be long/short, got {direction!r}")
    # If we're shorting because the spread says equities should compress,
    # the magnitude of z is the expected reversion size.
    return abs(z) * basis_per_z


def crypto_pnl_per_dollar(
    z: float,
    direction: str,
    basis_per_z: float = CRYPTO_BASIS_PER_Z,
) -> float:
    if direction not in (DIRECTION_LONG, DIRECTION_SHORT):
        raise ValueError(f"direction must be long/short, got {direction!r}")
    return abs(z) * basis_per_z


def estimate(
    surface: str,
    instrument: str,
    direction: str,
    *,
    yes_prices: Sequence[float] | None = None,
    z: float | None = None,
) -> PnLEstimate:
    """Dispatch on surface."""
    if surface in {"polymarket", "ibkr_prediction", "kalshi"}:
        if not yes_prices:
            raise ValueError(f"{surface} surface requires yes_prices")
        est = event_contract_pnl_per_dollar(yes_prices)
        return PnLEstimate(
            surface=surface,
            instrument=instrument,
            direction=direction,
            est_pnl_per_dollar=est,
            inputs={"yes_prices": list(yes_prices)},
        )
    if surface == "ibkr":
        if z is None:
            raise ValueError("ibkr surface requires z")
        est = equity_pnl_per_dollar(z, direction)
        return PnLEstimate(
            surface=surface,
            instrument=instrument,
            direction=direction,
            est_pnl_per_dollar=est,
            inputs={"z": z},
        )
    if surface == "crypto":
        if z is None:
            raise ValueError("crypto surface requires z")
        est = crypto_pnl_per_dollar(z, direction)
        return PnLEstimate(
            surface=surface,
            instrument=instrument,
            direction=direction,
            est_pnl_per_dollar=est,
            inputs={"z": z},
        )
    raise ValueError(f"unknown surface {surface!r}")
