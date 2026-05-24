"""Canonical spread exposure package.

The package is the product object the Arc job wraps. Individual venues are
only expression legs:

1. Compute the electricity-compute spread.
2. Build a canonical package with a thesis and intended leg map.
3. Express the package through available direct event legs and proxy legs.
4. Let the judge decide; only EXECUTE can reach Arc.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, Iterable

from agent.arb_identifier import (
    ArbSignal,
    DIRECTION_COMPUTE_EXPENSIVE,
    DIRECTION_ELEC_EXPENSIVE,
)

PACKAGE_VERSION = "spread_package_v1"

FOUR_STEP_FLOW = [
    "Compute S_t = compute_per_gpu_hr - k * electricity_per_MWh * kWh_per_gpu_hr.",
    "Canonicalize the signal, expected direction, leg map, and venue evidence into one package blob.",
    "Express the package through direct prediction-event legs first, then clearly labelled liquid proxy legs.",
    "Call judge.classify(); only EXECUTE can wrap the package as an Arc ERC-8183 job.",
]


def _hash_payload(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(body).hexdigest()


def _direction_thesis(signal: ArbSignal) -> tuple[str, str, list[dict[str, Any]]]:
    if signal.direction == DIRECTION_ELEC_EXPENSIVE:
        thesis = (
            "Electricity is expensive relative to GPU compute. The package "
            "expects energy/grid stress to outperform compute-demand outcomes "
            "and miner-margin-sensitive proxies."
        )
        payoff = (
            "Pays if the long energy-stress leg or short compute-demand/miner "
            "proxy leg wins over the signal TTL."
        )
        intended_pair = [
            {
                "role": "direct_energy_leg",
                "surface": "polymarket",
                "direction": "long",
                "instrument": "energy/grid stress outcome",
                "economic_link": "Direct claim on the energy side of the spread.",
                "directness": "direct",
            },
            {
                "role": "direct_compute_demand_leg",
                "surface": "polymarket",
                "direction": "short",
                "instrument": "AI release/popularity/compute-demand outcome",
                "economic_link": "Power stress can delay or reduce compute-heavy AI activity.",
                "directness": "direct",
            },
        ]
    elif signal.direction == DIRECTION_COMPUTE_EXPENSIVE:
        thesis = (
            "GPU compute is expensive relative to electricity. The package "
            "expects compute-demand outcomes to outperform energy-stress "
            "outcomes."
        )
        payoff = (
            "Pays if the long compute-demand leg or short energy-stress leg "
            "wins over the signal TTL."
        )
        intended_pair = [
            {
                "role": "direct_compute_demand_leg",
                "surface": "polymarket",
                "direction": "long",
                "instrument": "AI release/popularity/compute-demand outcome",
                "economic_link": "Direct claim on the compute-demand side of the spread.",
                "directness": "direct",
            },
            {
                "role": "direct_energy_leg",
                "surface": "polymarket",
                "direction": "short",
                "instrument": "energy/grid stress outcome",
                "economic_link": "Relative-value hedge against energy stress.",
                "directness": "direct",
            },
        ]
    else:
        thesis = "No actionable spread direction."
        payoff = "No package should be wrapped without an actionable signal."
        intended_pair = []
    return thesis, payoff, intended_pair


def leg_role_for_candidate(candidate: Any) -> dict[str, Any]:
    surface = getattr(candidate, "surface", "")
    instrument = getattr(candidate, "instrument", "")
    direction = getattr(candidate, "direction", "")
    metadata = getattr(candidate, "metadata", {}) or {}

    if surface in {"polymarket", "ibkr_prediction", "kalshi"}:
        template = metadata.get("energy_template_id") or ""
        venue = metadata.get("venue") or (
            "IBKR ForecastTrader" if surface == "ibkr_prediction" else surface
        )
        title = metadata.get("title") or instrument
        return {
            "role": "direct_prediction_event",
            "surface": surface,
            "venue": venue,
            "instrument": instrument,
            "direction": direction,
            "title": title,
            "slug": metadata.get("slug") or "",
            "description": metadata.get("description") or "",
            "start_date": metadata.get("start_date") or "",
            "end_date": metadata.get("end_date") or "",
            "energy_template_id": template,
            "economic_link": (
                "Prediction/event-contract leg. It is direct when paired as "
                "long energy/grid stress versus short AI compute-demand, or "
                "the inverse for compute-expensive signals."
            ),
            "directness": "direct_when_event_matches_thesis",
        }
    if surface == "crypto":
        return {
            "role": "miner_margin_proxy",
            "surface": surface,
            "instrument": instrument,
            "direction": direction,
            "title": f"{instrument} miner-margin proxy",
            "economic_link": (
                "BTC/USD or ETH/USD is not the securitized claim. It is a "
                "liquid proxy for miner-margin stress: mining revenue is crypto "
                "price times block reward, while power is the largest variable "
                "cost."
            ),
            "directness": "proxy",
        }
    if surface == "ibkr":
        return {
            "role": "liquid_equity_proxy",
            "surface": surface,
            "instrument": instrument,
            "direction": direction,
            "title": f"{instrument} liquid equity proxy",
            "economic_link": (
                "Paper equity proxy for cloud/miner margin sensitivity to the "
                "energy-compute spread."
            ),
            "directness": "proxy",
        }
    return {
        "role": "unknown_leg",
        "surface": surface,
        "instrument": instrument,
        "direction": direction,
        "economic_link": "No package mapping is defined for this surface.",
        "directness": "unknown",
    }


def build_package(signal: ArbSignal, candidates: Iterable[Any]) -> dict[str, Any]:
    legs = [leg_role_for_candidate(candidate) for candidate in candidates]
    thesis, payoff, intended_pair = _direction_thesis(signal)
    payload = {
        "version": PACKAGE_VERSION,
        "arb_signal_id": signal.signal_id,
        "direction": signal.direction,
        "signal": {
            "region": signal.region,
            "S_t": signal.S_t,
            "z": signal.z,
            "conviction": signal.conviction,
            "ttl_hours": signal.ttl_hours,
            "electricity_per_mwh": signal.electricity_per_mwh,
            "compute_per_gpu_hr": signal.compute_per_gpu_hr,
        },
        "thesis": thesis,
        "expected_payoff": payoff,
        "intended_direct_pair": intended_pair,
        "available_expression_legs": legs,
        "flow": FOUR_STEP_FLOW,
        "risk_note": (
            "Proxy legs such as BTC/USD, ETH/USD, or equities are labelled "
            "as proxies and must not be presented as the direct securitized "
            "energy-compute claim."
        ),
    }
    payload["package_hash"] = _hash_payload(payload)
    payload["package_id"] = payload["package_hash"][:12]
    return payload


def annotate_candidates(signal: ArbSignal, candidates: list[Any]) -> list[Any]:
    package = build_package(signal, candidates)
    out = []
    for candidate in candidates:
        metadata = dict(getattr(candidate, "metadata", {}) or {})
        metadata["spread_package"] = package
        metadata["spread_leg"] = leg_role_for_candidate(candidate)
        out.append(replace(candidate, metadata=metadata))
    return out


def package_summary_for_candidate(candidate_dict: dict[str, Any]) -> dict[str, Any] | None:
    metadata = candidate_dict.get("metadata") or {}
    package = metadata.get("spread_package")
    if isinstance(package, dict):
        return {
            "package_id": package.get("package_id"),
            "version": package.get("version"),
            "thesis": package.get("thesis"),
            "expected_payoff": package.get("expected_payoff"),
            "selected_leg": metadata.get("spread_leg") or {},
            "package_hash": package.get("package_hash"),
        }
    return None
