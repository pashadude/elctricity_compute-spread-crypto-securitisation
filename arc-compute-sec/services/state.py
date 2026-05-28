"""Read-only, sanitized backend state for API, worker, and Telegram.

This module intentionally reads only public runtime artifacts. It never exposes
`logs/identity.tsv`, wallet IDs, entity secrets, or `.env` values.
"""
from __future__ import annotations

import csv
import functools
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from services.env import load_project_env
from agent.synthetic_instrument import propose_synthetic_instrument
from agent import spread_family_backtest
from agent import proxy_basket_backtest
from adapters.yahoo_finance import fetch_chart_quote, fetch_chart_history
from contracts.arc_addresses import EXPLORER
from feeds import cache
from templates.energy.classifier import classify_energy

load_project_env()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_FRONTEND_DIR = REPO_ROOT / "frontend"
KNOWN_PUBLIC_SURFACES = {"polymarket", "ibkr_prediction", "ibkr", "crypto", "kalshi"}
DEFAULT_IBKR_DIRECT_EVENT_SYMBOLS = ("RETXC", "ITNVD", "CRUDB", "NGP")
DEFAULT_POLYMARKET_DIRECT_EVENT_SLUGS = (
    "ai-data-center-moratorium-passed-before-2027",
    "ai-bubble-burst-by",
)
DEFAULT_KALSHI_DIRECT_EVENT_TERMS = (
    "ai",
    "artificial intelligence",
    "openai",
    "anthropic",
    "nvidia",
    "gpu",
    "llm",
    "agi",
    "data center",
    "compute",
)
DEFAULT_PUBLIC_HEDGE_SYMBOLS = ("NVDA", "VRT", "ETN", "CEG", "NRG", "BTC-USD", "ETH-USD")
DEFAULT_PUBLIC_HEDGE_PRICE_SOURCES = ("yahoo",)
DEFAULT_IBKR_FORECAST_PROXY_PRICE_SOURCES = ("ibkr", "yahoo")
DEFAULT_PROXY_BASKET_HISTORY_RANGE = "6mo"
DEFAULT_PROXY_BASKET_HISTORY_INTERVAL = "1d"
IBKR_FORECAST_SYMBOL_META: dict[str, dict[str, str]] = {
    "RETXC": {
        "title": "Texas Commercial Electricity Generation Sales Revenue",
        "description": "IBKR ForecastTrader electricity revenue contract used as an energy/grid-stress leg.",
        "pair_role": "energy/grid-stress leg",
        "direction": "long",
    },
    "ITNVD": {
        "title": "NVIDIA Inference vs. Training Revenue",
        "description": "IBKR ForecastTrader AI infrastructure contract used as the compute-demand leg.",
        "pair_role": "AI compute-demand leg",
        "direction": "short",
    },
    "CRUDB": {
        "title": "Brent Crude Oil Price",
        "description": "IBKR ForecastTrader crude contract used as an energy input-cost leg.",
        "pair_role": "energy input-cost leg",
        "direction": "long",
    },
    "NGP": {
        "title": "US Natural Gas Production",
        "description": "IBKR ForecastTrader natural-gas contract used as a power-stack supply leg.",
        "pair_role": "power fuel-supply leg",
        "direction": "long",
    },
    "FF": {
        "title": "US Fed Funds Target Rate",
        "description": "IBKR ForecastTrader macro-rate contract. This is context, not a direct compute/energy leg.",
        "pair_role": "macro context",
        "direction": "watch",
        "leg_role": "macro_context_forecast",
    },
}
IBKR_FORECAST_PROXY_META: dict[str, dict[str, str]] = {
    "RETXC": {
        "symbol": "NRG",
        "title": "NRG Energy",
        "role": "merchant power external proxy",
    },
    "ITNVD": {
        "symbol": "NVDA",
        "title": "NVIDIA",
        "role": "AI compute-demand external proxy",
    },
    "CRUDB": {
        "symbol": "BZ=F",
        "title": "Brent crude futures",
        "role": "energy input-cost external proxy",
    },
    "NGP": {
        "symbol": "NG=F",
        "title": "Henry Hub natural gas futures",
        "role": "power-stack fuel external proxy",
    },
    "FF": {
        "symbol": "ZQ=F",
        "title": "30-day Fed Funds futures",
        "role": "macro-rate external proxy",
    },
}
POLYMARKET_WATCHLIST_META: dict[str, dict[str, str]] = {
    "ai-data-center-moratorium-passed-before-2027": {
        "title": "AI data center moratorium passed before 2027?",
        "description": (
            "Polymarket event on whether US AI data-center construction or expansion "
            "is blocked by a qualifying moratorium before 2027. Used as a grid-stress "
            "and power-siting policy leg."
        ),
        "end_date": "2026-12-31T00:00:00Z",
        "pair_role": "energy/grid-stress leg",
        "direction": "long",
    },
    "ai-bubble-burst-by": {
        "title": "AI bubble burst by...?",
        "description": (
            "Polymarket event on AI-industry downturn conditions, including NVIDIA, "
            "H100 rental prices, and major AI hardware suppliers. Used as a "
            "compute-demand stress leg."
        ),
        "end_date": "2026-12-31T00:00:00Z",
        "pair_role": "AI compute-demand leg",
        "direction": "short",
    },
}
PUBLIC_HEDGE_META: dict[str, dict[str, str]] = {
    "NVDA": {
        "title": "NVIDIA",
        "role": "AI compute-demand equity proxy",
        "direction": "long_compute_short_power",
        "description": "Public equity proxy for GPU demand and AI infrastructure capex.",
    },
    "VRT": {
        "title": "Vertiv",
        "role": "data-center power/cooling infrastructure proxy",
        "direction": "long_compute_load_growth",
        "description": "Public equity proxy for data-center power, cooling, and electrical infrastructure demand.",
    },
    "ETN": {
        "title": "Eaton",
        "role": "grid/electrification equipment proxy",
        "direction": "long_grid_upgrade_demand",
        "description": "Public equity proxy for electrification and grid equipment demand.",
    },
    "CEG": {
        "title": "Constellation Energy",
        "role": "nuclear baseload power proxy",
        "direction": "long_clean_baseload_power",
        "description": "Public equity proxy for nuclear-heavy baseload power exposed to data-center procurement.",
    },
    "NRG": {
        "title": "NRG Energy",
        "role": "merchant power proxy",
        "direction": "long_power_price_exposure",
        "description": "Public equity proxy for merchant power exposure and retail load sensitivity.",
    },
    "BTC-USD": {
        "title": "Bitcoin",
        "role": "miner-margin proxy",
        "direction": "short_when_power_expensive",
        "description": "Liquid proxy for proof-of-work miner margin sensitivity to electricity costs.",
    },
    "ETH-USD": {
        "title": "Ether",
        "role": "crypto beta proxy",
        "direction": "watch",
        "description": "Liquid crypto proxy retained for beta context; not a direct power claim.",
    },
}

SENSITIVE_FIELD_MARKERS = (
    "wallet",
    "secret",
    "entity",
    "api_key",
    "apikey",
    "token",
    "user_id",
    "private",
    "mnemonic",
    "seed",
)


def log_dir(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("ARC_LOG_DIR") or os.environ.get("LOG_DIR") or DEFAULT_LOG_DIR)


def frontend_dir(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("FRONTEND_DIR") or DEFAULT_FRONTEND_DIR)


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _is_sensitive_key(key: str) -> bool:
    low = key.lower()
    return any(marker in low for marker in SENSITIVE_FIELD_MARKERS)


def _coerce_value(value: str) -> Any:
    if value == "":
        return ""
    text = value.strip()
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return value


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_value(inner)
            for key, inner in value.items()
            if key is not None and not _is_sensitive_key(str(key))
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _coerce_value(value)
    return value


def sanitize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key is None or _is_sensitive_key(str(key)):
            continue
        out[str(key)] = _sanitize_value(value)
    tx_hash = out.get("tx_hash")
    if isinstance(tx_hash, str) and tx_hash.startswith("0x"):
        out["arcscan_url"] = f"{EXPLORER}/tx/{tx_hash}"
    return out


