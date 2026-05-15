"""Phase 0.7 live feed smoke.

Fetches exactly the v0 feed pair used by the electricity-compute spread:
one ERCOT electricity proxy point from EIA and one AWS p4d.24xlarge
us-east-1 spot price. It clears only the EIA/AWS feed caches first so the
result proves live network access instead of a stale local cache hit.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from feeds import cache
from feeds.aws_spot import fetch_gpu_spot
from feeds.eia import ERCOT, fetch_latest


def main() -> int:
    cache.clear("eia")
    cache.clear("aws_spot")

    eia_point = fetch_latest(ERCOT)
    if eia_point is None:
        print("EIA ERCOT: no usable point", file=sys.stderr)
        return 1

    aws_points = fetch_gpu_spot(
        regions=("us-east-1",),
        instances=("p4d.24xlarge",),
        os_type="linux",
    )
    if not aws_points:
        print("AWS spot: no p4d.24xlarge us-east-1 linux price", file=sys.stderr)
        return 1
    aws_point = aws_points[0]

    print(
        "EIA ERCOT: "
        f"period={eia_point.period} state={eia_point.state} "
        f"value_mwh={eia_point.value_mwh:.4f} "
        f"raw={eia_point.raw_value:.4f} {eia_point.raw_unit}"
    )
    print(
        "AWS spot: "
        f"region={aws_point.region} instance={aws_point.instance_type} "
        f"os={aws_point.os_type} price_per_hour={aws_point.price_per_hour:.4f} "
        f"price_per_gpu_hour={aws_point.price_per_gpu_hour:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
