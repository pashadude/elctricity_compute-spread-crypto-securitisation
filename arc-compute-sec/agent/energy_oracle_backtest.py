"""Offline S-4 energy verification over historical fill rows.

This is deliberately local and deterministic. It does not call Opoint, Nebius,
Arc, Circle, Polymarket, IBKR, or any external API. By default it verifies the
v0 desk's hard pre-chain premium gate over current repo data:

    historical fill -> energy classifier -> S-4 non-negative premium gate

When `--llm-receipts-jsonl` is supplied, it also overlays saved Opoint+Nebius
LLM oracle receipts and scores those decisions against resolved fills.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from agent.scorer_bridge import score_candidate
from templates.energy.classifier import classify_energy


DEFAULT_MASTER_FILLS = Path(__file__).resolve().parent.parent / "data" / "master_fills_v4.tsv"


@dataclass(frozen=True, slots=True)
class OracleFill:
    fill_ts: str
    slug: str
    event_slug: str
    condition_id: str
    energy_template_id: str
    entry_price: float
    premium: float
    realized_pnl: float
    win: bool
    category: str
    cadence: str
    gate_premium: float
    oracle_verdict: str
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class LlmDecision:
    verdict: str
    p_yes: float | None
    reason_code: str | None
    receipt: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SegmentMetrics:
    n: int
    wr: float | None
    pnl: float


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pseudo_title(row: dict[str, str]) -> str:
    return f"{row.get('slug') or ''} {row.get('event_slug') or ''}".strip()


def _score_premium_gate(row: dict[str, str]) -> tuple[bool, float, str | None]:
    """Run the row through the same non-negative premium invariant as S-4.

    `master_fills_v4.tsv` stores the historical scalar premium directly. The
    scorer bridge expects `(price, event_avg_yes_price)`, so reconstruct an
    equivalent pair where `price + event_avg_yes_price - 1 == premium`.
    """
    entry_price = _as_float(row.get("entry_price"))
    premium = _as_float(row.get("premium"))
    if premium < 0:
        return False, premium, "premium_gate_fail"
    event_avg_yes_price = 1.0 + premium - entry_price
    # Historical rows are rounded; clamp tiny float noise but preserve the
    # premium sign that the scorer gate enforces.
    event_avg_yes_price = max(0.0, min(1.0, event_avg_yes_price))
    gate = score_candidate(
        price=entry_price,
        event_avg_yes_price=event_avg_yes_price,
    )
    if gate.passes_gate:
        return True, gate.premium, None
    return False, gate.premium, "premium_gate_fail"


def load_energy_fills(path: Path) -> list[OracleFill]:
    fills: list[OracleFill] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            template = classify_energy(
                title=_pseudo_title(row),
                description="",
                upstream_category=row.get("category"),
            )
            if template is None:
                continue
            passes_gate, gate_premium, reason_code = _score_premium_gate(row)
            fills.append(OracleFill(
                fill_ts=row.get("fill_ts") or "",
                slug=row.get("slug") or "",
                event_slug=row.get("event_slug") or "",
                condition_id=row.get("condition_id") or "",
                energy_template_id=template,
                entry_price=_as_float(row.get("entry_price")),
                premium=_as_float(row.get("premium")),
                realized_pnl=_as_float(row.get("realized_pnl")),
                win=(row.get("resolution_outcome") == "WIN"),
                category=row.get("category") or "",
                cadence=row.get("cadence") or "",
                gate_premium=gate_premium,
                oracle_verdict="KEEP" if passes_gate else "VETO",
                reason_code=reason_code,
            ))
    return fills


def metrics(rows: Iterable[OracleFill]) -> SegmentMetrics:
    materialized = list(rows)
    n = len(materialized)
    return SegmentMetrics(
        n=n,
        wr=(sum(1 for r in materialized if r.win) / n) if n else None,
        pnl=sum(r.realized_pnl for r in materialized),
    )


def _by_template(rows: Iterable[OracleFill]) -> dict[str, SegmentMetrics]:
    grouped: dict[str, list[OracleFill]] = {}
    for row in rows:
        grouped.setdefault(row.energy_template_id, []).append(row)
    return {template: metrics(items) for template, items in sorted(grouped.items())}


def _fill_keys(fill: OracleFill) -> list[str]:
    return [x for x in (fill.condition_id, fill.slug, fill.event_slug) if x]


def _receipt_keys(record: dict[str, Any]) -> list[str]:
    return [
        str(x)
        for x in (
            record.get("condition_id"),
            record.get("slug"),
            record.get("event_slug"),
        )
        if x
    ]


def load_llm_decisions(path: Path | None) -> dict[str, LlmDecision]:
    if path is None:
        return {}
    decisions: dict[str, LlmDecision] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            verdict = str(record.get("verdict") or "").upper()
            if verdict not in {"KEEP", "VETO", "DEFER"}:
                raise ValueError(f"{path}:{line_no}: invalid LLM verdict {verdict!r}")
            p_yes = _as_float(record.get("p_yes")) if record.get("p_yes") is not None else None
            decision = LlmDecision(
                verdict=verdict,
                p_yes=p_yes,
                reason_code=str(record.get("reason_code") or "") or None,
                receipt=record,
            )
            keys = _receipt_keys(record)
            if not keys:
                raise ValueError(f"{path}:{line_no}: missing condition_id/slug/event_slug")
            for key in keys:
                decisions[key] = decision
    return decisions


def _lookup_llm(fill: OracleFill, decisions: dict[str, LlmDecision]) -> LlmDecision | None:
    for key in _fill_keys(fill):
        decision = decisions.get(key)
        if decision is not None:
            return decision
    return None


def _summarize_llm_overlay(
    fills: list[OracleFill],
    decisions: dict[str, LlmDecision],
) -> dict[str, Any] | None:
    if not decisions:
        return None
    covered_pairs = [(fill, _lookup_llm(fill, decisions)) for fill in fills]
    covered = [(fill, decision) for fill, decision in covered_pairs if decision is not None]
    covered_fills = [fill for fill, _decision in covered]
    kept = [fill for fill, decision in covered if decision and decision.verdict == "KEEP"]
    vetoed = [fill for fill, decision in covered if decision and decision.verdict == "VETO"]
    deferred = [fill for fill, decision in covered if decision and decision.verdict == "DEFER"]
    covered_baseline = metrics(covered_fills)
    llm_kept = metrics(kept)
    llm_vetoed = metrics(vetoed)
    return {
        "coverage": {
            "receipts": len(decisions),
            "covered_fills": len(covered_fills),
            "uncovered_fills": len(fills) - len(covered_fills),
        },
        "covered_baseline": asdict(covered_baseline),
        "llm_kept": asdict(llm_kept),
        "llm_vetoed": asdict(llm_vetoed),
        "llm_deferred": asdict(metrics(deferred)),
        "improvement": {
            "kept_pnl_minus_covered_baseline_pnl": llm_kept.pnl - covered_baseline.pnl,
            "kept_wr_minus_covered_baseline_wr": (
                None if covered_baseline.wr is None or llm_kept.wr is None
                else llm_kept.wr - covered_baseline.wr
            ),
            "losses_vetoed": sum(1 for fill in vetoed if not fill.win),
            "wins_vetoed": sum(1 for fill in vetoed if fill.win),
            "vetoed_pnl": llm_vetoed.pnl,
        },
    }


def summarize(
    fills: list[OracleFill],
    *,
    llm_decisions: dict[str, LlmDecision] | None = None,
) -> dict[str, Any]:
    kept = [f for f in fills if f.oracle_verdict == "KEEP"]
    vetoed = [f for f in fills if f.oracle_verdict == "VETO"]
    baseline = metrics(fills)
    gate = metrics(kept)
    rejected = metrics(vetoed)
    summary = {
        "policy": "energy_classifier_plus_s4_non_negative_premium_gate",
        "baseline": asdict(baseline),
        "gate_kept": asdict(gate),
        "gate_vetoed": asdict(rejected),
        "improvement": {
            "kept_pnl_minus_baseline_pnl": gate.pnl - baseline.pnl,
            "kept_wr_minus_baseline_wr": (
                None if baseline.wr is None or gate.wr is None else gate.wr - baseline.wr
            ),
            "vetoed_pnl": rejected.pnl,
            "losses_vetoed": sum(1 for f in vetoed if not f.win),
            "wins_vetoed": sum(1 for f in vetoed if f.win),
        },
        "by_template": {
            template: {
                "baseline": asdict(base),
                "gate_kept": asdict(_by_template(kept).get(template, SegmentMetrics(0, None, 0.0))),
                "gate_vetoed": asdict(_by_template(vetoed).get(template, SegmentMetrics(0, None, 0.0))),
            }
            for template, base in _by_template(fills).items()
        },
    }
    llm_overlay = _summarize_llm_overlay(fills, llm_decisions or {})
    if llm_overlay is not None:
        summary["llm_oracle"] = llm_overlay
    return summary


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_report(summary: dict[str, Any]) -> str:
    baseline = summary["baseline"]
    kept = summary["gate_kept"]
    vetoed = summary["gate_vetoed"]
    improvement = summary["improvement"]
    lines = [
        "# Energy Gate Backtest Report",
        "",
        "Offline replay over `master_fills_v4.tsv`. No external API calls.",
        "",
        f"Policy: `{summary['policy']}`",
        "",
        "| Segment | Fills | WR | PnL |",
        "|---|---:|---:|---:|",
        f"| Baseline energy-classified | {baseline['n']} | {_fmt(baseline['wr'])} | {_fmt(baseline['pnl'])} |",
        f"| Premium-gate kept | {kept['n']} | {_fmt(kept['wr'])} | {_fmt(kept['pnl'])} |",
        f"| Premium-gate vetoed | {vetoed['n']} | {_fmt(vetoed['wr'])} | {_fmt(vetoed['pnl'])} |",
        "",
        "| Improvement | Value |",
        "|---|---:|",
        f"| Kept PnL minus baseline PnL | {_fmt(improvement['kept_pnl_minus_baseline_pnl'])} |",
        f"| Kept WR minus baseline WR | {_fmt(improvement['kept_wr_minus_baseline_wr'])} |",
        f"| Losses vetoed | {improvement['losses_vetoed']} |",
        f"| Wins vetoed | {improvement['wins_vetoed']} |",
        f"| Vetoed PnL | {_fmt(improvement['vetoed_pnl'])} |",
        "",
        "| Template | Baseline n | Baseline WR | Baseline PnL | Gate kept n | Gate kept WR | Gate kept PnL | Gate vetoed n | Gate vetoed PnL |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for template, row in summary["by_template"].items():
        b = row["baseline"]
        k = row["gate_kept"]
        v = row["gate_vetoed"]
        lines.append(
            f"| `{template}` | {b['n']} | {_fmt(b['wr'])} | {_fmt(b['pnl'])} | "
            f"{k['n']} | {_fmt(k['wr'])} | {_fmt(k['pnl'])} | "
            f"{v['n']} | {_fmt(v['pnl'])} |"
        )
    if "llm_oracle" in summary:
        llm = summary["llm_oracle"]
        cov = llm["coverage"]
        b = llm["covered_baseline"]
        k = llm["llm_kept"]
        v = llm["llm_vetoed"]
        d = llm["llm_deferred"]
        imp = llm["improvement"]
        lines.extend([
            "",
            "## Opoint+Nebius LLM Overlay",
            "",
            f"Receipts: {cov['receipts']}; covered fills: {cov['covered_fills']}; uncovered fills: {cov['uncovered_fills']}.",
            "",
            "| Segment | Fills | WR | PnL |",
            "|---|---:|---:|---:|",
            f"| Covered baseline | {b['n']} | {_fmt(b['wr'])} | {_fmt(b['pnl'])} |",
            f"| LLM kept | {k['n']} | {_fmt(k['wr'])} | {_fmt(k['pnl'])} |",
            f"| LLM vetoed | {v['n']} | {_fmt(v['wr'])} | {_fmt(v['pnl'])} |",
            f"| LLM deferred | {d['n']} | {_fmt(d['wr'])} | {_fmt(d['pnl'])} |",
            "",
            "| LLM improvement | Value |",
            "|---|---:|",
            f"| Kept PnL minus covered baseline PnL | {_fmt(imp['kept_pnl_minus_covered_baseline_pnl'])} |",
            f"| Kept WR minus covered baseline WR | {_fmt(imp['kept_wr_minus_covered_baseline_wr'])} |",
            f"| Losses vetoed | {imp['losses_vetoed']} |",
            f"| Wins vetoed | {imp['wins_vetoed']} |",
            f"| Vetoed PnL | {_fmt(imp['vetoed_pnl'])} |",
        ])
    return "\n".join(lines) + "\n"


def write_decisions(path: Path, fills: Iterable[OracleFill]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for fill in fills:
            fh.write(json.dumps(asdict(fill), sort_keys=True) + "\n")


def run(
    master_fills_tsv: Path = DEFAULT_MASTER_FILLS,
    *,
    llm_receipts_jsonl: Path | None = None,
) -> tuple[dict[str, Any], list[OracleFill]]:
    fills = load_energy_fills(master_fills_tsv)
    llm_decisions = load_llm_decisions(llm_receipts_jsonl)
    return summarize(fills, llm_decisions=llm_decisions), fills


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline S-4 energy oracle backtest over historical fills",
    )
    parser.add_argument("--master-fills-tsv", type=Path, default=DEFAULT_MASTER_FILLS)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--metrics-out", type=Path)
    parser.add_argument("--decisions-out", type=Path)
    parser.add_argument("--llm-receipts-jsonl", type=Path,
                        help="Saved Opoint+Nebius oracle receipts to overlay")
    args = parser.parse_args(argv)

    summary, fills = run(args.master_fills_tsv, llm_receipts_jsonl=args.llm_receipts_jsonl)
    report = render_report(summary)
    print(report, end="")
    if args.report_out:
        args.report_out.write_text(report, encoding="utf-8")
    if args.metrics_out:
        args.metrics_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if args.decisions_out:
        write_decisions(args.decisions_out, fills)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