def read_tsv(name: str, *, limit: int | None = None, logs: Path | str | None = None) -> list[dict[str, Any]]:
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"invalid log name: {name!r}")
    if name == "identity.tsv":
        raise ValueError("identity.tsv is private runtime state and is not API-readable")
    path = log_dir(logs) / name
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as fh:
        rows = [sanitize_row(row) for row in csv.DictReader(fh, delimiter="\t")]
    if limit is None:
        return rows
    return rows[-limit:]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                text = line.strip()
                if not text:
                    continue
                try:
                    decoded = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(decoded, dict):
                    rows.append(sanitize_row(decoded))
    except OSError:
        return []
    if limit is None:
        return rows
    return rows[-limit:]


def latest_row(name: str, *, logs: Path | str | None = None) -> dict[str, Any] | None:
    rows = read_tsv(name, limit=1, logs=logs)
    return rows[-1] if rows else None


def _latest_first(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(reversed(rows))


def _maybe_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return decoded if isinstance(decoded, list) else []
    return []


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:
        return None
    return out


def _coerce_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= price <= 1.0:
        return price
    return None


def _event_yes_prices(event: dict[str, Any]) -> list[float]:
    prices: list[float] = []
    for raw in event.get("markets") or []:
        if not isinstance(raw, dict):
            continue
        price = None
        for key in ("outcomePrice", "lastPrice", "price", "bestBid", "lastTradePrice"):
            price = _coerce_price(raw.get(key))
            if price is not None:
                break
        if price is None:
            outcome_prices = _maybe_json_list(raw.get("outcomePrices"))
            outcomes = _maybe_json_list(raw.get("outcomes"))
            yes_idx = 0
            for idx, outcome in enumerate(outcomes):
                if str(outcome).strip().lower() == "yes":
                    yes_idx = idx
                    break
            if yes_idx < len(outcome_prices):
                price = _coerce_price(outcome_prices[yes_idx])
        if price is not None:
            prices.append(price)
    return prices


def _polymarket_event_summary(event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event.get("id") or "")
    slug = str(event.get("slug") or "")
    return {
        "id": event_id,
        "slug": slug,
        "title": str(event.get("title") or event.get("question") or slug or event_id),
        "description": str(event.get("description") or ""),
        "start_date": str(event.get("startDate") or event.get("start_date") or ""),
        "end_date": str(event.get("endDate") or event.get("end_date") or ""),
        "active": bool(event.get("active", False)),
        "closed": bool(event.get("closed", False)),
        "volume": event.get("volume") or event.get("volumeNum") or "",
        "liquidity": event.get("liquidity") or event.get("liquidityNum") or "",
        "yes_prices": _event_yes_prices(event),
    }


@functools.lru_cache(maxsize=256)
def _fetch_polymarket_event(key: str) -> dict[str, Any] | None:
    key = str(key or "").strip()
    if not key or key.startswith("mock"):
        return None
    if key.isdigit():
        path = key
    else:
        path = f"slug/{urllib.parse.quote(key, safe='')}"
    url = f"https://gamma-api.polymarket.com/events/{path}"
    req = urllib.request.Request(
        url,
        headers={"accept": "application/json", "user-agent": "arc-compute-sec/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            event = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    if isinstance(event, dict):
        return _polymarket_event_summary(event)
    return None


def _polymarket_cache_event_index(*, logs: Path | str | None = None) -> dict[str, dict[str, Any]]:
    path = log_dir(logs) / "_feed_cache.sqlite"
    if not path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(path))
        rows = conn.execute(
            "SELECT value FROM cache WHERE ns = ? ORDER BY expires_at DESC",
            ("polymarket_events",),
        ).fetchall()
        conn.close()
    except sqlite3.DatabaseError:
        return {}
    index: dict[str, dict[str, Any]] = {}
    for (raw_value,) in rows:
        try:
            events = json.loads(raw_value)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            summary = _polymarket_event_summary(event)
            event_id = summary["id"]
            slug = summary["slug"]
            for key in (event_id, slug, f"polymarket:{event_id}" if event_id else ""):
                if key and key not in index:
                    index[key] = summary
    return index


def _instrument_lookup_key(row: dict[str, Any]) -> str:
    instrument = str(row.get("instrument") or "")
    if instrument.startswith("polymarket:"):
        return instrument.split(":", 2)[1]
    if instrument.startswith("kalshi:"):
        return instrument.split(":", 2)[1]
    return instrument


def _fallback_leg_role(surface: str) -> str:
    return {
        "polymarket": "direct_prediction_event",
        "ibkr_prediction": "direct_prediction_event",
        "kalshi": "direct_prediction_event",
        "crypto": "miner_margin_proxy",
        "ibkr": "liquid_equity_proxy",
    }.get(surface, "expression_leg")


def _leg_connection(surface: str, role: str) -> str:
    if surface in {"polymarket", "ibkr_prediction", "kalshi"} or role == "direct_prediction_event":
        return (
            "Direct event leg: the package pairs energy/grid-stress outcomes "
            "against AI compute-demand outcomes, so this event is one side of "
            "the judged spread expression."
        )
    if role == "macro_context_forecast":
        return (
            "Context forecast only: macro event contracts can condition sizing "
            "or risk review, but they are not the securitized compute/energy leg."
        )
    if surface == "crypto" or role == "miner_margin_proxy":
        return (
            "Proxy leg only: BTC/ETH are used for miner-margin stress because "
            "mining revenue is crypto-linked while electricity is the main "
            "variable cost."
        )
    if surface == "ibkr" or role == "liquid_equity_proxy":
        return (
            "Proxy leg only: the equity leg reflects compute/energy margin "
            "sensitivity and is not the direct securitized outcome."
        )
    return "Expression leg in the canonical compute/energy spread package."


def _is_mock_leg(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "").lower()
        for key in ("instrument", "leg_title", "leg_slug", "display_label")
    )
    return "mock" in text


def _is_legacy_artifact(row: dict[str, Any]) -> bool:
    surface = str(row.get("surface") or "")
    display = str(row.get("display_label") or "")
    return surface not in KNOWN_PUBLIC_SURFACES or display == "unknown leg"


def _is_thesis_mismatch(row: dict[str, Any]) -> bool:
    surface = str(row.get("surface") or "")
    role = str(row.get("leg_role") or "")
    if row.get("is_mock") or role != "direct_prediction_event":
        return False
    if surface not in {"polymarket", "ibkr_prediction", "kalshi"}:
        return False
    title = str(row.get("leg_title") or row.get("display_label") or row.get("instrument") or "")
    description = str(row.get("leg_description") or "")
    return classify_energy(title, description) is None


def _enrich_leg_rows(rows: list[dict[str, Any]], *, logs: Path | str | None = None) -> list[dict[str, Any]]:
    event_index = _polymarket_cache_event_index(logs=logs)
    for row in rows:
        surface = str(row.get("surface") or "")
        event = None
        if surface == "polymarket":
            for key in (
                str(row.get("leg_slug") or ""),
                _instrument_lookup_key(row),
                str(row.get("instrument") or ""),
            ):
                event = event_index.get(key)
                if event:
                    break
            if not event:
                should_fetch = not row.get("inventory") or bool_env("POLYMARKET_DIRECT_EVENT_FETCH", False)
                if should_fetch:
                    event = _fetch_polymarket_event(_instrument_lookup_key(row))
        if event:
            row["leg_title"] = row.get("leg_title") or event.get("title", "")
            row["leg_slug"] = row.get("leg_slug") or event.get("slug", "")
            row["leg_description"] = row.get("leg_description") or event.get("description", "")
            row["leg_end_date"] = row.get("leg_end_date") or event.get("end_date", "")
        role = str(row.get("leg_role") or _fallback_leg_role(surface))
        row["leg_role"] = role
        row["leg_connection"] = _leg_connection(surface, role)
        row["display_label"] = row.get("leg_title") or row.get("instrument") or "unknown leg"
        row["is_mock"] = _is_mock_leg(row)
        row["is_legacy_artifact"] = _is_legacy_artifact(row)
        row["is_thesis_mismatch"] = _is_thesis_mismatch(row)
    return rows


def spread_state(*, logs: Path | str | None = None, limit: int = 120) -> dict[str, Any]:
    rows = read_tsv("spread_history.tsv", limit=limit, logs=logs)
    latest = dict(rows[-1]) if rows else None
    history: list[float] = []
    for row in rows:
        try:
            history.append(float(row.get("S_t", 0.0)))
        except (TypeError, ValueError):
            continue
    source_rows = read_jsonl(log_dir(logs) / "spread_mark_sources.jsonl", limit=1)
    source = source_rows[-1] if source_rows else {}
    if latest and source:
        latest.update({
            "electricity_source": source.get("electricity_source", ""),
            "electricity_source_status": source.get("electricity_source_status", ""),
            "electricity_base_per_mwh": source.get("electricity_base_per_mwh", ""),
            "electricity_proxy_weighted_return_pct": source.get("electricity_proxy_weighted_return_pct", ""),
            "electricity_proxy_symbols": source.get("electricity_proxy_symbols", []),
            "electricity_proxy_used_quotes": source.get("electricity_proxy_used_quotes", ""),
            "electricity_proxy_quote_sources": source.get("electricity_proxy_quote_sources", []),
            "electricity_proxy_formula": source.get("electricity_proxy_formula", ""),
            "eia_period": source.get("eia_period", ""),
            "compute_source": source.get("compute_source", ""),
            "compute_instance": source.get("compute_instance", ""),
            "compute_region": source.get("compute_region", ""),
            "power_cost_per_gpu_hr": source.get("power_cost_per_gpu_hr", latest.get("power_cost_per_gpu_hr", "")),
            "power_cost_share": source.get("power_cost_share", latest.get("power_cost_share", "")),
            "power_cost_share_pct": source.get("power_cost_share_pct", latest.get("power_cost_share_pct", "")),
        })
    if latest:
        compute = _as_float(latest.get("compute_per_gpu_hr"))
        elec = _as_float(latest.get("electricity_per_mwh"))
        k = _as_float(latest.get("k"))
        kwh = _as_float(latest.get("kwh_per_gpu_hr") or latest.get("kWh_per_gpu_hr"))
        if compute and elec and k and kwh and not latest.get("power_cost_per_gpu_hr"):
            power_cost = k * (elec / 1000.0) * kwh
            latest["power_cost_per_gpu_hr"] = round(power_cost, 6)
            latest["power_cost_share"] = round(power_cost / compute, 6) if compute > 0 else 0.0
            latest["power_cost_share_pct"] = round((power_cost / compute) * 100.0, 4) if compute > 0 else 0.0
        elif latest.get("power_cost_share") and not latest.get("power_cost_share_pct"):
            latest["power_cost_share_pct"] = round(_as_float(latest.get("power_cost_share")) * 100.0, 4)
    return {"latest": latest, "history": history, "mark_source": source}


def spread_family_state(*, logs: Path | str | None = None, limit: int = 720) -> dict[str, Any]:
    rows = read_tsv("spread_history.tsv", limit=limit, logs=logs)
    strategies = (
        spread_family_backtest.STRATEGY_MEAN_REVERSION,
        spread_family_backtest.STRATEGY_MOMENTUM,
    )
    recorded = spread_family_backtest.summarize(rows, strategy_modes=strategies)
    proxy_rows = read_tsv("spread_proxy_history.tsv", limit=limit, logs=logs)
    proxy = spread_family_backtest.summarize(proxy_rows, strategy_modes=strategies) if proxy_rows else None
    recorded_primary = recorded.get("primary_family") or {}
    proxy_primary = (proxy or {}).get("primary_family") or {}
    proxy_has_stronger_sample = (
        proxy
        and proxy.get("entry_gate_pass")
        and (
            not recorded.get("entry_gate_pass")
            or int(_as_float(proxy_primary.get("tested_trades")) or 0)
            > int(_as_float(recorded_primary.get("tested_trades")) or 0)
        )
    )
    chosen = proxy if proxy_has_stronger_sample else recorded
    source = "proxy_history" if chosen is proxy else "recorded_runtime_marks"
    out = dict(chosen)
    out["primary_source"] = source
    out["recorded_history_replay"] = recorded
    if proxy is not None:
        out["proxy_history_replay"] = proxy
    out["source_status"] = (
        "using public proxy history because recorded runtime marks are too flat"
        if source == "proxy_history"
        else "using recorded runtime marks"
    )
    return out


def _proxy_basket_report_path(*, logs: Path | str | None = None) -> Path:
    return log_dir(logs) / "proxy_basket_backtest.json"


def _fetch_yahoo_history_cached(
    symbol: str,
    *,
    range_name: str = DEFAULT_PROXY_BASKET_HISTORY_RANGE,
    interval: str = DEFAULT_PROXY_BASKET_HISTORY_INTERVAL,
) -> dict[str, Any] | None:
    clean = str(symbol or "").strip().upper()
    if not clean:
        return None
    key = f"{range_name}|{interval}|{clean}"
    cached = cache.get("yahoo_history", key)
    if isinstance(cached, dict):
        return cached
    timeout = _num_env("PROXY_BASKET_HISTORY_TIMEOUT", 2.5)
    try:
        history = fetch_chart_history(clean, range=range_name, interval=interval, timeout=timeout)
    except Exception as exc:
        history = {"symbol": clean, "points": [], "source": "yahoo_finance_chart", "error": exc.__class__.__name__}
    if isinstance(history, dict):
        cache.put("yahoo_history", key, history, ttl_seconds=int(_num_env("PROXY_BASKET_HISTORY_CACHE_SECONDS", 21_600)))
        return history
    return None


def _num_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def proxy_basket_state(*, logs: Path | str | None = None) -> dict[str, Any]:
    saved = read_json(_proxy_basket_report_path(logs=logs), default={})
    if isinstance(saved, dict) and saved.get("version") == "proxy_basket_replay_v1":
        return saved
    if not bool_env("PROXY_BASKET_BACKTEST_FETCH", False):
        out = proxy_basket_backtest.summarize({})
        out["fetch_enabled"] = False
        out["status_reason"] = "Set PROXY_BASKET_BACKTEST_FETCH=1 or run npm run proxy:backtest to load Yahoo close-history replay."
        return out
    range_name = os.environ.get("PROXY_BASKET_HISTORY_RANGE", DEFAULT_PROXY_BASKET_HISTORY_RANGE)
    interval = os.environ.get("PROXY_BASKET_HISTORY_INTERVAL", DEFAULT_PROXY_BASKET_HISTORY_INTERVAL)
    histories = {
        symbol: history
        for symbol in proxy_basket_backtest.required_symbols()
        if (history := _fetch_yahoo_history_cached(symbol, range_name=range_name, interval=interval))
    }
    out = proxy_basket_backtest.summarize(histories)
    out["fetch_enabled"] = True
    out["history_range"] = range_name
    out["history_interval"] = interval
    return out


def _proxy_basket_entry_gate(basket: dict[str, Any], fallback: Any = None) -> bool | None:
    if not basket:
        return bool(fallback) if fallback is not None else None
    if "is_promotable" in basket:
        return bool(basket.get("is_promotable"))
    status = str(basket.get("status") or "")
    if status:
        return status == "PROMOTABLE"
    return bool(fallback) if fallback is not None else None


def select_proxy_basket_for_direction(proxy_baskets: dict[str, Any], direction: str) -> tuple[dict[str, Any], bool | None]:
    validation = proxy_baskets if isinstance(proxy_baskets, dict) else {}
    primary = validation.get("primary_basket") if isinstance(validation.get("primary_basket"), dict) else {}
    baskets = [basket for basket in validation.get("baskets") or [] if isinstance(basket, dict)]
    if primary and all(basket.get("basket_id") != primary.get("basket_id") for basket in baskets):
        baskets.append(primary)

    clean_direction = str(direction or "").strip()
    if clean_direction and clean_direction != "no_signal":
        for basket in baskets:
            if str(basket.get("direction") or "").strip() == clean_direction:
                return basket, _proxy_basket_entry_gate(basket)
        if primary and not str(primary.get("direction") or "").strip():
            return primary, _proxy_basket_entry_gate(primary, validation.get("entry_gate_pass"))
        if baskets or primary:
            return {
                "basket_id": "no_direction_matched_proxy_basket",
                "direction": clean_direction,
                "label": "No direction-matched proxy basket",
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
    return primary, _proxy_basket_entry_gate(primary, validation.get("entry_gate_pass"))


def signal_state(*, logs: Path | str | None = None, limit: int = 25) -> dict[str, Any]:
    rows = read_tsv("arb_signals.tsv", limit=limit, logs=logs)
    return {"latest": rows[-1] if rows else None, "recent": _latest_first(rows)}


def verdict_state(*, logs: Path | str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    rows = read_tsv("judgements.tsv", limit=limit, logs=logs)
    return _latest_first(_enrich_leg_rows(rows, logs=logs))


def position_state(*, logs: Path | str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    rows = read_tsv("positions.tsv", limit=limit, logs=logs)
    for row in rows:
        stage = str(row.get("stage", ""))
        if "status" not in row:
            row["status"] = "completed" if stage == "settled" else stage or "unknown"
    return _latest_first(_enrich_leg_rows(rows, logs=logs))


def _env_csv(name: str, default: tuple[str, ...] = ()) -> list[str]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return list(default)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _pricing_status_label(status: Any) -> str:
    low = str(status or "").strip().lower()
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
    if low == "price_unavailable":
        return "Price unavailable"
    if low == "closed_watchlist":
        return "Closed"
    return str(status or "Needs review").replace("_", " ")


def _fetch_ibkr_public_quote(symbol: str) -> dict[str, Any] | None:
    clean = str(symbol or "").strip().upper()
    if not clean:
        return None
    try:
        from adapters.ibkr import fetch_public_quote

        quote = fetch_public_quote(clean)
    except Exception as exc:
        return {
            "symbol": clean,
            "price": None,
            "source": "ibkr_tws",
            "error": exc.__class__.__name__,
        }
    if not isinstance(quote, dict) or quote.get("price") is None:
        return None
    return quote


def _fetch_alpaca_public_quote(symbol: str) -> dict[str, Any] | None:
    clean = str(symbol or "").strip().upper()
    if not clean or "-" in clean:
        return None
    key = os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET")
    if not key or not secret:
        return None
    url = f"https://data.alpaca.markets/v2/stocks/{urllib.parse.quote(clean, safe='')}/trades/latest"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "User-Agent": "arc-compute-sec/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        trade = data.get("trade") if isinstance(data, dict) else {}
        price = trade.get("p") if isinstance(trade, dict) else None
        if price is None:
            return None
        return {
            "symbol": clean,
            "price": float(price),
            "currency": "USD",
            "exchange": str(trade.get("x") or "alpaca"),
            "regular_market_time": str(trade.get("t") or ""),
            "source": "alpaca_market_data",
        }
    except Exception as exc:
        return {
            "symbol": clean,
            "price": None,
            "source": "alpaca_market_data",
            "error": exc.__class__.__name__,
        }


def _fetch_yahoo_public_quote(symbol: str) -> dict[str, Any] | None:
    try:
        return fetch_chart_quote(symbol)
    except Exception as exc:
        return {
            "symbol": str(symbol or "").strip().upper(),
            "price": None,
            "source": "yahoo_finance_chart",
            "error": exc.__class__.__name__,
        }


def _fetch_public_quote(symbol: str, sources: list[str] | tuple[str, ...] | None = None) -> dict[str, Any] | None:
    cache_key = str(symbol or "").strip().upper()
    if not cache_key:
        return None
    selected_sources = [
        item.lower()
        for item in (
            list(sources)
            if sources is not None
            else _env_csv("PUBLIC_HEDGE_PRICE_SOURCES", DEFAULT_PUBLIC_HEDGE_PRICE_SOURCES)
        )
    ]
    source_key = ",".join(selected_sources) or "yahoo"
    cached = cache.get("public_quote", f"{source_key}|{cache_key}")
    if isinstance(cached, dict):
        return cached
    quote: dict[str, Any] | None = None
    errors: list[str] = []
    for source in selected_sources:
        if source == "ibkr":
            quote = _fetch_ibkr_public_quote(cache_key)
        elif source == "alpaca":
            quote = _fetch_alpaca_public_quote(cache_key)
        elif source == "yahoo":
            quote = _fetch_yahoo_public_quote(cache_key)
        else:
            errors.append(f"{source}:unsupported")
            quote = None
        if isinstance(quote, dict) and quote.get("price") is not None:
            quote["source_priority"] = source_key
            if errors:
                quote["fallback_errors"] = errors[:4]
            cache.put("public_quote", f"{source_key}|{cache_key}", quote, ttl_seconds=900)
            return quote
        if isinstance(quote, dict) and quote.get("error"):
            errors.append(f"{quote.get('source')}:{quote.get('error')}")
    if quote is None:
        quote = {"symbol": cache_key, "price": None, "source": source_key}
    if errors:
        quote["fallback_errors"] = errors[:4]
    cache.put("public_quote", f"{source_key}|{cache_key}", quote, ttl_seconds=300)
    return quote


def public_hedge_state(*, logs: Path | str | None = None) -> list[dict[str, Any]]:
    """Priced public-market proxies used when direct event contracts are unpriced.

    These are not direct claims on compute or electricity. They are liquid,
    priced hedge references for the commercial compute-sale package.
    """
    now = time.time()
    rows: list[dict[str, Any]] = []
    fetch_live = bool_env("PUBLIC_HEDGE_FETCH", True)
    for symbol in _env_csv("PUBLIC_HEDGE_SYMBOLS", DEFAULT_PUBLIC_HEDGE_SYMBOLS):
        clean = symbol.strip().upper()
        if not clean:
            continue
        meta = PUBLIC_HEDGE_META.get(clean, {})
        quote = _fetch_public_quote(clean) if fetch_live else None
        price = quote.get("price") if isinstance(quote, dict) else None
        row = sanitize_row({
            "ts": now,
            "surface": "public_market",
            "instrument": clean,
            "leg_slug": clean,
            "leg_title": meta.get("title") or clean,
            "display_label": meta.get("title") or clean,
            "leg_role": "priced_public_hedge",
            "direct_pair_role": meta.get("role") or "public hedge proxy",
            "direction": meta.get("direction") or "watch",
            "label": "PRICED" if price is not None else "PRICE_MISSING",
            "pricing_status": "priced_public_market" if price is not None else "price_unavailable",
            "pricing_status_label": _pricing_status_label("priced_public_market" if price is not None else "price_unavailable"),
            "last_price": price if price is not None else "",
            "currency": quote.get("currency", "") if isinstance(quote, dict) else "",
            "exchange": quote.get("exchange", "") if isinstance(quote, dict) else "",
            "source": quote.get("source", "yahoo_finance_chart") if isinstance(quote, dict) else "yahoo_finance_chart",
            "source_priority": quote.get("source_priority", "") if isinstance(quote, dict) else "",
            "leg_description": meta.get("description") or "",
            "inventory": True,
        })
        rows.append(row)
    return rows


def _forecast_inventory_path(*, logs: Path | str | None = None) -> Path:
    return log_dir(logs) / "ibkr_forecast_inventory.json"


def _read_ibkr_forecast_inventory(*, logs: Path | str | None = None) -> dict[str, dict[str, Any]]:
    data = read_json(_forecast_inventory_path(logs=logs), default={})
    if isinstance(data, dict):
        raw_events = data.get("events") or []
    elif isinstance(data, list):
        raw_events = data
    else:
        raw_events = []
    out: dict[str, dict[str, Any]] = {}
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        symbol = str(event.get("symbol") or "").strip().upper()
        if not symbol:
            slug = str(event.get("slug") or "")
            symbol = slug.split("-", 1)[0].upper()
        if symbol and symbol not in out:
            out[symbol] = event
    return out


def _inventory_sizing(surface: str) -> str:
    if surface == "ibkr_prediction":
        env_name = "SIZING_IBKR_PREDICTION_USDC"
    elif surface == "kalshi":
        env_name = "SIZING_KALSHI_USDC"
    else:
        env_name = "SIZING_POLYMARKET_USDC"
    return str(os.environ.get(env_name, "1.0"))


def _ibkr_forecast_proxy_meta(symbol: str) -> dict[str, str]:
    clean = str(symbol or "").strip().upper()
    meta = dict(IBKR_FORECAST_PROXY_META.get(clean, {}))
    raw = os.environ.get("IBKR_FORECAST_PROXY_SYMBOLS_JSON", "").strip()
    if not raw:
        return meta
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return meta
    if not isinstance(decoded, dict):
        return meta
    override = decoded.get(clean)
    if isinstance(override, str):
        meta["symbol"] = override.strip().upper()
    elif isinstance(override, dict):
        for key in ("symbol", "title", "role"):
            if override.get(key):
                meta[key] = str(override[key])
    return meta


def _ibkr_external_proxy_quote_fields(symbol: str, pricing_status: str) -> dict[str, Any]:
    if not bool_env("IBKR_FORECAST_PROXY_QUOTE_FETCH", True):
        return {}
    if str(pricing_status or "").strip().lower() in {"priced", "priced_watchlist"}:
        return {}
    meta = _ibkr_forecast_proxy_meta(symbol)
    proxy_symbol = str(meta.get("symbol") or "").strip().upper()
    if not proxy_symbol:
        return {}
    sources = _env_csv("IBKR_FORECAST_PROXY_PRICE_SOURCES", DEFAULT_IBKR_FORECAST_PROXY_PRICE_SOURCES)
    quote = _fetch_public_quote(proxy_symbol, sources=sources)
    price = quote.get("price") if isinstance(quote, dict) else None
    base = {
        "external_proxy_symbol": proxy_symbol,
        "external_proxy_title": meta.get("title") or proxy_symbol,
        "external_proxy_role": meta.get("role") or "external proxy quote",
        "external_proxy_status": "priced_external_proxy" if price is not None else "external_proxy_price_unavailable",
        "external_proxy_status_label": "External proxy price available" if price is not None else "External proxy price unavailable",
    }
    if isinstance(quote, dict):
        base.update({
            "external_proxy_last_price": float(price) if price is not None else "",
            "external_proxy_currency": quote.get("currency", ""),
            "external_proxy_exchange": quote.get("exchange", ""),
            "external_proxy_source": quote.get("source", ""),
            "external_proxy_source_priority": quote.get("source_priority", ""),
            "external_proxy_regular_market_time": quote.get("regular_market_time", ""),
            "external_proxy_expiry": quote.get("expiry", ""),
            "external_proxy_stale": bool(quote.get("stale")),
        })
    return base


def _ibkr_inventory_rows(*, logs: Path | str | None = None) -> list[dict[str, Any]]:
    symbols = [s.upper() for s in _env_csv("IBKR_DIRECT_EVENT_SYMBOLS", DEFAULT_IBKR_DIRECT_EVENT_SYMBOLS)]
    live_events = _read_ibkr_forecast_inventory(logs=logs)
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        meta = IBKR_FORECAST_SYMBOL_META.get(symbol, {})
        event = live_events.get(symbol, {})
        title = str(event.get("title") or meta.get("title") or symbol)
        event_description = str(event.get("description") or "")
        meta_description = str(meta.get("description") or "")
        description = event_description
        if meta_description and meta_description not in description:
            description = f"{description} {meta_description}".strip()
        role = str(meta.get("leg_role") or "direct_prediction_event")
        pricing_status = str(event.get("pricing_status") or "inventory_unpriced")
        proxy_fields = _ibkr_external_proxy_quote_fields(symbol, pricing_status)
        status_label = _pricing_status_label(pricing_status)
        if proxy_fields.get("external_proxy_status") == "priced_external_proxy":
            status_label = f"{status_label}; proxy price available"
        row = {
            "ts": event.get("ts") or event.get("generated_at") or time.time(),
            "surface": "ibkr_prediction",
            "instrument": f"ibkr-prediction:{symbol}-EC",
            "direction": event.get("direction") or meta.get("direction") or "watch",
            "sizing_usdc": _inventory_sizing("ibkr_prediction"),
            "label": "WATCHLIST",
            "reason_code": pricing_status,
            "leg_title": title,
            "leg_slug": str(event.get("slug") or f"{symbol.lower()}-ec"),
            "leg_description": description,
            "leg_end_date": str(event.get("end_date") or event.get("last_trade_date") or ""),
            "leg_role": role,
            "direct_pair_role": str(meta.get("pair_role") or "direct forecast leg"),
            "pricing_status": pricing_status,
            "pricing_status_label": status_label,
            "pricing_detail": str(event.get("pricing_detail") or ""),
            "venue": str(event.get("venue") or "IBKR ForecastTrader"),
            "exchange": str(event.get("exchange") or "FORECASTX"),
            "sec_type": str(event.get("sec_type") or "EC"),
            "underlier_conid": str(event.get("underlier_conid") or event.get("yes_conid") or ""),
            "yes_conid": str(event.get("yes_conid") or event.get("underlier_conid") or ""),
            "yes_prices": event.get("yes_prices") or [],
            "inventory": True,
            "source": "ibkr_forecast_inventory",
        }
        row.update(proxy_fields)
        rows.append(row)
    return rows


def _polymarket_inventory_rows() -> list[dict[str, Any]]:
    slugs = _env_csv("POLYMARKET_DIRECT_EVENT_SLUGS", DEFAULT_POLYMARKET_DIRECT_EVENT_SLUGS)
    rows: list[dict[str, Any]] = []
    fetch_live = bool_env("POLYMARKET_DIRECT_EVENT_FETCH", True)
    for slug in slugs:
        fallback = POLYMARKET_WATCHLIST_META.get(slug, {})
        event = _fetch_polymarket_event(slug) if fetch_live else {}
        event = event or {}
        title = str(event.get("title") or fallback.get("title") or slug)
        description = str(event.get("description") or fallback.get("description") or "")
        yes_prices = event.get("yes_prices") if isinstance(event.get("yes_prices"), list) else []
        status = "priced_watchlist" if yes_prices else "metadata_watchlist"
        if event.get("closed") is True:
            status = "closed_watchlist"
        rows.append({
            "ts": time.time(),
            "surface": "polymarket",
            "instrument": f"polymarket:{event.get('id') or slug}",
            "direction": fallback.get("direction") or "watch",
            "sizing_usdc": _inventory_sizing("polymarket"),
            "label": "WATCHLIST",
            "reason_code": status,
            "leg_title": title,
            "leg_slug": str(event.get("slug") or slug),
            "leg_description": description,
            "leg_end_date": str(event.get("end_date") or fallback.get("end_date") or ""),
            "leg_role": "direct_prediction_event",
            "direct_pair_role": str(fallback.get("pair_role") or "direct prediction-event leg"),
            "pricing_status": status,
            "pricing_status_label": _pricing_status_label(status),
            "yes_prices": yes_prices,
            "volume": event.get("volume") or "",
            "liquidity": event.get("liquidity") or "",
            "inventory": True,
            "source": "polymarket_direct_watchlist",
        })
    return rows


def _fetch_kalshi_ai_events() -> list[dict[str, Any]]:
    if not bool_env("KALSHI_DIRECT_EVENT_FETCH", True):
        return []
    from adapters.kalshi import fetch_ai_events

    return fetch_ai_events(
        limit=int(os.environ.get("KALSHI_DIRECT_EVENT_LIMIT", "200")),
        max_pages=int(os.environ.get("KALSHI_DIRECT_EVENT_MAX_PAGES", "3")),
        max_events=int(os.environ.get("KALSHI_DIRECT_EVENT_MAX_EVENTS", "8")),
        terms=_env_csv("KALSHI_DIRECT_EVENT_TERMS", DEFAULT_KALSHI_DIRECT_EVENT_TERMS),
    )


def _kalshi_inventory_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in _fetch_kalshi_ai_events():
        if not isinstance(event, dict):
            continue
        yes_prices = event.get("yes_prices") if isinstance(event.get("yes_prices"), list) else []
        status = "priced_watchlist" if yes_prices else "metadata_watchlist"
        event_ticker = str(event.get("event_ticker") or event.get("id") or event.get("slug") or "")
        if not event_ticker:
            continue
        rows.append({
            "ts": time.time(),
            "surface": "kalshi",
            "instrument": f"kalshi:{event_ticker}",
            "direction": "short",
            "sizing_usdc": _inventory_sizing("kalshi"),
            "label": "WATCHLIST",
            "reason_code": status,
            "leg_title": str(event.get("title") or event_ticker),
            "leg_slug": str(event.get("slug") or event_ticker.lower()),
            "leg_description": str(event.get("description") or ""),
            "leg_end_date": str(event.get("end_date") or ""),
            "leg_role": "direct_prediction_event",
            "direct_pair_role": "AI compute-demand leg",
            "pricing_status": status,
            "pricing_status_label": _pricing_status_label(status),
            "yes_prices": yes_prices,
            "volume": event.get("volume") or "",
            "liquidity": event.get("liquidity") or "",
            "venue": "Kalshi",
            "category": str(event.get("category") or ""),
            "series_ticker": str(event.get("series_ticker") or ""),
            "market_tickers": event.get("market_tickers") or [],
            "mutually_exclusive": bool(event.get("mutually_exclusive")),
            "inventory": True,
            "source": "kalshi_direct_ai_watchlist",
        })
    return rows


def direct_inventory_state(*, logs: Path | str | None = None) -> list[dict[str, Any]]:
    """Configured real direct-event surfaces shown as watchlist inventory.

    Inventory rows explain currently monitored IBKR/Polymarket/Kalshi legs, but they
    are not candidate rows. Polymarket still needs the preserved premium gate;
    IBKR and Kalshi event contracts still need usable quote fields before either
    can reach judge.classify() or Arc.
    """
    if not bool_env("DIRECT_EVENT_INVENTORY_ENABLED", True):
        return []
    rows = _ibkr_inventory_rows(logs=logs) + _polymarket_inventory_rows() + _kalshi_inventory_rows()
    return _visible_leg_rows(_enrich_leg_rows(rows, logs=logs))


def _row_has_yes_price(row: dict[str, Any]) -> bool:
    prices = row.get("yes_prices")
    if isinstance(prices, list):
        return any(_as_float(price) is not None for price in prices)
    return False


def _row_has_public_price(row: dict[str, Any]) -> bool:
    return _as_float(row.get("last_price")) is not None


def _row_has_external_proxy_price(row: dict[str, Any]) -> bool:
    return _as_float(row.get("external_proxy_last_price")) is not None


def _status_from_counts(
    *,
    rows: int,
    priced: int,
    external_proxy: int = 0,
    empty_status: str = "NEEDS_DISCOVERY",
) -> str:
    if rows <= 0:
        return empty_status
    if priced > 0:
        return "LIVE_PRICED"
    if external_proxy > 0:
        return "PROXY_PRICED"
    return "NEEDS_PRICE"


def _venue_row(
    *,
    surface: str,
    label: str,
    role: str,
    rows: list[dict[str, Any]],
    status: str,
    gaps: list[str],
    evidence_only: bool = False,
    direct_event_surface: bool = False,
    premium_gate_required: bool = False,
) -> dict[str, Any]:
    priced = [
        row for row in rows
        if _row_has_yes_price(row) or _row_has_public_price(row)
        or str(row.get("pricing_status") or "") in {"priced_watchlist", "priced_public_market"}
    ]
    external = [row for row in rows if _row_has_external_proxy_price(row)]
    watchlist = [row for row in rows if str(row.get("label") or "") == "WATCHLIST" or row.get("inventory")]
    latest = max(rows, key=_row_ts) if rows else {}
    return {
        "surface": surface,
        "label": label,
        "role": role,
        "status": status,
        "row_count": len(rows),
        "priced_count": len(priced),
        "watchlist_count": len(watchlist),
        "external_proxy_count": len(external),
        "direct_event_surface": direct_event_surface,
        "evidence_only": evidence_only,
        "real_feed": len(rows) > 0,
        "can_drive_arc": False,
        "judge_required": True,
        "premium_gate_required": premium_gate_required,
        "latest_title": latest.get("display_label") or latest.get("leg_title") or latest.get("instrument") or "",
        "latest_slug": latest.get("leg_slug") or latest.get("instrument") or "",
        "latest_pricing_status": latest.get("pricing_status_label") or latest.get("pricing_status") or latest.get("reason_code") or "",
        "gaps": gaps,
    }


def _oracle_evidence_state(*, logs: Path | str | None = None) -> dict[str, Any]:
    receipts = read_jsonl(log_dir(logs) / "energy_llm_oracle.jsonl", limit=250)
    verdict_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    raw_articles = 0
    filtered_articles = 0
    for row in receipts:
        verdict = str(row.get("verdict") or "UNKNOWN")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        reason = str(row.get("reason_code") or "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        coverage = row.get("coverage") if isinstance(row.get("coverage"), dict) else {}
        raw_articles += int(_as_float(coverage.get("raw")) or 0)
        filtered_articles += int(_as_float(coverage.get("after_filter")) or 0)
    latest = receipts[-1] if receipts else {}
    return {
        "surface": "opoint_nebius",
        "label": "Opoint + Nebius oracle receipts",
        "role": "news-grounded evidence only",
        "status": "EVIDENCE_LOGGED" if receipts else "NO_RECEIPTS",
        "row_count": len(receipts),
        "priced_count": 0,
        "watchlist_count": 0,
        "external_proxy_count": 0,
        "direct_event_surface": False,
        "evidence_only": True,
        "real_feed": len(receipts) > 0,
        "can_drive_arc": False,
        "judge_required": True,
        "premium_gate_required": False,
        "latest_title": latest.get("event_slug") or latest.get("slug") or "",
        "latest_slug": latest.get("slug") or latest.get("event_slug") or "",
        "latest_pricing_status": latest.get("verdict") or "",
        "latest_model": latest.get("analyst_model") or "",
        "latest_reason_code": latest.get("reason_code") or "",
        "verdict_counts": verdict_counts,
        "reason_counts": reason_counts,
        "raw_articles": raw_articles,
        "filtered_articles": filtered_articles,
        "gaps": [
            "Oracle receipts are evidence only; they cannot trigger Circle or Arc.",
            "Missing or DEFER oracle output must not bypass premium scorer or judge.classify().",
        ],
    }


def venue_evidence_state(
    *,
    direct_inventory: list[dict[str, Any]],
    public_hedges: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    logs: Path | str | None = None,
) -> dict[str, Any]:
    """Explain which real surfaces are feeding the desk and what still blocks use.

    This is an operator-facing projection only. It does not fetch venues, score,
    judge, or route orders.
    """
    visible_verdicts = _visible_leg_rows(verdicts)

    def rows_for(surface: str) -> list[dict[str, Any]]:
        return [
            row for row in [*direct_inventory, *visible_verdicts]
            if str(row.get("surface") or "") == surface
        ]

    polymarket = rows_for("polymarket")
    kalshi = rows_for("kalshi")
    ibkr_prediction = rows_for("ibkr_prediction")
    public_market = [*public_hedges, *[row for row in visible_verdicts if str(row.get("surface") or "") in {"ibkr", "public_market"}]]
    crypto = [
        row for row in [*public_hedges, *visible_verdicts]
        if str(row.get("surface") or "") == "crypto"
        or str(row.get("leg_slug") or row.get("instrument") or "").upper() in {"BTC-USD", "ETH-USD", "BTC/USD", "ETH/USD"}
    ]

    ibkr_priced = sum(1 for row in ibkr_prediction if _row_has_yes_price(row) or str(row.get("pricing_status") or "") == "priced_watchlist")
    ibkr_proxy = sum(1 for row in ibkr_prediction if _row_has_external_proxy_price(row))
    rows = [
        _venue_row(
            surface="polymarket",
            label="Polymarket Gamma",
            role="direct event watchlist after premium scoring",
            rows=polymarket,
            status=_status_from_counts(
                rows=len(polymarket),
                priced=sum(1 for row in polymarket if _row_has_yes_price(row) or str(row.get("pricing_status") or "") == "priced_watchlist"),
            ),
            gaps=["Premium scorer must pass before any Polymarket leg can be promoted."] if polymarket else ["No configured Polymarket direct event rows."],
            direct_event_surface=True,
            premium_gate_required=True,
        ),
        _venue_row(
            surface="kalshi",
            label="Kalshi public event feed",
            role="direct AI/data-center forecast events",
            rows=kalshi,
            status=_status_from_counts(
                rows=len(kalshi),
                priced=sum(1 for row in kalshi if _row_has_yes_price(row) or str(row.get("pricing_status") or "") == "priced_watchlist"),
                empty_status="NEEDS_EVENT_MATCH",
            ),
            gaps=["Needs thesis-matched priced event contracts before promotion."] if kalshi else ["No thesis-matched Kalshi rows in the current snapshot."],
            direct_event_surface=True,
        ),
        _venue_row(
            surface="ibkr_prediction",
            label="IBKR ForecastTrader / ForecastEx",
            role="direct electricity and AI compute forecast contracts",
            rows=ibkr_prediction,
            status=_status_from_counts(rows=len(ibkr_prediction), priced=ibkr_priced, external_proxy=ibkr_proxy),
            gaps=(
                ["IBKR EC metadata is present, but venue bid/ask/last is still missing; external proxy marks are labelled separately."]
                if ibkr_prediction and ibkr_priced == 0 and ibkr_proxy > 0
                else ["Needs live EC bid/ask/last from Client Portal or TWS."]
            ),
            direct_event_surface=True,
        ),
        _venue_row(
            surface="public_market",
            label="Yahoo / IBKR / Alpaca public quote proxies",
            role="liquid public hedge expression",
            rows=public_market,
            status=_status_from_counts(
                rows=len(public_market),
                priced=sum(1 for row in public_market if _row_has_public_price(row) or str(row.get("pricing_status") or "") == "priced_public_market"),
                empty_status="NEEDS_QUOTES",
            ),
            gaps=["These are liquid proxies, not direct compute or electricity claims."],
        ),
        _venue_row(
            surface="crypto",
            label="BTC/ETH miner-margin proxy",
            role="power-sensitive miner-margin proxy",
            rows=crypto,
            status=_status_from_counts(
                rows=len(crypto),
                priced=sum(1 for row in crypto if _row_has_public_price(row) or str(row.get("pricing_status") or "") == "priced_public_market"),
                empty_status="NEEDS_QUOTES",
            ),
            gaps=["Crypto is proxy-only unless explicit miner-margin evidence is attached."],
        ),
        _oracle_evidence_state(logs=logs),
    ]
    return {
        "version": "venue_evidence_matrix_v1",
        "guardrail": "All rows are evidence or watchlist state only; no Circle or Arc action can happen before judge.classify() returns EXECUTE.",
        "rows": rows,
        "summary": {
            "surfaces": len(rows),
            "real_feed_surfaces": sum(1 for row in rows if row.get("real_feed")),
            "direct_event_surfaces": sum(1 for row in rows if row.get("direct_event_surface")),
            "priced_surfaces": sum(1 for row in rows if int(row.get("priced_count") or 0) > 0),
            "evidence_only_surfaces": sum(1 for row in rows if row.get("evidence_only")),
            "arc_ready_surfaces": 0,
        },
    }


def arc_tx_state(*, logs: Path | str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return _latest_first(read_tsv("arc_txs.tsv", limit=limit, logs=logs))


def pnl_state(*, logs: Path | str | None = None) -> dict[str, Any]:
    rows = read_tsv("pnl_reconciliation.tsv", logs=logs)
    total = 0.0
    wins = 0
    counted = 0
    for row in rows:
        value = row.get("actual_pnl") or row.get("actual_pnl_usd") or row.get("realized_pnl_usd")
        try:
            pnl = float(value)
        except (TypeError, ValueError):
            continue
        total += pnl
        wins += 1 if pnl > 0 else 0
        counted += 1
    return {
        "total": round(total, 6),
        "trades": counted,
        "win_rate": round((wins / counted) * 100.0, 3) if counted else 0.0,
    }


def enrich_pnl_state(
    pnl: dict[str, Any],
    *,
    spread_families: dict[str, Any],
    proxy_baskets: dict[str, Any],
    signal_direction: str = "",
    visible_positions: int,
) -> dict[str, Any]:
    trades = int(_as_float(pnl.get("trades")) or 0)
    primary_family = spread_families.get("primary_family") if isinstance(spread_families, dict) else {}
    primary_proxy, _proxy_gate = select_proxy_basket_for_direction(proxy_baskets, signal_direction)
    if trades <= 0:
        status = "NO_SETTLED_PNL"
        status_label = "No settled PnL"
        note = (
            "No reconciled fills or settlements exist yet. Replay rows and local mock "
            "tickets are not realized PnL."
        )
    elif visible_positions <= 0:
        status = "RECONCILED_ONLY"
        status_label = "Reconciled history only"
        note = "PnL comes from reconciliation rows; there are no currently visible Arc positions."
    else:
        status = "SETTLED_PNL"
        status_label = "Settled PnL"
        note = "PnL comes from reconciled fills or settlements."
    pnl.update({
        "status": status,
        "status_label": status_label,
        "display_total": f"${float(pnl.get('total') or 0):.4f}" if trades > 0 else status_label,
        "display_trades": str(trades) if trades > 0 else "0 settled",
        "mark_to_market_note": note,
        "spread_replay_status": (primary_family or {}).get("status", ""),
        "spread_replay_reason": (primary_family or {}).get("status_reason", ""),
        "spread_mark_changes": (primary_family or {}).get("observations", 0),
        "spread_raw_observations": (primary_family or {}).get("raw_observations", 0),
        "spread_collapsed_polls": (primary_family or {}).get("collapsed_repeated_marks", 0),
        "proxy_basket_id": (primary_proxy or {}).get("basket_id", ""),
        "proxy_basket_direction": (primary_proxy or {}).get("direction", ""),
        "proxy_latest_signal": (primary_proxy or {}).get("latest_signal", ""),
        "proxy_replay_status": (primary_proxy or {}).get("status", ""),
        "proxy_5d_return_pct": (((primary_proxy or {}).get("trailing_returns") or {}).get("5d") or {}).get("return_pct", ""),
        "proxy_1m_return_pct": (((primary_proxy or {}).get("trailing_returns") or {}).get("1m") or {}).get("return_pct", ""),
    })
    return pnl


def _row_ts(row: dict[str, Any]) -> float:
    try:
        return float(row.get("ts") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _visible_leg_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if not row.get("is_mock")
        and not row.get("is_thesis_mismatch")
        and not row.get("is_legacy_artifact")
    ]


def _leg_rollup_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(row.get("surface") or ""),
        str(row.get("instrument") or ""),
        str(row.get("direction") or ""),
        str(row.get("leg_role") or ""),
        str(row.get("label") or row.get("status") or ""),
        str(row.get("reason_code") or ""),
    )


def rollup_leg_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated scan rows while keeping the newest public metadata."""
    by_key: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=_row_ts, reverse=True):
        key = _leg_rollup_key(row)
        current = by_key.get(key)
        if current is None:
            copy = dict(row)
            copy["repeat_count"] = 1
            copy["latest_ts"] = row.get("ts", "")
            copy["first_ts"] = row.get("ts", "")
            by_key[key] = copy
            continue
        current["repeat_count"] = int(current.get("repeat_count") or 1) + 1
        current["first_ts"] = row.get("ts", current.get("first_ts", ""))
    return sorted(by_key.values(), key=_row_ts, reverse=True)


def _package_key(row: dict[str, Any]) -> str:
    return (
        str(row.get("package_id") or "")
        or str(row.get("arb_signal_id") or "")
        or "|".join(str(part) for part in _leg_rollup_key(row)[:4])
    )


def _package_label(legs: list[dict[str, Any]]) -> str:
    labels = [str(leg.get("label") or "") for leg in legs]
    if "EXECUTE" in labels:
        return "EXECUTE"
    if labels and all(label == "REJECT" for label in labels):
        return "REJECT"
    if "CHALLENGE" in labels:
        return "CHALLENGE"
    if "DEFER" in labels:
        return "DEFER"
    return labels[0] if labels else "PENDING"


def _repeat_total(rows: list[dict[str, Any]]) -> int:
    return sum(int(row.get("repeat_count") or 1) for row in rows)


def _reason_codes(rows: list[dict[str, Any]]) -> list[str]:
    reasons = {
        str(row.get("reason_code") or "").strip()
        for row in rows
        if str(row.get("reason_code") or "").strip()
    }
    return sorted(reasons)


def _package_reason(label: str, legs: list[dict[str, Any]], fallback: str = "") -> str:
    matching = [leg for leg in legs if str(leg.get("label") or "") == label]
    if matching:
        latest = max(matching, key=_row_ts)
        return str(latest.get("reason_code") or fallback)
    actionable = [leg for leg in legs if str(leg.get("label") or "") != "REJECT"]
    if actionable:
        latest = max(actionable, key=_row_ts)
        return str(latest.get("reason_code") or fallback)
    return str(fallback or "")


def _blocked_summary(kind: str, rows: list[dict[str, Any]]) -> str:
    count = _repeat_total(rows)
    if count <= 0:
        return ""
    reasons = ", ".join(_reason_codes(rows)) or "judge gate"
    leg_word = "row" if count == 1 else "rows"
    return f"{count} {kind} scan {leg_word} blocked by {reasons}"


def package_state(
    verdicts: list[dict[str, Any]],
    positions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group recent public legs into understandable spread packages.

    The raw TSV rows remain append-only audit state. This projection is the
    operator-facing view: one package, its direct legs, its proxy legs, and the
    latest judge result.
    """
    visible_verdicts = _visible_leg_rows(verdicts)
    visible_positions = _visible_leg_rows(positions)
    grouped: dict[str, dict[str, Any]] = {}
    for row in sorted(visible_verdicts, key=_row_ts, reverse=True):
        key = _package_key(row)
        pkg = grouped.setdefault(key, {
            "id": key,
            "package_id": row.get("package_id", ""),
            "arb_signal_id": row.get("arb_signal_id", ""),
            "ts": row.get("ts", ""),
            "direction": row.get("direction", ""),
            "legs": [],
            "positions": [],
        })
        if _row_ts(row) >= _row_ts(pkg):
            pkg["ts"] = row.get("ts", pkg.get("ts", ""))
            pkg["direction"] = row.get("direction", pkg.get("direction", ""))
            pkg["reason_code"] = row.get("reason_code", pkg.get("reason_code", ""))
        pkg["legs"].append(row)
    for row in sorted(visible_positions, key=_row_ts, reverse=True):
        key = _package_key(row)
        pkg = grouped.setdefault(key, {
            "id": key,
            "package_id": row.get("package_id", ""),
            "arb_signal_id": row.get("arb_signal_id", ""),
            "ts": row.get("ts", ""),
            "direction": row.get("direction", ""),
            "legs": [],
            "positions": [],
        })
        pkg["positions"].append(row)
        if _row_ts(row) >= _row_ts(pkg):
            pkg["ts"] = row.get("ts", pkg.get("ts", ""))
            pkg["direction"] = row.get("direction", pkg.get("direction", ""))

    packages: list[dict[str, Any]] = []
    for pkg in grouped.values():
        legs = rollup_leg_rows(pkg["legs"])
        direct = [
            leg for leg in legs
            if str(leg.get("leg_role") or "") == "direct_prediction_event"
            or str(leg.get("surface") or "") in {"polymarket", "ibkr_prediction", "kalshi"}
        ]
        proxy = [leg for leg in legs if leg not in direct]
        actionable = [leg for leg in legs if str(leg.get("label") or "") != "REJECT"]
        actionable_direct = [leg for leg in direct if str(leg.get("label") or "") != "REJECT"]
        actionable_proxy = [leg for leg in proxy if str(leg.get("label") or "") != "REJECT"]
        rejected = [leg for leg in legs if str(leg.get("label") or "") == "REJECT"]
        rejected_direct = [leg for leg in direct if str(leg.get("label") or "") == "REJECT"]
        rejected_proxy = [leg for leg in proxy if str(leg.get("label") or "") == "REJECT"]
        label = _package_label(legs)
        reason = _package_reason(label, legs, str(pkg.get("reason_code") or ""))
        packages.append({
            **pkg,
            "label": label,
            "reason_code": reason,
            "legs": legs,
            "direct_legs": direct,
            "proxy_legs": proxy,
            "positions": rollup_leg_rows(pkg["positions"]),
            "leg_count": len(legs),
            "direct_leg_count": len(direct),
            "proxy_leg_count": len(proxy),
            "actionable_leg_count": len(actionable),
            "actionable_direct_leg_count": len(actionable_direct),
            "actionable_proxy_leg_count": len(actionable_proxy),
            "rejected_leg_count": len(rejected),
            "rejected_direct_leg_count": len(rejected_direct),
            "rejected_proxy_leg_count": len(rejected_proxy),
            "rejected_repeat_count": _repeat_total(rejected),
            "rejected_direct_repeat_count": _repeat_total(rejected_direct),
            "rejected_proxy_repeat_count": _repeat_total(rejected_proxy),
            "direct_reject_reasons": _reason_codes(rejected_direct),
            "proxy_reject_reasons": _reason_codes(rejected_proxy),
            "direct_blocked_summary": _blocked_summary("direct event", rejected_direct),
            "proxy_blocked_summary": _blocked_summary("proxy", rejected_proxy),
            "repeat_count": _repeat_total(legs),
        })
    return sorted(packages, key=_row_ts, reverse=True)


def runtime_status(*, logs: Path | str | None = None) -> dict[str, Any]:
    status = read_json(log_dir(logs) / "runtime_status.json", default={})
    if not isinstance(status, dict):
        return {}
    return sanitize_row(status)


def snapshot(*, logs: Path | str | None = None) -> dict[str, Any]:
    now = time.time()
    spread = spread_state(logs=logs)
    spread_families = spread_family_state(logs=logs)
    proxy_baskets = proxy_basket_state(logs=logs)
    signal = signal_state(logs=logs)
    signal_latest = signal.get("latest") if isinstance(signal.get("latest"), dict) else {}
    signal_direction = str((signal_latest or {}).get("direction") or "")
    active_proxy_basket, active_proxy_gate = select_proxy_basket_for_direction(proxy_baskets, signal_direction)
    if isinstance(proxy_baskets, dict):
        proxy_baskets = dict(proxy_baskets)
        proxy_baskets["active_direction"] = signal_direction
        proxy_baskets["active_basket"] = active_proxy_basket
        proxy_baskets["active_entry_gate_pass"] = active_proxy_gate
    verdicts = verdict_state(logs=logs)
    positions = position_state(logs=logs)
    direct_inventory = direct_inventory_state(logs=logs)
    public_hedges = public_hedge_state(logs=logs)
    verdict_rollups = rollup_leg_rows(_visible_leg_rows(verdicts))
    packages = package_state(verdicts, positions)
    venue_evidence = venue_evidence_state(
        direct_inventory=direct_inventory,
        public_hedges=public_hedges,
        verdicts=verdict_rollups,
        logs=logs,
    )
    oracle_evidence = _oracle_evidence_state(logs=logs)
    synthetic_instrument = propose_synthetic_instrument(
        spread=spread,
        signal=signal,
        direct_inventory=direct_inventory,
        public_hedges=public_hedges,
        packages=packages,
        verdicts=verdict_rollups,
        positions=positions,
        spread_family_validation=spread_families,
        proxy_basket_validation=proxy_baskets,
        oracle_evidence=oracle_evidence,
    )
    pnl = pnl_state(logs=logs)
    real_positions = _visible_leg_rows(positions)
    real_verdicts = _visible_leg_rows(verdicts)
    job_ids = {
        str(row.get("job_id"))
        for row in real_positions
        if row.get("job_id") not in ("", None)
    }
    pnl.update({
        "has_reconciled": int(pnl.get("trades") or 0) > 0,
        "reconciled_trades": pnl.get("trades", 0),
        "wrapped_jobs": len(job_ids),
        "executed_verdicts": sum(1 for row in real_verdicts if row.get("label") == "EXECUTE"),
        "visible_positions": len(real_positions),
    })
    pnl = enrich_pnl_state(
        pnl,
        spread_families=spread_families,
        proxy_baskets=proxy_baskets,
        signal_direction=signal_direction,
        visible_positions=len(real_positions),
    )
    return {
        "ok": True,
        "generated_at": now,
        "mode": {
            "live_chain_enabled": bool_env("ENABLE_LIVE_CHAIN", False),
            "telegram_enabled": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        },
        "runtime": runtime_status(logs=logs),
        "spread": spread,
        "spread_families": spread_families,
        "proxy_baskets": proxy_baskets,
        "signal": signal,
        "verdicts": verdicts,
        "verdict_rollups": verdict_rollups,
        "packages": packages,
        "synthetic_instrument": synthetic_instrument,
        "direct_inventory": direct_inventory,
        "public_hedges": public_hedges,
        "venue_evidence": venue_evidence,
        "positions": positions,
        "arc_txs": arc_tx_state(logs=logs),
        "pnl": pnl,
        "oracle": oracle_evidence,
    }
