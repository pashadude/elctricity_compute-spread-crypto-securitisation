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

from agent import judge
from agent.arb_identifier import DIRECTION_COMPUTE_EXPENSIVE, DIRECTION_ELEC_EXPENSIVE
from agent.spread_family_backtest import SPREAD_ARCHETYPE_CATALOG

SYNTHETIC_INSTRUMENT_VERSION = "synthetic_instrument_v1"
DIRECT_SURFACES = {"polymarket", "ibkr_prediction", "kalshi"}
VENUE_COPY_ORDER = {
    "polymarket": 0,
    "kalshi": 1,
    "ibkr_prediction": 2,
    "public_market": 3,
    "crypto": 4,
    "opoint_nebius": 5,
}
DEFAULT_DEMO_GPU_HOURS = 5_000.0
DEFAULT_GPU_KWH = 0.7
DEFAULT_HEDGE_RATIO = 0.35
ARC_SETTLEMENT_BUFFER_USDC = 5.0
LIQUIDITY_BUFFER_RATE = 0.05
ENTRY_SIGNAL_BUY_THRESHOLD = 70.0
MIN_MODELED_POWER_COST_SHARE_FOR_BUY = 0.025
MIN_STRUCTURAL_POWER_COST_SHARE = 0.10
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

COLLATERAL_PROFILE_TEMPLATES = (
    {
        "profile_id": "cloud_gpu_receivable",
        "label": "Cloud GPU receivable",
        "cashflow": "Resold public-cloud GPU-hour receivable.",
        "compute_price_multiplier": 1.00,
        "kwh_multiplier": 1.00,
        "k_factor_multiplier": 1.00,
        "collateral_needed": ["GPU-hour invoice", "cloud bill hash", "delivery meter"],
        "best_for": "Compute scarcity, but usually weak as an electricity hedge.",
    },
    {
        "profile_id": "owned_colo_gpu_receivable",
        "label": "Owned / colocation GPU receivable",
        "cashflow": "GPU-hour receivable from owned servers or colocation with metered power.",
        "compute_price_multiplier": 0.70,
        "kwh_multiplier": 1.80,
        "k_factor_multiplier": 1.15,
        "collateral_needed": ["GPU rental receivable", "colo power meter", "PUE or power allocation policy"],
        "best_for": "Power-cost share and regional electricity hedging.",
    },
    {
        "profile_id": "curtailed_power_gpu_batch",
        "label": "Curtailable power GPU batch",
        "cashflow": "Discounted batch compute that can be scheduled around power availability.",
        "compute_price_multiplier": 0.45,
        "kwh_multiplier": 1.55,
        "k_factor_multiplier": 1.00,
        "collateral_needed": ["batch compute sale", "curtailment clause", "node-level meter"],
        "best_for": "Energy-driven compute margin and grid-flexibility exposure.",
    },
    {
        "profile_id": "miner_margin_energy_package",
        "label": "Miner-margin energy package",
        "cashflow": "Hashprice or miner receivable plus power contract; not an AI GPU receivable.",
        "compute_price_multiplier": 0.10,
        "kwh_multiplier": 1.65,
        "k_factor_multiplier": 1.00,
        "collateral_needed": ["hashrate report", "mining power contract", "BTC/ETH quote snapshot"],
        "best_for": "Electricity-expensive miner-margin compression.",
    },
)

SYNDICATED_INSTRUMENT_TYPES = [
    {
        "instrument_type": "compute_receivable_hedge_note",
        "basket_id": "compute_scarcity_ai_infra",
        "signal_direction": DIRECTION_COMPUTE_EXPENSIVE,
        "title": "Compute scarcity receivable hedge note",
        "spread_archetype": "compute_spark_spread",
        "payoff": "Long AI compute-demand and datacenter infrastructure proxies against power-cost proxies.",
        "collateral_needed": ["GPU-hour invoice", "delivery meter", "buyer/seller terms"],
        "direct_leg_target": "long AI compute-demand vs short energy/grid stress",
    },
    {
        "instrument_type": "power_stress_receivable_hedge",
        "basket_id": "power_stress_receivable_hedge",
        "signal_direction": DIRECTION_ELEC_EXPENSIVE,
        "title": "Power-stress compute receivable hedge",
        "spread_archetype": "power_cost_share",
        "payoff": "Long power beneficiaries and short compute/miner-margin beta when electricity is expensive.",
        "collateral_needed": ["compute receivable", "PPA or power hedge", "delivery meter"],
        "direct_leg_target": "long energy/grid stress vs short AI compute-demand",
    },
    {
        "instrument_type": "grid_load_growth_note",
        "basket_id": "grid_equipment_load_growth",
        "signal_direction": "compute_load_growth",
        "title": "Grid load-growth basket note",
        "spread_archetype": "regional_compute_power_basis",
        "payoff": "Long electrical equipment, cooling, and baseload beneficiaries against generic GPU beta.",
        "collateral_needed": ["datacenter load contract", "interconnect milestone evidence", "quote snapshot"],
        "direct_leg_target": "data-center load growth vs generic AI capex beta",
    },
    {
        "instrument_type": "miner_margin_power_pair",
        "basket_id": "miner_margin_power_pair",
        "signal_direction": DIRECTION_ELEC_EXPENSIVE,
        "title": "Miner-margin power pair",
        "spread_archetype": "fuel_stack_compute_spread",
        "payoff": "Short crypto miner-margin beta against power beneficiaries when electricity pressure rises.",
        "collateral_needed": ["mining power contract", "hashrate or energy-use report", "BTC/ETH quote snapshot"],
        "direct_leg_target": "power-cost stress vs crypto-linked miner revenue",
    },
    {
        "instrument_type": "fuel_stack_compute_hedge",
        "basket_id": "fuel_stack_power_input",
        "signal_direction": DIRECTION_ELEC_EXPENSIVE,
        "title": "Fuel-stack compute input hedge",
        "spread_archetype": "fuel_stack_compute_spread",
        "payoff": "Long gas/oil input-cost proxies and power beneficiaries, short generic compute beta.",
        "collateral_needed": ["regional power exposure", "fuel-index reference", "compute sale tenor"],
        "direct_leg_target": "fuel input tightness vs AI compute-demand beta",
    },
    {
        "instrument_type": "compute_calendar_forward_hedge",
        "basket_id": "compute_calendar_ai_capex",
        "signal_direction": DIRECTION_COMPUTE_EXPENSIVE,
        "title": "Compute calendar forward hedge",
        "spread_archetype": "compute_calendar_spread",
        "payoff": "Long prompt compute beneficiaries when spot GPU rental tightens versus its trailing term proxy.",
        "collateral_needed": ["forward GPU-hour sale", "spot/term compute mark policy", "delivery tenor"],
        "direct_leg_target": "front compute scarcity vs term compute availability",
    },
    {
        "instrument_type": "electricity_calendar_power_hedge",
        "basket_id": "electricity_calendar_power_prompt",
        "signal_direction": DIRECTION_ELEC_EXPENSIVE,
        "title": "Electricity calendar power hedge",
        "spread_archetype": "electricity_calendar_spread",
        "payoff": "Long prompt power and fuel beneficiaries when front electricity tightens versus trailing term proxy.",
        "collateral_needed": ["PPA or power hedge", "regional load meter", "front/term power mark policy"],
        "direct_leg_target": "front power tightness vs term power availability",
    },
    {
        "instrument_type": "compute_power_calendar_basis_note",
        "basket_id": "compute_power_calendar_pair",
        "signal_direction": DIRECTION_COMPUTE_EXPENSIVE,
        "title": "Compute-power calendar basis note",
        "spread_archetype": "compute_power_calendar_basis",
        "payoff": "Long prompt compute beneficiaries and short power/fuel proxies when compute tightens faster than power.",
        "collateral_needed": ["compute sale tenor", "regional power tenor", "calendar-basis mark policy"],
        "direct_leg_target": "compute calendar premium vs power calendar premium",
    },
]


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _text(value: Any, default: str = "") -> str:
    out = str(value or "").strip()
    return out or default


def _first_nonempty(*values: Any, default: str = "") -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return default


def _gpu_kwh(spread_latest: dict[str, Any], signal_latest: dict[str, Any]) -> float:
    return _num(
        spread_latest.get("kwh_per_gpu_hr", spread_latest.get("kWh_per_gpu_hr")),
        _num(signal_latest.get("kwh_per_gpu_hr", signal_latest.get("kWh_per_gpu_hr")), DEFAULT_GPU_KWH),
    )


def _k_factor(spread_latest: dict[str, Any], signal_latest: dict[str, Any]) -> float:
    return _num(spread_latest.get("k"), _num(signal_latest.get("k"), 0.5))


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
    if low == "ibkr_quote_unavailable":
        return "IBKR quote unavailable"
    if low == "metadata_watchlist":
        return "Metadata only"
    if low == "priced_watchlist":
        return "Live price available"
    if low == "priced_public_market":
        return "Public price available"
    if low == "priced_close_history":
        return "Close-history replay available"
    if low == "price_unavailable":
        return "Price unavailable"
    if low == "closed_watchlist":
        return "Closed"
    return _text(status, default="Needs review").replace("_", " ")


def _gap_next_step(row: dict[str, Any]) -> str:
    surface = _text(row.get("surface"))
    pricing = _text(row.get("pricing_status")).lower()
    if surface == "ibkr_prediction" and pricing == "ibkr_quote_unavailable":
        return "IBKR returned ForecastTrader metadata but no bid/ask/last. Keep Client Portal authenticated, enable TWS/Gateway API market data, check ForecastTrader entitlement/trading hours, then rerun priced discovery."
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
    if label == "REJECT" or "unpriced" in pricing or pricing in {"metadata_watchlist", "price_unavailable", "ibkr_quote_unavailable"}:
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
            "source_priority": leg.get("source_priority") or "",
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


def _proxy_basket_passes_entry_gate(basket: dict[str, Any], fallback: Any = None) -> bool | None:
    if not basket:
        return bool(fallback) if fallback is not None else None
    if "is_promotable" in basket:
        return bool(basket.get("is_promotable"))
    status = _text(basket.get("status"))
    if status:
        return status == "PROMOTABLE"
    return bool(fallback) if fallback is not None else None


def _proxy_basket_for_direction(
    proxy_basket_validation: dict[str, Any] | None,
    direction: str,
) -> tuple[dict[str, Any], bool | None]:
    """Pick the proxy replay that matches the current spread direction.

    The saved proxy replay has a global `primary_basket`, but the recommendation
    gate must use the basket for the active signal. A compute-expensive signal
    should not borrow an electricity-expensive miner-margin BUY replay.
    """
    validation = proxy_basket_validation if isinstance(proxy_basket_validation, dict) else {}
    primary = validation.get("primary_basket") if isinstance(validation.get("primary_basket"), dict) else {}
    baskets = [basket for basket in validation.get("baskets") or [] if isinstance(basket, dict)]
    if primary and all(basket.get("basket_id") != primary.get("basket_id") for basket in baskets):
        baskets.append(primary)

    clean_direction = _text(direction)
    if clean_direction and clean_direction != "no_signal":
        for basket in baskets:
            if _text(basket.get("direction")) == clean_direction:
                return basket, _proxy_basket_passes_entry_gate(basket)
        # Backwards-compatible fixture path: older tests may pass a primary
        # basket without a direction field.
        if primary and not _text(primary.get("direction")):
            return primary, _proxy_basket_passes_entry_gate(primary, validation.get("entry_gate_pass"))
        if baskets or primary:
            return {
                "basket_id": "no_direction_matched_proxy_basket",
                "direction": clean_direction,
                "status": "DIRECTION_MISMATCH",
                "status_reason": f"No proxy basket replay matched the active {clean_direction} signal.",
                "recommendation": "MONITOR_ONLY",
                "latest_signal": "MONITOR",
                "signal_reason": "Proxy replay is available, but not for the active spread direction.",
                "trailing_returns": {},
                "total_return_pct": 0,
                "win_rate": 0,
                "max_drawdown_pct": 0,
            }, False
    return primary, _proxy_basket_passes_entry_gate(primary, validation.get("entry_gate_pass"))


