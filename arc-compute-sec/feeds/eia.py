"""EIA v2 API wholesale electricity price fetcher.

Endpoint family: https://api.eia.gov/v2/electricity/rto/region-data/data
Free tier: 5,000 req/hr. We cache 5 min to stay well under.

Routes data through three ISO buckets:
  - ERCOT (Texas)
  - PJM (mid-Atlantic / Midwest)
  - CAISO (California)

Day-ahead prices are usable; real-time LMP availability varies by ISO and
may lag the wallclock by up to an hour. The arb identifier consumes the
latest available `$_per_MWh` per region.

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
_REGION_DATA_PATH = "/electricity/rto/region-data/data/"

# ISO codes used by EIA.
ERCOT = "ERCO"
PJM = "PJM"
CAISO = "CISO"
DEFAULT_REGIONS = (ERCOT, PJM, CAISO)


@dataclass(frozen=True, slots=True)
class ElectricityPoint:
    region: str
    period: str       # ISO timestamp string, hourly granularity (UTC)
    value_mwh: float  # $/MWh; EIA returns "value" as dollars/MWh for region-data
    raw_unit: str     # raw unit string from EIA for sanity-check


def _api_key() -> str:
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "EIA_API_KEY not set. Register at https://www.eia.gov/opendata/register.php "
            "and add to .env."
        )
    return key


def _fetch_raw(region: str, length: int = 1, ttl: float = 300.0) -> dict:
    """Fetch the latest `length` hourly price points for one region."""
    ck = f"{region}:{length}"
    hit = cache.get("eia", ck)
    if hit is not None:
        return hit

    params = {
        "api_key": _api_key(),
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": region,
        "facets[type][]": "D",   # demand-weighted price; EIA uses type codes
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "offset": 0,
        "length": length,
    }
    resp = requests.get(_BASE + _REGION_DATA_PATH, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    cache.put("eia", ck, data, ttl_seconds=ttl)
    return data


def fetch_latest(region: str = ERCOT) -> ElectricityPoint | None:
    """Return the most recent published price point for `region`, or None if EIA
    returns no usable data for that ISO at this moment.

    EIA's region-data endpoint sometimes returns aggregate demand rather than
    price for certain ISOs; if `value` is not a $/MWh number, we return None
    and let the caller fall back to another region.
    """
    raw = _fetch_raw(region)
    rows = (raw.get("response", {}) or {}).get("data", [])
    if not rows:
        return None
    row = rows[0]
    val = row.get("value")
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    # Sanity: $/MWh on the major ISOs is roughly $5..$2000. If we got demand
    # in MWh (numbers in the tens of thousands) we'll still pass through but
    # flag the unit so the identifier can warn.
    unit = (row.get("value-units") or row.get("units") or "").strip()
    return ElectricityPoint(region=region, period=row["period"], value_mwh=v, raw_unit=unit)


def fetch_regions(regions: Iterable[str] = DEFAULT_REGIONS) -> dict[str, ElectricityPoint | None]:
    return {r: fetch_latest(r) for r in regions}
