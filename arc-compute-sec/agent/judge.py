"""4-way judge classifier. Runs on every Candidate before any chain action.

Labels:
    EXECUTE   - all gates pass; route to the adapter
    REJECT    - hard gate fails (size cap, premium gate, concurrency cap)
    DEFER     - usable in principle but data is stale or surface under-sampled
    CHALLENGE - non-trivial size with conviction asymmetry; v0 routes to DEFER
                (no debate loop yet)

State the judge reads:
    {
      "max_position_usdc": float,
      "challenge_threshold_usdc": float,
      "positions_open": int,
      "max_concurrent_positions": int,
      "max_data_age_seconds": int,
      "surface_resolutions_30d": dict[surface -> int],
      "min_resolutions_for_execute": int,
    }
"""
from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_JUDGEMENTS_PATH = Path(__file__).resolve().parent.parent / "logs" / "judgements.tsv"

LABEL_EXECUTE = "EXECUTE"
LABEL_REJECT = "REJECT"
LABEL_DEFER = "DEFER"
LABEL_CHALLENGE = "CHALLENGE"


@dataclass(frozen=True, slots=True)
class Verdict:
    label: str
    reason_code: str
    confidence: float


def default_state() -> dict[str, Any]:
    return {
        "max_position_usdc": 5.0,
        "challenge_threshold_usdc": 10.0,
        "positions_open": 0,
        "max_concurrent_positions": 6,
        "max_data_age_seconds": 60 * 30,        # 30 min
        "surface_resolutions_30d": {"polymarket": 1, "ibkr": 1, "crypto": 1},
        "min_resolutions_for_execute": 0,        # v0: don't gate on this
    }


def classify(
    candidate: dict[str, Any],
    state: dict[str, Any],
    scorer_result: dict[str, Any] | None = None,
) -> Verdict:
    """Apply the 4-way classifier to one candidate.

    `candidate` is the asdict() of `surface_router.Candidate` plus optional
    `data_age_seconds`. `scorer_result` is the GateResult.__dict__ for
    Polymarket-surface candidates only; ignored for other surfaces.
    """
    # REJECT — hard gates first
    if scorer_result is not None and not scorer_result.get("passes_gate", True):
        return Verdict(LABEL_REJECT, "premium_gate_fail", 1.0)

    notional = float(candidate.get("sizing_usdc", 0.0))
    if notional > float(state.get("max_position_usdc", 0.0)):
        return Verdict(LABEL_REJECT, "size_cap_breach", 1.0)

    if int(state.get("positions_open", 0)) >= int(state.get("max_concurrent_positions", 0)):
        return Verdict(LABEL_REJECT, "concurrency_cap", 1.0)

    # DEFER — data freshness / under-sampled surface
    surf = candidate.get("surface", "")
    surface_res = (state.get("surface_resolutions_30d") or {}).get(surf, 0)
    if surface_res < int(state.get("min_resolutions_for_execute", 0)):
        return Verdict(LABEL_DEFER, "surface_under_sampled", 0.8)

    age = float(candidate.get("data_age_seconds", 0.0))
    if age > float(state.get("max_data_age_seconds", 1e9)):
        return Verdict(LABEL_DEFER, "stale_data", 0.9)

    # CHALLENGE — non-trivial size; in v0 routes to DEFER
    if notional > float(state.get("challenge_threshold_usdc", 1e9)):
        return Verdict(LABEL_DEFER, "size_above_challenge_threshold_v0_defer", 0.6)

    # EXECUTE
    return Verdict(LABEL_EXECUTE, "all_gates_passed", 0.95)


def _action_hash(candidate: dict[str, Any]) -> str:
    h = hashlib.sha256(json.dumps(candidate, sort_keys=True, default=str).encode()).hexdigest()
    return h[:16]


def log(verdict: Verdict, candidate: dict[str, Any], scorer_result: dict[str, Any] | None = None) -> None:
    _JUDGEMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    new = not _JUDGEMENTS_PATH.exists()
    with _JUDGEMENTS_PATH.open("a", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        if new:
            writer.writerow([
                "ts", "arb_signal_id", "surface", "instrument", "direction",
                "sizing_usdc", "est_pnl_per_dollar", "action_kind",
                "action_payload_hash", "energy_template_id",
                "label", "reason_code", "confidence",
                "scorer_premium", "scorer_passes_gate",
            ])
        writer.writerow([
            f"{time.time():.0f}",
            candidate.get("arb_signal_id", ""),
            candidate.get("surface", ""),
            candidate.get("instrument", ""),
            candidate.get("direction", ""),
            f"{float(candidate.get('sizing_usdc', 0.0)):.6f}",
            f"{float(candidate.get('est_pnl_per_dollar', 0.0)):.6f}",
            "open_position",
            _action_hash(candidate),
            (candidate.get("metadata") or {}).get("energy_template_id", ""),
            verdict.label,
            verdict.reason_code,
            f"{verdict.confidence:.3f}",
            f"{(scorer_result or {}).get('premium', '')}",
            f"{(scorer_result or {}).get('passes_gate', '')}",
        ])
