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
    pricing_status = _first_nonempty(row.get("pricing_status"), row.get("status"), row.get("label"))
    return {
        "surface": surface,
        "title": _leg_title(row),
        "slug": _leg_slug(row),
        "role": role,
        "direction": _first_nonempty(row.get("direction"), row.get("dir"), default="watch"),
        "status": _first_nonempty(row.get("label"), row.get("status"), row.get("pricing_status"), default="WATCHLIST"),
        "resolution": _first_nonempty(row.get("leg_end_date"), row.get("end_date")),
        "pricing_status": pricing_status,
        "status_label": _status_label(pricing_status),
        "last_price": row.get("last_price", ""),
        "currency": _text(row.get("currency")),
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
    pricing = _text(row.get("pricing_status")).lower()
    surface = _text(row.get("surface"))
    if row.get("inventory") and surface in DIRECT_SURFACES and label != "EXECUTE":
        return pricing == "priced_watchlist"
    return (
        label != "REJECT"
        and "unpriced" not in pricing
        and pricing != "metadata_watchlist"
        and pricing != "price_unavailable"
        and not row.get("is_mock")
        and not row.get("is_thesis_mismatch")
        and not row.get("is_legacy_artifact")
    )


def _status_label(status: Any) -> str:
    low = _text(status).lower()
    if low == "unpriced_snapshot":
        return "Needs live venue price"
    if low == "metadata_watchlist":
        return "Metadata only"
    if low == "priced_watchlist":
        return "Live price available"
    if low == "priced_public_market":
        return "Public price available"
    if low == "price_unavailable":
        return "Price unavailable"
    if low == "closed_watchlist":
        return "Closed"
    return _text(status, default="Needs review").replace("_", " ")


def _gap_next_step(row: dict[str, Any]) -> str:
    surface = _text(row.get("surface"))
    pricing = _text(row.get("pricing_status")).lower()
    if surface == "ibkr_prediction" and "unpriced" in pricing:
        return "Reconnect IBKR Client Portal, fetch EC bid/ask or yes/no contracts, then rerun priced discovery."
    if surface == "polymarket" and pricing == "metadata_watchlist":
        return "Fetch Gamma market prices and run the premium scorer before showing this as a direct reference."
    if pricing == "price_unavailable":
        return "Fetch a current public quote or replace the leg with a priced proxy."
    return "Add price, tenor, and liquidity before promoting this row."


def _discovery_gap(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    pricing = _text(row.get("pricing_status")).lower()
    label = _text(row.get("label")).upper()
    reason = _first_nonempty(row.get("reason_code"), row.get("pricing_status"), row.get("label"), default="not priced")
    if label == "REJECT" or "unpriced" in pricing or pricing in {"metadata_watchlist", "price_unavailable"}:
        return {
            "surface": _text(row.get("surface")),
            "title": _leg_title(row),
            "slug": _leg_slug(row),
            "role": _leg_role(row),
            "reason": reason,
            "status_label": _status_label(reason),
            "next_step": _gap_next_step(row),
        }
    return None


def _best_package(packages: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    ranked = {"EXECUTE": 0, "CHALLENGE": 1, "DEFER": 2, "PENDING": 3, "REJECT": 4}
    valid = [pkg for pkg in packages if isinstance(pkg, dict)]
    if not valid:
        return None
    return sorted(valid, key=lambda pkg: (ranked.get(_text(pkg.get("label")), 9), -_num(pkg.get("ts"))))[0]


def _agent_actions(
    direct_legs: list[dict[str, Any]],
    hedge_basket: list[dict[str, Any]],
    discovery_gaps: list[dict[str, Any]],
    collateral_status: str,
) -> list[str]:
    actions = []
    has_energy = any("energy" in leg["role"].lower() or "power" in leg["role"].lower() or "grid" in leg["role"].lower() for leg in direct_legs)
    has_compute = any("compute" in leg["role"].lower() or "ai" in leg["role"].lower() or "nvidia" in leg["title"].lower() for leg in direct_legs)
    if not has_energy:
        actions.append("Find one direct regional energy/grid-stress leg with slug, venue, tenor, and pricing.")
    if not has_compute:
        actions.append("Find one direct AI compute-demand or GPU-infrastructure leg with slug, venue, tenor, and pricing.")
    if not hedge_basket:
        actions.append("Fetch priced public hedge proxies before showing a tradable basket.")
    if direct_legs:
        actions.append("Run the premium scorer and judge on the matched direct pair before any Arc action.")
    if hedge_basket:
        actions.append("Size the priced public hedge basket by volatility and liquidity, then freeze direction/quantum/tenor for the next run.")
    if discovery_gaps:
        actions.append("Keep unpriced IBKR/Polymarket rows in discovery gaps, not in the hedge basket.")
    if collateral_status != "asset_backed":
        actions.append("Request real collateral files: GPU rental receivables, compute invoices, PPAs, power hedges, or escrow proof.")
    actions.append("Apply FDR/search-adjusted promotion: count every tested slug/model before calling a strategy robust.")
    actions.append("Backtest the exact leg pair against historical spread moves before promoting it to channel alerts.")
    return actions


def _build_instructions(
    direct_legs: list[dict[str, Any]],
    hedge_basket: list[dict[str, Any]],
    discovery_gaps: list[dict[str, Any]],
    collateral_status: str,
) -> list[dict[str, str]]:
    hedge_names = ", ".join(leg["slug"] for leg in hedge_basket[:4]) or "no priced basket yet"
    direct_names = ", ".join(leg["slug"] for leg in direct_legs[:3]) or "no priced direct pair yet"
    gap_names = ", ".join(gap["slug"] for gap in discovery_gaps[:3]) or "none"
    return [
        {
            "status": "READY" if collateral_status == "asset_backed" else "NEEDS COLLATERAL",
            "title": "Attach compute sale",
            "detail": "Upload or hash the GPU-hour invoice, rental receivable, delivery meter, and buyer/seller terms.",
        },
        {
            "status": "READY" if hedge_basket else "NEEDS PRICE",
            "title": "Freeze priced hedge basket",
            "detail": f"Use public-priced proxies for sizing now: {hedge_names}.",
        },
        {
            "status": "READY" if direct_legs else "SEARCHING",
            "title": "Match direct event legs",
            "detail": f"Pair one energy/grid leg with one compute-demand leg: {direct_names}.",
        },
        {
            "status": "NEEDS ACTION" if discovery_gaps else "CLEAR",
            "title": "Resolve discovery gaps",
            "detail": f"Rows needing price or eligibility before promotion: {gap_names}.",
        },
        {
            "status": "LOCKED",
            "title": "Judge then Arc wrap",
            "detail": "Run premium scorer, judge.classify(), and only then create the ERC-8183 job if verdict is EXECUTE.",
        },
    ]


def _schematic_steps(
    *,
    collateral_status: str,
    hedge_basket: list[dict[str, Any]],
    direct_legs: list[dict[str, Any]],
    discovery_gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "key": "cashflow",
            "label": "1. Compute sale",
            "status": "ready" if collateral_status == "asset_backed" else "needs collateral",
            "detail": "Forward GPU-hours, invoice or receivable, delivery meter.",
        },
        {
            "key": "hedge",
            "label": "2. Priced hedge basket",
            "status": "ready" if hedge_basket else "needs price",
            "detail": ", ".join(leg["slug"] for leg in hedge_basket[:5]) or "Fetch public market quotes.",
        },
        {
            "key": "direct_refs",
            "label": "3. Direct event refs",
            "status": "ready" if direct_legs else "searching",
            "detail": ", ".join(leg["slug"] for leg in direct_legs[:4]) or "Search Polymarket/IBKR/Kalshi style event legs.",
        },
        {
            "key": "judge",
            "label": "4. Judge gates",
            "status": "pending",
            "detail": "Energy classifier, premium scorer, judge.classify().",
        },
        {
            "key": "arc",
            "label": "5. Arc wrap",
            "status": "locked" if discovery_gaps or collateral_status != "asset_backed" else "ready",
            "detail": "ERC-8183 job only after EXECUTE.",
        },
    ]


def _agent_search_plan(
    region_profile: dict[str, Any],
    direction_profile: dict[str, str],
    direct_legs: list[dict[str, Any]],
    discovery_gaps: list[dict[str, Any]],
) -> list[dict[str, str]]:
    region = _text(region_profile.get("region"), "ERCOT/Texas")
    direct_pair = direction_profile["direct_pair"]
    has_energy = any("energy" in leg["role"].lower() or "power" in leg["role"].lower() or "grid" in leg["role"].lower() for leg in direct_legs)
    has_compute = any("compute" in leg["role"].lower() or "ai" in leg["role"].lower() or "gpu" in leg["title"].lower() for leg in direct_legs)
    gap_slugs = ", ".join(gap["slug"] for gap in discovery_gaps[:4]) or "none"
    return [
        {
            "surface": "opoint_nebius",
            "target": "news-grounded spread drivers",
            "query": f"{region} data center power grid interconnection AI GPU capacity electricity price",
            "reason": "Find evidence that power, grid, GPU, or AI-capacity news is driving the current spread.",
        },
        {
            "surface": "polymarket",
            "target": "direct event pair",
            "query": f"{direct_pair}; data center moratorium, AI capex, GPU shortage, power grid stress",
            "reason": "Find priced event contracts that can become direct references after premium scoring.",
        },
        {
            "surface": "ibkr_forecasttrader",
            "target": "forecast contract pricing",
            "query": f"Refresh EC prices for discovery gaps: {gap_slugs}",
            "reason": "Replace metadata-only ForecastTrader rows with priced yes/no contracts.",
        },
        {
            "surface": "public_market",
            "target": "liquid hedge basket",
            "query": "NVDA VRT ETN CEG NRG BTC-USD ETH-USD plus liquid data-center power beneficiaries",
            "reason": "Keep a priced, liquid hedge basket while direct event markets are thin.",
        },
        {
            "surface": "backtest",
            "target": "spread-linked validation",
            "query": "walk-forward test of each slug/symbol against electricity-compute spread changes",
            "reason": "Count every tested slug/model for FDR-style promotion control.",
        },
    ]


def propose_synthetic_instrument(
    *,
    spread: dict[str, Any],
    signal: dict[str, Any],
    direct_inventory: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    positions: list[dict[str, Any]] | None = None,
    public_hedges: list[dict[str, Any]] | None = None,
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
    discovery_gaps = [
        gap for gap in (_discovery_gap(leg) for leg in direct_inventory)
        if gap is not None
    ][:6]
    direct_legs = _dedupe_legs([*package_direct, *visible_inventory])
    proxy_source = package_proxy or [
        row for row in verdicts
        if _text(row.get("surface")) not in DIRECT_SURFACES and _proposal_visible_leg(row)
    ]
    proxy_legs = _dedupe_legs(proxy_source)
    priced_public_hedges = [
        row for row in (public_hedges or [])
        if _proposal_visible_leg(row) and row.get("last_price") not in ("", None)
    ]
    hedge_basket = _dedupe_legs([*priced_public_hedges, *proxy_source], limit=8)
    collateral_status = "asset_backed" if any(_text((pos or {}).get("collateral_hash")) for pos in (positions or [])) else "not_asset_backed_v0"
    tenor_days = max(1, int(_num((package or {}).get("ttl_hours"), 24.0) / 24.0) if package else 30)
    build_instructions = _build_instructions(direct_legs, hedge_basket, discovery_gaps, collateral_status)
    schematic_steps = _schematic_steps(
        collateral_status=collateral_status,
        hedge_basket=hedge_basket,
        direct_legs=direct_legs,
        discovery_gaps=discovery_gaps,
    )
    agent_search_plan = _agent_search_plan(region_profile, direction_profile, direct_legs, discovery_gaps)

    thesis = (
        f"Hedge a forward compute sale in {region_profile['short_name']} against AI compute demand. "
        f"{direction_profile['payoff']} Target direct pair: {direction_profile['direct_pair']}. "
        "Like hedging a physical shipment, the product starts from a commercial cashflow, then wraps a priced hedge basket. "
        "The agent must prove the selected legs are driven by the spread, not by a generic top-down compute index."
    )
    payload = {
        "version": SYNTHETIC_INSTRUMENT_VERSION,
        "direction": direction,
        "region": region_profile["region"],
        "reference_package_id": (package or {}).get("package_id") or (package or {}).get("id") or signal_latest.get("signal_id", ""),
        "direct_leg_slugs": [leg["slug"] for leg in direct_legs],
        "proxy_leg_slugs": [leg["slug"] for leg in proxy_legs],
        "hedge_leg_slugs": [leg["slug"] for leg in hedge_basket],
        "z": _num(signal_latest.get("z")),
        "S_t": _num(signal_latest.get("S_t"), _num(spread_latest.get("S_t"))),
    }
    instrument_hash = _hash_payload(payload)
    return {
        **payload,
        "proposal_id": instrument_hash[:12],
        "instrument_name": f"{region_profile['short_name']} compute receivable hedge note {instrument_hash[:6]}",
        "status": "PROPOSED" if direction != "no_signal" else "RESEARCH",
        "proposal_type": "compute_receivable_hedge_note",
        "asset_backed": collateral_status == "asset_backed",
        "collateral_status": collateral_status,
        "thesis": thesis,
        "region_profile": region_profile,
        "structure": {
            "securitization_style": "synthetic hedge note around a compute sale; not legal ABS until collateral is attached",
            "reference_obligation": "forward GPU-hour sale receivable plus priced public hedge basket",
            "settlement_rail": "Arc ERC-8183 only after judge.classify() returns EXECUTE",
            "cashflow_model": "fixed compute-sale revenue minus floating power/compute hedge basket PnL; no fixed coupon in v1",
            "tenor_days": tenor_days,
            "index_governance": {
                "direction": "agent chooses long/short exposure from the spread signal",
                "quantum": "weights sized from volatility, liquidity, and judge-approved notional",
                "tenor": "proposal tenor must match commercial compute sale tenor and signal TTL",
                "rebalance": "daily review; no channel alert unless priced basket and judge gate pass",
                "input_hierarchy": ["commercial compute exposure", "public priced hedges", "direct event contracts", "oracle/news evidence"],
            },
            "rwa_upgrade_path": [
                "GPU rental receivables",
                "compute invoices",
                "data-center power purchase agreements",
                "miner power hedges",
                "escrowed USDC or tokenized collateral claim",
            ],
            "schematic_steps": schematic_steps,
        },
        "inputs": {
            "spread_formula": "S_t = compute_per_gpu_hr - k * electricity_per_MWh / 1000 * kWh_per_gpu_hr",
            "underlying_contract": {
                "type": "forward_compute_sale",
                "seller_risk": "seller delivers GPU-hours and is short power/availability/capacity cost inflation",
                "buyer_risk": "buyer wants predictable compute cost and delivery evidence",
                "required_for_asset_backing": ["signed compute invoice or receivable", "delivery meter", "PPA or power hedge", "escrow or collateral proof"],
            },
            "electricity_per_mwh": _num(spread_latest.get("electricity_per_mwh"), _num(signal_latest.get("electricity_per_mwh"))),
            "compute_per_gpu_hr": _num(spread_latest.get("compute_per_gpu_hr"), _num(signal_latest.get("compute_per_gpu_hr"))),
            "z": _num(signal_latest.get("z")),
            "energy_stack": region_profile["energy_stack"],
            "oracle_role": "Opoint/Nebius evidence can propose or criticize links, but cannot replace scorer or judge gates.",
            "search_adjustment": {
                "tested_candidates": len(direct_inventory) + len(public_hedges or []) + len(verdicts),
                "rule": "FDR-style search penalty: every tested slug/model counts before promoting a robust product.",
            },
        },
        "outputs": {
            "direct_reference_legs": direct_legs,
            "proxy_reference_legs": proxy_legs,
            "priced_hedge_basket": hedge_basket,
            "discovery_gaps": discovery_gaps,
            "build_instructions": build_instructions,
            "agent_search_plan": agent_search_plan,
            "guardrails": [
                "No on-chain action before judge.classify().",
                "No Arc action unless verdict is EXECUTE.",
                "Polymarket premium gate remains required when Polymarket is used.",
                "Proxy legs must not be marketed as asset-backed compute or power claims.",
            ],
            "agent_next_actions": _agent_actions(direct_legs, hedge_basket, discovery_gaps, collateral_status),
        },
        "monetization_path": [
            "paid discovery/watchlist feed",
            "paid judge verdicts and backtest reports",
            "structuring/API fee for Arc-wrapped packages",
            "future RWA lending support only when real collateral is attached",
        ],
    }
