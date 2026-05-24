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
DEFAULT_DEMO_GPU_HOURS = 5_000.0
DEFAULT_GPU_KWH = 0.7
DEFAULT_HEDGE_RATIO = 0.35
ARC_SETTLEMENT_BUFFER_USDC = 5.0
LIQUIDITY_BUFFER_RATE = 0.05
WEIGHTS_ELECTRICITY_EXPENSIVE = {
    "NRG": 0.24,
    "CEG": 0.20,
    "ETN": 0.14,
    "VRT": 0.12,
    "NVDA": -0.20,
    "BTC-USD": -0.07,
    "ETH-USD": -0.03,
}
WEIGHTS_COMPUTE_EXPENSIVE = {
    "NVDA": 0.34,
    "VRT": 0.20,
    "ETN": 0.14,
    "CEG": -0.14,
    "NRG": -0.10,
    "BTC-USD": 0.05,
    "ETH-USD": 0.03,
}
LEG_EXPLANATIONS = {
    "NVDA": {
        "what": "GPU supply and AI accelerator capex proxy.",
        "driver": "Moves with AI compute demand, datacenter GPU purchasing, and inference/training capex expectations.",
        "sell_reason": "The NVIDIA leg is hurting the mock contract when AI chip demand reprices against the chosen short/long side.",
    },
    "VRT": {
        "what": "Datacenter power and cooling infrastructure proxy.",
        "driver": "Moves with datacenter buildout, cooling systems, UPS gear, and electrical infrastructure orders.",
        "sell_reason": "The Vertiv leg is hurting the mock contract when datacenter infrastructure demand moves against the hedge.",
    },
    "ETN": {
        "what": "Grid electrification and power equipment proxy.",
        "driver": "Moves with transformer, switchgear, grid upgrade, and industrial electrification demand.",
        "sell_reason": "The Eaton leg is hurting the mock contract when grid-equipment beta moves against the hedge.",
    },
    "CEG": {
        "what": "Nuclear-heavy baseload power proxy.",
        "driver": "Moves with clean baseload scarcity, data-center PPAs, and power procurement premiums.",
        "sell_reason": "The Constellation leg is hurting the mock contract when clean-power scarcity is not confirming the thesis.",
    },
    "NRG": {
        "what": "Merchant power and retail load proxy.",
        "driver": "Moves with merchant power price exposure, retail load, and regional electricity margin expectations.",
        "sell_reason": "The NRG leg is hurting the mock contract when merchant-power exposure is not confirming the thesis.",
    },
    "BTC-USD": {
        "what": "Proof-of-work miner-margin proxy.",
        "driver": "Mining revenue is crypto-linked while electricity is a major variable cost; power spikes can compress miner margins.",
        "sell_reason": "The BTC leg is hurting the mock contract when miner-margin beta moves against the power-cost hedge.",
    },
    "ETH-USD": {
        "what": "Crypto beta and liquidity proxy.",
        "driver": "Retained as a liquid beta reference for crypto-risk appetite; it is not a direct electricity claim.",
        "sell_reason": "The ETH leg is hurting the mock contract when broad crypto beta overwhelms the spread thesis.",
    },
}


