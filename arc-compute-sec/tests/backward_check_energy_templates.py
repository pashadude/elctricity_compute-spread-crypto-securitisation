"""Phase 3 backward-window check (adapted to real TSV columns).

DRIFT from prior TASK.md (delta D4): real columns are
  - `resolution_outcome` ∈ {WIN, LOSS}   (not `outcome_win`)
  - `realized_pnl`                        (not `face_value_pnl`)
  - `slug`, `event_slug`                  (no `title`/`description` cols)

Pseudo-title := slug + event_slug.

Writes the result to `templates/energy/backward_check.txt` so it can be
committed alongside the classifier.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from templates.energy.classifier import classify_energy

TSV_PATH = _ROOT / "data" / "master_fills_v4.tsv"
OUT_PATH = _ROOT / "templates" / "energy" / "backward_check.txt"


def run() -> None:
    df = pd.read_csv(TSV_PATH, sep="\t")
    df["pseudo_title"] = df["slug"].fillna("") + " " + df["event_slug"].fillna("")
    df["energy_template_id"] = df.apply(
        lambda r: classify_energy(r["pseudo_title"], "", r.get("category")), axis=1,
    )
    df["win"] = (df["resolution_outcome"] == "WIN").astype(int)
    caught = df[df["energy_template_id"].notna()]

    lines: list[str] = []
    lines.append(f"# Backward-window energy classifier check — {pd.Timestamp.utcnow().isoformat()}Z")
    lines.append(f"Total fills:        {len(df)}")
    lines.append(f"Energy-classified:  {len(caught)}")
    lines.append("")
    if len(caught) == 0:
        lines.append("WARNING: no energy-classified fills. Classifier too narrow OR TSV pseudo-title coverage is weak.")
        lines.append("")
    else:
        grouped = caught.groupby("energy_template_id").agg(
            n=("slug", "count"),
            wr=("win", "mean"),
            pnl=("realized_pnl", "sum"),
        ).round(3)
        lines.append("Per template:")
        lines.append(grouped.to_string())
        lines.append("")
        # Acceptance gates (soft per delta D9).
        passes = []
        in_band = 10 <= len(caught) <= 100
        wr_ok = all(
            (g.n < 5) or (g.wr >= 0.85) for g in grouped.itertuples()
        )
        pnl_ok = caught["realized_pnl"].sum() > 0
        for label, ok in [
            ("n_caught in [10, 100]", in_band),
            ("per-template WR >= 0.85 (where n>=5)", wr_ok),
            ("gated subset PnL > 0", pnl_ok),
        ]:
            passes.append((label, ok))
        lines.append("Soft-acceptance:")
        for label, ok in passes:
            lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        lines.append("")
        if not all(ok for _, ok in passes):
            lines.append("NOTE: §6.4 thresholds are SOFT acceptance per delta D9. "
                          "Phase 4 still runs against a mock energy event regardless.")

    OUT_PATH.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    run()
