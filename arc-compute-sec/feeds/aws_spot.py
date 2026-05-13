"""AWS EC2 Spot pricing fetcher. Public, no auth.

We use the spot-price-history JSON published at
https://spot-price.s3.amazonaws.com/spot.json (legacy global), and fall back
to per-region price-list endpoints if needed.

Instance focus: GPU compute proxies.
  - p4d.24xlarge — 8 × A100 (40 GB), ~3500 W
  - p5.48xlarge  — 8 × H100, ~6000 W

Spot prices update ~every 5 minutes. We cache 5 minutes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

import requests

from . import cache

_SPOT_FEED = "https://spot-price.s3.amazonaws.com/spot.json"

# GPU instance proxies and their nominal GPU counts (for $/gpu-hr conversion).
GPU_INSTANCES = {
    "p4d.24xlarge": 8,
    "p4de.24xlarge": 8,
    "p5.48xlarge": 8,
    "p5e.48xlarge": 8,
    "g5.48xlarge": 8,   # A10G; weaker but a useful liquid proxy
}

DEFAULT_REGIONS = ("us-east-1", "us-west-2")


@dataclass(frozen=True, slots=True)
class SpotPoint:
    region: str
    instance_type: str
    os_type: str
    price_per_hour: float
    gpu_count: int
    price_per_gpu_hour: float


def _fetch_raw(ttl: float = 300.0) -> dict:
    hit = cache.get("aws_spot", "global")
    if hit is not None:
        return hit
    resp = requests.get(_SPOT_FEED, timeout=20)
    resp.raise_for_status()
    # AWS wraps in JSONP-ish "callback({...})"; tolerate both shapes.
    text = resp.text.strip()
    if text.startswith("callback("):
        text = text[len("callback("):].rstrip(");")
    data = json.loads(text)
    cache.put("aws_spot", "global", data, ttl_seconds=ttl)
    return data


def fetch_gpu_spot(
    regions: Iterable[str] = DEFAULT_REGIONS,
    instances: Iterable[str] = ("p4d.24xlarge", "p5.48xlarge"),
    os_type: str = "linux",
) -> list[SpotPoint]:
    """Return one SpotPoint per (region, instance, os) tuple that exists.

    If the feed is missing a specific size, that tuple is skipped. Caller
    should handle empty list (fall back to a different instance or region).
    """
    data = _fetch_raw()
    points: list[SpotPoint] = []
    region_set = set(regions)
    instance_set = set(instances)
    # The legacy spot.json shape is approximately:
    #   {"vers": ..., "config": {"rate": ..., "valueColumns": [...],
    #     "regions": [{"region": "us-east-1",
    #                  "instanceTypes": [{"type": "generalCurrentGen",
    #                                     "sizes": [{"size": "p4d.24xlarge",
    #                                                "valueColumns": [
    #                                                  {"name": "linux",
    #                                                   "prices": {"USD": "12.345"}}]}]}]}]}}
    config = data.get("config") or {}
    for region in config.get("regions", []):
        rname = region.get("region")
        if rname not in region_set:
            continue
        for itype in region.get("instanceTypes", []):
            for size in itype.get("sizes", []):
                sname = size.get("size")
                if sname not in instance_set:
                    continue
                gpu_count = GPU_INSTANCES.get(sname, 1)
                for col in size.get("valueColumns", []):
                    if col.get("name") != os_type:
                        continue
                    raw = (col.get("prices") or {}).get("USD")
                    try:
                        price = float(raw)
                    except (TypeError, ValueError):
                        continue
                    if price <= 0:
                        continue
                    points.append(
                        SpotPoint(
                            region=rname,
                            instance_type=sname,
                            os_type=os_type,
                            price_per_hour=price,
                            gpu_count=gpu_count,
                            price_per_gpu_hour=price / gpu_count,
                        )
                    )
    return points
