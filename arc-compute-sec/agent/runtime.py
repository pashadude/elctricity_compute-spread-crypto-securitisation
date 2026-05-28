"""Agent runtime — orchestrates ONE pass through the rail. Not a loop.

  arb_identifier  →  surface_router  →  adapters  →  judge  →  on_chain
                                                              wrap + settle

Modes (signal source, mutually exclusive):
    --scan          one live pass: fetch EIA + AWS, compute spread, then
                    route canonical spread-package expression legs and exit
    --once          one mock pass: synthesize signal from --mock-elec /
                    --mock-compute / --force-signal flags

Chain submission (independent flags):
    --live          disable dry-run; actually submit txs via Circle SDK
                    (default: dry-run ON — safe to use without creds)
    --settle        after wrap, run the reconciliation pass too

Gap 7 from review_session_deliverables.md (v0): continuous polling is
DEFERRED to v2. The runtime does ONE pass, writes its logs, and exits.
Anything observability-shaped (notifications, retries on RPC 429, idle
back-off, daemon loops) is out of scope for v0.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent import arb_identifier, judge, surface_router
from agent.spread_package import package_summary_for_candidate

_POSITIONS_PATH = Path(__file__).resolve().parent.parent / "logs" / "positions.tsv"
_ARC_TXS_PATH = Path(__file__).resolve().parent.parent / "logs" / "arc_txs.tsv"
_SPREAD_MARK_SOURCES_PATH = Path(__file__).resolve().parent.parent / "logs" / "spread_mark_sources.jsonl"
_POSITIONS_HEADERS = [
    "ts", "stage", "job_id", "arb_signal_id", "surface", "instrument",
    "direction", "notional_usdc", "deliverable_hash", "reason_hash",
    "tx_hash", "fill_report_path", "action_key",
    "leg_title", "leg_slug", "leg_description", "leg_end_date",
    "leg_role", "package_id",
]


def _identity_row() -> dict[str, str]:
    p = Path(__file__).resolve().parent.parent / "logs" / "identity.tsv"
    if not p.exists():
        raise RuntimeError(
            f"logs/identity.tsv missing. Run identity/register_agent.ts first."
        )
    with p.open() as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    if not rows:
        raise RuntimeError("logs/identity.tsv is empty.")
    return rows[-1]


def _keccak_hex(data: bytes) -> str:
    """keccak256 hex including 0x prefix."""
    from eth_utils import keccak
    return "0x" + keccak(data).hex()


def _canonical_outcome_blob(candidate_dict: dict[str, Any], fill_report: dict[str, Any] | None,
                            signal: arb_identifier.ArbSignal | None) -> bytes:
    blob = {
        "candidate": candidate_dict,
        "fill_report": fill_report or {},
        "arb_signal": asdict(signal) if signal is not None else {},
        "spread_package": package_summary_for_candidate(candidate_dict) or {},
    }
    return json.dumps(blob, sort_keys=True, default=str).encode()


def _action_key(candidate_dict: dict[str, Any]) -> str:
    stable = {k: v for k, v in candidate_dict.items() if k != "candidate_id"}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()[:32]


def _public_leg_fields(candidate_dict: dict[str, Any]) -> dict[str, str]:
    metadata = candidate_dict.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    spread_leg = metadata.get("spread_leg") if isinstance(metadata, dict) else {}
    spread_package = metadata.get("spread_package") if isinstance(metadata, dict) else {}
    if not isinstance(spread_leg, dict):
        spread_leg = {}
    if not isinstance(spread_package, dict):
        spread_package = {}
    return {
        "leg_title": str(metadata.get("title") or spread_leg.get("title") or candidate_dict.get("instrument", "")),
        "leg_slug": str(metadata.get("slug") or spread_leg.get("slug") or ""),
        "leg_description": str(metadata.get("description") or spread_leg.get("description") or ""),
        "leg_end_date": str(metadata.get("end_date") or spread_leg.get("end_date") or ""),
        "leg_role": str(spread_leg.get("role") or ""),
        "package_id": str(spread_package.get("package_id") or ""),
    }


def _position_already_recorded(action_key: str) -> bool:
    if not _POSITIONS_PATH.exists():
        return False
    with _POSITIONS_PATH.open("r", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if not reader.fieldnames or "action_key" not in reader.fieldnames:
            return False
        return any(row.get("action_key") == action_key for row in reader)


def _append_position_row(row: dict[str, Any]) -> None:
    _POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ensure_position_schema()
    new = not _POSITIONS_PATH.exists()
    with _POSITIONS_PATH.open("a", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        if new:
            writer.writerow(_POSITIONS_HEADERS)
        writer.writerow([str(row.get(h, "")) for h in _POSITIONS_HEADERS])


def _ensure_position_schema() -> None:
    if not _POSITIONS_PATH.exists():
        return
    with _POSITIONS_PATH.open("r", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        old_headers = reader.fieldnames or []
        if old_headers == _POSITIONS_HEADERS:
            return
        rows = list(reader)
    backup = _POSITIONS_PATH.with_suffix(".legacy.tsv")
    if not backup.exists():
        backup.write_text(_POSITIONS_PATH.read_text())
    migrated = [_migrate_position_row(row, old_headers) for row in rows]
    with _POSITIONS_PATH.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_POSITIONS_HEADERS, delimiter="\t")
        writer.writeheader()
        writer.writerows(migrated)


def _migrate_position_row(row: dict[str, str], headers: list[str]) -> dict[str, str]:
    if "arb_signal_id" in headers:
        return {h: row.get(h, "") for h in _POSITIONS_HEADERS}
    out = {h: "" for h in _POSITIONS_HEADERS}
    out.update({
        "ts": row.get("ts", ""),
        "stage": row.get("stage", ""),
        "job_id": row.get("job_id", ""),
        "surface": row.get("surface", ""),
        "instrument": row.get("market", ""),
        "notional_usdc": row.get("notional_usdc", ""),
        "deliverable_hash": row.get("deliverable_hash", ""),
        "reason_hash": row.get("reason_hash", ""),
        "tx_hash": row.get("settle_tx") or row.get("submit_tx") or row.get("fund_tx") or row.get("open_tx", ""),
    })
    if row.get("market") == "polymarket" and row.get("expired_at") in {"short", "long"}:
        out.update({
            "arb_signal_id": row.get("surface", ""),
            "surface": row.get("market", ""),
            "instrument": row.get("notional_usdc", ""),
            "direction": row.get("expired_at", ""),
            "notional_usdc": row.get("description", ""),
            "deliverable_hash": row.get("open_tx", ""),
            "reason_hash": row.get("fund_tx", ""),
            "tx_hash": row.get("submit_tx") or row.get("settle_tx", ""),
            "action_key": row.get("deliverable_hash", ""),
        })
    return out


def _append_arc_tx_row(row: dict[str, Any]) -> None:
    _ARC_TXS_PATH.parent.mkdir(parents=True, exist_ok=True)
    new = not _ARC_TXS_PATH.exists()
    headers = [
        "ts", "stage", "job_id", "circle_tx_id", "tx_hash", "block_number",
    ]
    with _ARC_TXS_PATH.open("a", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        if new:
            writer.writerow(headers)
        writer.writerow([str(row.get(h, "")) for h in headers])


def _log_chain_tx(stage: str, job_id: int | str, tx: Any) -> None:
    _append_arc_tx_row({
        "ts": time.time(),
        "stage": stage,
        "job_id": job_id,
        "circle_tx_id": getattr(tx, "circle_tx_id", ""),
        "tx_hash": getattr(tx, "tx_hash", ""),
        "block_number": getattr(tx, "block_number", ""),
    })


def _append_spread_mark_source(row: dict[str, Any]) -> None:
    _SPREAD_MARK_SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _SPREAD_MARK_SOURCES_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _live_spread(*, persist_source: bool = True) -> arb_identifier.SpreadPoint:
    """Fetch live EIA + AWS feeds and compute the latest spread."""
    from feeds.eia import fetch_regions, ERCOT
    from feeds.aws_spot import fetch_gpu_spot
    from feeds.power_proxy import adjust_electricity_mark
    e_map = fetch_regions((ERCOT,))
    elec = e_map.get(ERCOT)
    if elec is None or elec.value_mwh <= 0:
        raise RuntimeError(f"EIA returned no usable point for ERCOT: {elec}")
    aws_points = fetch_gpu_spot()
    if not aws_points:
        raise RuntimeError("AWS Spot feed returned no GPU points")
    # Pick the lowest $/GPU-hr we can find (the marginal trade).
    aws_points.sort(key=lambda p: p.price_per_gpu_hour)
    aws_min = aws_points[0]
    power_mark = adjust_electricity_mark(elec.value_mwh)
    point = arb_identifier.compute_spread(
        electricity_per_mwh=power_mark.electricity_per_mwh,
        compute_per_gpu_hr=aws_min.price_per_gpu_hour,
        region="ERCOT|us-east-1",
    )
    if persist_source:
        _append_spread_mark_source({
            "ts": point.ts,
            "region": point.region,
            "S_t": point.S_t,
            "compute_per_gpu_hr": point.compute_per_gpu_hr,
            "electricity_per_mwh": point.electricity_per_mwh,
            "power_cost_per_gpu_hr": point.power_cost_per_gpu_hr,
            "power_cost_share": point.power_cost_share,
            "power_cost_share_pct": point.power_cost_share * 100.0,
            "electricity_base_per_mwh": power_mark.base_electricity_per_mwh,
            "electricity_source": power_mark.source,
            "electricity_source_status": power_mark.status,
            "electricity_proxy_weighted_return_pct": power_mark.weighted_return_pct,
            "electricity_proxy_symbols": power_mark.symbols,
            "electricity_proxy_used_quotes": power_mark.used_quotes,
            "electricity_proxy_quote_sources": power_mark.quote_sources,
            "electricity_proxy_formula": power_mark.formula,
            "electricity_proxy_quotes": power_mark.quotes,
            "eia_region": elec.region,
            "eia_state": elec.state,
            "eia_period": elec.period,
            "eia_raw_unit": elec.raw_unit,
            "eia_raw_value": elec.raw_value,
            "compute_source": "aws_spot",
            "compute_instance": getattr(aws_min, "instance_type", ""),
            "compute_region": getattr(aws_min, "region", ""),
            "compute_os": getattr(aws_min, "os_type", ""),
        })
    return point


def _mock_polymarket_events(direction: str, energy_template: str = "energy_oil_price") -> list[dict]:
    """For Phase 4 Case A demo: produce mocked Polymarket events shaped so the
    NO-overlay arb has positive premium. Real events would come through
    adapters/polymarket.py; this stub keeps the runtime testable without a
    live Polymarket fetch.
    """
    return [
        {
            "id": "mock-event-A",
            "slug": "mock-oil-price-q3",
            "yes_prices": [0.55, 0.50],   # scorer premium = 0.55 + 0.50 - 1.0
            "energy_template_id": energy_template,
            "title": "Mock: oil price > $X in Q3",
        }
    ]


def _polymarket_events_for_signal(signal: arb_identifier.ArbSignal, *, live_scan: bool) -> list[dict]:
    if not live_scan:
        return _mock_polymarket_events(signal.direction)
    from adapters import polymarket
    return polymarket.classify_and_gate(polymarket.fetch_events(), include_rejected=True)


def _optional_polymarket_events_for_signal(
    signal: arb_identifier.ArbSignal,
    *,
    live_scan: bool,
    allow_failure: bool,
) -> list[dict]:
    try:
        return _polymarket_events_for_signal(signal, live_scan=live_scan)
    except Exception as exc:
        if not allow_failure:
            raise
        print(f"[runtime] Polymarket research surface unavailable; continuing with proxy legs: {exc}")
        return []


def _ibkr_prediction_events_for_signal(signal: arb_identifier.ArbSignal) -> list[dict]:
    from adapters.ibkr import fetch_prediction_events
    return fetch_prediction_events()


def _kalshi_events_for_signal(signal: arb_identifier.ArbSignal) -> list[dict]:
    from adapters.kalshi import fetch_ai_events
    return fetch_ai_events()


def _optional_kalshi_events_for_signal(
    signal: arb_identifier.ArbSignal,
    *,
    allow_failure: bool,
) -> list[dict]:
    try:
        return _kalshi_events_for_signal(signal)
    except Exception as exc:
        if not allow_failure:
            raise
        print(f"[runtime] Kalshi research surface unavailable; continuing without Kalshi legs: {exc}")
        return []


def _polymarket_candidates(
    signal: arb_identifier.ArbSignal,
    *,
    live_scan: bool,
    sizing_usdc: float,
) -> list[surface_router.Candidate]:
    events = _optional_polymarket_events_for_signal(
        signal,
        live_scan=live_scan,
        allow_failure=False,
    )
    candidates = surface_router.route(
        signal,
        polymarket_events=events,
        ibkr_prediction_events=(),
        kalshi_events=(),
        sizing_per_equity_usdc=0.0,
        sizing_crypto_usdc=0.0,
        sizing_polymarket_usdc=sizing_usdc,
        sizing_ibkr_prediction_usdc=0.0,
        sizing_kalshi_usdc=0.0,
    )
    return [c for c in candidates if c.surface == "polymarket"]


def _candidates_for_signal(
    signal: arb_identifier.ArbSignal,
    *,
    live_scan: bool,
    multi_surface: bool,
    sizing_equity: float,
    sizing_crypto: float,
    sizing_polymarket: float,
    sizing_ibkr_prediction: float,
    sizing_kalshi: float,
) -> list[surface_router.Candidate]:
    events = _optional_polymarket_events_for_signal(
        signal,
        live_scan=live_scan,
        allow_failure=multi_surface,
    )
    ibkr_prediction_events = _ibkr_prediction_events_for_signal(signal) if multi_surface else []
    kalshi_events = _optional_kalshi_events_for_signal(signal, allow_failure=True) if multi_surface else []
    candidates = surface_router.route(
        signal,
        polymarket_events=events,
        ibkr_prediction_events=ibkr_prediction_events,
        kalshi_events=kalshi_events,
        sizing_per_equity_usdc=sizing_equity if multi_surface else 0.0,
        sizing_crypto_usdc=sizing_crypto if multi_surface else 0.0,
        sizing_polymarket_usdc=sizing_polymarket,
        sizing_ibkr_prediction_usdc=sizing_ibkr_prediction if multi_surface else 0.0,
        sizing_kalshi_usdc=sizing_kalshi if multi_surface else 0.0,
    )
    if multi_surface:
        return candidates
    return [c for c in candidates if c.surface == "polymarket"]


def _settle_outcome_blob(candidate_dict: dict, fill_report: dict, action: str,
                         reason_code: str) -> tuple[bytes, bytes]:
    """Return (outcome_blob_bytes, reason_blob_bytes).

    Loss path uses keccak256("reject:" + reason_code) per delta D6.
    """
    out = {
        "candidate": candidate_dict,
        "fill_report": fill_report,
        "settle": {"action": action, "reason_code": reason_code},
        "ts": time.time(),
    }
    out_bytes = json.dumps(out, sort_keys=True, default=str).encode()
    if action == "reject":
        reason_bytes = f"reject:{reason_code}".encode()
    else:
        reason_bytes = json.dumps({"reason_code": reason_code, "action": "complete"},
                                   sort_keys=True).encode()
    return out_bytes, reason_bytes


def execute_candidate(
    candidate: surface_router.Candidate,
    *,
    dry_run: bool,
    signal: arb_identifier.ArbSignal | None,
) -> dict[str, Any]:
    """Place the (paper) order via the appropriate adapter; return fill report dict."""
    surf = candidate.surface
    md = candidate.metadata or {}
    if surf == "polymarket":
        from adapters.polymarket import simulate_gated_fill
        fr = simulate_gated_fill(candidate.instrument, md.get("yes_prices") or [])
    elif surf == "ibkr":
        from adapters.ibkr import place_paper_order
        fr = place_paper_order(candidate.instrument, candidate.direction,
                               qty=int(md.get("qty_hint", 1)), dry_run=dry_run)
    elif surf == "ibkr_prediction":
        from adapters.ibkr import simulate_prediction_fill
        fr = simulate_prediction_fill(
            candidate.instrument,
            candidate.direction,
            md.get("yes_prices") or [],
            notional_usdc=candidate.sizing_usdc,
            metadata=md,
        )
    elif surf == "crypto":
        from adapters.crypto import paper_fill
        fr = paper_fill(candidate.instrument, candidate.direction,
                        notional_usdc=candidate.sizing_usdc)
    elif surf == "kalshi":
        from adapters.kalshi import paper_fill as kalshi_fill
        fr = kalshi_fill(
            candidate.instrument,
            candidate.direction,
            notional_usdc=candidate.sizing_usdc,
            yes_prices=md.get("yes_prices") or [],
            metadata=md,
        )
    else:
        raise ValueError(f"unknown surface {surf!r}")
    return fr


def _scorer_result_for_candidate(candidate: surface_router.Candidate) -> dict[str, Any] | None:
    if candidate.surface != "polymarket":
        return None
    md = candidate.metadata or {}
    existing = md.get("scorer_result")
    if isinstance(existing, dict):
        return existing
    from agent.scorer_bridge import score_candidate as score_polym
    yp = md.get("yes_prices") or []
    if not yp:
        return None
    gate = score_polym(price=yp[0], event_avg_yes_price=sum(yp[1:]) / max(1, len(yp) - 1))
    return asdict(gate)


def _require_execute_verdict_for_chain(verdict: judge.Verdict | None) -> None:
    if verdict is None:
        raise RuntimeError("live Arc wrap requires judge.classify() verdict")
    if verdict.label != judge.LABEL_EXECUTE:
        raise RuntimeError(
            f"live Arc wrap requires EXECUTE verdict, got {verdict.label}:{verdict.reason_code}"
        )


def wrap_position(candidate: surface_router.Candidate, fill_report: dict[str, Any],
                  signal: arb_identifier.ArbSignal | None, identity: dict[str, str],
                  expires_seconds: int = 600, dry_run: bool = True,
                  verdict: judge.Verdict | None = None) -> dict[str, Any]:
    """Wrap one filled candidate as an ERC-8183 job on Arc. Returns a dict with
    job_id and all tx hashes from the lifecycle. If `dry_run`, skips chain
    and returns a stub.
    """
    out_blob = _canonical_outcome_blob(asdict(candidate), fill_report, signal)
    deliverable_hash = _keccak_hex(out_blob)
    if dry_run:
        return {
            "dry_run": True,
            "deliverable_hash": deliverable_hash,
            "candidate_id": candidate.candidate_id,
        }
    _require_execute_verdict_for_chain(verdict)
    from agent import on_chain
    description = (
        f"surface={candidate.surface}|instrument={candidate.instrument}"
        f"|signal={candidate.arb_signal_id}"
    )
    client_id = identity["client_wallet_id"]
    client_addr = identity.get("client_wallet_addr", "")
    desk_id = identity["desk_wallet_id"]
    judge_id = identity["judge_wallet_id"]
    expired_at = int(time.time()) + int(expires_seconds)
    desk_addr = identity["desk_wallet_addr"]
    judge_addr = identity["judge_wallet_addr"]
    if not client_addr:
        raise RuntimeError("identity row missing client_wallet_addr; run Phase 2 open-position setup first")
    top_up = on_chain.ensure_client_usdc(
        desk_wallet_id=desk_id,
        client_wallet_id=client_id,
        client_wallet_addr=client_addr,
        min_usdc=float(candidate.sizing_usdc),
        top_up_usdc=max(2.0, float(candidate.sizing_usdc)),
    )
    if top_up is not None:
        _log_chain_tx("client_top_up", "", top_up)
    created = on_chain.create_job(
        wallet_id=client_id,
        provider=desk_addr,
        evaluator=judge_addr,
        expired_at=expired_at,
        description=description,
    )
    job_id_log = next((l for l in created.logs if l["event"] == "JobCreated"), None)
    if job_id_log is None:
        raise RuntimeError(f"JobCreated event not found in tx {created.tx_hash}")
    job_id = int(job_id_log["args"]["jobId"])
    # Provider sets the budget.
    budget = on_chain.set_budget(desk_id, job_id, float(candidate.sizing_usdc))
    # Client approves USDC and funds.
    approval = on_chain.approve_usdc(client_id, on_chain.AGENTIC_COMMERCE, float(candidate.sizing_usdc))
    funded = on_chain.fund_job(client_id, job_id)
    # Provider submits deliverable.
    submitted = on_chain.submit_deliverable(desk_id, job_id, deliverable_hash)
    for stage, tx in (
        ("create_job", created),
        ("set_budget", budget),
        ("approve_usdc", approval),
        ("fund_job", funded),
        ("submit_deliverable", submitted),
    ):
        _log_chain_tx(stage, job_id, tx)
    return {
        "dry_run": False,
        "job_id": job_id,
        "deliverable_hash": deliverable_hash,
        "create_tx": created.tx_hash,
        "set_budget_tx": budget.tx_hash,
        "approve_tx": approval.tx_hash,
        "fund_tx": funded.tx_hash,
        "submit_tx": submitted.tx_hash,
    }


def settle_position(job_id: int, candidate_dict: dict[str, Any], fill_report: dict[str, Any],
                    identity: dict[str, str], action: str, reason_code: str,
                    score: int, dry_run: bool = True) -> dict[str, Any]:
    """Evaluator settles. action ∈ {"complete", "reject"}. Both call complete()
    on chain; the reason hash distinguishes them offchain (delta D6).
    """
    out_blob, reason_blob = _settle_outcome_blob(candidate_dict, fill_report, action, reason_code)
    reason_hash = _keccak_hex(reason_blob)
    if dry_run:
        return {"dry_run": True, "reason_hash": reason_hash, "action": action}
    from agent import on_chain
    judge_id = identity["judge_wallet_id"]
    desk_agent_id = int(identity["desk_agent_id"])
    settle = on_chain.complete_job(judge_id, job_id, reason_hash)
    feedback_hash = _keccak_hex(reason_blob + str(score).encode())
    fb = on_chain.give_feedback(
        wallet_id=judge_id,
        agent_id=desk_agent_id,
        score=int(score),
        kind=0,
        tag=f"{action}:{reason_code}"[:32],
        feedback_hash_hex=feedback_hash,
    )
    _log_chain_tx("complete_job", job_id, settle)
    _log_chain_tx("give_feedback", job_id, fb)
    return {
        "dry_run": False,
        "job_id": job_id,
        "settle_tx": settle.tx_hash,
        "feedback_tx": fb.tx_hash,
        "reason_hash": reason_hash,
        "action": action,
        "score": score,
    }


def process_candidates(
    candidates: list[surface_router.Candidate],
    *,
    state: dict[str, Any],
    dry_run: bool,
    signal: arb_identifier.ArbSignal | None,
    identity: dict[str, str] | None = None,
    expires_seconds: int = 600,
    max_positions: int = 1,
) -> list[dict[str, Any]]:
    """Judge candidates and wrap only EXECUTE verdicts.

    This is the runtime's critical gate boundary. Tests monkeypatch
    `wrap_position` here to prove REJECT/DEFER paths have no chain side
    effect.
    """
    results: list[dict[str, Any]] = []
    executed_count = 0
    for cand in candidates:
        if executed_count >= max_positions:
            break
        cand_dict = asdict(cand)
        scorer_result = _scorer_result_for_candidate(cand)
        verdict = judge.classify(cand_dict, state, scorer_result)
        judge.log(verdict, cand_dict, scorer_result)
        print(f"  [{cand.surface}/{cand.instrument}] {verdict.label}: {verdict.reason_code}")
        if verdict.label != judge.LABEL_EXECUTE:
            results.append({"verdict": asdict(verdict), "candidate": cand_dict, "executed": False})
            continue
        action_key = _action_key(cand_dict)
        if _position_already_recorded(action_key):
            results.append({
                "verdict": {"label": judge.LABEL_DEFER, "reason_code": "duplicate_action_key", "confidence": 1.0},
                "candidate": cand_dict,
                "executed": False,
                "action_key": action_key,
            })
            continue
        fill = execute_candidate(cand, dry_run=dry_run, signal=signal)
        wrap = wrap_position(
            cand,
            fill,
            signal,
            identity or {},
            expires_seconds=expires_seconds,
            dry_run=dry_run,
            verdict=verdict,
        )
        results.append({
            "verdict": asdict(verdict),
            "candidate": cand_dict,
            "fill": fill,
            "wrap": wrap,
            "executed": True,
            "action_key": action_key,
        })
        executed_count += 1
        state["positions_open"] = state.get("positions_open", 0) + 1
        _append_position_row({
            "ts": time.time(),
            "stage": "open" if dry_run else "wrapped",
            "job_id": wrap.get("job_id", ""),
            "arb_signal_id": cand.arb_signal_id,
            "surface": cand.surface,
            "instrument": cand.instrument,
            "direction": cand.direction,
            "notional_usdc": cand.sizing_usdc,
            "deliverable_hash": wrap.get("deliverable_hash", ""),
            "reason_hash": "",
            "tx_hash": wrap.get("create_tx", ""),
            "fill_report_path": "",
            "action_key": action_key,
            **_public_leg_fields(cand_dict),
        })
    return results


def run_once(args: argparse.Namespace) -> int:
    """One scan-and-act cycle."""
    # 1. Acquire signal.
    if args.scan:
        pt = _live_spread(persist_source=not args.no_persist)
        signal = arb_identifier.score_signal(
            pt,
            threshold_z=args.z_threshold,
            forced=float(args.force_signal) if args.force_signal is not None else None,
            persist=not args.no_persist,
        )
        if signal is None:
            print(f"[runtime] z below threshold {args.z_threshold}; nothing to do "
                  f"(S_t={pt.S_t:.4f}, elec={pt.electricity_per_mwh:.2f}, "
                  f"compute={pt.compute_per_gpu_hr:.4f}).")
            return 0
    elif args.force_signal is not None:
        # Build a synthetic point so downstream still has region info.
        pt = arb_identifier.compute_spread(
            electricity_per_mwh=float(args.mock_elec or 80.0),
            compute_per_gpu_hr=float(args.mock_compute or 1.50),
            region="MOCK",
        )
        signal = arb_identifier.score_signal(pt, threshold_z=0.0,
                                              forced=float(args.force_signal),
                                              persist=not args.no_persist)
    elif args.once:
        pt = arb_identifier.compute_spread(
            electricity_per_mwh=float(args.mock_elec or 80.0),
            compute_per_gpu_hr=float(args.mock_compute or 1.50),
            region="MOCK",
        )
        signal = arb_identifier.score_signal(pt, threshold_z=0.0,
                                              forced=-2.0,
                                              persist=not args.no_persist)
    else:
        raise SystemExit("Specify one of: --scan, --once, --force-signal")

    assert signal is not None
    print(f"[runtime] signal {signal.signal_id}: direction={signal.direction} z={signal.z:.3f}")

    # 2. Route candidates. Default v1 is a canonical spread package: direct
    # prediction-event legs when available, then labelled liquid proxy legs.
    # `--polymarket-only` isolates the legacy S-4 path.
    candidates = _candidates_for_signal(
        signal,
        live_scan=bool(args.scan),
        multi_surface=bool(args.multi_surface),
        sizing_equity=args.sizing_equity,
        sizing_crypto=args.sizing_crypto,
        sizing_polymarket=args.sizing_polymarket,
        sizing_ibkr_prediction=args.sizing_ibkr_prediction,
        sizing_kalshi=getattr(args, "sizing_kalshi", 1.0),
    )
    if args.multi_surface:
        surfaces = ", ".join(sorted({c.surface for c in candidates})) or "none"
        print(f"[runtime] {len(candidates)} spread-package legs ({surfaces})")
    else:
        print(f"[runtime] {len(candidates)} experimental Polymarket candidates")
    if not candidates:
        return 0

    # 3. Judge + execute + wrap.
    state = judge.default_state()
    identity = None
    if not args.dry_run:
        identity = _identity_row()
    executed = process_candidates(
        candidates,
        state=state,
        dry_run=args.dry_run,
        signal=signal,
        identity=identity,
        expires_seconds=args.expires,
        max_positions=args.max_actions,
    )

    # 4. Optional settle pass (Phase 5 reconciliation): only when not dry-run
    #    and the caller asked for it.
    if args.settle and not args.dry_run and identity is not None:
        for r in executed:
            if not r.get("executed"):
                continue
            job_id = r["wrap"].get("job_id")
            if not job_id:
                continue
            cand_dict = r["candidate"]
            fill = r["fill"]
            # In v0, we naively mark the position complete with score = clipped(est * 100).
            score = max(0, min(95, int(float(cand_dict.get("est_pnl_per_dollar", 0)) * 1000)))
            settle = settle_position(int(job_id), cand_dict, fill, identity,
                                      action="complete", reason_code="paper_settle_v0",
                                      score=score, dry_run=args.dry_run)
            _append_position_row({
                "ts": time.time(),
                "stage": "settled",
                "job_id": job_id,
                "arb_signal_id": signal.signal_id,
                "surface": cand_dict.get("surface", ""),
                "instrument": cand_dict.get("instrument", ""),
                "direction": cand_dict.get("direction", ""),
                "notional_usdc": cand_dict.get("sizing_usdc", 0),
                "deliverable_hash": r["wrap"].get("deliverable_hash", ""),
                "reason_hash": settle.get("reason_hash", ""),
                "tx_hash": settle.get("settle_tx", ""),
                "fill_report_path": "",
                "action_key": r.get("action_key", ""),
                **_public_leg_fields(cand_dict),
            })

    print(f"[runtime] complete. {sum(1 for r in executed if r.get('executed'))} executed, "
          f"{sum(1 for r in executed if not r.get('executed'))} skipped.")
    return 0


def scan_once(
    *,
    max_positions: int = 1,
    dry_run: bool = True,
    settle: bool = False,
    no_persist: bool = False,
    sizing_equity: float = 1.0,
    sizing_crypto: float = 1.0,
    sizing_polymarket: float = 1.0,
    sizing_ibkr_prediction: float = 1.0,
    sizing_kalshi: float = 1.0,
    z_threshold: float = arb_identifier.DEFAULT_Z_THRESHOLD,
    multi_surface: bool = True,
) -> int:
    """Run the spread-package stateless scan exactly once and exit."""
    args = argparse.Namespace(
        scan=True,
        once=False,
        force_signal=None,
        mock_elec=None,
        mock_compute=None,
        z_threshold=z_threshold,
        sizing_equity=sizing_equity if multi_surface else 0.0,
        sizing_crypto=sizing_crypto if multi_surface else 0.0,
        sizing_polymarket=sizing_polymarket,
        sizing_ibkr_prediction=sizing_ibkr_prediction if multi_surface else 0.0,
        sizing_kalshi=sizing_kalshi if multi_surface else 0.0,
        multi_surface=multi_surface,
        max_actions=max_positions,
        expires=600,
        dry_run=dry_run,
        settle=settle,
        no_persist=no_persist,
    )
    return run_once(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arb securitization agent runtime")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--scan", action="store_true",
                      help="One live pass via EIA + AWS feeds (not a continuous loop — see module docstring)")
    mode.add_argument("--once", action="store_true",
                      help="One mock pass with synthetic signal params")
    parser.add_argument("--force-signal", type=float, default=None,
                        help="Force a z-score (bypasses threshold check)")
    parser.add_argument("--mock-elec", type=float, default=None,
                        help="Mock electricity $/MWh (used with --once / --force-signal)")
    parser.add_argument("--mock-compute", type=float, default=None,
                        help="Mock compute $/GPU-hr")
    parser.add_argument("--z-threshold", type=float, default=arb_identifier.DEFAULT_Z_THRESHOLD)
    parser.add_argument("--sizing-equity", type=float, default=1.0)
    parser.add_argument("--sizing-crypto", type=float, default=1.0)
    parser.add_argument("--sizing-polymarket", type=float, default=1.0)
    parser.add_argument("--sizing-ibkr-prediction", type=float, default=1.0)
    parser.add_argument("--sizing-kalshi", type=float, default=1.0)
    parser.set_defaults(multi_surface=True)
    parser.add_argument("--multi-surface", dest="multi_surface", action="store_true",
                        help="Route the canonical spread package across direct and proxy legs (default)")
    parser.add_argument("--polymarket-only", dest="multi_surface", action="store_false",
                        help="Route only the experimental S-4 Polymarket surface")
    parser.add_argument("--max-positions", "--max-actions", dest="max_actions", type=int, default=1,
                        help="Maximum wrapped positions for this one-shot run (default: 1)")
    parser.add_argument("--expires", type=int, default=600,
                        help="Job expiredAt offset in seconds")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Skip chain submission (default ON)")
    parser.add_argument("--live", dest="dry_run", action="store_false",
                        help="Disable dry-run; actually submit to Arc")
    parser.add_argument("--settle", action="store_true",
                        help="After wrap, also run the settle pass (requires --live)")
    parser.add_argument("--no-persist", action="store_true",
                        help="Don't append spread_history.tsv / arb_signals.tsv")
    args = parser.parse_args(argv)
    return run_once(args)


if __name__ == "__main__":
    sys.exit(main())
