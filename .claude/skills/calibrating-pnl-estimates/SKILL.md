---
name: calibrating-pnl-estimates
description: Principles for when and how to update the basis_per_z constants and PnL formulas in agent/pnl_probe.py. Use after Phase 5 reconciliation, when realized PnL drifts from estimates, or when a new surface is added.
---

# Calibrating PnL estimates

`agent/pnl_probe.py` attaches an `est_pnl_per_dollar` to every candidate the router emits. The judge logs it; the operator reads it; the self-improver compares it to realized PnL after settlement. The constants — `EQUITY_BASIS_PER_Z`, `CRYPTO_BASIS_PER_Z`, and per-surface formulas — are deliberately conservative at v0 because the rail has no calibration data yet.

This skill says **when** to update them, **how** to update them, and **what to look for** that's not just noise.

## Core principles

**Conservative estimates are the desk's friend.**
An under-estimate that lands above realized is a happy surprise. An over-estimate that lands below realized is a reputation hit — the desk sold optimism. When in doubt, lower the basis.

**Bias-toward-zero, not bias-toward-symmetry.**
Don't try to make `est` track `realized` perfectly. Track it from below. Realized should usually be higher than est, occasionally equal, rarely lower. If realized > est in 7+ of last 10 settlements, that's healthy. If realized < est in 3+ of last 10, that's a calibration problem.

**Per-surface basis constants ARE the calibration.**
`EQUITY_BASIS_PER_Z = 0.005` says "expect 50 bps of mean-reversion per σ of spread dislocation on equities." This is one number per surface. Don't add slope, curvature, time-decay, or other parameters until you have ≥ 100 settled positions on that surface — premature complexity will fit the noise.

**Don't calibrate on fewer than 10 reconciled positions per surface.**
Below n=10 the standard error on the basis is wider than the basis itself. The right answer at n<10 is to wait. The self-improvement loop should refuse to propose a basis change if the per-surface sample is too small.

## The calibration step

After Phase 5 reconciliation writes `logs/pnl_reconciliation.tsv`:

1. Group by `surface`. For each surface with n ≥ 10 in the last 30 days:
2. Compute `delta_i = realized_pnl_per_dollar_i − est_pnl_per_dollar_at_open_i` for each settled position
3. Compute `median(delta) / median(z_at_open)` — this is the empirical basis correction
4. If `|correction| > 0.2 × current_basis`, propose an update; otherwise leave the basis alone
5. New basis = `current_basis + 0.5 × correction` (Bayesian half-step toward the empirical, not full step — protects against single-window overreaction)

## When the formula itself is wrong (not just the basis)

If realized PnL is correlated with something the formula does NOT take as input — for example, equity PnL turns out to depend on signal `direction` differently from how we modeled — that's a **formula bug**, not a basis bug. Surface this in `improving-arb-skills`:

- Find the latent variable that explains the residual (`realized − est`)
- Add it to the formula in `pnl_probe.py`
- Propose a new SKILL.md edit explaining *why* that variable belongs

Don't keep stretching the basis to fit a structurally wrong formula.

## Anti-patterns

- **Don't calibrate to a single big winner or loser.** Outliers are not basis updates; they're outliers. Use median, not mean, when computing corrections.
- **Don't change all surfaces' basis in one PR.** One surface per skill-edit cycle. The operator should be able to review each calibration on its own merits.
- **Don't reduce the basis below 0.** A negative basis means you expect to lose money on every position — at that point the right answer is to stop routing to that surface, not to keep paper-trading at negative expectation.
- **Don't update basis just because realized > est consistently.** That's the desired regime (see "Bias-toward-zero"). Only update if realized < est consistently or if realized ≫ est by 3× — the latter means the desk is dramatically under-pricing its product.

## What gets edited where

- **The basis number** → `arc-compute-sec/policy.yaml` under `pnl_probe.equity_basis_per_z` etc.
- **The formula shape** → `agent/pnl_probe.py` (Python edit; needs operator review + unit-test addition)
- **The principle** ("this surface needs a regime variable", "miners should be priced jointly with BTC") → this SKILL.md

## Calibration cadence

- **Weekly** during active development: scan reconciliation log; propose basis updates if any surface crosses the 0.2 × threshold.
- **Per surface launch**: when a new surface goes live (e.g., Kalshi after v0), set its basis at 0.7× the closest existing-surface analog and label it `provisional` in policy.yaml. Re-calibrate after n=10.
- **Quarterly**: rebuild the formula from scratch using all available reconciliation data; if the new formula's out-of-sample fit is materially better, propose a structural edit (formula change, not basis tweak).
