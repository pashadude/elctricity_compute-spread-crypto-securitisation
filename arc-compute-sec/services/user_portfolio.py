"""Account-scoped paper portfolio for Power by Botozen.

This is deliberately not an execution venue. It stores local paper tickets
against backend-generated syndicated instruments so a paid account can see
position, mark, and PnL state without browser-only localStorage.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services import state


PORTFOLIO_VERSION = 1
_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _store_path(logs: Path | str | None = None) -> Path:
    explicit = os.environ.get("ACCOUNT_PORTFOLIO_STORE_PATH")
    if explicit:
        return Path(explicit)
    return state.log_dir(logs) / "account_portfolios.json"


def _empty_store() -> dict[str, Any]:
    return {"version": PORTFOLIO_VERSION, "positions": {}, "realized": {}}


def _read_store(logs: Path | str | None = None) -> dict[str, Any]:
    path = _store_path(logs)
    if not path.exists():
        return _empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    data.setdefault("version", PORTFOLIO_VERSION)
    data.setdefault("positions", {})
    data.setdefault("realized", {})
    return data


def _write_store(data: dict[str, Any], logs: Path | str | None = None) -> None:
    path = _store_path(logs)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".account_portfolios.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _round_money(value: Any) -> float:
    return round(_num(value), 2)


def _instrument_id(row: dict[str, Any]) -> str:
    raw = str(row.get("instrument_type") or row.get("basket_id") or row.get("title") or "instrument")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{raw.replace(' ', '_').lower()}-{digest}"


def _signal(row: dict[str, Any], ledger: dict[str, Any]) -> str:
    raw = str(ledger.get("latest_signal") or row.get("latest_signal") or "MONITOR").upper()
    if raw == "BUY":
        return "ENTER"
    if raw == "SELL":
        return "CLOSE_OR_AVOID"
    return "HOLD"


def _history_from_marks(ledger: dict[str, Any], mark_nav: float) -> list[float]:
    marks = ledger.get("recent_paper_marks")
    if not isinstance(marks, list) or not marks:
        return [1.0, mark_nav]
    closes = [_num(item.get("index_close")) for item in marks if isinstance(item, dict) and item.get("index_close") not in ("", None)]
    closes = [value for value in closes if value > 0]
    if len(closes) < 2:
        return [1.0, mark_nav]
    first = closes[0] or 1.0
    return [round(value / first, 6) for value in closes]


def instrument_catalog(snapshot_data: dict[str, Any] | None = None, *, logs: Path | str | None = None) -> list[dict[str, Any]]:
    snap = snapshot_data if isinstance(snapshot_data, dict) else state.snapshot(logs=logs)
    outputs = ((snap.get("synthetic_instrument") or {}).get("outputs") or {})
    menu = outputs.get("syndicated_instrument_menu") or []
    ledger_rows = ((snap.get("profitability_ledger") or {}).get("rows") or [])
    ledger_by_basket = {
        str(row.get("basket_id") or ""): row
        for row in ledger_rows
        if isinstance(row, dict)
    }
    ledger_by_archetype = {
        str(row.get("archetype_id") or ""): row
        for row in ledger_rows
        if isinstance(row, dict)
    }
    direct_inventory = snap.get("direct_inventory") or []
    public_hedges = snap.get("public_hedges") or []
    hedge_by_symbol = {
        str((row or {}).get("instrument") or (row or {}).get("leg_slug") or "").upper(): row
        for row in public_hedges
        if isinstance(row, dict)
    }

    out: list[dict[str, Any]] = []
    for row in menu:
        if not isinstance(row, dict):
            continue
        basket_id = str(row.get("basket_id") or "")
        archetype_id = str(row.get("spread_archetype") or "")
        ledger = ledger_by_basket.get(basket_id) or ledger_by_archetype.get(archetype_id) or {}
        total_return_pct = _num(
            ledger.get("paper_total_return_pct")
            if ledger.get("paper_total_return_pct") not in ("", None)
            else row.get("total_return_pct")
        )
        mark_nav = max(0.01, 1.0 + total_return_pct / 100.0)
        priced_symbols = [str(symbol) for symbol in row.get("priced_symbols") or []]
        missing_symbols = [str(symbol) for symbol in row.get("missing_symbols") or []]
        priced_legs = []
        for symbol in priced_symbols:
            hedge = hedge_by_symbol.get(symbol.upper()) or {}
            priced_legs.append({
                "side": "long" if "short" not in str(row.get("payoff") or "").lower() else "basket",
                "sym": symbol,
                "name": hedge.get("leg_title") or hedge.get("title") or symbol,
                "last_price": hedge.get("last_price", ""),
                "source": hedge.get("source") or hedge.get("quote_source") or hedge.get("pricing_status") or "",
                "role": hedge.get("pair_role") or hedge.get("role") or "priced hedge leg",
            })
        direct_legs = []
        for leg in direct_inventory:
            if not isinstance(leg, dict):
                continue
            direct_legs.append({
                "surface": leg.get("surface") or "",
                "slug": leg.get("leg_slug") or leg.get("slug") or "",
                "title": leg.get("leg_title") or leg.get("title") or "",
                "role": leg.get("direct_pair_role") or leg.get("pair_role") or "",
                "direction": leg.get("direction") or "",
                "pricing_status": leg.get("pricing_status") or leg.get("label") or "",
            })
        replay = row.get("paper_trade_replay") if isinstance(row.get("paper_trade_replay"), dict) else {}
        out.append({
            "id": _instrument_id(row),
            "instrumentType": row.get("instrument_type") or "",
            "basketId": basket_id,
            "name": row.get("title") or row.get("instrument_type") or "Spread note",
            "form": archetype_id or row.get("instrument_type") or "spread",
            "spreadArchetype": archetype_id,
            "signal": _signal(row, ledger),
            "latestSignal": ledger.get("latest_signal") or row.get("latest_signal") or "MONITOR",
            "status": row.get("status") or ledger.get("profitability_status") or "MONITOR_ONLY",
            "profitabilityStatus": ledger.get("profitability_status") or "",
            "statusReason": row.get("status_reason") or ledger.get("reason") or "",
            "signalReason": ledger.get("signal_reason") or row.get("signal_reason") or "",
            "thesis": row.get("payoff") or row.get("copying_spread") or "",
            "copyingSpread": row.get("copying_spread") or "",
            "tenor": row.get("direct_leg_target") or "rolling paper basket",
            "assetBacked": bool(row.get("asset_backed")),
            "collateralStatus": row.get("collateral_status") or "not_asset_backed_v0",
            "collateralNeeded": row.get("collateral_needed") or [],
            "circleAskUsdc": _round_money(row.get("circle_testnet_ask_usdc")),
            "markNav": round(mark_nav, 6),
            "hist": _history_from_marks(ledger, mark_nav),
            "totalReturnPct": round(total_return_pct, 4),
            "return5dPct": _num(ledger.get("paper_5d_return_pct")),
            "return1mPct": _num(ledger.get("paper_1m_return_pct")),
            "winRate": _num(row.get("win_rate") or ledger.get("paper_win_rate")),
            "maxDrawdownPct": _num(row.get("max_drawdown_pct")),
            "replay": {
                "window": replay.get("window") or "backend replay",
                "obs": replay.get("closed_trade_count") or ledger.get("spread_oos_test_trades") or 0,
                "status": row.get("replay_status") or ledger.get("spread_replay_status") or "NO_REPLAY",
                "yield": total_return_pct,
                "vol": 0,
                "maxDd": _num(row.get("max_drawdown_pct")),
                "sharpe": 0,
                "hit": _num(replay.get("hit_rate") or row.get("win_rate") or 0) / 100.0,
                "closedTrades": replay.get("closed_trades") or [],
                "openTrade": replay.get("open_trade"),
            },
            "legs": priced_legs,
            "directLegs": direct_legs,
            "pricedSymbols": priced_symbols,
            "missingSymbols": missing_symbols,
            "supportsFreshBuy": bool(ledger.get("supports_fresh_buy")) or str(row.get("status")) in {"PAPER_BUY_ONLY", "READY_FOR_JUDGE"},
            "arcGate": row.get("arc_gate") or "LOCKED_UNTIL_JUDGE_EXECUTE",
        })
    return out


def _instrument_by_id(snapshot_data: dict[str, Any] | None, instrument_id: str, *, logs: Path | str | None = None) -> dict[str, Any] | None:
    for item in instrument_catalog(snapshot_data, logs=logs):
        if item["id"] == instrument_id or item.get("instrumentType") == instrument_id or item.get("basketId") == instrument_id:
            return item
    return None


def _account_id(account: dict[str, Any] | None) -> str:
    return str((account or {}).get("id") or "")


def _positions_for(data: dict[str, Any], account_id: str) -> list[dict[str, Any]]:
    return list(data.get("positions", {}).get(account_id, []))


def _realized_for(data: dict[str, Any], account_id: str) -> list[dict[str, Any]]:
    return list(data.get("realized", {}).get(account_id, []))


def _mark_position(pos: dict[str, Any], catalog_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    instrument = catalog_by_id.get(str(pos.get("instrumentId") or ""))
    mark = _num((instrument or {}).get("markNav"), _num(pos.get("entryMark"), 1.0))
    entry = _num(pos.get("entryMark"), 1.0)
    notional = _num(pos.get("notionalUsdc"))
    pnl = (mark - entry) * notional
    ret_pct = ((mark - entry) / entry * 100.0) if entry else 0.0
    return {
        **pos,
        "currentMark": round(mark, 6),
        "unrealizedPnlUsdc": round(pnl, 2),
        "returnPct": round(ret_pct, 4),
        "latestSignal": (instrument or {}).get("latestSignal", pos.get("latestSignal", "")),
        "status": (instrument or {}).get("status", pos.get("status", "")),
    }


def portfolio_state(
    account: dict[str, Any] | None,
    *,
    snapshot_data: dict[str, Any] | None = None,
    logs: Path | str | None = None,
) -> dict[str, Any]:
    account_id = _account_id(account)
    catalog = instrument_catalog(snapshot_data, logs=logs)
    if not account_id:
        return {
            "ok": True,
            "account_required": True,
            "account": None,
            "positions": [],
            "realized": [],
            "summary": {"openNotionalUsdc": 0, "unrealizedPnlUsdc": 0, "realizedPnlUsdc": 0, "netPnlUsdc": 0, "openCount": 0, "realizedCount": 0},
            "instruments": catalog,
        }
    with _LOCK:
        data = _read_store(logs)
        positions = _positions_for(data, account_id)
        realized = _realized_for(data, account_id)
    catalog_by_id = {item["id"]: item for item in catalog}
    marked = [_mark_position(pos, catalog_by_id) for pos in positions if pos.get("status") == "open"]
    realized_total = sum(_num(row.get("pnlUsdc")) for row in realized)
    unrealized_total = sum(_num(row.get("unrealizedPnlUsdc")) for row in marked)
    open_notional = sum(_num(row.get("notionalUsdc")) for row in marked)
    return {
        "ok": True,
        "account_required": False,
        "account": {"id": account_id, "walletAddress": account.get("walletAddress", ""), "planId": account.get("planId", "")},
        "positions": marked,
        "realized": realized,
        "summary": {
            "openNotionalUsdc": round(open_notional, 2),
            "unrealizedPnlUsdc": round(unrealized_total, 2),
            "realizedPnlUsdc": round(realized_total, 2),
            "netPnlUsdc": round(realized_total + unrealized_total, 2),
            "openCount": len(marked),
            "realizedCount": len(realized),
        },
        "instruments": catalog,
    }


def open_position(
    account: dict[str, Any] | None,
    *,
    instrument_id: str,
    notional_usdc: Any,
    snapshot_data: dict[str, Any] | None = None,
    logs: Path | str | None = None,
) -> dict[str, Any]:
    account_id = _account_id(account)
    if not account_id:
        raise PermissionError("account_required")
    notional = _round_money(notional_usdc)
    if notional <= 0:
        raise ValueError("notional_usdc_required")
    if notional > 250_000:
        raise ValueError("notional_too_large_for_demo")
    instrument = _instrument_by_id(snapshot_data, str(instrument_id), logs=logs)
    if not instrument:
        raise ValueError("unknown_instrument")
    now = _now_iso()
    position = {
        "positionId": f"pos_{secrets.token_hex(6)}",
        "accountId": account_id,
        "instrumentId": instrument["id"],
        "instrumentType": instrument.get("instrumentType", ""),
        "noteName": instrument.get("name", ""),
        "form": instrument.get("form", ""),
        "signal": instrument.get("signal", "HOLD"),
        "latestSignal": instrument.get("latestSignal", ""),
        "status": "open",
        "notionalUsdc": notional,
        "entryMark": _num(instrument.get("markNav"), 1.0),
        "entryTs": int(time.time() * 1000),
        "openedAt": now,
        "legs": instrument.get("legs", []),
        "directLegs": instrument.get("directLegs", []),
        "collateralStatus": instrument.get("collateralStatus", ""),
        "arcGate": instrument.get("arcGate", "LOCKED_UNTIL_JUDGE_EXECUTE"),
        "paperOnly": True,
    }
    with _LOCK:
        data = _read_store(logs)
        data.setdefault("positions", {}).setdefault(account_id, [])
        data["positions"][account_id].insert(0, position)
        _write_store(data, logs)
    return portfolio_state(account, snapshot_data=snapshot_data, logs=logs)


def close_position(
    account: dict[str, Any] | None,
    *,
    position_id: str,
    snapshot_data: dict[str, Any] | None = None,
    logs: Path | str | None = None,
) -> dict[str, Any]:
    account_id = _account_id(account)
    if not account_id:
        raise PermissionError("account_required")
    catalog_by_id = {item["id"]: item for item in instrument_catalog(snapshot_data, logs=logs)}
    with _LOCK:
        data = _read_store(logs)
        positions = _positions_for(data, account_id)
        pos = next((row for row in positions if row.get("positionId") == position_id and row.get("status") == "open"), None)
        if not pos:
            raise ValueError("unknown_position")
        marked = _mark_position(pos, catalog_by_id)
        entry = _num(marked.get("entryMark"), 1.0)
        exit_mark = _num(marked.get("currentMark"), entry)
        ret_pct = ((exit_mark - entry) / entry * 100.0) if entry else 0.0
        realized = {
            **marked,
            "status": "closed",
            "exitMark": round(exit_mark, 6),
            "closedAt": _now_iso(),
            "exitTs": int(time.time() * 1000),
            "pnlUsdc": round(_num(marked.get("unrealizedPnlUsdc")), 2),
            "retPct": round(ret_pct, 4),
        }
        data["positions"][account_id] = [row for row in positions if row.get("positionId") != position_id]
        data.setdefault("realized", {}).setdefault(account_id, []).insert(0, realized)
        _write_store(data, logs)
    return portfolio_state(account, snapshot_data=snapshot_data, logs=logs)