def _materiality_status(
    *,
    margin: float,
    modeled_power_share: float,
    proxy_signal: str,
    proxy_status: str,
) -> tuple[str, str, str]:
    if margin <= 0:
        return (
            "UNIT_ECONOMICS_FAIL",
            "AVOID",
            "The cashflow is not profitable after gross power cost.",
        )
    if modeled_power_share < MIN_MODELED_POWER_COST_SHARE_FOR_BUY:
        return (
            "WEAK_ENERGY_LINK",
            "MONITOR",
            "Power is too small a share of revenue for a clean energy-compute hedge.",
        )
    if modeled_power_share < MIN_STRUCTURAL_POWER_COST_SHARE:
        return (
            "THIN_ENERGY_LINK",
            "MONITOR",
            "Power is visible but still a thin share of the cashflow; direct legs or stronger proxy confirmation are required.",
        )
    if proxy_signal == "SELL":
        return (
            "MATERIAL_BUT_PROXY_SELL",
            "AVOID_OR_CLOSE",
            "Power is material, but the direction-matched proxy basket is in sell mode.",
        )
    if proxy_signal == "BUY" and proxy_status == "PROMOTABLE":
        return (
            "STRUCTURABLE",
            "PAPER_BUY_CANDIDATE",
            "Power is material and the direction-matched proxy replay supports a paper/testnet structure.",
        )
    return (
        "MATERIAL_WAIT_FOR_CONFIRMATION",
        "MONITOR",
        "Power is material, but proxy replay or direct event legs are not yet confirming a fresh buy.",
    )


