---
name: judging-arb-candidates
description: Use when editing agent/judge.py, agent/runtime.py, verdict handling, EXECUTE/CHALLENGE/DEFER/REJECT semantics, rejection counters, logs/judgements.tsv, or tests proving no chain call happens unless verdict is EXECUTE. Do not use for PnL basis calibration or Arc SDK syntax.
---

# Judging arb candidates

## Codex routing header

open agent/judge.py, agent/runtime.py, tests/test_judge.py, logs/judgements.tsv, AGENTS.md
only EXECUTE may lead to on-chain side effects
CHALLENGE, DEFER, and REJECT never call Arc
premium gate failures are REJECT
if rejection counter is zero for too long, investigate whether the gate is bypassed

The judge is the only thing between an arb signal and a USDC outflow. It decides one of four labels per candidate — EXECUTE, REJECT, DEFER, CHALLENGE — and that decision becomes a row in `logs/judgements.tsv` that the rail later answers for.

This skill is the **why** behind the judge. The **what** (thresholds, numeric caps) lives in `arc-compute-sec/policy.yaml`; the Python in `agent/judge.py` reads both. When the self-improvement skill edits this file, it sharpens the judge's reasoning. When it edits `policy.yaml`, it tightens or loosens a specific cap.

## Core principles

**Sound like someone who runs the desk, not someone who processes signals.**
The judge sits where capital meets a position. Speak in those terms.

**REJECT is irrevocable; use it only for things that would burn the rail's reputation.**
A rejected candidate is a publicly-observable "no" — `arc-canteen update-traction` references rejection counts, ERC-8004 reputation accrues from the pattern of judgements over time. False REJECTs cost less than false EXECUTEs, but persistent over-rejection signals a dead desk. Reserve REJECT for: scorer gate failure (the only 100%-WR filter the desk has), size caps that would breach risk budget, and concurrency caps that would dilute reputation across too many positions.

**DEFER is the cost-free wait.**
If data is stale, surface is under-sampled, or the signal is on the edge of the z-threshold, DEFER. The rail keeps trying on the next cycle; nothing is committed. Default to DEFER when uncertain — REJECT is only for things we're sure about.

**CHALLENGE is a flag for the self-improvement loop, not a runtime gate.**
v0 routes CHALLENGE to DEFER because there's no debate loop yet. A CHALLENGE row in `logs/judgements.tsv` is a hint to the next self-improvement cycle: "this candidate sat on the boundary of a rule — should the rule move?" The self-improver reads CHALLENGE rows preferentially.

**EXECUTE means the rail is on the hook.**
Every EXECUTE row binds the desk's reputation to a specific outcome. If the position settles in the money, the rail earns reputation; if not, the rail earns a loss row plus a calibration data point. Both outcomes are useful — what's NOT useful is an EXECUTE that the judge couldn't justify in plain English to the operator.

## When to REJECT

- The upstream premium gate (`scorer_bridge.score_candidate(...).passes_gate`) is False — never override this. The gate has 100% WR backward on 1,301 fills; we don't have anything better.
- Notional exceeds `policy.max_position_usdc` — the cap reflects the desk's drawdown tolerance, not an arbitrary number. Increasing it should follow a calibration cycle, not a one-off override.
- `state.positions_open >= state.max_concurrent_positions` — concurrency dilutes reputation; if every position is one of fifty, no single one moves the dial.

## When to DEFER

- Surface resolutions in the trailing 30d are below `policy.min_resolutions_for_execute`. A new surface lacks the reputation history to absorb a loss without disproportionate damage.
- `data_age_seconds > policy.max_data_age_seconds` — the signal direction may have inverted by the time we'd act. Stale data is a silent bad-fill engine.
- The signal `|z| ≤ policy.z_threshold + small_margin` — borderline signals are not free; the cycle cost of waiting one tick is cheaper than the expected loss of a marginal-conviction position.

## When to CHALLENGE (v0: routes to DEFER)

- Notional is above the routine threshold but below the size cap — a "large but not huge" position should get a second look before commitment.
- Signal conviction is high but the surface has poor historical fit for the signal direction — the router said yes, but the calibration says no.
- The energy classifier matched on a borderline keyword (one that has produced false-positives historically).

CHALLENGE rows in `logs/judgements.tsv` are the highest-priority input to the next self-improvement cycle. The self-improver should propose a rule sharpening that resolves the ambiguity.

## Anti-patterns

- **Don't encode reporter-authored content as judge rules.** If the operator complains about one specific position, that's a calibration point — not a new rule. A skill edit should describe how to think about the *class* of position, not how to handle the one that just lost.
- **Don't weaken the premium-gate REJECT.** It's the only filter with cross-validated alpha. Every other gate is heuristic; this one is empirical.
- **Don't retry a candidate with `require_non_negative_premium=False`.** The gate is irrevocable at the codepath level, not just at the policy level.
- **Don't add rules without retiring an equivalent rule.** The judge's job is to be small enough that the operator can hold it in their head. If a new principle subsumes an old one, retire the old one.
- **Don't make CHALLENGE a hard gate in v0.** Until the debate loop is built, CHALLENGE that doesn't route to DEFER will silently halt positions that should have run.

## Calibration cadence

After every Phase 5 reconciliation:
- Read the last 14 days of `logs/judgements.tsv` joined to `logs/pnl_reconciliation.tsv` on `position_id`.
- For each REJECT and DEFER, check whether the *would-be* position would have made or lost money. (This is hindsight, not a target — use it sparingly.)
- For each EXECUTE that lost more than `est_pnl_per_dollar` predicted, check which gate *should* have caught it.
- Propose at most ONE principle edit per cycle. Many small edits over many cycles beat one big edit per quarter.
- If the REJECT counter has been zero for 48+ hours during active scanning, investigate. The gate should be catching something; silence means the classifier or router may have drifted.
