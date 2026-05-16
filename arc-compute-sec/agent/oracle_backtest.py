"""Offline backtest for saved LLM-oracle receipts.

This module evaluates *saved* analyst/critic JSONL records against resolved
outcomes. It never calls Opoint, Nebius, Arc, Circle, Polymarket, or any other
external API. The oracle is treated as evidence only; the runtime judge and
premium gate remain the execution gates.

Accepted JSONL shape is intentionally close to the py-builder longtail audit
log:

{
  "event_id": "evt-1",
  "event_slug": "will-wti-close-above-90",
  "candidate_outcome": "YES",
  "side": "NO",
  "resolved_outcome": "NO",
  "realized_pnl": 0.03,
  "analyst": {
    "probabilities": {"YES": 0.20, "NO": 0.80},
    "confidence": 0.7
  },
  "critic": {"passed": true}
}

If `resolved_outcome` is absent from an oracle row, pass an outcomes JSONL with
records keyed by `event_id`, `event_slug`, or `candidate_id`.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class OracleCase:
    key: str
    probabilities: dict[str, float]
    resolved_outcome: str
    candidate_outcome: str | None
    side: str | None
    confidence: float | None
    realized_pnl: float | None
    critic_passed: bool


@dataclass(frozen=True, slots=True)
class CaseScore:
    key: str
    resolved_outcome: str
    top_outcome: str
    top_probability: float
    resolved_probability: float
    brier: float
    top1_hit: bool
    candidate_outcome: str | None
    side: str | None
    candidate_probability: float | None
    candidate_win: bool | None
    oracle_veto: bool | None
    realized_pnl: float | None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _key(record: dict[str, Any]) -> str:
    for field in ("candidate_id", "event_id", "event_slug", "slug", "market"):
        value = record.get(field)
        if value:
            return str(value)
    raise ValueError("record missing candidate_id/event_id/event_slug key")


def _keys(record: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for field in ("candidate_id", "event_id", "event_slug", "slug", "market"):
        value = record.get(field)
        if value:
            keys.append(str(value))
    return keys


def _probabilities(record: dict[str, Any]) -> dict[str, float]:
    raw = record.get("probabilities")
    if raw is None and isinstance(record.get("analyst"), dict):
        raw = record["analyst"].get("probabilities")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("record missing probabilities")
    out: dict[str, float] = {}
    for outcome, value in raw.items():
        p = _as_float(value)
        if p is None or not (0.0 <= p <= 1.0):
            raise ValueError(f"invalid probability for {outcome!r}: {value!r}")
        out[str(outcome)] = p
    total = sum(out.values())
    if not (0.95 <= total <= 1.05):
        raise ValueError(f"probabilities sum {total:.4f}, outside [0.95, 1.05]")
    return out


def _critic_passed(record: dict[str, Any]) -> bool:
    critic = record.get("critic")
    if critic is None:
        return True
    if not isinstance(critic, dict):
        return False
    return bool(critic.get("passed", False))


def _confidence(record: dict[str, Any]) -> float | None:
    value = record.get("confidence")
    if value is None and isinstance(record.get("analyst"), dict):
        value = record["analyst"].get("confidence")
    f = _as_float(value)
    if f is None:
        return None
    return max(0.0, min(1.0, f))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            records.append(record)
    return records


def load_outcomes(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    out: dict[str, str] = {}
    for record in load_jsonl(path):
        resolved = record.get("resolved_outcome") or record.get("resolution")
        if resolved is None:
            raise ValueError(f"outcome record missing resolved_outcome: {record}")
        for field in ("candidate_id", "event_id", "event_slug", "slug", "market"):
            value = record.get(field)
            if value:
                out[str(value)] = str(resolved)
    return out


def parse_cases(
    records: Iterable[dict[str, Any]],
    *,
    outcomes: dict[str, str] | None = None,
    include_critic_fail: bool = False,
) -> tuple[list[OracleCase], list[str]]:
    """Return valid cases and skip reasons.

    Critic-failed rows are skipped by default because critic rejection means the
    analyst output should not become positive execution evidence.
    """
    outcome_map = outcomes or {}
    cases: list[OracleCase] = []
    skips: list[str] = []
    for idx, record in enumerate(records, 1):
        try:
            key = _key(record)
            critic_passed = _critic_passed(record)
            if not critic_passed and not include_critic_fail:
                skips.append(f"{idx}:{key}:critic_failed")
                continue
            resolved = record.get("resolved_outcome") or record.get("resolution")
            if resolved is None:
                for candidate_key in _keys(record):
                    resolved = outcome_map.get(candidate_key)
                    if resolved is not None:
                        break
            if resolved is None:
                skips.append(f"{idx}:{key}:missing_resolution")
                continue
            probs = _probabilities(record)
            resolved_s = str(resolved)
            if resolved_s not in probs:
                skips.append(f"{idx}:{key}:resolution_not_in_probabilities")
                continue
            realized_pnl = _as_float(record.get("realized_pnl"))
            cases.append(OracleCase(
                key=key,
                probabilities=probs,
                resolved_outcome=resolved_s,
                candidate_outcome=(
                    str(record["candidate_outcome"])
                    if record.get("candidate_outcome") is not None
                    else None
                ),
                side=(str(record["side"]).upper() if record.get("side") is not None else None),
                confidence=_confidence(record),
                realized_pnl=realized_pnl,
                critic_passed=critic_passed,
            ))
        except ValueError as exc:
            skips.append(f"{idx}:invalid:{exc}")
    return cases, skips


def score_case(
    case: OracleCase,
    *,
    no_veto_threshold: float = 0.10,
    yes_min_probability: float = 0.50,
) -> CaseScore:
    top_outcome, top_probability = max(
        case.probabilities.items(),
        key=lambda item: item[1],
    )
    brier = sum(
        (p - (1.0 if outcome == case.resolved_outcome else 0.0)) ** 2
        for outcome, p in case.probabilities.items()
    )
    candidate_probability: float | None = None
    candidate_win: bool | None = None
    oracle_veto: bool | None = None
    side = case.side.upper() if case.side else None
    if case.candidate_outcome is not None and case.candidate_outcome in case.probabilities:
        candidate_probability = case.probabilities[case.candidate_outcome]
        if side in {"NO", "SHORT"}:
            candidate_win = case.resolved_outcome != case.candidate_outcome
            oracle_veto = candidate_probability > no_veto_threshold
        elif side in {"YES", "LONG"}:
            candidate_win = case.resolved_outcome == case.candidate_outcome
            oracle_veto = candidate_probability < yes_min_probability
    return CaseScore(
        key=case.key,
        resolved_outcome=case.resolved_outcome,
        top_outcome=top_outcome,
        top_probability=top_probability,
        resolved_probability=case.probabilities[case.resolved_outcome],
        brier=brier,
        top1_hit=top_outcome == case.resolved_outcome,
        candidate_outcome=case.candidate_outcome,
        side=case.side,
        candidate_probability=candidate_probability,
        candidate_win=candidate_win,
        oracle_veto=oracle_veto,
        realized_pnl=case.realized_pnl,
    )


def summarize(scores: list[CaseScore], *, n_records: int, n_skipped: int) -> dict[str, Any]:
    n = len(scores)
    candidate_scores = [s for s in scores if s.candidate_win is not None and s.oracle_veto is not None]
    vetoed = [s for s in candidate_scores if s.oracle_veto]
    kept = [s for s in candidate_scores if not s.oracle_veto]
    losses_filtered = [s for s in vetoed if s.candidate_win is False]
    wins_filtered = [s for s in vetoed if s.candidate_win is True]
    vetoed_pnl = sum(s.realized_pnl for s in vetoed if s.realized_pnl is not None)
    return {
        "records": n_records,
        "scored": n,
        "skipped": n_skipped,
        "coverage": (n / n_records) if n_records else 0.0,
        "mean_brier": _mean(s.brier for s in scores),
        "top1_accuracy": _mean(1.0 if s.top1_hit else 0.0 for s in scores),
        "mean_resolved_probability": _mean(s.resolved_probability for s in scores),
        "candidate_scored": len(candidate_scores),
        "candidate_win_rate": _mean(1.0 if s.candidate_win else 0.0 for s in candidate_scores),
        "vetoed": len(vetoed),
        "kept": len(kept),
        "vetoed_win_rate": _mean(1.0 if s.candidate_win else 0.0 for s in vetoed),
        "kept_win_rate": _mean(1.0 if s.candidate_win else 0.0 for s in kept),
        "losses_filtered": len(losses_filtered),
        "wins_filtered": len(wins_filtered),
        "vetoed_realized_pnl": vetoed_pnl,
        "oracle_saved_pnl_by_veto": -vetoed_pnl,
    }


def _mean(values: Iterable[float]) -> float | None:
    vals = list(values)
    if not vals:
        return None
    return sum(vals) / len(vals)


def render_report(metrics: dict[str, Any], *, skips: list[str]) -> str:
    def fmt(value: Any) -> str:
        if value is None:
            return "n/a"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    lines = [
        "# Oracle Backtest Report",
        "",
        "Offline replay of saved oracle receipts. No external API calls.",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in (
        "records",
        "scored",
        "skipped",
        "coverage",
        "mean_brier",
        "top1_accuracy",
        "mean_resolved_probability",
        "candidate_scored",
        "candidate_win_rate",
        "vetoed",
        "kept",
        "vetoed_win_rate",
        "kept_win_rate",
        "losses_filtered",
        "wins_filtered",
        "vetoed_realized_pnl",
        "oracle_saved_pnl_by_veto",
    ):
        lines.append(f"| `{key}` | {fmt(metrics.get(key))} |")
    if skips:
        lines.extend(["", "## Skips", ""])
        for reason in skips[:50]:
            lines.append(f"- `{reason}`")
        if len(skips) > 50:
            lines.append(f"- `... {len(skips) - 50} more`")
    return "\n".join(lines) + "\n"


def run_backtest(
    *,
    oracle_jsonl: Path,
    outcomes_jsonl: Path | None = None,
    include_critic_fail: bool = False,
    no_veto_threshold: float = 0.10,
    yes_min_probability: float = 0.50,
) -> tuple[dict[str, Any], list[CaseScore], list[str]]:
    records = load_jsonl(oracle_jsonl)
    outcomes = load_outcomes(outcomes_jsonl)
    cases, skips = parse_cases(
        records,
        outcomes=outcomes,
        include_critic_fail=include_critic_fail,
    )
    scores = [
        score_case(
            c,
            no_veto_threshold=no_veto_threshold,
            yes_min_probability=yes_min_probability,
        )
        for c in cases
    ]
    metrics = summarize(scores, n_records=len(records), n_skipped=len(skips))
    return metrics, scores, skips


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline backtest for saved LLM-oracle receipts")
    parser.add_argument("--oracle-jsonl", type=Path, required=True,
                        help="Saved oracle analysis JSONL")
    parser.add_argument("--outcomes-jsonl", type=Path,
                        help="Optional resolved outcomes JSONL")
    parser.add_argument("--include-critic-fail", action="store_true",
                        help="Include critic-failed rows instead of skipping them")
    parser.add_argument("--no-veto-threshold", type=float, default=0.10,
                        help="For NO/SHORT candidates, veto when P(candidate YES) exceeds this")
    parser.add_argument("--yes-min-probability", type=float, default=0.50,
                        help="For YES/LONG candidates, veto when P(candidate outcome) is below this")
    parser.add_argument("--report-out", type=Path,
                        help="Write markdown report to this path")
    parser.add_argument("--metrics-out", type=Path,
                        help="Write metrics JSON to this path")
    parser.add_argument("--scores-out", type=Path,
                        help="Write per-case scores JSONL to this path")
    args = parser.parse_args(argv)

    metrics, scores, skips = run_backtest(
        oracle_jsonl=args.oracle_jsonl,
        outcomes_jsonl=args.outcomes_jsonl,
        include_critic_fail=args.include_critic_fail,
        no_veto_threshold=args.no_veto_threshold,
        yes_min_probability=args.yes_min_probability,
    )
    report = render_report(metrics, skips=skips)
    print(report, end="")
    if args.report_out:
        args.report_out.write_text(report, encoding="utf-8")
    if args.metrics_out:
        args.metrics_out.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    if args.scores_out:
        with args.scores_out.open("w", encoding="utf-8") as fh:
            for score in scores:
                fh.write(json.dumps(asdict(score), sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
