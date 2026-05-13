"""Agent runtime — orchestrates one --scan or --once cycle.

  arb_identifier  →  surface_router  →  adapters  →  judge  →  on_chain
                                                              wrap + settle

Modes:
    --scan          live: fetch EIA + AWS, compute signal, route, execute
    --once          single mock signal (operator-provided params)
    --force-signal  override z-score (still uses live feeds; useful when
                    market is calm and we need the demo to fire)

This module DOES write to chain when run with the chain flags below. By
default `--dry-run` is on, so a session that's still in pre-Gate-A doesn't
accidentally try to call Circle without credentials.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent import arb_identifier, judge, surface_router
from agent.pnl_probe import estimate as pnl_estimate

_POSITIONS_PATH = Path(__file__).resolve().parent.parent / "logs" / "positions.tsv"
_RECON_PATH = Path(__file__).resolve().parent.parent / "logs" / "pnl_reconciliation.tsv"


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
        "ts": time.time(),
    }
    return json.dumps(blob, sort_keys=True, default=str).encode()


def _append_position_row(row: dict[str, Any]) -> None:
    _POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    new = not _POSITIONS_PATH.exists()
    headers = [
        "ts", "stage", "job_id", "arb_signal_id", "surface", "instrument",
        "direction", "notional_usdc", "deliverable_hash", "reason_hash",
        "tx_hash", "fill_report_path",
    ]
    with _POSITIONS_PATH.open("a", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        if new:
            writer.writerow(headers)
        writer.writerow([str(row.get(h, "")) for h in headers])


def _live_spread() -> arb_identifier.SpreadPoint:
    """Fetch live EIA + AWS feeds and compute the latest spread."""
    from feeds.eia import fetch_regions, ERCOT
    from feeds.aws_spot import fetch_gpu_spot
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
    return arb_identifier.compute_spread(
        electricity_per_mwh=elec.value_mwh,
        compute_per_gpu_hr=aws_min.price_per_gpu_hour,
        region="ERCOT|us-east-1",
    )


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
            "yes_prices": [0.40, 0.40, 0.23],   # sum = 1.03, premium +0.03
            "energy_template_id": energy_template,
            "title": "Mock: oil price > $X in Q3",
        }
    ]


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
    elif surf == "crypto":
        from adapters.crypto import paper_fill
        fr = paper_fill(candidate.instrument, candidate.direction,
                        notional_usdc=candidate.sizing_usdc)
    elif surf == "kalshi":
        from adapters.kalshi import paper_fill as kalshi_fill
        fr = kalshi_fill(candidate.instrument, candidate.direction,
                          notional_usdc=candidate.sizing_usdc)
    else:
        raise ValueError(f"unknown surface {surf!r}")
    return fr


def wrap_position(candidate: surface_router.Candidate, fill_report: dict[str, Any],
                  signal: arb_identifier.ArbSignal | None, identity: dict[str, str],
                  expires_seconds: int = 600, dry_run: bool = True) -> dict[str, Any]:
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
    from agent import on_chain
    description = (
        f"surface={candidate.surface}|instrument={candidate.instrument}"
        f"|signal={candidate.arb_signal_id}"
    )
    client_id = identity["client_wallet_id"]
    desk_id = identity["desk_wallet_id"]
    judge_id = identity["judge_wallet_id"]
    expired_at = int(time.time()) + int(expires_seconds)
    desk_addr = identity["desk_wallet_addr"]
    judge_addr = identity["judge_wallet_addr"]
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
    on_chain.set_budget(desk_id, job_id, float(candidate.sizing_usdc))
    # Client approves USDC and funds.
    on_chain.approve_usdc(client_id, on_chain.AGENTIC_COMMERCE, float(candidate.sizing_usdc))
    on_chain.fund_job(client_id, job_id)
    # Provider submits deliverable.
    on_chain.submit_deliverable(desk_id, job_id, deliverable_hash)
    return {
        "dry_run": False,
        "job_id": job_id,
        "deliverable_hash": deliverable_hash,
        "create_tx": created.tx_hash,
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
    return {
        "dry_run": False,
        "job_id": job_id,
        "settle_tx": settle.tx_hash,
        "feedback_tx": fb.tx_hash,
        "reason_hash": reason_hash,
        "action": action,
        "score": score,
    }


def run_once(args: argparse.Namespace) -> int:
    """One scan-and-act cycle."""
    # 1. Acquire signal.
    if args.force_signal is not None:
        # Build a synthetic point so downstream still has region info.
        pt = arb_identifier.compute_spread(
            electricity_per_mwh=float(args.mock_elec or 80.0),
            compute_per_gpu_hr=float(args.mock_compute or 1.50),
            region="MOCK",
        )
        signal = arb_identifier.score_signal(pt, threshold_z=0.0,
                                              forced=float(args.force_signal),
                                              persist=not args.no_persist)
    elif args.scan:
        pt = _live_spread()
        signal = arb_identifier.score_signal(pt, threshold_z=args.z_threshold,
                                              persist=not args.no_persist)
        if signal is None:
            print(f"[runtime] z below threshold {args.z_threshold}; nothing to do "
                  f"(S_t={pt.S_t:.4f}, elec={pt.electricity_per_mwh:.2f}, "
                  f"compute={pt.compute_per_gpu_hr:.4f}).")
            return 0
    else:
        raise SystemExit("Specify one of: --scan, --force-signal")

    assert signal is not None
    print(f"[runtime] signal {signal.signal_id}: direction={signal.direction} z={signal.z:.3f}")

    # 2. Route to candidates.
    polym_events = _mock_polymarket_events(signal.direction)
    candidates = surface_router.route(
        signal,
        polymarket_events=polym_events,
        sizing_per_equity_usdc=args.sizing_equity,
        sizing_crypto_usdc=args.sizing_crypto,
        sizing_polymarket_usdc=args.sizing_polymarket,
    )
    print(f"[runtime] {len(candidates)} candidates across surfaces")
    if not candidates:
        return 0

    # 3. Judge + execute + wrap.
    state = judge.default_state()
    identity = None
    if not args.dry_run:
        identity = _identity_row()
    executed: list[dict] = []
    for cand in candidates[: args.max_actions]:
        cand_dict = asdict(cand)
        scorer_result = None
        if cand.surface == "polymarket":
            from agent.scorer_bridge import score_candidate as score_polym
            yp = (cand.metadata or {}).get("yes_prices") or []
            if yp:
                gate = score_polym(price=yp[0], event_avg_yes_price=sum(yp[1:])/max(1, len(yp)-1))
                scorer_result = gate.__dict__
        verdict = judge.classify(cand_dict, state, scorer_result)
        judge.log(verdict, cand_dict, scorer_result)
        print(f"  [{cand.surface}/{cand.instrument}] {verdict.label}: {verdict.reason_code}")
        if verdict.label != "EXECUTE":
            executed.append({"verdict": asdict(verdict), "candidate": cand_dict, "executed": False})
            continue
        fill = execute_candidate(cand, dry_run=args.dry_run, signal=signal)
        wrap = wrap_position(cand, fill, signal, identity or {}, expires_seconds=args.expires,
                             dry_run=args.dry_run)
        executed.append({"verdict": asdict(verdict), "candidate": cand_dict,
                         "fill": fill, "wrap": wrap, "executed": True})
        state["positions_open"] = state.get("positions_open", 0) + 1
        # Append a position row immediately (open stage).
        _append_position_row({
            "ts": time.time(),
            "stage": "open" if args.dry_run else "wrapped",
            "job_id": wrap.get("job_id", ""),
            "arb_signal_id": signal.signal_id,
            "surface": cand.surface,
            "instrument": cand.instrument,
            "direction": cand.direction,
            "notional_usdc": cand.sizing_usdc,
            "deliverable_hash": wrap.get("deliverable_hash", ""),
            "reason_hash": "",
            "tx_hash": wrap.get("create_tx", ""),
            "fill_report_path": "",
        })

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
            })

    print(f"[runtime] complete. {sum(1 for r in executed if r.get('executed'))} executed, "
          f"{sum(1 for r in executed if not r.get('executed'))} skipped.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arb securitization agent runtime")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--scan", action="store_true", help="Live scan via EIA + AWS feeds")
    mode.add_argument("--once", action="store_true", help="Single mock cycle")
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
    parser.add_argument("--max-actions", type=int, default=6)
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
