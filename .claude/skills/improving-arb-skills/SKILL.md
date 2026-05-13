---
name: improving-arb-skills
description: The 7-step self-improvement loop — runs after Phase 5 reconciliation against logs/judgements.tsv + logs/pnl_reconciliation.tsv + logs/grades.tsv. Proposes edits to judging-arb-candidates, routing-cross-surface-signals, calibrating-pnl-estimates, and policy.yaml. NEVER auto-merges. Always opens a PR.
---

# Improving arb skills

This is the **self-improvement skill** — the one that edits the other skills. It runs after Phase 5 reconciliation, reads recent outcomes, and proposes targeted edits to the rail's policy. It is invoked by `python -m agent.self_improvement --propose`.

This skill's only output is a **draft PR**. It must never push to main, never auto-merge, and never edit live `policy.yaml` without operator approval. The operator's merge is the receipt of policy change — without that receipt, the rail's accountability story breaks.

## The 7-step framework

Apply these in order. Stop at step 3 if no pattern emerges across cases — single-case feedback is noise.

### 1. Identify what went wrong (or right) — start from specific feedback, be concrete

Read the trailing 14 days from:
- `logs/judgements.tsv` — every classifier output
- `logs/pnl_reconciliation.tsv` — paper vs realized per settled position
- `logs/grades.tsv` — code/model/human grader outputs
- `logs/operator_notes.tsv` — operator one-liners

Pick the rows where:
- `realized_pnl_per_dollar < est_pnl_per_dollar − 1σ` (worse than predicted), OR
- `realized_pnl_per_dollar > est_pnl_per_dollar + 2σ` (much better than predicted; under-priced product), OR
- A grader (code/model/human) flagged the row, OR
- The operator left a note

Cite specific `candidate_id` values. No "in general" — start from "candidate `c1a2b3` at signal `s4d5e6` did X."

### 2. Ask: why? — the failure is a symptom, find the underlying cause

For each cited candidate, trace the chain:
- What signal produced it? (`arb_signals.tsv`)
- Which surface did the router pick, and what alternatives did it skip?
- What did the judge classify it as, and which gate fired?
- What was the realized outcome and which adapter executed it?

The cause might be in arb_identifier (wrong signal), surface_router (wrong surface for the direction), judge (wrong gate threshold), or pnl_probe (wrong estimate). Name the layer.

### 3. Zoom out to the pattern — would this apply beyond this one case?

If only one candidate exhibits this issue, **stop**. Do not propose an edit. Single-candidate feedback is the leading source of overfitting in skill files.

If 3+ candidates over 14 days exhibit the same shape: there's a pattern. Describe it in one sentence. Examples:
- "Polymarket AI-release shorts on `electricity_expensive` signals consistently underperform their est_pnl by 50%"
- "Equity shorts on signals with `|z| < 1.3` produce wins more often than the basis predicts"
- "Crypto paper-fills timestamp within 60s of the AWS spot price refresh have higher realized variance than older fills"

### 4. Check against existing principles — sharpen, edit, delete, or add?

Read the three skills (`judging-arb-candidates`, `routing-cross-surface-signals`, `calibrating-pnl-estimates`). For your pattern:
- **Sharpen** an existing principle if the pattern is a refinement of an existing rule
- **Edit** if the principle is too broad and produced this failure
- **Delete** if the principle is contradicted by the evidence (rare; needs strong support)
- **Add** only if no existing principle covers this — and only if you can't subsume it into an existing one

The goal is to keep the skill files small. A skill that grew by 50% in three months is a sign of over-fitting to recent noise.

### 5. Write it as a principle, not a rule — describe how to think, not what to do

**Principle:** "Polymarket AI-release events have execution lag that the equity surfaces don't — when both are routed on the same signal, prefer the equity for short-horizon signals."

**Rule (wrong):** "If signal_ttl_hours < 48 and surface in {polymarket_ai, ibkr_googl}, set polymarket_ai sizing to 0."

The rule version is brittle: as soon as a fourth surface is added, the rule fails to update. The principle version generalizes.

### 6. Put it where it belongs — section matters for the agent to apply it right

- Decision-time logic (when to REJECT/DEFER/EXECUTE) → `judging-arb-candidates`
- Pre-decision filtering (which surfaces appear as candidates) → `routing-cross-surface-signals`
- PnL number (the est_pnl_per_dollar formula or basis) → `calibrating-pnl-estimates`
- Numeric threshold update only → `arc-compute-sec/policy.yaml` (no SKILL.md edit needed)

A principle that touches multiple sections usually decomposes into one principle per section. Decompose it.

### 7. Edit and commit — update the skill file, keep it tight, merge overlapping principles

Open a draft PR via `gh pr create`. Title format: `Phase 6: <skill-name> — <pattern in 8 words or less>`. Body:
- Window analyzed (date range, n candidates)
- Top 3 patterns identified (one sentence each, with candidate_id citations)
- Before/after diff per skill (use `diff -u`)
- Per-section motivation: why this section, not the others
- Expected behavioral change: which class of candidate will the rail treat differently after merge
- Rollback plan: how to revert (revert the PR; the agent will reload skills on next init)

**Mark the PR as draft.** The operator turns it ready-for-review after they read it.

## Anti-patterns

- **Don't propose more than ONE edit per cycle.** Many small edits beat one big edit. The operator can review small things; big things get rubber-stamped or ignored.
- **Don't generalize from a single operator note.** A complaint is a calibration point, not a principle source. Note + pattern = principle source; note alone = pending data.
- **Don't edit the premium-gate REJECT.** It's the only filter with cross-validated alpha. If you propose softening it, the PR will (and should) be closed.
- **Don't open a PR if the trailing window has n < 30 settled positions across all surfaces.** Not enough signal. Wait.
- **Don't auto-merge.** This is the rail's accountability rail. Every policy change is a human-in-the-loop receipt visible on `arc-canteen update-product`.

## Cadence

- Triggered automatically by `agent/runtime.py --scan --settle` once Phase 5 reconciliation produces new rows
- Operator can invoke manually: `python -m agent.self_improvement --propose --since 14d`
- Output: at most one PR per invocation; zero is fine if no pattern crosses the threshold

## After the PR merges

- The agent's next `python -m agent.runtime --scan` re-reads all `.claude/skills/*.md` and `policy.yaml` at init
- The next batch of judgement rows will be tagged with the new policy version (extra column: `policy_sha` = current commit SHA)
- Reconciliation a week later will tell you whether the edit helped — if not, revert and try a different formulation