def _hash_payload(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(body).hexdigest()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round_money(value: Any) -> float:
    return round(_num(value), 2)


def _round_units(value: Any) -> float:
    out = _num(value)
    return round(out, 8 if abs(out) < 1 else 4)


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
        "source": _text(row.get("source")),
        "exchange": _text(row.get("exchange")),
        "description": _first_nonempty(row.get("leg_description"), row.get("description")),
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
    mock_construction: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    hedge_names = ", ".join(leg["slug"] for leg in hedge_basket[:4]) or "no priced basket yet"
    direct_names = ", ".join(leg["slug"] for leg in direct_legs[:3]) or "no priced direct pair yet"
    gap_names = ", ".join(gap["slug"] for gap in discovery_gaps[:3]) or "none"
    circle_ask = _round_money((mock_construction or {}).get("circle_testnet_usdc_request"))
    circle_detail = (
        f"Request {circle_ask:,.2f} test USDC from Circle for hedge notional, liquidity buffer, and Arc settlement buffer."
        if circle_ask > 0
        else "Request Circle test USDC after the hedge notional is sized."
    )
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
            "status": "READY" if circle_ask > 0 else "NEEDS SIZE",
            "title": "Request Circle test USDC",
            "detail": circle_detail,
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


def _weights_for_direction(direction: str) -> dict[str, float]:
    if direction == DIRECTION_COMPUTE_EXPENSIVE:
        return WEIGHTS_COMPUTE_EXPENSIVE
    return WEIGHTS_ELECTRICITY_EXPENSIVE


def _weighted_hedge_legs(hedge_basket: list[dict[str, Any]], hedge_notional: float, direction: str) -> list[dict[str, Any]]:
    weights = _weights_for_direction(direction)
    rows: list[dict[str, Any]] = []
    remaining = 1.0
    unweighted: list[dict[str, Any]] = []
    for leg in hedge_basket:
        slug = _text(leg.get("slug")).upper()
        if slug in weights:
            remaining -= abs(weights[slug])
        else:
            unweighted.append(leg)
    fallback_weight = max(0.0, remaining) / len(unweighted) if unweighted else 0.0
    for leg in hedge_basket:
        slug = _text(leg.get("slug")).upper()
        raw_weight = weights.get(slug, fallback_weight)
        price = _num(leg.get("last_price"))
        if price <= 0 or raw_weight == 0:
            continue
        leg_notional = hedge_notional * abs(raw_weight)
        side = "long" if raw_weight > 0 else "short"
        explanation = LEG_EXPLANATIONS.get(slug, {})
        rows.append({
            "surface": leg.get("surface", "public_market"),
            "slug": leg.get("slug"),
            "title": leg.get("title"),
            "side": side,
            "weight": round(raw_weight, 4),
            "last_price": _round_money(price),
            "currency": leg.get("currency") or "USD",
            "notional_usdc": _round_money(leg_notional),
            "units": _round_units(leg_notional / price),
            "role": leg.get("role"),
            "pricing_status": leg.get("pricing_status"),
            "source": leg.get("source") or "public_quote",
            "exchange": leg.get("exchange") or "",
            "description": explanation.get("what") or leg.get("description") or "",
            "risk_driver": explanation.get("driver") or leg.get("direct_pair_role") or leg.get("role") or "",
            "sell_reason": explanation.get("sell_reason") or f"{slug} moved against the mock hedge.",
            "tracking_symbol": slug,
        })
    total_abs = sum(abs(_num(row.get("weight"))) for row in rows) or 1.0
    if abs(total_abs - 1.0) > 0.0001:
        for row in rows:
            row["weight"] = round(_num(row.get("weight")) / total_abs, 4)
            row["notional_usdc"] = _round_money(hedge_notional * abs(_num(row["weight"])))
            row["units"] = _round_units(_num(row["notional_usdc"]) / _num(row["last_price"]))
    return rows


def _mock_hedge_construction(
    *,
    direction: str,
    spread_latest: dict[str, Any],
    signal_latest: dict[str, Any],
    hedge_basket: list[dict[str, Any]],
    direct_legs: list[dict[str, Any]],
) -> dict[str, Any]:
    compute_per_gpu_hr = _num(spread_latest.get("compute_per_gpu_hr"), _num(signal_latest.get("compute_per_gpu_hr")))
    electricity_per_mwh = _num(spread_latest.get("electricity_per_mwh"), _num(signal_latest.get("electricity_per_mwh")))
    gpu_hours = max(1.0, _num(spread_latest.get("demo_gpu_hours"), DEFAULT_DEMO_GPU_HOURS))
    gpu_kwh = max(0.01, _num(spread_latest.get("kWh_per_gpu_hr"), _num(signal_latest.get("kWh_per_gpu_hr"), DEFAULT_GPU_KWH)))
    receivable = compute_per_gpu_hr * gpu_hours
    power_cost = electricity_per_mwh / 1000.0 * gpu_kwh * gpu_hours
    margin = receivable - power_cost
    hedge_notional = max(100.0, receivable * DEFAULT_HEDGE_RATIO)
    weighted_legs = _weighted_hedge_legs(hedge_basket, hedge_notional, direction)
    direct_event_budget = 0.0
    liquidity_buffer = hedge_notional * LIQUIDITY_BUFFER_RATE
    circle_ask = hedge_notional + direct_event_budget + liquidity_buffer + ARC_SETTLEMENT_BUFFER_USDC
    circle_ask = float(int((circle_ask + 9.99) // 10 * 10))
    power_stress_loss = -(power_cost * 0.25 + receivable * 0.05)
    hedge_offset = hedge_notional * 0.10
    compute_relief_gain = receivable * 0.08
    hedge_drag = -hedge_notional * 0.04
    z_score = _num(signal_latest.get("z"))
    margin_ratio = margin / receivable if receivable > 0 else 0.0
    live_prices = [row for row in weighted_legs if _num(row.get("last_price")) > 0]
    profitability_score = abs(z_score) * 0.55 + max(-0.5, min(margin_ratio, 0.5))
    recommended_action = "BUY_CONTRACT" if live_prices and profitability_score >= 0.65 else "MONITOR_ONLY"
    quote_sources = sorted({
        _text(row.get("source"), "public_quote")
        for row in weighted_legs
        if row.get("source")
    }) or ["public_quote"]
    return {
        "demo": True,
        "label": "Mock testnet hedge construction",
        "based_on": "live public quote snapshots plus current electricity and compute inputs",
        "quote_sources": quote_sources,
        "recommended_action": recommended_action,
        "profitability_score": _round_units(profitability_score),
        "profitability_note": (
            "Buy the mock contract while the spread z-score is strong and the priced hedge basket confirms the thesis; "
            "monitor live leg drift and close when the biggest contributor turns the package negative."
        ),
        "demo_gpu_hours": _round_units(gpu_hours),
        "gpu_kwh_per_hr": _round_units(gpu_kwh),
        "receivable_usdc": _round_money(receivable),
        "estimated_power_cost_usdc": _round_money(power_cost),
        "estimated_compute_margin_usdc": _round_money(margin),
        "hedge_ratio": DEFAULT_HEDGE_RATIO,
        "hedge_notional_usdc": _round_money(hedge_notional),
        "direct_event_budget_usdc": _round_money(direct_event_budget),
        "liquidity_buffer_usdc": _round_money(liquidity_buffer),
        "arc_settlement_buffer_usdc": _round_money(ARC_SETTLEMENT_BUFFER_USDC),
        "circle_testnet_usdc_request": _round_money(circle_ask),
        "circle_request_note": "Request test USDC from Circle/faucet for demo funding only; do not transfer or wrap until judge.classify() returns EXECUTE.",
        "weighted_legs": weighted_legs,
        "scenario_checks": [
            {
                "name": "Power +25%, compute -5%",
                "unhedged_pnl_usdc": _round_money(power_stress_loss),
                "mock_hedge_offset_usdc": _round_money(hedge_offset),
                "net_pnl_usdc": _round_money(power_stress_loss + hedge_offset),
            },
            {
                "name": "Compute +8%, power flat",
                "unhedged_pnl_usdc": _round_money(compute_relief_gain),
                "mock_hedge_offset_usdc": _round_money(hedge_drag),
                "net_pnl_usdc": _round_money(compute_relief_gain + hedge_drag),
            },
        ],
        "limitations": [
            "Mock weights are deterministic demo weights, not executed orders.",
            "Public-market proxies are not direct claims on compute sale collateral.",
            "Circle USDC request funds this mock hedge and buffers only; venue event contracts stay in research scouting.",
        ],
        "agent_tooling": [
            {
                "name": "Quote scout",
                "uses": "IBKR, Alpaca, Yahoo/public quotes when configured",
                "job": "Refresh prices and mark stale or missing legs before recommending a buy.",
            },
            {
                "name": "Contract creator",
                "uses": "Arc ERC-8183 mock wrapper after judge EXECUTE",
                "job": "Freeze the canonical price blob, leg weights, and entry prices for tracking.",
            },
            {
                "name": "Profitability monitor",
                "uses": "live leg marks plus spread z-score",
                "job": "Recommend hold/sell and explain which leg is making the package unprofitable.",
            },
        ],
    }


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
    mock_construction = _mock_hedge_construction(
        direction=direction,
        spread_latest=spread_latest,
        signal_latest=signal_latest,
        hedge_basket=hedge_basket,
        direct_legs=direct_legs,
    )
    build_instructions = _build_instructions(direct_legs, hedge_basket, discovery_gaps, collateral_status, mock_construction)
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
            "mock_hedge_construction": mock_construction,
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
