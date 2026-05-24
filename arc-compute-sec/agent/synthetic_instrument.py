"""Agent-authored synthetic instrument proposals.

This module turns the current compute/energy state into a term-sheet shaped
proposal. It does not route capital, call venues, call LLMs, or call Arc. The
proposal is an auditable description of what the agent would try to securitize
next, and which real-world inputs are still missing before it becomes a true
asset-backed RWA.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from agent.arb_identifier import DIRECTION_COMPUTE_EXPENSIVE, DIRECTION_ELEC_EXPENSIVE

SYNTHETIC_INSTRUMENT_VERSION = "synthetic_instrument_v1"
DIRECT_SURFACES = {"polymarket", "ibkr_prediction", "kalshi"}


def _hash_payload(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(body).hexdigest()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any, default: str = "") -> str:
    out = str(value or "").strip()
    return out or default


def _first_nonempty(*values: Any, default: str = "") -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return default


def _region_profile(region: str) -> dict[str, Any]:
    low = region.lower()
    if "ercot" in low or "texas" in low or "retx" in low:
        return {
            "region": region or "ERCOT/Texas",
            "short_name": "ERCOT power",
            "energy_stack": ["natural gas marginal generation", "wind/solar intermittency", "transmission congestion"],
            "source_note": (
                "Texas compute and mining loads are exposed to local power volatility, gas-fired marginal supply, "
                "renewable intermittency, and congestion."
            ),
        }
    if "pjm" in low or "virginia" in low or "us-east" in low or "ashburn" in low:
        return {
            "region": region or "PJM/data-center corridor",
            "short_name": "PJM data-center power",
            "energy_stack": ["nuclear baseload", "natural gas balancing", "transmission/interconnect constraints"],
            "source_note": (
                "Nuclear baseload can reduce short-run energy volatility, but data-center interconnect queues, "
                "gas balancing, and transmission constraints still matter."
            ),
        }
    if "caiso" in low or "california" in low:
        return {
            "region": region or "CAISO/California",
            "short_name": "CAISO power",
            "energy_stack": ["solar duck-curve", "gas ramping", "battery/storage constraints"],
            "source_note": (
                "California compute loads face a solar-heavy daily shape, gas ramping costs, and local siting constraints."
            ),
        }
    return {
        "region": region or "multi-region",
        "short_name": "regional power",
        "energy_stack": ["local generation mix", "grid congestion", "power purchase agreements"],
        "source_note": (
            "The energy leg must be regional and source-aware; nuclear, gas, hydro, renewables, PPAs, and congestion "
            "create different compute-margin exposures."
        ),
    }


def _direction_profile(direction: str) -> dict[str, str]:
    if direction == DIRECTION_ELEC_EXPENSIVE:
        return {
            "name": "power-stress-over-compute",
            "payoff": "Long energy/grid-stress outcomes and short compute-demand or miner-margin-sensitive proxies.",
            "direct_pair": "long energy/grid stress vs short AI compute-demand",
        }
    if direction == DIRECTION_COMPUTE_EXPENSIVE:
        return {
            "name": "compute-scarcity-over-power",
            "payoff": "Long compute-demand/scarcity outcomes and short energy/grid-stress outcomes.",
            "direct_pair": "long AI compute-demand vs short energy/grid stress",
        }
    return {
        "name": "research-watchlist",
        "payoff": "No tradeable payoff until the spread signal clears threshold and a judged leg package exists.",
        "direct_pair": "discover one energy leg and one compute-demand leg",
    }


def _leg_role(row: dict[str, Any]) -> str:
    return _first_nonempty(row.get("direct_pair_role"), row.get("leg_role"), row.get("role"), default="expression leg")


def _leg_slug(row: dict[str, Any]) -> str:
    return _first_nonempty(row.get("leg_slug"), row.get("slug"), row.get("instrument"))


def _leg_title(row: dict[str, Any]) -> str:
    return _first_nonempty(row.get("display_label"), row.get("leg_title"), row.get("title"), row.get("instrument"), default="unknown leg")


def _leg_summary(row: dict[str, Any]) -> dict[str, Any]:
    surface = _text(row.get("surface"))
    role = _leg_role(row)
    return {
        "surface": surface,
        "title": _leg_title(row),
        "slug": _leg_slug(row),
        "role": role,
        "direction": _first_nonempty(row.get("direction"), row.get("dir"), default="watch"),
        "status": _first_nonempty(row.get("label"), row.get("status"), row.get("pricing_status"), default="WATCHLIST"),
        "resolution": _first_nonempty(row.get("leg_end_date"), row.get("end_date")),
        "directness": "direct" if surface in DIRECT_SURFACES or "direct" in role.lower() else "proxy",
    }


def _dedupe_legs(rows: Iterable[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        leg = _leg_summary(row)
        key = (leg["surface"], leg["slug"], leg["role"])
        if key in seen:
            continue
        seen.add(key)
        out.append(leg)
        if len(out) >= limit:
            break
    return out


def _proposal_visible_leg(row: dict[str, Any]) -> bool:
    label = _text(row.get("label")).upper()
    return (
        label != "REJECT"
        and not row.get("is_mock")
        and not row.get("is_thesis_mismatch")
        and not row.get("is_legacy_artifact")
    )


def _best_package(packages: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    ranked = {"EXECUTE": 0, "CHALLENGE": 1, "DEFER": 2, "PENDING": 3, "REJECT": 4}
    valid = [pkg for pkg in packages if isinstance(pkg, dict)]
    if not valid:
        return None
    return sorted(valid, key=lambda pkg: (ranked.get(_text(pkg.get("label")), 9), -_num(pkg.get("ts"))))[0]


def _agent_actions(direct_legs: list[dict[str, Any]], proxy_legs: list[dict[str, Any]], collateral_status: str) -> list[str]:
    actions = []
    has_energy = any("energy" in leg["role"].lower() or "power" in leg["role"].lower() or "grid" in leg["role"].lower() for leg in direct_legs)
    has_compute = any("compute" in leg["role"].lower() or "ai" in leg["role"].lower() or "nvidia" in leg["title"].lower() for leg in direct_legs)
    if not has_energy:
        actions.append("Find one direct regional energy/grid-stress leg with slug, venue, tenor, and pricing.")
    if not has_compute:
        actions.append("Find one direct AI compute-demand or GPU-infrastructure leg with slug, venue, tenor, and pricing.")
    if direct_legs:
        actions.append("Run the premium scorer and judge on the matched direct pair before any Arc action.")
    if proxy_legs:
        actions.append("Keep BTC/ETH/equity rows labelled as proxies and exclude them from asset-backed claims.")
    if collateral_status != "asset_backed":
        actions.append("Request real collateral files: GPU rental receivables, compute invoices, PPAs, power hedges, or escrow proof.")
    actions.append("Backtest the exact leg pair against historical spread moves before promoting it to channel alerts.")
    return actions


def propose_synthetic_instrument(
    *,
    spread: dict[str, Any],
    signal: dict[str, Any],
    direct_inventory: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    positions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the current agent-authored instrument proposal.

    The output is safe for README/frontend/TG display: it states that v1 is a
    synthetic reference package, not a legal ABS or asset-backed product.
    """
    signal_latest = signal.get("latest") if isinstance(signal, dict) else {}
    signal_latest = signal_latest if isinstance(signal_latest, dict) else {}
    spread_latest = spread.get("latest") if isinstance(spread, dict) else {}
    spread_latest = spread_latest if isinstance(spread_latest, dict) else {}
    package = _best_package(packages)
    direction = _first_nonempty(signal_latest.get("direction"), package.get("direction") if package else "", default="no_signal")
    region = _first_nonempty(signal_latest.get("region"), spread_latest.get("region"), default="multi-region")
    region_profile = _region_profile(region)
    direction_profile = _direction_profile(direction)

    package_direct = [leg for leg in (package.get("direct_legs", []) if package else []) if _proposal_visible_leg(leg)]
    package_proxy = [leg for leg in (package.get("proxy_legs", []) if package else []) if _proposal_visible_leg(leg)]
    visible_inventory = [leg for leg in direct_inventory if _proposal_visible_leg(leg)]
    direct_legs = _dedupe_legs([*package_direct, *visible_inventory])
    proxy_source = package_proxy or [
        row for row in verdicts
        if _text(row.get("surface")) not in DIRECT_SURFACES and _proposal_visible_leg(row)
    ]
    proxy_legs = _dedupe_legs(proxy_source)
    collateral_status = "asset_backed" if any(_text((pos or {}).get("collateral_hash")) for pos in (positions or [])) else "not_asset_backed_v0"

    thesis = (
        f"Reference {region_profile['short_name']} against AI compute demand. "
        f"{direction_profile['payoff']} Target direct pair: {direction_profile['direct_pair']}. "
        "The agent must prove the selected legs are driven by the spread, not by a generic top-down compute index."
    )
    payload = {
        "version": SYNTHETIC_INSTRUMENT_VERSION,
        "direction": direction,
        "region": region_profile["region"],
        "reference_package_id": (package or {}).get("package_id") or (package or {}).get("id") or signal_latest.get("signal_id", ""),
        "direct_leg_slugs": [leg["slug"] for leg in direct_legs],
        "proxy_leg_slugs": [leg["slug"] for leg in proxy_legs],
        "z": _num(signal_latest.get("z")),
        "S_t": _num(signal_latest.get("S_t"), _num(spread_latest.get("S_t"))),
    }
    instrument_hash = _hash_payload(payload)
    return {
        **payload,
        "proposal_id": instrument_hash[:12],
        "instrument_name": f"{region_profile['short_name']} / AI compute spread note {instrument_hash[:6]}",
        "status": "PROPOSED" if direction != "no_signal" else "RESEARCH",
        "proposal_type": "synthetic_reference_instrument",
        "asset_backed": collateral_status == "asset_backed",
        "collateral_status": collateral_status,
        "thesis": thesis,
        "region_profile": region_profile,
        "structure": {
            "securitization_style": "synthetic reference package, not legal ABS",
            "reference_obligation": "canonical compute/energy spread package plus selected venue legs",
            "settlement_rail": "Arc ERC-8183 only after judge.classify() returns EXECUTE",
            "cashflow_model": "external venue leg payoff; no fixed coupon in v1",
            "rwa_upgrade_path": [
                "GPU rental receivables",
                "compute invoices",
                "data-center power purchase agreements",
                "miner power hedges",
                "escrowed USDC or tokenized collateral claim",
            ],
        },
        "inputs": {
            "spread_formula": "S_t = compute_per_gpu_hr - k * electricity_per_MWh / 1000 * kWh_per_gpu_hr",
            "electricity_per_mwh": _num(spread_latest.get("electricity_per_mwh"), _num(signal_latest.get("electricity_per_mwh"))),
            "compute_per_gpu_hr": _num(spread_latest.get("compute_per_gpu_hr"), _num(signal_latest.get("compute_per_gpu_hr"))),
            "z": _num(signal_latest.get("z")),
            "energy_stack": region_profile["energy_stack"],
            "oracle_role": "Opoint/Nebius evidence can propose or criticize links, but cannot replace scorer or judge gates.",
        },
        "outputs": {
            "direct_reference_legs": direct_legs,
            "proxy_reference_legs": proxy_legs,
            "guardrails": [
                "No on-chain action before judge.classify().",
                "No Arc action unless verdict is EXECUTE.",
                "Polymarket premium gate remains required when Polymarket is used.",
                "Proxy legs must not be marketed as asset-backed compute or power claims.",
            ],
            "agent_next_actions": _agent_actions(direct_legs, proxy_legs, collateral_status),
        },
        "monetization_path": [
            "paid discovery/watchlist feed",
            "paid judge verdicts and backtest reports",
            "structuring/API fee for Arc-wrapped packages",
            "future RWA lending support only when real collateral is attached",
        ],
    }
