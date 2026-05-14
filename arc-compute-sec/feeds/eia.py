"""EIA v2 API wholesale-proxy electricity price fetcher.

Endpoint: https://api.eia.gov/v2/electricity/retail-sales/data/
Free tier: 5,000 req/hr. We cache 1 hour because the data is monthly anyway.

EIA v2 does NOT expose real-time ISO LMP prices. The closest publicly-
available proxy is monthly average INDUSTRIAL retail prices per state
(`sectorid=IND`), which tracks wholesale ± a small markup. We map each
ISO/region to a representative state:

  ERCOT  → TX        (Texas — entire ERCOT footprint)
  CAISO  → CA        (California)
  PJM    → PA        (Pennsylvania — largest PJM state by load)
  NYISO  → NY        (New York)
  MISO   → IL        (Illinois — proxy for MISO mid)
  ISO-NE → MA        (Massachusetts)

Prices returned by EIA are `cents per kilowatt-hour`. We convert to the
standard $/MWh unit at the boundary so downstream (arb_identifier,
pnl_probe) sees one canonical unit:

    $/MWh = (cents/kWh) × 10

Data lag: monthly, typically 60-90 days behind realtime. That's fine for
v0 demo (the arb_identifier computes a z-score from rolling history, so
all that matters is the SHAPE of the series, not its real-time freshness).
Continuous real-time LMP is a v2 task — wire ERCOT EMIL / CAISO OASIS /
PJM Data Miner adapters when there's an actual operator running it.

Register a free API key at https://www.eia.gov/opendata/register.php
and set `EIA_API_KEY` in `.env`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

import requests

from . import cache

_BASE = "https://api.eia.gov/v2"
_RETAIL_PATH = "/electricity/retail-sales/data/"

# Region → representative US state for industrial-price proxy.
ERCOT = "ERCO"
PJM = "PJM"
CAISO = "CISO"
NYISO = "NYIS"
MISO = "MISO"
ISONE = "ISNE"
DEFAULT_REGIONS = (ERCOT, PJM, CAISO)

REGION_TO_STATE: dict[str, str] = {
    ERCOT: "TX",
    PJM:   "PA",
    CAISO: "CA",
    NYISO: "NY",
    MISO:  "IL",
    ISONE: "MA",
}


@dataclass(frozen=True, slots=True)
class ElectricityPoint:
    region: str        # ISO code we asked for (ERCO, PJM, CISO, …)
    state: str         # US state actually queried as the proxy
    period: str        # YYYY-MM
    value_mwh: float   # $/MWh (converted from cents/kWh × 10)
    raw_unit: str      # original EIA unit string for sanity-check
    raw_value: float   # original EIA value (cents/kWh) for traceability


def _api_key() -> str:
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "EIA_API_KEY not set. Register at https://www.eia.gov/opendata/register.php "
            "and add to .env."
        )
    return key


def _fetch_raw(state: str, length: int = 1, ttl: float = 3600.0) -> dict:
    """Fetch the latest `length` monthly industrial-price points for one US state."""
    ck = f"IND:{state}:{length}"
    hit = cache.get("eia", ck)
    if hit is not None:
        return hit
    params = {
        "api_key": _api_key(),
        "frequency": "monthly",
        "data[0]": "price",
        "facets[sectorid][]": "IND",
        "facets[stateid][]": state,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "offset": 0,
        "length": length,
    }
    resp = requests.get(_BASE + _RETAIL_PATH, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    cache.put("eia", ck, data, ttl_seconds=ttl)
    return data


def fetch_latest(region: str = ERCOT) -> ElectricityPoint | None:
    """Return the most recent monthly industrial-price point for the state
    proxying `region`, converted to $/MWh. Returns None when EIA has no
    usable row for the state."""
    state = REGION_TO_STATE.get(region)
    if not state:
        return None
    raw = _fetch_raw(state)
    rows = (raw.get("response", {}) or {}).get("data", [])
    if not rows:
        return None
    row = rows[0]
    val = row.get("price")
    if val is None:
        return None
    try:
        cents_per_kwh = float(val)
    except (TypeError, ValueError):
        return None
    # EIA returns industrial price in cents/kWh; convert to $/MWh.
    # 1 cent/kWh = $0.01/kWh = $10/MWh (1000 kWh per MWh ÷ 100 cents per $)
    value_mwh = cents_per_kwh * 10.0
    unit = (row.get("price-units") or row.get("units") or "").strip()
    return ElectricityPoint(
        region=region,
        state=state,
        period=row["period"],
        value_mwh=value_mwh,
        raw_unit=unit,
        raw_value=cents_per_kwh,
    )


def fetch_regions(regions: Iterable[str] = DEFAULT_REGIONS) -> dict[str, ElectricityPoint | None]:
    return {r: fetch_latest(r) for r in regions}