def _collateral_profile_candidates(
    *,
    direction: str,
    spread_latest: dict[str, Any],
    signal_latest: dict[str, Any],
    proxy_basket_validation: dict[str, Any] | None,
    spread_family_validation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    compute_per_gpu_hr = _num(spread_latest.get("compute_per_gpu_hr"), _num(signal_latest.get("compute_per_gpu_hr")))
    electricity_per_mwh = _num(spread_latest.get("electricity_per_mwh"), _num(signal_latest.get("electricity_per_mwh")))
    gpu_hours = max(1.0, _num(spread_latest.get("demo_gpu_hours"), DEFAULT_DEMO_GPU_HOURS))
    base_gpu_kwh = max(0.01, _gpu_kwh(spread_latest, signal_latest))
    base_k = max(0.01, _k_factor(spread_latest, signal_latest))
    proxy_basket, _proxy_gate = _proxy_basket_for_direction(proxy_basket_validation, direction)
    proxy_signal = _text(proxy_basket.get("latest_signal"), "MONITOR")
    proxy_status = _text(proxy_basket.get("status"), "NO_REPLAY")
    spread_primary = (spread_family_validation or {}).get("primary_family") or {}
    spread_replay_status = _text(spread_primary.get("status"), "NO_REPLAY")
    rows: list[dict[str, Any]] = []
    for idx, template in enumerate(COLLATERAL_PROFILE_TEMPLATES):
        profile_compute = max(0.0001, compute_per_gpu_hr * _num(template.get("compute_price_multiplier"), 1.0))
        profile_kwh = max(0.01, base_gpu_kwh * _num(template.get("kwh_multiplier"), 1.0))
        profile_k = max(0.01, base_k * _num(template.get("k_factor_multiplier"), 1.0))
        revenue = profile_compute * gpu_hours
        gross_power_cost = electricity_per_mwh / 1000.0 * profile_kwh * gpu_hours
        modeled_power_cost = gross_power_cost * profile_k
        margin = revenue - gross_power_cost
        modeled_power_share = modeled_power_cost / revenue if revenue > 0 else 0.0
        gross_power_share = gross_power_cost / revenue if revenue > 0 else 0.0
        status, action, reason = _materiality_status(
            margin=margin,
            modeled_power_share=modeled_power_share,
            proxy_signal=proxy_signal,
            proxy_status=proxy_status,
        )
        materiality_score = min(40.0, modeled_power_share / MIN_STRUCTURAL_POWER_COST_SHARE * 40.0)
        margin_score = _clamp((margin / revenue) if revenue > 0 else 0.0, -0.25, 0.5) * 40.0
        replay_score = 10.0 if spread_replay_status == "PROMOTABLE" else 0.0
        proxy_score = 10.0 if proxy_signal == "BUY" and proxy_status == "PROMOTABLE" else 0.0
        entry_score = _clamp(materiality_score + margin_score + replay_score + proxy_score, 0.0, 100.0)
        rows.append({
            "profile_id": template["profile_id"],
            "label": template["label"],
            "rank": idx + 1,
            "cashflow": template["cashflow"],
            "best_for": template["best_for"],
            "is_current_profile": template["profile_id"] == "cloud_gpu_receivable",
            "compute_per_gpu_hr": _round_units(profile_compute),
            "electricity_per_mwh": _round_units(electricity_per_mwh),
            "kwh_per_unit_hr": _round_units(profile_kwh),
            "k_factor": _round_units(profile_k),
            "demo_units": _round_units(gpu_hours),
            "receivable_usdc": _round_money(revenue),
            "gross_power_cost_usdc": _round_money(gross_power_cost),
            "modeled_power_cost_usdc": _round_money(modeled_power_cost),
            "gross_power_cost_share_pct": _round_units(gross_power_share * 100.0),
            "modeled_power_cost_share_pct": _round_units(modeled_power_share * 100.0),
            "margin_usdc": _round_money(margin),
            "margin_pct": _round_units((margin / revenue) * 100.0 if revenue > 0 else 0.0),
            "materiality_gate": "PASS" if modeled_power_share >= MIN_STRUCTURAL_POWER_COST_SHARE else "MONITOR",
            "status": status,
            "action": action,
            "status_reason": reason,
            "entry_score": _round_units(entry_score),
            "proxy_signal": proxy_signal,
            "proxy_status": proxy_status,
            "spread_replay_status": spread_replay_status,
            "collateral_needed": template["collateral_needed"],
        })
    action_rank = {"PAPER_BUY_CANDIDATE": 0, "MONITOR": 1, "AVOID_OR_CLOSE": 2, "AVOID": 3}
    rows.sort(key=lambda row: (
        action_rank.get(row["action"], 9),
        0 if row["materiality_gate"] == "PASS" else 1,
        -_num(row["entry_score"]),
        row["rank"],
    ))
    return rows


def _mock_recommendation(
    *,
    direction: str,
    spread_latest: dict[str, Any],
    signal_latest: dict[str, Any],
    direct_legs: list[dict[str, Any]],
    weighted_legs: list[dict[str, Any]],
    spread_family_validation: dict[str, Any] | None,
    proxy_basket_validation: dict[str, Any] | None,
    receivable: float,
    power_cost: float,
    modeled_power_cost: float,
    margin: float,
    hedge_notional: float,
    circle_ask: float,
) -> dict[str, Any]:
    z_score = _num(signal_latest.get("z"))
    abs_z = abs(z_score)
    margin_ratio = margin / receivable if receivable > 0 else 0.0
    gross_power_share = power_cost / receivable if receivable > 0 else 0.0
    modeled_power_share = modeled_power_cost / receivable if receivable > 0 else 0.0
    live_prices = [row for row in weighted_legs if _num(row.get("last_price")) > 0]
    primary_family = (spread_family_validation or {}).get("primary_family") or {}
    entry_gate_pass = (spread_family_validation or {}).get("entry_gate_pass")
    primary_proxy_basket, proxy_entry_gate_pass = _proxy_basket_for_direction(proxy_basket_validation, direction)
    z_component = min(abs_z, 4.0) / 4.0 * 60.0
    margin_component = _clamp(margin_ratio, -0.25, 0.50) * 50.0
    quote_component = 15.0 if live_prices else 0.0
    direct_component = 5.0 if direct_legs else 0.0
    edge_score = _clamp(z_component + margin_component + quote_component + direct_component, 0.0, 100.0)
    basis = {
        "direction": direction,
        "spread": {
            "region": spread_latest.get("region") or signal_latest.get("region") or "",
            "electricity_per_mwh": _round_units(spread_latest.get("electricity_per_mwh")),
            "compute_per_gpu_hr": _round_units(spread_latest.get("compute_per_gpu_hr")),
            "S_t": _round_units(spread_latest.get("S_t")),
            "kWh_per_gpu_hr": _round_units(_gpu_kwh(spread_latest, signal_latest)),
        },
        "signal": {
            "z": _round_units(z_score),
            "direction": signal_latest.get("direction") or direction,
        },
        "economics": {
            "receivable_usdc": _round_money(receivable),
            "power_cost_usdc": _round_money(power_cost),
            "power_cost_share_pct": _round_units(gross_power_share * 100.0),
            "modeled_power_cost_usdc": _round_money(modeled_power_cost),
            "modeled_power_cost_share_pct": _round_units(modeled_power_share * 100.0),
            "margin_usdc": _round_money(margin),
            "hedge_notional_usdc": _round_money(hedge_notional),
            "circle_ask_usdc": _round_money(circle_ask),
        },
        "legs": [
            {
                "slug": row.get("slug"),
                "side": row.get("side"),
                "price": row.get("last_price"),
                "source": row.get("source"),
            }
            for row in weighted_legs
        ],
        "direct_leg_slugs": [leg.get("slug") for leg in direct_legs],
        "spread_family_validation": {
            "entry_gate_pass": entry_gate_pass,
            "primary_family": primary_family.get("family_id", ""),
            "primary_status": primary_family.get("status", ""),
            "primary_status_reason": primary_family.get("status_reason", ""),
            "primary_tested_trades": primary_family.get("tested_trades", 0),
            "primary_win_rate": primary_family.get("win_rate", 0),
            "primary_total_pnl_per_unit": primary_family.get("total_pnl_per_unit", 0),
        } if spread_family_validation else {},
        "proxy_basket_validation": {
            "entry_gate_pass": proxy_entry_gate_pass,
            "primary_basket": primary_proxy_basket.get("basket_id", ""),
            "primary_status": primary_proxy_basket.get("status", ""),
            "primary_status_reason": primary_proxy_basket.get("status_reason", ""),
            "primary_recommendation": primary_proxy_basket.get("recommendation", ""),
            "primary_latest_signal": primary_proxy_basket.get("latest_signal", ""),
            "primary_signal_reason": primary_proxy_basket.get("signal_reason", ""),
            "primary_trailing_returns": primary_proxy_basket.get("trailing_returns", {}),
            "primary_total_return_pct": primary_proxy_basket.get("total_return_pct", 0),
            "primary_win_rate": primary_proxy_basket.get("win_rate", 0),
            "primary_max_drawdown_pct": primary_proxy_basket.get("max_drawdown_pct", 0),
        } if proxy_basket_validation else {},
    }
    basis_hash = _hash_payload(basis)[:16]
    state = judge.default_state()
    state["surface_resolutions_30d"] = {
        **(state.get("surface_resolutions_30d") or {}),
        "mock_contract": 1,
    }
    candidate = {
        "arb_signal_id": _text(signal_latest.get("signal_id"), basis_hash),
        "surface": "mock_contract",
        "instrument": "compute_energy_spread_mock_contract",
        "direction": direction,
        "sizing_usdc": min(5.0, max(1.0, _round_money(hedge_notional))),
        "est_pnl_per_dollar": _round_units(edge_score / 10000.0),
        "action_kind": "mock_contract_recommendation",
        "data_age_seconds": _num(signal_latest.get("data_age_seconds"), _num(spread_latest.get("data_age_seconds"))),
        "metadata": {
            "decision_basis_hash": basis_hash,
            "scope": "local_mock_contract_recommendation",
            "circle_request_usdc": _round_money(circle_ask),
            "full_mock_notional_usdc": _round_money(hedge_notional),
        },
    }
    verdict = judge.classify(candidate, state)
    judge_verdict = {
        "label": verdict.label,
        "reason_code": verdict.reason_code,
        "confidence": _round_units(verdict.confidence),
    }
    judge_candidate_hash = _hash_payload(candidate)[:16]
    judge_scope = (
        "Non-logging spread-decision judge pass for the local mock recommendation. "
        "Runtime venue candidates are still re-judged before any Circle or Arc action."
    )

    def with_judge(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            **payload,
            "entry_threshold_score": ENTRY_SIGNAL_BUY_THRESHOLD,
            "judge_verdict": judge_verdict,
            "judge_candidate_hash": judge_candidate_hash,
            "judge_scope": judge_scope,
        }

    if not live_prices:
        return with_judge({
            "recommended_action": "MONITOR_ONLY",
            "recommendation_label": "Wait for prices",
            "recommendation_reason": "No live-priced hedge legs are available, so a buy would not give the user a defensible entry mark.",
            "recommendation_summary": "Monitor only until the basket has fresh prices.",
            "entry_signal_score": 0.0,
            "score_scale": "0-100 entry score; buy threshold is 70 and raw z-score is not shown to users",
            "decision_basis_hash": basis_hash,
            "decision_basis": basis,
        })

    if margin <= 0:
        return with_judge({
            "recommended_action": "MONITOR_ONLY",
            "recommendation_label": "Avoid new exposure",
            "recommendation_reason": "The underlying compute sale is not profitable at current compute and power marks; buying a new mock ticket would hide bad unit economics.",
            "recommendation_summary": "Avoid a new ticket until compute margin turns positive.",
            "entry_signal_score": _round_units(edge_score),
            "score_scale": "0-100 entry score; buy threshold is 70 and raw z-score is not shown to users",
            "decision_basis_hash": basis_hash,
            "decision_basis": basis,
        })

    if verdict.label != judge.LABEL_EXECUTE:
        return with_judge({
            "recommended_action": "MONITOR_ONLY",
            "recommendation_label": f"Monitor: judge {verdict.label.lower()}",
            "recommendation_reason": (
                f"The spread-decision judge refreshed on the latest inputs and returned "
                f"{verdict.label}/{verdict.reason_code}; the user should not open a new mock ticket yet."
            ),
            "recommendation_summary": "Monitor only; the judge gate did not clear on the latest spread state.",
            "entry_signal_score": _round_units(edge_score),
            "score_scale": "0-100 entry score; buy threshold is 70 and raw z-score is not shown to users",
            "decision_basis_hash": basis_hash,
            "decision_basis": basis,
        })

    if entry_gate_pass is False:
        status = primary_family.get("status") or "not_promotable"
        status_reason = primary_family.get("status_reason") or "Spread-family replay has not cleared the promotion gate."
        return with_judge({
            "recommended_action": "MONITOR_ONLY",
            "recommendation_label": "Monitor: replay gate",
            "recommendation_reason": (
                f"The latest judge pass is EXECUTE, but the spread-family replay is {status}. "
                f"{status_reason}"
            ),
            "recommendation_summary": "Monitor only; replay must show enough history, variation, and positive PnL before a user-facing buy.",
            "entry_signal_score": _round_units(edge_score),
            "score_scale": "0-100 entry score; buy threshold is 70 and raw z-score is not shown to users",
            "decision_basis_hash": basis_hash,
            "decision_basis": basis,
        })

    if proxy_entry_gate_pass is False and primary_proxy_basket:
        status = primary_proxy_basket.get("status") or "not_promotable"
        status_reason = primary_proxy_basket.get("status_reason") or "Proxy basket replay has not cleared the promotion gate."
        recommendation = primary_proxy_basket.get("recommendation") or "MONITOR_ONLY"
        label = "Avoid: proxy replay" if recommendation == "SELL_OR_AVOID" else "Monitor: proxy replay"
        return with_judge({
            "recommended_action": "MONITOR_ONLY",
            "recommendation_label": label,
            "recommendation_reason": (
                f"The spread judge passed, but the liquid proxy basket replay is {status}. "
                f"{status_reason}"
            ),
            "recommendation_summary": "Monitor only; the public proxy expression must show positive replay before a user-facing buy.",
            "entry_signal_score": _round_units(edge_score),
            "score_scale": "0-100 entry score; buy threshold is 70 and raw z-score is not shown to users",
            "decision_basis_hash": basis_hash,
            "decision_basis": basis,
        })

    if primary_proxy_basket:
        proxy_signal = primary_proxy_basket.get("latest_signal") or ""
        if proxy_signal in {"SELL", "HOLD"}:
            status_reason = (
                primary_proxy_basket.get("signal_reason")
                or primary_proxy_basket.get("status_reason")
                or "Proxy basket profitability is not confirming a fresh buy."
            )
            label = "Sell/avoid: proxy PnL" if proxy_signal == "SELL" else "Hold: proxy PnL"
            summary = (
                "Avoid a fresh buy; the liquid proxy expression is in sell mode."
                if proxy_signal == "SELL"
                else "Hold/monitor; the liquid proxy expression is promotable but not a fresh buy."
            )
            return with_judge({
                "recommended_action": "MONITOR_ONLY",
                "recommendation_label": label,
                "recommendation_reason": status_reason,
                "recommendation_summary": summary,
                "entry_signal_score": _round_units(edge_score),
                "score_scale": "0-100 entry score; buy threshold is 70 and raw z-score is not shown to users",
                "decision_basis_hash": basis_hash,
                "decision_basis": basis,
            })

    if modeled_power_share < MIN_MODELED_POWER_COST_SHARE_FOR_BUY:
        return with_judge({
            "recommended_action": "MONITOR_ONLY",
            "recommendation_label": "Monitor: weak energy link",
            "recommendation_reason": (
                f"The modeled electricity component is only {modeled_power_share * 100.0:.2f}% of GPU-hour revenue. "
                "That makes the current cloud-compute mark mostly a compute-price signal, so a fresh hedge ticket "
                "needs stronger proxy-basket confirmation or a more power-intensive collateral profile."
            ),
            "recommendation_summary": "Monitor only; the live compute sale is profitable, but energy materiality is too weak for a fresh buy.",
            "entry_signal_score": _round_units(edge_score),
            "score_scale": "0-100 entry score; buy threshold is 70 and raw z-score is not shown to users",
            "decision_basis_hash": basis_hash,
            "decision_basis": basis,
        })

    if edge_score >= ENTRY_SIGNAL_BUY_THRESHOLD:
        return with_judge({
            "recommended_action": "BUY_CONTRACT",
            "recommendation_label": "Open paper hedge",
            "recommendation_reason": "The entry score clears the buy threshold, the compute sale has positive margin, live hedge marks are present, and the judge returned EXECUTE. This opens only a local paper/testnet ticket; it is not guaranteed profit.",
            "recommendation_summary": "Open a paper/testnet hedge ticket; expected value comes from spread edge versus live hedge marks, then leg PnL must be monitored.",
            "entry_signal_score": _round_units(edge_score),
            "score_scale": "0-100 entry score; buy threshold is 70 and raw z-score is not shown to users",
            "decision_basis_hash": basis_hash,
            "decision_basis": basis,
        })

    if edge_score >= 45.0:
        reason = "The spread is present, but the entry score is still below the buy threshold after quote and funding checks."
    else:
        reason = "The spread is too weak for a user-facing buy recommendation."
    return with_judge({
        "recommended_action": "MONITOR_ONLY",
        "recommendation_label": "Monitor",
        "recommendation_reason": f"{reason} Score must clear {ENTRY_SIGNAL_BUY_THRESHOLD:.0f}/100 before a user-facing paper ticket is recommended.",
        "recommendation_summary": "Monitor only; wait for a stronger spread move or better-priced hedge basket.",
        "entry_signal_score": _round_units(edge_score),
        "score_scale": "0-100 entry score; buy threshold is 70 and raw z-score is not shown to users",
        "decision_basis_hash": basis_hash,
        "decision_basis": basis,
    })


def _mock_hedge_construction(
    *,
    direction: str,
    spread_latest: dict[str, Any],
    signal_latest: dict[str, Any],
    hedge_basket: list[dict[str, Any]],
    direct_legs: list[dict[str, Any]],
    spread_family_validation: dict[str, Any] | None = None,
    proxy_basket_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    compute_per_gpu_hr = _num(spread_latest.get("compute_per_gpu_hr"), _num(signal_latest.get("compute_per_gpu_hr")))
    electricity_per_mwh = _num(spread_latest.get("electricity_per_mwh"), _num(signal_latest.get("electricity_per_mwh")))
    gpu_hours = max(1.0, _num(spread_latest.get("demo_gpu_hours"), DEFAULT_DEMO_GPU_HOURS))
    gpu_kwh = max(0.01, _gpu_kwh(spread_latest, signal_latest))
    k_factor = max(0.01, _k_factor(spread_latest, signal_latest))
    receivable = compute_per_gpu_hr * gpu_hours
    power_cost = electricity_per_mwh / 1000.0 * gpu_kwh * gpu_hours
    modeled_power_cost = electricity_per_mwh / 1000.0 * gpu_kwh * k_factor * gpu_hours
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
    recommendation = _mock_recommendation(
        direction=direction,
        spread_latest=spread_latest,
        signal_latest=signal_latest,
        direct_legs=direct_legs,
        weighted_legs=weighted_legs,
        spread_family_validation=spread_family_validation,
        proxy_basket_validation=proxy_basket_validation,
        receivable=receivable,
        power_cost=power_cost,
        modeled_power_cost=modeled_power_cost,
        margin=margin,
        hedge_notional=hedge_notional,
        circle_ask=circle_ask,
    )
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
        "recommended_action": recommendation["recommended_action"],
        "recommendation_label": recommendation["recommendation_label"],
        "recommendation_reason": recommendation["recommendation_reason"],
        "recommendation_summary": recommendation["recommendation_summary"],
        "entry_signal_score": recommendation["entry_signal_score"],
        "entry_threshold_score": recommendation["entry_threshold_score"],
        "profitability_score": recommendation["entry_signal_score"],
        "score_scale": recommendation["score_scale"],
        "decision_basis_hash": recommendation["decision_basis_hash"],
        "decision_basis": recommendation["decision_basis"],
        "spread_family_validation": (recommendation["decision_basis"] or {}).get("spread_family_validation", {}),
        "proxy_basket_validation": (recommendation["decision_basis"] or {}).get("proxy_basket_validation", {}),
        "judge_verdict": recommendation["judge_verdict"],
        "judge_candidate_hash": recommendation["judge_candidate_hash"],
        "judge_scope": recommendation["judge_scope"],
        "profitability_note": recommendation["recommendation_summary"],
        "demo_gpu_hours": _round_units(gpu_hours),
        "gpu_kwh_per_hr": _round_units(gpu_kwh),
        "k_factor": _round_units(k_factor),
        "receivable_usdc": _round_money(receivable),
        "estimated_power_cost_usdc": _round_money(power_cost),
        "modeled_power_cost_usdc": _round_money(modeled_power_cost),
        "power_cost_share_pct": _round_units((power_cost / receivable) * 100.0 if receivable > 0 else 0.0),
        "modeled_power_cost_share_pct": _round_units((modeled_power_cost / receivable) * 100.0 if receivable > 0 else 0.0),
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
                "name": "Venue inviter",
                "uses": "IBKR ForecastTrader, Polymarket, and future event venues",
                "job": "Find or request new venue contracts, but keep them in research until they are priced and thesis-matched.",
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


def _basket_by_id(proxy_basket_validation: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for basket in (proxy_basket_validation or {}).get("baskets") or []:
        if isinstance(basket, dict) and basket.get("basket_id"):
            out[str(basket["basket_id"])] = basket
    primary = (proxy_basket_validation or {}).get("primary_basket")
    if isinstance(primary, dict) and primary.get("basket_id"):
        out.setdefault(str(primary["basket_id"]), primary)
    return out


def _instrument_signal_status(
    *,
    basket: dict[str, Any],
    collateral_status: str,
    has_direct_legs: bool,
) -> tuple[str, str]:
    latest_signal = _text(basket.get("latest_signal"), "MONITOR")
    if collateral_status != "asset_backed":
        if latest_signal == "BUY":
            return "PAPER_BUY_ONLY", "Proxy replay says BUY, but the structure is not asset-backed until collateral is attached."
        if latest_signal == "SELL":
            return "AVOID_OR_SELL", "Current proxy signal says SELL; avoid new exposure and close local mock tickets if already open."
        return "MONITOR_ONLY", "Collateral is missing, so this remains a monitored synthetic package."
    if not has_direct_legs:
        return "NEEDS_DIRECT_LEGS", "Collateral exists, but direct event legs still need priced venue references."
    if latest_signal == "BUY":
        return "READY_FOR_JUDGE", "Collateral and direct legs exist; run scorer and judge before Arc wrap."
    if latest_signal == "SELL":
        return "AVOID_OR_SELL", "Do not wrap; current proxy signal says sell/avoid."
    return "MONITOR_ONLY", "Hold in research until replay and judge both confirm."


def _oracle_judge_evidence(oracle_evidence: dict[str, Any] | None) -> dict[str, Any]:
    """Compact Opoint/Nebius receipt state for the term sheet.

    The oracle is evidence only. The returned blob is safe to hash/reference in
    the synthetic proposal, but it never changes the Arc gate by itself.
    """
    if not isinstance(oracle_evidence, dict) or not oracle_evidence:
        payload = {
            "status": "NO_RECEIPTS",
            "role": "LLM/news evidence only; not an execution gate.",
            "row_count": 0,
            "latest_verdict": "",
            "latest_reason_code": "",
            "verdict_counts": {},
            "reason_counts": {},
            "raw_articles": 0,
            "filtered_articles": 0,
            "can_drive_arc": False,
            "judge_required": True,
            "gate_note": "No Opoint/Nebius receipt is attached; scorer and judge gates are unchanged.",
        }
    else:
        verdict_counts = oracle_evidence.get("verdict_counts") if isinstance(oracle_evidence.get("verdict_counts"), dict) else {}
        reason_counts = oracle_evidence.get("reason_counts") if isinstance(oracle_evidence.get("reason_counts"), dict) else {}
        payload = {
            "status": _text(oracle_evidence.get("status"), "NO_RECEIPTS"),
            "role": _text(oracle_evidence.get("role"), "news-grounded evidence only"),
            "row_count": int(_num(oracle_evidence.get("row_count"))),
            "latest_title": _text(oracle_evidence.get("latest_title")),
            "latest_slug": _text(oracle_evidence.get("latest_slug")),
            "latest_verdict": _text(oracle_evidence.get("latest_pricing_status")),
            "latest_model": _text(oracle_evidence.get("latest_model")),
            "latest_reason_code": _text(oracle_evidence.get("latest_reason_code")),
            "verdict_counts": verdict_counts,
            "reason_counts": reason_counts,
            "raw_articles": int(_num(oracle_evidence.get("raw_articles"))),
            "filtered_articles": int(_num(oracle_evidence.get("filtered_articles"))),
            "can_drive_arc": False,
            "judge_required": True,
            "gate_note": "LLM/news evidence can support or criticize a leg, but cannot replace premium scoring or judge.classify().",
        }
    payload["oracle_evidence_hash"] = _hash_payload(payload)[:16]
    return payload


def _syndicated_instrument_menu(
    *,
    region_profile: dict[str, Any],
    signal_direction: str,
    collateral_status: str,
    direct_legs: list[dict[str, Any]],
    hedge_basket: list[dict[str, Any]],
    mock_construction: dict[str, Any],
    proxy_basket_validation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    by_id = _basket_by_id(proxy_basket_validation)
    priced_symbols = {str(leg.get("slug") or "").upper() for leg in hedge_basket}
    base_ask = _num(mock_construction.get("circle_testnet_usdc_request"))
    rows: list[dict[str, Any]] = []
    clean_signal_direction = _text(signal_direction)
    for template in SYNDICATED_INSTRUMENT_TYPES:
        basket = by_id.get(template["basket_id"], {})
        basket_direction = _first_nonempty(basket.get("direction"), template.get("signal_direction"))
        direction_aligned = bool(clean_signal_direction and clean_signal_direction != "no_signal" and basket_direction == clean_signal_direction)
        weights = basket.get("weights") if isinstance(basket.get("weights"), dict) else {}
        required_symbols = list(weights) or list(basket.get("symbols_required") or [])
        priced = [symbol for symbol in required_symbols if str(symbol).upper() in priced_symbols]
        direct_ready = bool(direct_legs)
        status, status_reason = _instrument_signal_status(
            basket=basket,
            collateral_status=collateral_status,
            has_direct_legs=direct_ready,
        )
        trailing = basket.get("trailing_returns") if isinstance(basket.get("trailing_returns"), dict) else {}
        paper_trade_replay = basket.get("paper_trade_replay") if isinstance(basket.get("paper_trade_replay"), dict) else {}
        out_of_sample_replay = basket.get("out_of_sample_replay") if isinstance(basket.get("out_of_sample_replay"), dict) else {}
        rows.append({
            **template,
            "region": region_profile.get("region"),
            "active_signal_direction": clean_signal_direction,
            "basket_direction": basket_direction,
            "direction_aligned": direction_aligned,
            "has_basket_replay": bool(basket),
            "asset_backed": collateral_status == "asset_backed",
            "collateral_status": collateral_status,
            "status": status,
            "status_reason": status_reason,
            "latest_signal": _text(basket.get("latest_signal"), "MONITOR"),
            "signal_reason": _text(basket.get("signal_reason"), _text(basket.get("status_reason"), "Backtest not available.")),
            "replay_status": _text(basket.get("status"), "NO_REPLAY"),
            "recommendation": _text(basket.get("recommendation"), "MONITOR_ONLY"),
            "total_return_pct": _round_units(basket.get("total_return_pct")),
            "win_rate": _round_units(basket.get("win_rate")),
            "max_drawdown_pct": _round_units(basket.get("max_drawdown_pct")),
            "trailing_returns": trailing,
            "paper_trade_replay": paper_trade_replay,
            "out_of_sample_replay": out_of_sample_replay,
            "required_symbols": required_symbols,
            "priced_symbols": priced,
            "missing_symbols": [symbol for symbol in required_symbols if symbol not in priced],
            "direct_leg_count": len(direct_legs),
            "direct_leg_target_ready": direct_ready,
            "circle_testnet_ask_usdc": _round_money(base_ask if base_ask else 0),
            "copying_spread": (
                f"Copies the {template['spread_archetype']} through a priced public basket and "
                f"direct-event target: {template['direct_leg_target']}."
            ),
            "arc_gate": "LOCKED_UNTIL_JUDGE_EXECUTE",
        })
    signal_rank = {"BUY": 0, "HOLD": 1, "MONITOR": 2, "SELL": 3}
    status_rank = {"READY_FOR_JUDGE": 0, "PAPER_BUY_ONLY": 1, "MONITOR_ONLY": 2, "NEEDS_DIRECT_LEGS": 3, "AVOID_OR_SELL": 4}
    rows.sort(key=lambda row: (
        0 if row.get("direction_aligned") or clean_signal_direction in {"", "no_signal"} else 1,
        0 if row.get("has_basket_replay") else 1,
        signal_rank.get(row["latest_signal"], 9),
        status_rank.get(row["status"], 9),
        -_num(row.get("total_return_pct")),
        row["instrument_type"],
    ))
    return rows


def _operator_signal_sheet(
    *,
    direction: str,
    mock_construction: dict[str, Any],
    collateral_profiles: list[dict[str, Any]],
    proxy_basket_validation: dict[str, Any] | None,
    spread_family_validation: dict[str, Any] | None,
    syndicated_menu: list[dict[str, Any]],
) -> dict[str, Any]:
    proxy_basket, _proxy_gate = _proxy_basket_for_direction(proxy_basket_validation, direction)
    proxy_signal = _text(proxy_basket.get("latest_signal"), "MONITOR")
    proxy_status = _text(proxy_basket.get("status"), "NO_REPLAY")
    trailing = proxy_basket.get("trailing_returns") if isinstance(proxy_basket.get("trailing_returns"), dict) else {}
    spread_primary = (spread_family_validation or {}).get("primary_family") or {}
    archetypes = (spread_family_validation or {}).get("archetype_scoreboard") or []
    promotable_archetypes = [row for row in archetypes if isinstance(row, dict) and row.get("is_promotable")]
    top_profile = collateral_profiles[0] if collateral_profiles else {}
    current_profile = next((row for row in collateral_profiles if row.get("is_current_profile")), top_profile)
    active_structure = next((row for row in syndicated_menu if row.get("direction_aligned")), syndicated_menu[0] if syndicated_menu else {})

    if proxy_signal == "SELL":
        overall_action = "AVOID_OR_CLOSE"
        headline = "Avoid fresh buys; close local mock exposure if already open."
        reason = _text(proxy_basket.get("signal_reason"), "The direction-matched proxy basket is in sell mode.")
    elif mock_construction.get("recommended_action") == "BUY_CONTRACT":
        overall_action = "PAPER_BUY_CANDIDATE"
        headline = "Paper/testnet buy candidate."
        reason = _text(mock_construction.get("recommendation_reason"), "Entry score and judge gate cleared.")
    elif top_profile.get("action") == "PAPER_BUY_CANDIDATE":
        overall_action = "STRUCTURE_THEN_JUDGE"
        headline = "Structurable profile found; attach collateral before Arc."
        reason = _text(top_profile.get("status_reason"), "Power materiality and replay support a candidate profile.")
    else:
        overall_action = "MONITOR"
        headline = "Monitor; do not open a fresh ticket yet."
        reason = _text(mock_construction.get("recommendation_reason"), "Entry gates have not all cleared.")

    rows = [
        {
            "key": "current_mock_contract",
            "label": "Current mock contract",
            "action": _text(mock_construction.get("recommended_action"), "MONITOR_ONLY"),
            "signal": _text(mock_construction.get("recommendation_label"), "Monitor"),
            "score": _round_units(mock_construction.get("entry_signal_score")),
            "reason": _text(mock_construction.get("recommendation_summary"), _text(mock_construction.get("recommendation_reason"))),
        },
        {
            "key": "active_proxy_basket",
            "label": _text(proxy_basket.get("label"), "Active proxy basket"),
            "action": "AVOID_OR_CLOSE" if proxy_signal == "SELL" else ("BUY_OR_HOLD" if proxy_signal == "BUY" else "MONITOR"),
            "signal": proxy_signal,
            "status": proxy_status,
            "score": _round_units(proxy_basket.get("total_return_pct")),
            "return_5d_pct": ((trailing.get("5d") or {}).get("return_pct") if isinstance(trailing.get("5d"), dict) else ""),
            "return_1m_pct": ((trailing.get("1m") or {}).get("return_pct") if isinstance(trailing.get("1m"), dict) else ""),
            "reason": _text(proxy_basket.get("signal_reason"), _text(proxy_basket.get("status_reason"))),
        },
        {
            "key": "current_collateral_profile",
            "label": _text(current_profile.get("label"), "Current collateral profile"),
            "action": _text(current_profile.get("action"), "MONITOR"),
            "signal": _text(current_profile.get("materiality_gate"), "MONITOR"),
            "score": _round_units(current_profile.get("entry_score")),
            "power_share_pct": current_profile.get("modeled_power_cost_share_pct", ""),
            "reason": _text(current_profile.get("status_reason"), "No collateral profile data."),
        },
        {
            "key": "best_collateral_profile",
            "label": _text(top_profile.get("label"), "Best collateral profile"),
            "action": _text(top_profile.get("action"), "MONITOR"),
            "signal": _text(top_profile.get("materiality_gate"), "MONITOR"),
            "score": _round_units(top_profile.get("entry_score")),
            "power_share_pct": top_profile.get("modeled_power_cost_share_pct", ""),
            "reason": _text(top_profile.get("status_reason"), "No collateral profile passed yet."),
        },
        {
            "key": "spread_replay",
            "label": _text(spread_primary.get("label"), "Spread replay"),
            "action": "PROMOTABLE" if spread_primary.get("is_promotable") else "MONITOR",
            "signal": _text(spread_primary.get("status"), "NO_REPLAY"),
            "score": _round_units(spread_primary.get("total_pnl_per_unit")),
            "win_rate": spread_primary.get("win_rate", ""),
            "reason": _text(spread_primary.get("status_reason"), "No replay status."),
        },
        {
            "key": "active_syndicated_structure",
            "label": _text(active_structure.get("title"), "Active syndicated structure"),
            "action": _text(active_structure.get("status"), "MONITOR_ONLY"),
            "signal": _text(active_structure.get("latest_signal"), "MONITOR"),
            "score": _round_units(active_structure.get("total_return_pct")),
            "reason": _text(active_structure.get("status_reason"), "No structure selected."),
        },
    ]
    return {
        "version": "operator_signal_sheet_v1",
        "direction": direction,
        "overall_action": overall_action,
        "headline": headline,
        "reason": reason,
        "active_proxy_basket_id": _text(proxy_basket.get("basket_id")),
        "promotable_spread_archetypes": [
            {
                "archetype_id": row.get("archetype_id"),
                "label": row.get("label"),
                "total_pnl_per_unit": row.get("total_pnl_per_unit"),
                "win_rate": row.get("win_rate"),
            }
            for row in promotable_archetypes[:3]
        ],
        "rows": rows,
        "guardrail": "Operator signals are advisory. Circle/Arc remains locked unless judge.classify() returns EXECUTE.",
    }


def _spread_archetype_trade_map(
    *,
    signal_direction: str,
    spread_family_validation: dict[str, Any] | None,
    proxy_basket_validation: dict[str, Any] | None,
    syndicated_menu: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Tie each oil-style spread archetype to its tradable expression.

    Spread-family replay answers "does this index expression mean-revert or
    trend profitably?" Proxy-basket replay answers "can the desk express that
    thesis through currently priced public legs?" This table joins those two
    answers so the frontend/bot can avoid showing disconnected lists.
    """
    scoreboard = (spread_family_validation or {}).get("archetype_scoreboard") or []
    replay_by_archetype = {
        str(row.get("archetype_id")): row
        for row in scoreboard
        if isinstance(row, dict) and row.get("archetype_id")
    }
    baskets_by_id = _basket_by_id(proxy_basket_validation)
    menu_by_archetype: dict[str, list[dict[str, Any]]] = {}
    for item in syndicated_menu:
        if not isinstance(item, dict):
            continue
        archetype_id = _text(item.get("spread_archetype"))
        if not archetype_id:
            continue
        menu_by_archetype.setdefault(archetype_id, []).append(item)

    rows: list[dict[str, Any]] = []
    for archetype in SPREAD_ARCHETYPE_CATALOG:
        archetype_id = str(archetype["id"])
        replay = replay_by_archetype.get(archetype_id, {})
        structures = menu_by_archetype.get(archetype_id, [])
        expression_rows: list[dict[str, Any]] = []
        for structure in structures:
            basket_id = _text(structure.get("basket_id"))
            basket = baskets_by_id.get(basket_id, {})
            trailing = basket.get("trailing_returns") if isinstance(basket.get("trailing_returns"), dict) else structure.get("trailing_returns", {})
            recent_marks = basket.get("recent_index_marks") if isinstance(basket.get("recent_index_marks"), list) else structure.get("recent_index_marks", [])
            paper_trade_replay = basket.get("paper_trade_replay") if isinstance(basket.get("paper_trade_replay"), dict) else structure.get("paper_trade_replay", {})
            out_of_sample_replay = basket.get("out_of_sample_replay") if isinstance(basket.get("out_of_sample_replay"), dict) else structure.get("out_of_sample_replay", {})
            expression_rows.append({
                "instrument_type": structure.get("instrument_type"),
                "title": structure.get("title"),
                "basket_id": basket_id,
                "basket_label": _text(basket.get("label"), _text(structure.get("title"))),
                "basket_direction": _first_nonempty(basket.get("direction"), structure.get("basket_direction"), structure.get("signal_direction")),
                "direction_aligned": bool(structure.get("direction_aligned")),
                "latest_signal": _first_nonempty(basket.get("latest_signal"), structure.get("latest_signal"), default="MONITOR"),
                "signal_reason": _first_nonempty(basket.get("signal_reason"), structure.get("signal_reason")),
                "current_action": _first_nonempty(basket.get("current_action"), structure.get("current_action")),
                "current_action_reason": _first_nonempty(basket.get("current_action_reason"), structure.get("current_action_reason")),
                "replay_status": _first_nonempty(basket.get("status"), structure.get("replay_status"), default="NO_REPLAY"),
                "recommendation": _first_nonempty(basket.get("recommendation"), structure.get("recommendation"), default="MONITOR_ONLY"),
                "status": _text(structure.get("status"), "MONITOR_ONLY"),
                "status_reason": _text(structure.get("status_reason")),
                "return_5d_pct": ((trailing.get("5d") or {}).get("return_pct") if isinstance(trailing.get("5d"), dict) else ""),
                "return_1m_pct": ((trailing.get("1m") or {}).get("return_pct") if isinstance(trailing.get("1m"), dict) else ""),
                "total_return_pct": _round_units(_first_nonempty(basket.get("total_return_pct"), structure.get("total_return_pct"), default=0)),
                "win_rate": _round_units(_first_nonempty(basket.get("win_rate"), structure.get("win_rate"), default=0)),
                "recent_index_marks": recent_marks,
                "paper_trade_replay": paper_trade_replay,
                "out_of_sample_replay": out_of_sample_replay,
                "priced_symbols": structure.get("priced_symbols") or [],
                "missing_symbols": structure.get("missing_symbols") or [],
                "direct_leg_target": structure.get("direct_leg_target"),
                "direct_leg_target_ready": bool(structure.get("direct_leg_target_ready")),
                "copying_spread": structure.get("copying_spread"),
            })

        selected = next((row for row in expression_rows if row["direction_aligned"]), expression_rows[0] if expression_rows else {})
        replay_status = _first_nonempty(replay.get("replay_status"), replay.get("status"), default="NO_REPLAY")
        replay_promotable = bool(replay.get("is_promotable"))
        selected_signal = _text(selected.get("latest_signal"), "MONITOR") if selected else "MONITOR"
        selected_status = _text(selected.get("status"), "NO_EXPRESSION") if selected else "NO_EXPRESSION"
        if not expression_rows:
            action = "NEEDS_EXPRESSION"
            reason = "No syndicated expression has been mapped to this spread archetype yet."
        elif selected_signal == "SELL" or "AVOID" in selected_status:
            action = "AVOID_OR_SELL"
            reason = _text(selected.get("status_reason"), "Mapped proxy basket says sell/avoid.")
        elif replay_status == "NEEDS_INDEX_HISTORY":
            action = "NEEDS_INDEX_HISTORY"
            reason = "Required index history is not available yet, so proxy PnL alone cannot promote a fresh buy."
        elif not replay_promotable:
            action = "WAIT_FOR_SPREAD_REPLAY"
            reason = _text(replay.get("status_reason"), "Mapped proxy expression is constructive, but spread replay has not cleared the promotion gate.")
        elif selected_signal == "BUY" and selected_status in {"PAPER_BUY_ONLY", "READY_FOR_JUDGE"}:
            action = selected_status
            reason = _text(selected.get("status_reason"), "Mapped proxy basket says buy, but Arc still needs the judge gate.")
        elif replay_promotable and selected_signal in {"BUY", "HOLD"}:
            action = "PAPER_BUY_CANDIDATE"
            reason = "Spread replay and mapped proxy expression are both constructive."
        else:
            action = "MONITOR"
            reason = _text(replay.get("status_reason"), _text(selected.get("status_reason"), "Keep monitoring replay and venue evidence."))

        rows.append({
            "archetype_id": archetype_id,
            "label": archetype.get("label"),
            "formula": archetype.get("formula"),
            "oil_analogy": archetype.get("oil_analogy"),
            "catalog_status": archetype.get("status"),
            "required_indexes": archetype.get("required_indexes", []),
            "signal_direction": signal_direction,
            "replay_status": replay_status,
            "replay_promotable": replay_promotable,
            "evidence_level": _text(replay.get("evidence_level"), "planned"),
            "latest_z": replay.get("latest_z", 0),
            "tested_trades": replay.get("tested_trades", 0),
            "win_rate": replay.get("win_rate", 0),
            "total_pnl_per_unit": replay.get("total_pnl_per_unit", 0),
            "spread_oos_status": replay.get("oos_status", ""),
            "spread_oos_test_trades": replay.get("oos_test_trades", 0),
            "spread_oos_test_pnl_per_unit": replay.get("oos_test_pnl_per_unit", 0),
            "spread_oos_test_win_rate": replay.get("oos_test_win_rate", 0),
            "spread_out_of_sample_replay": replay.get("out_of_sample_replay", {}),
            "tradability_action": action,
            "tradability_reason": reason,
            "selected_expression": selected,
            "expressions": expression_rows,
            "arc_gate": "LOCKED_UNTIL_JUDGE_EXECUTE",
        })
    action_rank = {
        "READY_FOR_JUDGE": 0,
        "PAPER_BUY_ONLY": 1,
        "PAPER_BUY_CANDIDATE": 2,
        "AVOID_OR_SELL": 3,
        "SPREAD_REPLAY_ONLY": 4,
        "WAIT_FOR_SPREAD_REPLAY": 5,
        "MONITOR": 6,
        "NEEDS_INDEX_HISTORY": 7,
        "NEEDS_EXPRESSION": 8,
    }
    rows.sort(key=lambda row: (
        0 if (row.get("selected_expression") or {}).get("direction_aligned") else 1,
        action_rank.get(str(row.get("tradability_action")), 9),
        0 if row.get("replay_promotable") else 1,
        -abs(_num(row.get("latest_z"))),
        str(row.get("archetype_id") or ""),
    ))
    return rows


def _scaled_recent_paper_marks(recent_marks: list[dict[str, Any]], notional_usdc: float) -> list[dict[str, Any]]:
    if not recent_marks:
        return []
    notional = max(0.0, _num(notional_usdc))
    rows: list[dict[str, Any]] = []
    for idx, mark in enumerate(recent_marks):
        pnl_pct = _num(mark.get("paper_return_since_entry_pct"))
        daily_pct = _num(mark.get("daily_return_pct"))
        rows.append({
            "date": mark.get("date") or "",
            "mark_type": mark.get("mark_type") or ("entry" if idx == 0 else "mark"),
            "index_close": _round_units(mark.get("index_close")),
            "daily_return_pct": _round_units(daily_pct),
            "paper_return_since_entry_pct": _round_units(pnl_pct),
            "paper_pnl_usdc": _round_money(notional * pnl_pct / 100.0),
            "daily_pnl_usdc": _round_money(0.0 if idx == 0 else notional * daily_pct / 100.0),
        })
    return rows


def _scale_trade_pnl(value_pct: Any, notional_usdc: float) -> float:
    return _round_money(max(0.0, _num(notional_usdc)) * _num(value_pct) / 100.0)


def _scaled_paper_trade_replay(replay: dict[str, Any], notional_usdc: float) -> dict[str, Any]:
    if not replay:
        return {}
    closed_trades: list[dict[str, Any]] = []
    for trade in replay.get("closed_trades") or []:
        if not isinstance(trade, dict):
            continue
        closed_trades.append({
            **trade,
            "pnl_usdc": _scale_trade_pnl(trade.get("return_pct"), notional_usdc),
        })
    open_trade = replay.get("open_trade") if isinstance(replay.get("open_trade"), dict) else None
    scaled_open = None
    if open_trade:
        scaled_open = {
            **open_trade,
            "pnl_usdc": _scale_trade_pnl(open_trade.get("return_pct"), notional_usdc),
        }
    return {
        **replay,
        "closed_trades": closed_trades,
        "open_trade": scaled_open,
        "paper_notional_usdc": _round_money(notional_usdc),
        "realized_pnl_usdc": _scale_trade_pnl(replay.get("realized_return_pct"), notional_usdc),
        "open_pnl_usdc": _scale_trade_pnl(replay.get("open_return_pct"), notional_usdc),
        "total_pnl_usdc": _scale_trade_pnl(replay.get("total_return_pct"), notional_usdc),
    }


def _spread_profitability_ledger(trade_map: list[dict[str, Any]], *, paper_notional_usdc: float = 0.0) -> dict[str, Any]:
    """Rank spread expressions by actionable paper profitability.

    The ledger is deliberately labelled as paper replay. It uses public proxy
    basket returns and spread-family replay, not reconciled fills.
    """
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(trade_map):
        selected = item.get("selected_expression") if isinstance(item.get("selected_expression"), dict) else {}
        action = _text(item.get("tradability_action"), "MONITOR")
        latest_signal = _text(selected.get("latest_signal"), "MONITOR")
        ret_5d = selected.get("return_5d_pct", "")
        ret_1m = selected.get("return_1m_pct", "")
        total_return = selected.get("total_return_pct", "")
        replay_pnl = item.get("total_pnl_per_unit", 0)
        signal_reason = _first_nonempty(
            selected.get("signal_reason"),
            selected.get("status_reason"),
            item.get("tradability_reason"),
            default="No signal reason was attached to the selected expression.",
        )
        current_action_reason = _first_nonempty(
            selected.get("current_action_reason"),
            item.get("tradability_reason"),
            default="No current-action reason was attached to the selected expression.",
        )
        recent_marks = _scaled_recent_paper_marks(
            selected.get("recent_index_marks") if isinstance(selected.get("recent_index_marks"), list) else [],
            paper_notional_usdc,
        )
        trade_replay = _scaled_paper_trade_replay(
            selected.get("paper_trade_replay") if isinstance(selected.get("paper_trade_replay"), dict) else {},
            paper_notional_usdc,
        )
        oos_replay = selected.get("out_of_sample_replay") if isinstance(selected.get("out_of_sample_replay"), dict) else {}
        oos_status = _text(oos_replay.get("status"), "NO_OOS_REPLAY")
        latest_mark = recent_marks[-1] if recent_marks else {}
        buy_eligible_action = action in {"PAPER_BUY_ONLY", "READY_FOR_JUDGE", "PAPER_BUY_CANDIDATE"}
        supports_buy = buy_eligible_action and latest_signal == "BUY"
        holds_existing = buy_eligible_action and latest_signal == "HOLD"
        requires_close = "AVOID" in action or latest_signal == "SELL"
        if supports_buy and oos_status == "FAILED":
            status = "WAIT_FOR_OOS_CONFIRMATION"
            supports_buy = False
        elif supports_buy:
            status = "PAPER_BUY"
        elif holds_existing:
            status = "HOLD_EXISTING_ONLY"
        elif requires_close:
            status = "SELL_OR_AVOID"
        elif action == "SPREAD_REPLAY_ONLY":
            status = "WAIT_FOR_PROXY_CONFIRMATION"
        elif action == "WAIT_FOR_SPREAD_REPLAY":
            status = "WAIT_FOR_SPREAD_REPLAY"
        elif action in {"NEEDS_INDEX_HISTORY", "NEEDS_EXPRESSION"}:
            status = action
        else:
            status = "MONITOR"
        rows.append({
            "rank": idx + 1,
            "archetype_id": item.get("archetype_id"),
            "label": item.get("label"),
            "oil_analogy": item.get("oil_analogy"),
            "spread_replay_status": item.get("replay_status"),
            "spread_replay_promotable": bool(item.get("replay_promotable")),
            "spread_replay_pnl_per_unit": _round_units(replay_pnl),
            "spread_replay_win_rate": item.get("win_rate", 0),
            "spread_oos_status": item.get("spread_oos_status", ""),
            "spread_oos_test_trades": item.get("spread_oos_test_trades", 0),
            "spread_oos_test_pnl_per_unit": _round_units(item.get("spread_oos_test_pnl_per_unit")),
            "spread_oos_test_win_rate": item.get("spread_oos_test_win_rate", 0),
            "spread_out_of_sample_replay": item.get("spread_out_of_sample_replay", {}),
            "expression_title": selected.get("title") or selected.get("basket_label") or "",
            "basket_id": selected.get("basket_id") or "",
            "latest_signal": latest_signal,
            "signal_reason": signal_reason,
            "current_action": selected.get("current_action") or "",
            "current_action_reason": current_action_reason,
            "tradability_action": action,
            "profitability_status": status,
            "paper_5d_return_pct": ret_5d,
            "paper_1m_return_pct": ret_1m,
            "paper_total_return_pct": total_return,
            "paper_win_rate": selected.get("win_rate", 0),
            "paper_notional_usdc": _round_money(paper_notional_usdc),
            "recent_paper_marks": recent_marks,
            "latest_paper_mark": latest_mark,
            "latest_paper_pnl_usdc": latest_mark.get("paper_pnl_usdc", ""),
            "latest_paper_return_pct": latest_mark.get("paper_return_since_entry_pct", ""),
            "paper_trade_replay": trade_replay,
            "paper_trade_action": trade_replay.get("latest_trade_action", ""),
            "paper_trade_reason": trade_replay.get("latest_trade_reason", ""),
            "paper_trade_total_pnl_usdc": trade_replay.get("total_pnl_usdc", ""),
            "paper_trade_realized_pnl_usdc": trade_replay.get("realized_pnl_usdc", ""),
            "paper_trade_open_pnl_usdc": trade_replay.get("open_pnl_usdc", ""),
            "paper_trade_hit_rate": trade_replay.get("hit_rate", ""),
            "paper_trade_closed_count": trade_replay.get("closed_trade_count", 0),
            "paper_trade_open_count": trade_replay.get("open_trade_count", 0),
            "out_of_sample_replay": oos_replay,
            "oos_status": oos_status,
            "oos_passed": bool(oos_replay.get("passed")),
            "oos_test_return_pct": oos_replay.get("test_return_pct", ""),
            "oos_test_win_rate": oos_replay.get("test_win_rate", ""),
            "priced_symbols": selected.get("priced_symbols") or [],
            "missing_symbols": selected.get("missing_symbols") or [],
            "supports_fresh_buy": supports_buy,
            "holds_existing_only": holds_existing,
            "requires_close_or_avoid": requires_close,
            "signal_inputs": {
                "latest_signal": latest_signal,
                "signal_reason": signal_reason,
                "current_action": selected.get("current_action") or "",
                "current_action_reason": current_action_reason,
                "paper_5d_return_pct": ret_5d,
                "paper_1m_return_pct": ret_1m,
                "paper_total_return_pct": total_return,
                "paper_trade_action": trade_replay.get("latest_trade_action", ""),
                "paper_trade_reason": trade_replay.get("latest_trade_reason", ""),
                "oos_status": oos_status,
                "oos_test_return_pct": oos_replay.get("test_return_pct", ""),
                "spread_replay_status": item.get("replay_status"),
                "spread_oos_status": item.get("spread_oos_status", ""),
            },
            "reason": (
                "Proxy expression failed the out-of-sample replay slice; wait before promoting a fresh paper buy."
                if status == "WAIT_FOR_OOS_CONFIRMATION"
                else (
                    "Proxy replay is promotable, but current marks only say HOLD; do not open fresh exposure."
                    if status == "HOLD_EXISTING_ONLY"
                    else item.get("tradability_reason")
                )
            ),
        })
    status_rank = {
        "PAPER_BUY": 0,
        "SELL_OR_AVOID": 1,
        "HOLD_EXISTING_ONLY": 2,
        "WAIT_FOR_PROXY_CONFIRMATION": 3,
        "WAIT_FOR_OOS_CONFIRMATION": 4,
        "WAIT_FOR_SPREAD_REPLAY": 5,
        "MONITOR": 6,
        "NEEDS_INDEX_HISTORY": 7,
        "NEEDS_EXPRESSION": 8,
    }
    rows.sort(key=lambda row: (
        status_rank.get(str(row.get("profitability_status")), 9),
        -_num(row.get("paper_5d_return_pct")),
        -_num(row.get("paper_1m_return_pct")),
        -_num(row.get("spread_replay_pnl_per_unit")),
        str(row.get("archetype_id") or ""),
    ))
    for idx, row in enumerate(rows):
        row["rank"] = idx + 1
    best_buy = next((row for row in rows if row.get("supports_fresh_buy")), None)
    first_avoid = next((row for row in rows if row.get("requires_close_or_avoid")), None)
    return {
        "version": "spread_profitability_ledger_v1",
        "source": "spread_replay_plus_public_proxy_replay",
        "realized": False,
        "paper_notional_usdc": _round_money(paper_notional_usdc),
        "realized_note": "These are replay and live paper marks scaled to mock notional, not reconciled fills or settled PnL.",
        "best_buy_candidate": best_buy,
        "first_avoid_candidate": first_avoid,
        "counts": {
            "paper_buy": sum(1 for row in rows if row.get("supports_fresh_buy")),
            "hold_existing": sum(1 for row in rows if row.get("holds_existing_only")),
            "sell_or_avoid": sum(1 for row in rows if row.get("requires_close_or_avoid")),
            "needs_data": sum(1 for row in rows if str(row.get("profitability_status")).startswith("NEEDS")),
            "monitor": sum(1 for row in rows if row.get("profitability_status") == "MONITOR"),
        },
        "rows": rows,
    }


def _portfolio_signal_summary(profitability_ledger: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in (profitability_ledger or {}).get("rows", []) if isinstance(row, dict)]
    buy_rows = [row for row in rows if row.get("supports_fresh_buy")]
    close_rows = [row for row in rows if row.get("requires_close_or_avoid")]
    wait_rows = [
        row for row in rows
        if str(row.get("profitability_status") or "").startswith("WAIT")
        or str(row.get("profitability_status") or "").startswith("NEEDS")
    ]
    oos_pass_count = sum(1 for row in rows if row.get("oos_status") == "PASSED")
    oos_fail_count = sum(1 for row in rows if row.get("oos_status") == "FAILED")
    total_ticket_pnl = sum(_num(row.get("paper_trade_total_pnl_usdc")) for row in rows if row.get("paper_trade_total_pnl_usdc") not in ("", None))
    total_mark_pnl = sum(_num(row.get("latest_paper_pnl_usdc")) for row in rows if row.get("latest_paper_pnl_usdc") not in ("", None))
    realized_ticket_pnl = sum(_num(row.get("paper_trade_realized_pnl_usdc")) for row in rows if row.get("paper_trade_realized_pnl_usdc") not in ("", None))
    open_ticket_pnl = sum(_num(row.get("paper_trade_open_pnl_usdc")) for row in rows if row.get("paper_trade_open_pnl_usdc") not in ("", None))

    top_buy = buy_rows[0] if buy_rows else None
    top_close = close_rows[0] if close_rows else None
    if top_buy and top_close:
        action = "ROTATE"
        headline = f"Open {top_buy.get('label')} only after closing/avoiding {top_close.get('label')}."
    elif top_buy:
        action = "OPEN_TOP_PAPER_BUY"
        headline = f"Open paper ticket candidate: {top_buy.get('label')}."
    elif top_close:
        action = "CLOSE_OR_AVOID"
        headline = f"Close or avoid current sell signal: {top_close.get('label')}."
    elif wait_rows:
        action = "WAIT_FOR_DATA"
        headline = "Wait for spread replay, proxy confirmation, or index history."
    else:
        action = "MONITOR"
        headline = "Monitor spread menu; no fresh action."

    def row_action(row: dict[str, Any]) -> str:
        if row.get("supports_fresh_buy"):
            return "BUY_PAPER"
        if row.get("requires_close_or_avoid"):
            return "CLOSE_OR_AVOID"
        status = str(row.get("profitability_status") or "MONITOR")
        if status.startswith("WAIT") or status.startswith("NEEDS"):
            return status
        return "MONITOR"

    return {
        "version": "portfolio_signal_summary_v1",
        "source": "spread_profitability_ledger",
        "realized": False,
        "action": action,
        "headline": headline,
        "paper_notional_usdc": profitability_ledger.get("paper_notional_usdc", 0),
        "paper_ticket_total_pnl_usdc": _round_money(total_ticket_pnl),
        "paper_ticket_realized_pnl_usdc": _round_money(realized_ticket_pnl),
        "paper_ticket_open_pnl_usdc": _round_money(open_ticket_pnl),
        "latest_mark_total_pnl_usdc": _round_money(total_mark_pnl),
        "buy_count": len(buy_rows),
        "close_or_avoid_count": len(close_rows),
        "wait_count": len(wait_rows),
        "monitor_count": sum(1 for row in rows if row_action(row) == "MONITOR"),
        "oos_pass_count": oos_pass_count,
        "oos_fail_count": oos_fail_count,
        "top_buy": top_buy,
        "top_close_or_avoid": top_close,
        "rows": [
            {
                "rank": row.get("rank"),
                "archetype_id": row.get("archetype_id"),
                "label": row.get("label"),
                "action": row_action(row),
                "profitability_status": row.get("profitability_status"),
                "latest_signal": row.get("latest_signal"),
                "paper_trade_action": row.get("paper_trade_action"),
                "paper_trade_total_pnl_usdc": row.get("paper_trade_total_pnl_usdc", ""),
                "latest_paper_pnl_usdc": row.get("latest_paper_pnl_usdc", ""),
                "signal_reason": row.get("signal_reason", ""),
                "current_action_reason": row.get("current_action_reason", ""),
                "reason": row.get("reason"),
            }
            for row in rows[:6]
        ],
        "guardrail": "Portfolio signal is paper/replay guidance only. Circle/Arc remains locked unless judge.classify() returns EXECUTE.",
    }


def _venue_copy_role(row: dict[str, Any]) -> tuple[str, str]:
    surface = _text(row.get("surface"))
    evidence_only = bool(row.get("evidence_only"))
    direct = bool(row.get("direct_event_surface")) or surface in DIRECT_SURFACES
    if evidence_only or surface == "opoint_nebius":
        return "evidence_only", "News/LLM evidence only; cannot define or price the instrument."
    if surface == "public_market":
        return "liquid_proxy_hedge", "Public equities/futures are liquid proxy legs for sizing and mark-to-market."
    if surface == "crypto":
        return "miner_margin_proxy", "BTC/ETH are only miner-margin proxies when power cost matters."
    if direct:
        return "direct_event_leg", "Prediction/forecast contract can be a direct leg if priced, thesis-matched, and judged."
    return "research_surface", "Research surface; keep scouting until role and pricing are explicit."


def _surface_sample_legs(
    surface: str,
    *,
    direct_inventory: list[dict[str, Any]],
    hedge_basket: list[dict[str, Any]],
    direct_legs: list[dict[str, Any]],
    oracle_evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    if surface == "public_market":
        rows = [leg for leg in hedge_basket if leg.get("surface") in {"public_market", "ibkr"}]
    elif surface == "crypto":
        rows = [
            leg for leg in hedge_basket
            if "BTC" in str(leg.get("slug") or leg.get("instrument") or "") or "ETH" in str(leg.get("slug") or leg.get("instrument") or "")
        ]
    elif surface == "opoint_nebius":
        rows = [{
            "surface": "opoint_nebius",
            "leg_title": oracle_evidence.get("latest_title") or "latest oracle receipt",
            "leg_slug": oracle_evidence.get("latest_slug") or oracle_evidence.get("oracle_evidence_hash") or "oracle-evidence",
            "direct_pair_role": "news-grounded evidence only",
            "pricing_status": oracle_evidence.get("latest_verdict") or oracle_evidence.get("status") or "EVIDENCE",
        }]
    else:
        rows = [leg for leg in direct_inventory if _text(leg.get("surface")) == surface]
        if not rows:
            rows = [leg for leg in direct_legs if _text(leg.get("surface")) == surface]
    return _dedupe_legs(rows, limit=4)


def _venue_spread_links(surface: str, copy_role: str, spread_trade_map: list[dict[str, Any]]) -> list[dict[str, Any]]:
    linked: list[dict[str, Any]] = []
    for item in spread_trade_map:
        selected = item.get("selected_expression") if isinstance(item.get("selected_expression"), dict) else {}
        direct_ready = bool(selected.get("direct_leg_target_ready"))
        basket_id = _text(selected.get("basket_id"))
        include = False
        if copy_role == "direct_event_leg":
            include = direct_ready
        elif copy_role == "liquid_proxy_hedge":
            include = bool(basket_id)
        elif copy_role == "miner_margin_proxy":
            include = basket_id == "miner_margin_power_pair" or "miner" in _text(item.get("label")).lower()
        elif copy_role == "evidence_only":
            include = bool(item.get("archetype_id"))
        if not include:
            continue
        linked.append({
            "archetype_id": item.get("archetype_id"),
            "label": item.get("label"),
            "action": item.get("tradability_action"),
            "replay_status": item.get("replay_status"),
            "latest_signal": selected.get("latest_signal") or "MONITOR",
            "basket_id": basket_id,
        })
        if len(linked) >= 4:
            break
    return linked


def _venue_copy_status(row: dict[str, Any], copy_role: str) -> tuple[str, str]:
    status = _text(row.get("status"), "UNKNOWN")
    priced = _num(row.get("priced_count"))
    proxy = _num(row.get("external_proxy_count"))
    if copy_role == "evidence_only":
        return "EVIDENCE_ONLY", "Use as support/critique evidence; never as execution or collateral."
    if copy_role == "liquid_proxy_hedge":
        return ("PROXY_LIVE" if priced > 0 else "NEEDS_PROXY_PRICE", "Liquid proxy basket can mark PnL, but is not a direct compute/power claim.")
    if copy_role == "miner_margin_proxy":
        return ("PROXY_LIVE" if priced > 0 else "NEEDS_PROXY_PRICE", "Use only for miner-margin/power-cost packages, not generic compute securitization.")
    if copy_role == "direct_event_leg":
        if status == "LIVE_PRICED" and priced > 0:
            if row.get("premium_gate_required"):
                return "NEEDS_PREMIUM_AND_JUDGE", "Run premium scorer, pair with the opposite leg, then judge.classify()."
            return "NEEDS_JUDGE_PAIR", "Pair with the opposite energy/compute leg, then judge.classify()."
        if proxy > 0:
            return "DIRECT_METADATA_PROXY_PRICED", "Direct venue contract is identified, but only external proxy marks are priced."
        return "NEEDS_DIRECT_PRICE", "Fetch venue bid/ask/last before promotion."
    return "SCOUTING", "Keep in research until pricing and spread linkage are explicit."


def _direct_leg_bucket(leg: dict[str, Any]) -> str:
    role = _text(leg.get("role")).lower()
    title = _text(leg.get("title")).lower()
    description = _text(leg.get("description")).lower()
    energy_terms = ("energy", "electricity", "power", "grid", "nuclear", "gas", "oil", "brent", "crude", "generation")
    compute_terms = ("compute", "ai", "gpu", "nvidia", "openai", "anthropic", "data center", "datacenter", "semiconductor")
    if any(term in role for term in energy_terms):
        return "energy"
    if any(term in role for term in compute_terms):
        return "compute"
    text = " ".join([title, description])
    if any(term in text for term in energy_terms):
        return "energy"
    if any(term in text for term in compute_terms):
        return "compute"
    return ""


def _direct_pair_side(direction: str, bucket: str) -> str:
    if direction == DIRECTION_ELEC_EXPENSIVE:
        return "long" if bucket == "energy" else "short"
    if direction == DIRECTION_COMPUTE_EXPENSIVE:
        return "long" if bucket == "compute" else "short"
    return "watch"


def _leg_is_live_priced(leg: dict[str, Any]) -> bool:
    status = _text(leg.get("pricing_status")).lower()
    return status in {"priced_watchlist", "priced_public_market", "live_priced"} or _text(leg.get("status_label")).lower() in {"live price available", "public price available"}


def _pair_oracle_evidence(
    oracle_judge_evidence: dict[str, Any],
    *,
    energy: dict[str, Any],
    compute: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(oracle_judge_evidence, dict) or not oracle_judge_evidence:
        return {
            "status": "NO_RECEIPTS",
            "gate": "NO_ORACLE_RECEIPTS",
            "receipts": 0,
            "latest_verdict": "",
            "latest_reason_code": "",
            "oracle_evidence_hash": "",
            "matched_latest_receipt": False,
            "note": "No Opoint/Nebius receipt is attached; pair can still be judged, but news/LLM evidence is missing.",
            "can_drive_arc": False,
        }
    receipts = int(_num(oracle_judge_evidence.get("row_count")))
    latest_verdict = _text(oracle_judge_evidence.get("latest_verdict")).upper()
    latest_slug = _text(oracle_judge_evidence.get("latest_slug")).lower()
    latest_title = _text(oracle_judge_evidence.get("latest_title")).lower()
    pair_refs = {
        _text(energy.get("slug")).lower(),
        _text(energy.get("title")).lower(),
        _text(compute.get("slug")).lower(),
        _text(compute.get("title")).lower(),
    }
    matched = bool(latest_slug and latest_slug in pair_refs) or bool(latest_title and latest_title in pair_refs)
    if receipts <= 0:
        gate = "NO_ORACLE_RECEIPTS"
        note = "No Opoint/Nebius receipt is attached; pair can still be judged, but news/LLM evidence is missing."
    elif latest_verdict == "KEEP":
        gate = "EVIDENCE_ONLY_SUPPORT"
        note = "Latest Opoint/Nebius receipt supports keeping the candidate as evidence, but cannot execute it."
    elif latest_verdict == "VETO":
        gate = "EVIDENCE_ONLY_CRITIQUE"
        note = "Latest Opoint/Nebius receipt criticizes the candidate; judge should treat it as adverse evidence."
    elif latest_verdict == "DEFER":
        gate = "EVIDENCE_ONLY_DEFER"
        note = "Latest Opoint/Nebius receipt is inconclusive; judge should not promote solely from this evidence."
    else:
        gate = "EVIDENCE_ATTACHED"
        note = "Opoint/Nebius receipt is attached as evidence only; premium scorer and judge gates are unchanged."
    return {
        "status": _text(oracle_judge_evidence.get("status"), "NO_RECEIPTS"),
        "gate": gate,
        "receipts": receipts,
        "latest_verdict": latest_verdict,
        "latest_reason_code": _text(oracle_judge_evidence.get("latest_reason_code")),
        "oracle_evidence_hash": _text(oracle_judge_evidence.get("oracle_evidence_hash")),
        "matched_latest_receipt": matched,
        "raw_articles": int(_num(oracle_judge_evidence.get("raw_articles"))),
        "filtered_articles": int(_num(oracle_judge_evidence.get("filtered_articles"))),
        "note": note,
        "can_drive_arc": False,
    }


def _direct_event_pair_candidates(
    *,
    direction: str,
    direction_profile: dict[str, str],
    direct_legs: list[dict[str, Any]],
    oracle_judge_evidence: dict[str, Any],
) -> dict[str, Any]:
    energy_legs = [leg for leg in direct_legs if _direct_leg_bucket(leg) == "energy"]
    compute_legs = [leg for leg in direct_legs if _direct_leg_bucket(leg) == "compute"]
    rows: list[dict[str, Any]] = []
    for energy in energy_legs:
        for compute in compute_legs:
            if energy.get("slug") == compute.get("slug") and energy.get("surface") == compute.get("surface"):
                continue
            surfaces = sorted({_text(energy.get("surface")), _text(compute.get("surface"))})
            both_priced = _leg_is_live_priced(energy) and _leg_is_live_priced(compute)
            premium_required = "polymarket" in surfaces
            if both_priced and premium_required:
                readiness = "NEEDS_PREMIUM_AND_JUDGE"
                action = "Run Polymarket premium scorer on the Polymarket leg, then judge.classify() on the paired package."
            elif both_priced:
                readiness = "NEEDS_JUDGE"
                action = "Run judge.classify() on the paired package before any Arc action."
            else:
                readiness = "NEEDS_PRICE"
                action = "Fetch venue bid/ask/last for both direct legs before judging the pair."
            pair_payload = {
                "energy": [energy.get("surface"), energy.get("slug")],
                "compute": [compute.get("surface"), compute.get("slug")],
                "direction": direction,
            }
            oracle_pair_evidence = _pair_oracle_evidence(
                oracle_judge_evidence,
                energy=energy,
                compute=compute,
            )
            rows.append({
                "pair_id": _hash_payload(pair_payload)[:12],
                "direction": direction,
                "target_pair": direction_profile.get("direct_pair", ""),
                "readiness": readiness,
                "action": action,
                "surfaces": surfaces,
                "mixed_surface": len(surfaces) > 1,
                "premium_gate_required": premium_required,
                "judge_required": True,
                "oracle_required": False,
                "can_drive_arc": False,
                "oracle_evidence": oracle_pair_evidence,
                "judge_package_inputs": [
                    "energy_leg",
                    "compute_leg",
                    "latest_prices",
                    "premium_score" if premium_required else "venue_price",
                    "oracle_evidence_hash" if oracle_pair_evidence.get("oracle_evidence_hash") else "optional_oracle_evidence",
                    "spread_replay",
                    "proxy_replay",
                ],
                "energy_leg": {
                    **energy,
                    "bucket": "energy",
                    "pair_side": _direct_pair_side(direction, "energy"),
                },
                "compute_leg": {
                    **compute,
                    "bucket": "compute",
                    "pair_side": _direct_pair_side(direction, "compute"),
                },
                "why_connected": (
                    f"{energy.get('title') or energy.get('slug')} is the energy/grid-stress side; "
                    f"{compute.get('title') or compute.get('slug')} is the AI compute-demand side. "
                    f"Together they express {direction_profile.get('direct_pair', 'the compute/energy spread')}."
                ),
                "arc_gate": "LOCKED_UNTIL_JUDGE_EXECUTE",
            })
    rows.sort(key=lambda row: (
        0 if row.get("readiness") in {"NEEDS_PREMIUM_AND_JUDGE", "NEEDS_JUDGE"} else 1,
        0 if row.get("mixed_surface") else 1,
        VENUE_COPY_ORDER.get(str((row.get("energy_leg") or {}).get("surface")), 99),
        VENUE_COPY_ORDER.get(str((row.get("compute_leg") or {}).get("surface")), 99),
        str(row.get("pair_id") or ""),
    ))
    return {
        "version": "direct_event_pair_candidates_v1",
        "target_pair": direction_profile.get("direct_pair", ""),
        "direction": direction,
        "energy_leg_count": len(energy_legs),
        "compute_leg_count": len(compute_legs),
        "pair_count": len(rows),
        "ready_for_judge_count": sum(1 for row in rows if row.get("readiness") in {"NEEDS_PREMIUM_AND_JUDGE", "NEEDS_JUDGE"}),
        "oracle_evidence": {
            "status": oracle_judge_evidence.get("status", "NO_RECEIPTS") if isinstance(oracle_judge_evidence, dict) else "NO_RECEIPTS",
            "row_count": oracle_judge_evidence.get("row_count", 0) if isinstance(oracle_judge_evidence, dict) else 0,
            "latest_verdict": oracle_judge_evidence.get("latest_verdict", "") if isinstance(oracle_judge_evidence, dict) else "",
            "oracle_evidence_hash": oracle_judge_evidence.get("oracle_evidence_hash", "") if isinstance(oracle_judge_evidence, dict) else "",
            "can_drive_arc": False,
            "gate_note": "Opoint/Nebius evidence can support or criticize a pair, but it cannot replace premium scoring or judge.classify().",
        },
        "rows": rows[:8],
        "guardrail": "Direct event pairs are candidate packages only. Premium scorer and judge.classify() must pass before Circle or Arc.",
    }


def _real_venue_copy_matrix(
    *,
    venue_evidence: dict[str, Any] | None,
    direct_inventory: list[dict[str, Any]],
    hedge_basket: list[dict[str, Any]],
    direct_legs: list[dict[str, Any]],
    spread_trade_map: list[dict[str, Any]],
    oracle_judge_evidence: dict[str, Any],
) -> dict[str, Any]:
    evidence_rows = [
        row for row in ((venue_evidence or {}).get("rows") or [])
        if isinstance(row, dict)
    ]
    rows: list[dict[str, Any]] = []
    for source_row in evidence_rows:
        surface = _text(source_row.get("surface"))
        copy_role, role_note = _venue_copy_role(source_row)
        copy_status, action = _venue_copy_status(source_row, copy_role)
        sample_legs = _surface_sample_legs(
            surface,
            direct_inventory=direct_inventory,
            hedge_basket=hedge_basket,
            direct_legs=direct_legs,
            oracle_evidence=oracle_judge_evidence,
        )
        spread_links = _venue_spread_links(surface, copy_role, spread_trade_map)
        rows.append({
            "surface": surface,
            "label": source_row.get("label") or surface,
            "feed_status": source_row.get("status") or "UNKNOWN",
            "copy_status": copy_status,
            "copy_role": copy_role,
            "role_note": role_note,
            "action": action,
            "real_feed": bool(source_row.get("real_feed")),
            "direct_event_surface": bool(source_row.get("direct_event_surface")),
            "evidence_only": bool(source_row.get("evidence_only")),
            "premium_gate_required": bool(source_row.get("premium_gate_required")),
            "judge_required": True,
            "can_drive_arc": False,
            "priced_count": int(_num(source_row.get("priced_count"))),
            "watchlist_count": int(_num(source_row.get("watchlist_count"))),
            "external_proxy_count": int(_num(source_row.get("external_proxy_count"))),
            "latest_title": source_row.get("latest_title") or "",
            "latest_slug": source_row.get("latest_slug") or "",
            "sample_legs": sample_legs,
            "spread_links": spread_links,
            "gaps": source_row.get("gaps") or [],
        })
    rows.sort(key=lambda row: (
        VENUE_COPY_ORDER.get(str(row.get("surface")), 99),
        str(row.get("surface") or ""),
    ))
    return {
        "version": "real_venue_copy_matrix_v1",
        "rows": rows,
        "summary": {
            "surfaces": len(rows),
            "direct_event_surfaces": sum(1 for row in rows if row.get("direct_event_surface")),
            "proxy_surfaces": sum(1 for row in rows if str(row.get("copy_role")).endswith("proxy") or row.get("copy_role") == "liquid_proxy_hedge"),
            "evidence_only_surfaces": sum(1 for row in rows if row.get("evidence_only")),
            "priced_surfaces": sum(1 for row in rows if _num(row.get("priced_count")) > 0),
            "arc_ready_surfaces": 0,
        },
        "guardrail": "Venue rows can copy or evidence the package, but no Circle/Arc action can happen before judge.classify() returns EXECUTE.",
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
    spread_family_validation: dict[str, Any] | None = None,
    proxy_basket_validation: dict[str, Any] | None = None,
    oracle_evidence: dict[str, Any] | None = None,
    venue_evidence: dict[str, Any] | None = None,
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
        spread_family_validation=spread_family_validation,
        proxy_basket_validation=proxy_basket_validation,
    )
    collateral_profiles = _collateral_profile_candidates(
        direction=direction,
        spread_latest=spread_latest,
        signal_latest=signal_latest,
        proxy_basket_validation=proxy_basket_validation,
        spread_family_validation=spread_family_validation,
    )
    syndicated_menu = _syndicated_instrument_menu(
        region_profile=region_profile,
        signal_direction=direction,
        collateral_status=collateral_status,
        direct_legs=direct_legs,
        hedge_basket=hedge_basket,
        mock_construction=mock_construction,
        proxy_basket_validation=proxy_basket_validation,
    )
    spread_trade_map = _spread_archetype_trade_map(
        signal_direction=direction,
        spread_family_validation=spread_family_validation,
        proxy_basket_validation=proxy_basket_validation,
        syndicated_menu=syndicated_menu,
    )
    profitability_ledger = _spread_profitability_ledger(
        spread_trade_map,
        paper_notional_usdc=_num(mock_construction.get("hedge_notional_usdc")),
    )
    portfolio_signal_summary = _portfolio_signal_summary(profitability_ledger)
    operator_signal_sheet = _operator_signal_sheet(
        direction=direction,
        mock_construction=mock_construction,
        collateral_profiles=collateral_profiles,
        proxy_basket_validation=proxy_basket_validation,
        spread_family_validation=spread_family_validation,
        syndicated_menu=syndicated_menu,
    )
    build_instructions = _build_instructions(direct_legs, hedge_basket, discovery_gaps, collateral_status, mock_construction)
    schematic_steps = _schematic_steps(
        collateral_status=collateral_status,
        hedge_basket=hedge_basket,
        direct_legs=direct_legs,
        discovery_gaps=discovery_gaps,
    )
    agent_search_plan = _agent_search_plan(region_profile, direction_profile, direct_legs, discovery_gaps)
    oracle_judge_evidence = _oracle_judge_evidence(oracle_evidence)
    direct_event_pair_candidates = _direct_event_pair_candidates(
        direction=direction,
        direction_profile=direction_profile,
        direct_legs=direct_legs,
        oracle_judge_evidence=oracle_judge_evidence,
    )
    real_venue_copy_matrix = _real_venue_copy_matrix(
        venue_evidence=venue_evidence,
        direct_inventory=direct_inventory,
        hedge_basket=hedge_basket,
        direct_legs=direct_legs,
        spread_trade_map=spread_trade_map,
        oracle_judge_evidence=oracle_judge_evidence,
    )

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
            "oracle_evidence_hash": oracle_judge_evidence.get("oracle_evidence_hash"),
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
            "collateral_profile_candidates": collateral_profiles,
            "syndicated_instrument_menu": syndicated_menu,
            "spread_archetype_trade_map": spread_trade_map,
            "spread_profitability_ledger": profitability_ledger,
            "portfolio_signal_summary": portfolio_signal_summary,
            "operator_signal_sheet": operator_signal_sheet,
            "direct_event_pair_candidates": direct_event_pair_candidates,
            "real_venue_copy_matrix": real_venue_copy_matrix,
            "spread_family_validation": spread_family_validation or {},
            "proxy_basket_validation": proxy_basket_validation or {},
            "oracle_judge_evidence": oracle_judge_evidence,
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
