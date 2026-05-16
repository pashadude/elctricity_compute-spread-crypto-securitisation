"""Offline S-4 energy oracle verification over historical fill rows.

This is deliberately local and deterministic. It does not call Opoint, Nebius,
Arc, Circle, Polymarket, IBKR, or any external API. The "oracle" verified here
is the v0 desk's auditable pre-chain evidence stack over current repo data:

    historical fill -> energy classifier -> S-4 non-negative premium gate

The output answers whether the Phase 3 backward-window energy figures improve
once the v0 premium-gated oracle policy is applied.
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


def summarize(fills: list[OracleFill]) -> dict[str, Any]:
    kept = [f for f in fills if f.oracle_verdict == "KEEP"]
    vetoed = [f for f in fills if f.oracle_verdict == "VETO"]
    baseline = metrics(fills)
    oracle = metrics(kept)
    rejected = metrics(vetoed)
    return {
        "policy": "energy_classifier_plus_s4_non_negative_premium_gate",
        "baseline": asdict(baseline),
        "oracle_kept": asdict(oracle),
        "oracle_vetoed": asdict(rejected),
        "improvement": {
            "kept_pnl_minus_baseline_pnl": oracle.pnl - baseline.pnl,
            "kept_wr_minus_baseline_wr": (
                None if baseline.wr is None or oracle.wr is None else oracle.wr - baseline.wr
            ),
            "vetoed_pnl": rejected.pnl,
            "losses_vetoed": sum(1 for f in vetoed if not f.win),
            "wins_vetoed": sum(1 for f in vetoed if f.win),
        },
        "by_template": {
            template: {
                "baseline": asdict(base),
                "oracle_kept": asdict(_by_template(kept).get(template, SegmentMetrics(0, None, 0.0))),
                "oracle_vetoed": asdict(_by_template(vetoed).get(template, SegmentMetrics(0, None, 0.0))),
            }
            for template, base in _by_template(fills).items()
        },
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_report(summary: dict[str, Any]) -> str:
    baseline = summary["baseline"]
    kept = summary["oracle_kept"]
    vetoed = summary["oracle_vetoed"]
    improvement = summary["improvement"]
    lines = [
        "# Energy Oracle Backtest Report",
        "",
        "Offline replay over `master_fills_v4.tsv`. No external API calls.",
        "",
        f"Policy: `{summary['policy']}`",
        "",
        "| Segment | Fills | WR | PnL |",
        "|---|---:|---:|---:|",
        f"| Baseline energy-classified | {baseline['n']} | {_fmt(baseline['wr'])} | {_fmt(baseline['pnl'])} |",
        f"| Oracle kept | {kept['n']} | {_fmt(kept['wr'])} | {_fmt(kept['pnl'])} |",
        f"| Oracle vetoed | {vetoed['n']} | {_fmt(vetoed['wr'])} | {_fmt(vetoed['pnl'])} |",
        "",
        "| Improvement | Value |",
        "|---|---:|",
        f"| Kept PnL minus baseline PnL | {_fmt(improvement['kept_pnl_minus_baseline_pnl'])} |",
        f"| Kept WR minus baseline WR | {_fmt(improvement['kept_wr_minus_baseline_wr'])} |",
        f"| Losses vetoed | {improvement['losses_vetoed']} |",
        f"| Wins vetoed | {improvement['wins_vetoed']} |",
        f"| Vetoed PnL | {_fmt(improvement['vetoed_pnl'])} |",
        "",
        "| Template | Baseline n | Baseline WR | Baseline PnL | Kept n | Kept WR | Kept PnL | Vetoed n | Vetoed PnL |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for template, row in summary["by_template"].items():
        b = row["baseline"]
        k = row["oracle_kept"]
        v = row["oracle_vetoed"]
        lines.append(
            f"| `{template}` | {b['n']} | {_fmt(b['wr'])} | {_fmt(b['pnl'])} | "
            f"{k['n']} | {_fmt(k['wr'])} | {_fmt(k['pnl'])} | "
            f"{v['n']} | {_fmt(v['pnl'])} |"
        )
    return "\n".join(lines) + "\n"


def write_decisions(path: Path, fills: Iterable[OracleFill]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for fill in fills:
            fh.write(json.dumps(asdict(fill), sort_keys=True) + "\n")


def run(master_fills_tsv: Path = DEFAULT_MASTER_FILLS) -> tuple[dict[str, Any], list[OracleFill]]:
    fills = load_energy_fills(master_fills_tsv)
    return summarize(fills), fills


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline S-4 energy oracle backtest over historical fills",
    )
    parser.add_argument("--master-fills-tsv", type=Path, default=DEFAULT_MASTER_FILLS)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--metrics-out", type=Path)
    parser.add_argument("--decisions-out", type=Path)
    args = parser.parse_args(argv)

    summary, fills = run(args.master_fills_tsv)
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
