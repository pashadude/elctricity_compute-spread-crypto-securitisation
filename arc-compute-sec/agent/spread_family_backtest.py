"""Walk-forward replay for compute/energy spread families.

This module is deliberately read-only. It turns the existing spread history
into oil-style relative-value families and checks whether the latest signal is
supported by an out-of-sample replay. It does not route, trade, call venues, or
call Arc.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from agent.arb_identifier import DEFAULT_K, DEFAULT_KWH_PER_GPU_HR

DEFAULT_WINDOW = 30
DEFAULT_HORIZON_STEPS = 12
DEFAULT_THRESHOLD_Z = 1.0
DEFAULT_MIN_OBS = 48
DEFAULT_MIN_DISTINCT = 6
DEFAULT_MIN_TRADES = 8
MARK_EPSILON = 1e-10
STRATEGY_MEAN_REVERSION = "mean_reversion"
STRATEGY_MOMENTUM = "momentum"
DEFAULT_STRATEGY_MODES = (STRATEGY_MEAN_REVERSION,)


@dataclass(frozen=True, slots=True)
class SpreadFamily:
    family_id: str
    archetype_id: str
    label: str
    formula: str
    unit: str
    expensive_side: str
    trade_rule: str
    value_fn: Callable[[dict[str, float]], float]
    series_fn: Callable[[list[dict[str, Any]]], list[float]] | None = None


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _row_inputs(row: dict[str, Any]) -> dict[str, float]:
    elec = _num(row.get("electricity_per_mwh"))
    compute = _num(row.get("compute_per_gpu_hr"))
    k = _num(row.get("k"), DEFAULT_K)
    kwh = _num(row.get("kwh_per_gpu_hr", row.get("kWh_per_gpu_hr")), DEFAULT_KWH_PER_GPU_HR)
    power_cost = k * (elec / 1000.0) * kwh
    raw_power_cost = (elec / 1000.0) * kwh
    return {
        "electricity_per_mwh": elec,
        "compute_per_gpu_hr": compute,
        "k": k,
        "kwh_per_gpu_hr": kwh,
        "power_cost_per_gpu_hr": power_cost,
        "raw_power_cost_per_gpu_hr": raw_power_cost,
        "S_t": _num(row.get("S_t"), compute - power_cost),
    }


def _safe_ratio(num: float, den: float) -> float:
    if abs(den) < 1e-12:
        return 0.0
    return num / den


def _prior_mean(values: list[float], idx: int, window: int) -> float | None:
    if idx < window:
        return None
    sample = values[idx - window:idx]
    if not sample:
        return None
    return _mean(sample)


def _input_series(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = _row_inputs(row).get(key, 0.0)
        if math.isfinite(value):
            values.append(value)
    return values


def _calendar_series(rows: list[dict[str, Any]], key: str, *, window: int = 21) -> list[float]:
    """Front mark minus trailing prior-mark term proxy.

    The term proxy excludes the current row, so this remains no-lookahead even
    though the repo does not yet have a real forward GPU or power curve.
    """
    values = _input_series(rows, key)
    out: list[float] = []
    for idx, value in enumerate(values):
        term = _prior_mean(values, idx, window)
        if term is None:
            continue
        out.append(value - term)
    return out


def _calendar_pct_basis_series(rows: list[dict[str, Any]], *, window: int = 21) -> list[float]:
    """Prompt compute premium minus prompt electricity premium.

    Values are ratios, not dollars. This is a curve-shape basis: it asks
    whether front GPU rentals are tightening faster than front power marks.
    """
    compute = _input_series(rows, "compute_per_gpu_hr")
    power = _input_series(rows, "electricity_per_mwh")
    out: list[float] = []
    for idx in range(min(len(compute), len(power))):
        compute_term = _prior_mean(compute, idx, window)
        power_term = _prior_mean(power, idx, window)
        if compute_term is None or power_term is None:
            continue
        out.append(_safe_ratio(compute[idx] - compute_term, compute_term) - _safe_ratio(power[idx] - power_term, power_term))
    return out


SPREAD_FAMILIES: tuple[SpreadFamily, ...] = (
    SpreadFamily(
        family_id="compute_net_power_margin",
        archetype_id="compute_spark_spread",
        label="Compute minus power cost",
        formula="compute - k * (electricity/1000) * kWh",
        unit="USD/GPU-hr",
        expensive_side="High = compute expensive; low = power expensive.",
        trade_rule="Mean-revert: short when z is high, long when z is low.",
        value_fn=lambda x: x["compute_per_gpu_hr"] - x["power_cost_per_gpu_hr"],
    ),
    SpreadFamily(
        family_id="power_cost_share",
        archetype_id="power_cost_share",
        label="Power cost share",
        formula="k * (electricity/1000) * kWh / compute",
        unit="ratio",
        expensive_side="High = electricity consumes more of GPU-hour revenue.",
        trade_rule="Mean-revert: short when power share is high, long when it is low.",
        value_fn=lambda x: _safe_ratio(x["power_cost_per_gpu_hr"], x["compute_per_gpu_hr"]),
    ),
    SpreadFamily(
        family_id="compute_power_ratio",
        archetype_id="compute_power_ratio",
        label="Compute / power ratio",
        formula="compute / (k * electricity/1000 * kWh)",
        unit="ratio",
        expensive_side="High = compute rich versus power input cost.",
        trade_rule="Mean-revert: short when ratio is high, long when ratio is low.",
        value_fn=lambda x: _safe_ratio(x["compute_per_gpu_hr"], x["power_cost_per_gpu_hr"]),
    ),
    SpreadFamily(
        family_id="raw_compute_power_margin",
        archetype_id="fuel_stack_compute_spread",
        label="Raw compute minus power",
        formula="compute - (electricity/1000) * kWh",
        unit="USD/GPU-hr",
        expensive_side="High = compute rich before PUE/utilization haircut.",
        trade_rule="Mean-revert: short when z is high, long when z is low.",
        value_fn=lambda x: x["compute_per_gpu_hr"] - x["raw_power_cost_per_gpu_hr"],
    ),
    SpreadFamily(
        family_id="compute_prompt_calendar_21d",
        archetype_id="compute_calendar_spread",
        label="Compute prompt calendar proxy",
        formula="spot GPU rental - prior 21-mark GPU rental average",
        unit="USD/GPU-hr",
        expensive_side="High = front compute tight versus trailing term proxy.",
        trade_rule="Mean-revert or momentum depending on replay mode; no current mark enters the term proxy.",
        value_fn=lambda x: 0.0,
        series_fn=lambda rows: _calendar_series(rows, "compute_per_gpu_hr", window=21),
    ),
    SpreadFamily(
        family_id="electricity_prompt_calendar_21d",
        archetype_id="electricity_calendar_spread",
        label="Electricity prompt calendar proxy",
        formula="front electricity $/MWh - prior 21-mark electricity average",
        unit="USD/MWh",
        expensive_side="High = front power tight versus trailing term proxy.",
        trade_rule="Mean-revert or momentum depending on replay mode; no current mark enters the term proxy.",
        value_fn=lambda x: 0.0,
        series_fn=lambda rows: _calendar_series(rows, "electricity_per_mwh", window=21),
    ),
    SpreadFamily(
        family_id="compute_power_prompt_basis_21d",
        archetype_id="compute_power_calendar_basis",
        label="Compute-power prompt basis",
        formula="compute prompt premium % - electricity prompt premium %",
        unit="ratio",
        expensive_side="High = front compute tightening faster than front power.",
        trade_rule="Mean-revert or momentum depending on replay mode; both terms use prior 21 marks only.",
        value_fn=lambda x: 0.0,
        series_fn=lambda rows: _calendar_pct_basis_series(rows, window=21),
    ),
)


ELECTRICITY_INDEX_CATALOG = [
    {
        "id": "eia_ercot_tx_proxy",
        "label": "EIA ERCOT/TX electricity proxy",
        "venue": "EIA public feed",
        "role": "primary live electricity mark",
        "status": "active",
    },
    {
        "id": "eia_pjm_data_center_proxy",
        "label": "EIA PJM/data-center corridor electricity proxy",
        "venue": "EIA public feed",
        "role": "regional power index for US-East compute loads",
        "status": "planned",
    },
    {
        "id": "ercot_hub_rt_lmp",
        "label": "ERCOT hub real-time LMP",
        "venue": "ERCOT market data",
        "role": "physical prompt power index for Texas datacenter load",
        "status": "planned",
    },
    {
        "id": "pjm_da_rt_lmp",
        "label": "PJM day-ahead / real-time LMP",
        "venue": "PJM market data",
        "role": "physical prompt power index for US-East datacenter load",
        "status": "planned",
    },
    {
        "id": "caiso_sp15_np15_lmp",
        "label": "CAISO SP15/NP15 LMP",
        "venue": "CAISO OASIS",
        "role": "physical prompt power index for California compute loads",
        "status": "planned",
    },
    {
        "id": "eia_caiso_duck_curve_proxy",
        "label": "EIA/CAISO solar-ramp electricity proxy",
        "venue": "EIA/CAISO public feed",
        "role": "regional power index for California compute loads",
        "status": "planned",
    },
    {
        "id": "ibkr_retxc",
        "label": "Texas Commercial Electricity Generation Sales Revenue",
        "venue": "IBKR ForecastTrader",
        "role": "direct event electricity revenue leg",
        "status": "watchlist",
    },
    {
        "id": "ibkr_aeusa",
        "label": "Average Electricity Price for All Sectors",
        "venue": "IBKR ForecastTrader",
        "role": "forecast electricity price index",
        "status": "watchlist",
    },
    {
        "id": "ibkr_emusa_emusx",
        "label": "US total and renewable electricity generation ForecastTrader indexes",
        "venue": "IBKR ForecastTrader",
        "role": "direct electricity supply/renewables event legs",
        "status": "watchlist",
    },
    {
        "id": "ng_front_future",
        "label": "Henry Hub natural gas",
        "venue": "IBKR/Yahoo/Alpaca public quote",
        "role": "marginal power-stack input",
        "status": "proxy",
    },
    {
        "id": "brent_wti_front_future",
        "label": "Brent/WTI crude front futures",
        "venue": "IBKR/Yahoo/Alpaca public quote",
        "role": "fuel and macro energy input proxy",
        "status": "proxy",
    },
    {
        "id": "merchant_power_equity_proxy",
        "label": "NRG/CEG merchant and baseload power basket",
        "venue": "IBKR/Yahoo/Alpaca public quote",
        "role": "liquid public power-beneficiary proxy",
        "status": "proxy",
    },
    {
        "id": "power_curve_prompt_term_proxy",
        "label": "Prompt vs trailing-term electricity curve proxy",
        "venue": "derived from physical or public proxy marks",
        "role": "calendar-spread input for front power tightness",
        "status": "derived_active",
    },
]

COMPUTE_INDEX_CATALOG = [
    {
        "id": "aws_gpu_spot",
        "label": "AWS GPU spot $/GPU-hour",
        "venue": "AWS public spot feed",
        "role": "primary live compute mark",
        "status": "active",
    },
    {
        "id": "aws_gpu_region_basis",
        "label": "AWS p5/p4d regional spot basis",
        "venue": "AWS public spot feed",
        "role": "regional compute rental basis",
        "status": "planned",
    },
    {
        "id": "gcp_a3_gpu_price",
        "label": "GCP A3 / H100 GPU rental marks",
        "venue": "GCP public price pages",
        "role": "cloud GPU rental benchmark",
        "status": "planned",
    },
    {
        "id": "azure_nc_h100_price",
        "label": "Azure NC H100 GPU rental marks",
        "venue": "Azure public price pages",
        "role": "cloud GPU rental benchmark",
        "status": "planned",
    },
    {
        "id": "silicondata_h100_rental",
        "label": "SiliconData H100 rental index",
        "venue": "SiliconData public index",
        "role": "GPU rental price benchmark",
        "status": "watchlist",
    },
    {
        "id": "cloud_gpu_provider_basket",
        "label": "Lambda/RunPod/CoreWeave style GPU rental marks",
        "venue": "public cloud GPU price pages",
        "role": "private/public compute rental basket",
        "status": "planned",
    },
    {
        "id": "ibkr_itnvd",
        "label": "NVIDIA inference/training event contract",
        "venue": "IBKR ForecastTrader",
        "role": "direct AI compute-demand leg",
        "status": "watchlist",
    },
    {
        "id": "kalshi_ai_compute_events",
        "label": "Kalshi AI/data-center/AI-company event contracts",
        "venue": "Kalshi public event feed",
        "role": "direct compute-demand forecast legs",
        "status": "watchlist",
    },
    {
        "id": "polymarket_ai_infra_events",
        "label": "Polymarket AI infrastructure outcomes",
        "venue": "Polymarket Gamma",
        "role": "direct compute-demand forecast legs after premium scoring",
        "status": "watchlist",
    },
    {
        "id": "nvda_vrt_etn",
        "label": "NVDA/VRT/ETN data-center capex basket",
        "venue": "IBKR/Yahoo/Alpaca public quote",
        "role": "liquid compute infrastructure proxy",
        "status": "proxy",
    },
    {
        "id": "btc_eth_miner_margin",
        "label": "BTC/ETH miner-margin proxy",
        "venue": "public crypto quote",
        "role": "power-sensitive mining margin proxy",
        "status": "proxy_only",
    },
    {
        "id": "hashprice_miner_margin",
        "label": "BTC hashprice / miner-margin index",
        "venue": "public crypto/mining data",
        "role": "direct miner revenue per hash proxy",
        "status": "planned",
    },
    {
        "id": "compute_curve_prompt_term_proxy",
        "label": "Spot vs trailing-term compute curve proxy",
        "venue": "derived from GPU rental marks",
        "role": "calendar-spread input for prompt compute tightness",
        "status": "derived_active",
    },
]

SPREAD_ARCHETYPE_CATALOG = [
    {
        "id": "compute_spark_spread",
        "label": "Compute spark spread",
        "formula": "GPU-hour revenue - power input cost",
        "oil_analogy": "refining crack spread",
        "status": "active",
        "required_indexes": ["electricity $/MWh", "compute $/GPU-hour"],
    },
    {
        "id": "power_cost_share",
        "label": "Power cost share of compute revenue",
        "formula": "power input cost / GPU-hour revenue",
        "oil_analogy": "margin share / cost-cover ratio",
        "status": "active",
        "required_indexes": ["electricity $/MWh", "compute $/GPU-hour"],
    },
    {
        "id": "compute_power_ratio",
        "label": "Compute / power ratio",
        "formula": "GPU-hour revenue / power input cost",
        "oil_analogy": "refinery margin ratio",
        "status": "active",
        "required_indexes": ["electricity $/MWh", "compute $/GPU-hour"],
    },
    {
        "id": "regional_compute_power_basis",
        "label": "Regional compute-power basis",
        "formula": "region A compute spark - region B compute spark",
        "oil_analogy": "WTI-Brent or regional basis",
        "status": "planned",
        "required_indexes": ["two regional electricity marks", "two regional compute rental marks"],
    },
    {
        "id": "compute_calendar_spread",
        "label": "Compute calendar spread",
        "formula": "front GPU-hour rental - prior term-proxy GPU-hour rental",
        "oil_analogy": "front-month calendar spread",
        "status": "derived_active",
        "required_indexes": ["spot GPU rental", "prior-mark term proxy"],
    },
    {
        "id": "electricity_calendar_spread",
        "label": "Electricity calendar spread",
        "formula": "front electricity $/MWh - prior term-proxy electricity $/MWh",
        "oil_analogy": "prompt power calendar spread",
        "status": "derived_active",
        "required_indexes": ["front electricity mark", "prior-mark term proxy"],
    },
    {
        "id": "compute_power_calendar_basis",
        "label": "Compute-power calendar basis",
        "formula": "compute prompt premium % - electricity prompt premium %",
        "oil_analogy": "calendar crack / curve-shape basis",
        "status": "derived_active",
        "required_indexes": ["spot GPU rental history", "front electricity history"],
    },
    {
        "id": "fuel_stack_compute_spread",
        "label": "Fuel-stack compute spread",
        "formula": "compute margin vs Henry Hub/Brent power-input basket",
        "oil_analogy": "fuel crack / input-cost hedge",
        "status": "proxy",
        "required_indexes": ["compute $/GPU-hour", "fuel/power proxy basket"],
    },
]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    var = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(var, 0.0))


def _zscore(value: float, history: list[float]) -> float:
    sd = _stdev(history)
    if sd <= 0:
        return 0.0
    return (value - _mean(history)) / sd


def _max_drawdown(cumulative: list[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in cumulative:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return worst


def _status(
    *,
    raw_observations: int,
    observations: int,
    distinct_marks: int,
    trades: int,
    total_pnl: float,
    win_rate: float,
    min_obs: int,
    min_distinct: int,
    min_trades: int,
) -> tuple[str, str, bool]:
    if raw_observations >= min_obs and observations < min_obs:
        if distinct_marks < min_distinct:
            return (
                "INSUFFICIENT_VARIANCE",
                "Live marks are too flat; repeated poll ticks were collapsed before replay.",
                False,
            )
        return (
            "INSUFFICIENT_MARK_CHANGES",
            f"Need at least {min_obs} mark changes after collapsing repeated poll ticks.",
            False,
        )
    if observations < min_obs:
        return (
            "INSUFFICIENT_HISTORY",
            f"Need at least {min_obs} mark-change observations before promoting this spread family.",
            False,
        )
    if distinct_marks < min_distinct:
        return (
            "INSUFFICIENT_VARIANCE",
            "Live marks are too flat; this can create misleading z-scores and zero-day PnL rows.",
            False,
        )
    if trades < min_trades:
        return (
            "OBSERVE",
            f"Only {trades} walk-forward trades cleared the z gate; keep scouting.",
            False,
        )
    if total_pnl > 0 and win_rate >= 0.55:
        return (
            "PROMOTABLE",
            "Walk-forward replay is positive after counting every z-gated entry.",
            True,
        )
    return (
        "FAILED_REPLAY",
        "Walk-forward replay is not profitable enough for a user-facing buy signal.",
        False,
    )


def _series(rows: Iterable[dict[str, Any]], family: SpreadFamily) -> list[float]:
    row_list = list(rows)
    if family.series_fn is not None:
        return [value for value in family.series_fn(row_list) if math.isfinite(value)]
    values: list[float] = []
    for row in row_list:
        inputs = _row_inputs(row)
        value = family.value_fn(inputs)
        if math.isfinite(value):
            values.append(value)
    return values


def _collapse_repeated_marks(values: list[float]) -> list[float]:
    compact: list[float] = []
    for value in values:
        if not compact or abs(value - compact[-1]) > MARK_EPSILON:
            compact.append(value)
    return compact


def replay_family(
    rows: list[dict[str, Any]],
    family: SpreadFamily,
    *,
    strategy: str = STRATEGY_MEAN_REVERSION,
    window: int = DEFAULT_WINDOW,
    horizon_steps: int = DEFAULT_HORIZON_STEPS,
    threshold_z: float = DEFAULT_THRESHOLD_Z,
    min_obs: int = DEFAULT_MIN_OBS,
    min_distinct: int = DEFAULT_MIN_DISTINCT,
    min_trades: int = DEFAULT_MIN_TRADES,
) -> dict[str, Any]:
    raw_values = _series(rows, family)
    values = _collapse_repeated_marks(raw_values)
    raw_observations = len(raw_values)
    observations = len(values)
    latest = values[-1] if values else 0.0
    latest_history = values[-window - 1:-1] if len(values) > 1 else []
    latest_z = _zscore(latest, latest_history) if latest_history else 0.0
    distinct_marks = len({round(value, 8) for value in values})
    trades: list[dict[str, Any]] = []
    cumulative: list[float] = []
    running = 0.0
    max_i = max(0, len(values) - horizon_steps)
    for i in range(window, max_i):
        hist = values[i - window:i]
        z = _zscore(values[i], hist)
        if abs(z) < threshold_z:
            continue
        if strategy == STRATEGY_MOMENTUM:
            position = 1.0 if z > 0 else -1.0
        else:
            position = -1.0 if z > 0 else 1.0
        pnl = position * (values[i + horizon_steps] - values[i])
        running += pnl
        cumulative.append(running)
        trades.append({
            "entry_index": i,
            "exit_index": i + horizon_steps,
            "z": round(z, 4),
            "position": "short" if position < 0 else "long",
            "entry": values[i],
            "exit": values[i + horizon_steps],
            "pnl_per_unit": pnl,
        })
    wins = sum(1 for trade in trades if trade["pnl_per_unit"] > 0)
    total_pnl = sum(trade["pnl_per_unit"] for trade in trades)
    win_rate = wins / len(trades) if trades else 0.0
    status, reason, promotable = _status(
        raw_observations=raw_observations,
        observations=observations,
        distinct_marks=distinct_marks,
        trades=len(trades),
        total_pnl=total_pnl,
        win_rate=win_rate,
        min_obs=min_obs,
        min_distinct=min_distinct,
        min_trades=min_trades,
    )
    return {
        "family_id": family.family_id,
        "archetype_id": family.archetype_id,
        "strategy_id": strategy,
        "strategy_label": "Trend-following" if strategy == STRATEGY_MOMENTUM else "Mean-reversion",
        "label": family.label,
        "formula": family.formula,
        "unit": family.unit,
        "expensive_side": family.expensive_side,
        "trade_rule": (
            "Trend-follow: long when z is high, short when z is low."
            if strategy == STRATEGY_MOMENTUM
            else family.trade_rule
        ),
        "latest_value": round(latest, 8),
        "latest_z": round(latest_z, 4),
        "raw_observations": raw_observations,
        "observations": observations,
        "collapsed_repeated_marks": max(0, raw_observations - observations),
        "distinct_marks": distinct_marks,
        "tested_trades": len(trades),
        "win_rate": round(win_rate * 100.0, 2),
        "total_pnl_per_unit": round(total_pnl, 8),
        "avg_pnl_per_unit": round(total_pnl / len(trades), 8) if trades else 0.0,
        "max_drawdown_per_unit": round(_max_drawdown(cumulative), 8),
        "status": status,
        "status_reason": reason,
        "is_promotable": promotable,
        "recent_trades": [
            {
                **trade,
                "entry": round(trade["entry"], 8),
                "exit": round(trade["exit"], 8),
                "pnl_per_unit": round(trade["pnl_per_unit"], 8),
            }
            for trade in trades[-5:]
        ],
    }


def _family_sort_key(item: dict[str, Any]) -> tuple[int, float, float, str]:
    return (
        0 if item.get("is_promotable") else 1,
        -abs(float(item.get("latest_z") or 0.0)),
        -float(item.get("total_pnl_per_unit") or 0.0),
        str(item.get("family_id") or ""),
    )


def _archetype_scoreboard(families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for archetype in SPREAD_ARCHETYPE_CATALOG:
        matches = [family for family in families if family.get("archetype_id") == archetype["id"]]
        if matches:
            best = sorted(matches, key=_family_sort_key)[0]
            rows.append({
                "archetype_id": archetype["id"],
                "label": archetype["label"],
                "formula": archetype["formula"],
                "oil_analogy": archetype["oil_analogy"],
                "catalog_status": archetype["status"],
                "required_indexes": archetype.get("required_indexes", []),
                "replay_status": best.get("status", "UNKNOWN"),
                "status_reason": best.get("status_reason", ""),
                "is_promotable": bool(best.get("is_promotable")),
                "best_family_id": best.get("family_id", ""),
                "best_family_label": best.get("label", ""),
                "strategy_id": best.get("strategy_id", ""),
                "strategy_label": best.get("strategy_label", ""),
                "latest_z": best.get("latest_z", 0),
                "tested_trades": best.get("tested_trades", 0),
                "win_rate": best.get("win_rate", 0),
                "total_pnl_per_unit": best.get("total_pnl_per_unit", 0),
                "evidence_level": "replayed",
            })
            continue
        rows.append({
            "archetype_id": archetype["id"],
            "label": archetype["label"],
            "formula": archetype["formula"],
            "oil_analogy": archetype["oil_analogy"],
            "catalog_status": archetype["status"],
            "required_indexes": archetype.get("required_indexes", []),
            "replay_status": "NEEDS_INDEX_HISTORY" if archetype["status"] == "planned" else "NO_REPLAY",
            "status_reason": "Not yet replayed because the required index history is not available in the current feed set.",
            "is_promotable": False,
            "best_family_id": "",
            "best_family_label": "",
            "strategy_id": "",
            "strategy_label": "",
            "latest_z": 0,
            "tested_trades": 0,
            "win_rate": 0,
            "total_pnl_per_unit": 0,
            "evidence_level": "planned",
        })
    rows.sort(key=lambda row: (
        0 if row["is_promotable"] else 1,
        0 if row["evidence_level"] == "replayed" else 1,
        -abs(float(row.get("latest_z") or 0.0)),
        row["archetype_id"],
    ))
    return rows


def summarize(
    rows: list[dict[str, Any]],
    *,
    strategy_modes: tuple[str, ...] = DEFAULT_STRATEGY_MODES,
    window: int = DEFAULT_WINDOW,
    horizon_steps: int = DEFAULT_HORIZON_STEPS,
    threshold_z: float = DEFAULT_THRESHOLD_Z,
    min_obs: int = DEFAULT_MIN_OBS,
    min_distinct: int = DEFAULT_MIN_DISTINCT,
    min_trades: int = DEFAULT_MIN_TRADES,
) -> dict[str, Any]:
    families = []
    for strategy in strategy_modes or DEFAULT_STRATEGY_MODES:
        for family in SPREAD_FAMILIES:
            families.append(
                replay_family(
                    rows,
                    family,
                    strategy=strategy,
                    window=window,
                    horizon_steps=horizon_steps,
                    threshold_z=threshold_z,
                    min_obs=min_obs,
                    min_distinct=min_distinct,
                    min_trades=min_trades,
                )
            )
    families.sort(
        key=_family_sort_key
    )
    primary = families[0] if families else None
    archetype_scoreboard = _archetype_scoreboard(families)
    return {
        "version": "spread_family_replay_v1",
        "policy": "walk_forward_mean_reversion_no_lookahead",
        "window": window,
        "horizon_steps": horizon_steps,
        "threshold_z": threshold_z,
        "strategy_modes": list(strategy_modes or DEFAULT_STRATEGY_MODES),
        "entry_gate_pass": any(item["is_promotable"] for item in families),
        "primary_family": primary,
        "families": families,
        "archetype_scoreboard": archetype_scoreboard,
        "index_catalog": {
            "electricity": ELECTRICITY_INDEX_CATALOG,
            "compute": COMPUTE_INDEX_CATALOG,
            "spread_archetypes": SPREAD_ARCHETYPE_CATALOG,
        },
        "caveat": (
            "This validates spread-family behaviour from recorded marks only. "
            "Proxy hedge PnL must still be reconciled from frozen leg entry prices."
        ),
    }
