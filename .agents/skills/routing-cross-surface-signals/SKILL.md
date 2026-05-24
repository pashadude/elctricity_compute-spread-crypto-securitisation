---
name: routing-cross-surface-signals
description: Use when editing candidate routing, scanner output, cross-surface signal selection, energy/Polymarket routing, Hyperliquid or prediction-market routing, portfolio surface selection, or routing tests. Do not use for Arc settlement calls or PnL basis calibration.
---

# Routing cross-surface signals

## Codex routing header

open scanner/router files if present, templates/energy/classifier.py, agent/polymarket_scanner.py, agent/scorer_bridge.py, relevant tests, AGENTS.md
use for candidate routing and surface selection
do not call Arc directly
do not change PnL basis constants
do not bypass the energy classifier or scorer bridge


The router takes one `ArbSignal` and decides which surfaces to express it on. It does NOT decide whether to take a position — that's the judge. The router's first job is to build a canonical spread package: signal, thesis, intended direct event pair, available expression legs, and package hash. Venue candidates are legs of that package, not the package itself.

Numeric mappings (direction → instruments, sizing per surface) live in `arc-compute-sec/policy.yaml`. The principles below explain why those mappings exist.

## Core principles

**One signal can hit many surfaces — but the surfaces are not equally direct.**
A `compute_expensive` z-score implies several economic effects: hyperscaler cost relief, miner margin support, AI-release acceleration. Each effect manifests on a different surface with a different latency and edge magnitude. Prediction-market or event-contract pairs are the clearest direct package legs when they match the thesis. BTC/ETH and equities are liquid proxy legs and must be labelled as such. IBKR ForecastTrader/ForecastEx event contracts are direct-event candidates; IBKR stocks are proxy candidates.

**Directness beats liquidity for the story; liquidity matters for expression.**
A high-edge direct event candidate on a thin surface may be hard to size, but it explains the spread package better than a generic BTC/USD leg. A lower-edge proxy leg on a deep surface can be useful for live-read execution, but it must not be described as securitizing the spread.

**Tenor must match signal TTL.**
A 24-hour `electricity_expensive` signal does not survive a 30-day Polymarket event resolution. Match surface TTL to signal `ttl_hours` ± 50%. If no surface fits, the signal goes through the judge alone (Polymarket-only) rather than padding the candidate list with mismatched horizons.

**Cross-surface candidates compete for the same risk budget.**
The desk has a fixed concurrency cap (see `judging-arb-candidates`). Two candidates on the same signal can both be EXECUTEd only if the judge's concurrency state allows. The router should rank such that even partial fills produce the best PnL-weighted basket.

## Direction → surface mapping (the principle, not the table)

**`electricity_expensive` (electricity spike, compute unchanged):**
- Direct event pair: long energy/grid stress outcome and short AI release/popularity/compute-demand outcome, sourced from Polymarket, IBKR ForecastTrader/ForecastEx, or other approved event-contract venues
- BTC/ETH short only as a miner-margin proxy: mining margin = block_reward × BTC − power_cost × hashrate
- Hyperscaler equities short as a secondary paper proxy: cloud margin compresses on power cost
- Miner equities short as a secondary paper proxy when available

**`compute_expensive` (compute spot spike, electricity unchanged):**
- Direct event pair: long AI release/popularity/compute-demand outcome and short energy/grid stress outcome, sourced from Polymarket, IBKR ForecastTrader/ForecastEx, or other approved event-contract venues
- Hyperscaler equities long *only* if the compute spike is supply-driven (e.g., NVIDIA constraint) AND the hyperscaler is a beneficiary; skip in ambiguous cases
- Do not auto-route BTC/ETH here. Without explicit miner-margin evidence, generic crypto is too noisy to explain the spread package.

The v1 implementation attaches `spread_package` metadata to every candidate. Crypto is allowed only as a labelled miner-margin proxy on `electricity_expensive` signals; it is not direct securitization evidence. `ibkr_prediction` means IBKR event/forecast contract metadata and can be direct; `ibkr` means stock paper orders and remains proxy-only.

## When to skip a surface entirely

- The surface's adapter is in stub mode (e.g., Kalshi v0) — don't queue stub candidates; they pollute `logs/judgements.tsv` with rows that can't produce real outcomes
- The surface has produced 3+ consecutive REJECTs from the judge — the router is feeding it candidates that don't survive gating; tighten the routing rule
- The surface has produced 3+ consecutive losses with realized < est_pnl − 2σ — the basis_per_z for that surface is mis-calibrated; pause routing and trigger `calibrating-pnl-estimates`

## Ranking principles

Rank candidates by directness first, then `est_pnl_per_dollar × conviction × surface_health_factor`:
- direct prediction-event legs first when available and thesis-matched
- miner-margin crypto proxies second
- equity paper proxies after crypto
- `est_pnl_per_dollar` comes from `pnl_probe`
- `conviction` is the signal's `|z|`
- `surface_health_factor` ∈ [0, 1] — start at 1.0; downweight surfaces with recent loss runs

**Do not** rank by absolute notional. A $1 wrap that captures 5 bps reliably is better than a $10 wrap that captures 2 bps in expectation.

## Anti-patterns

- **Don't route to every surface on every signal.** The router is a filter, not a fan-out. If a signal doesn't fit a surface, the right answer is to omit it, not to size it small.
- **Don't present BTC/USD as the package.** It is a miner-margin proxy leg. The package is the canonical spread blob and direct/proxy leg map.
- **Don't conflate "surface produces no candidate" with "router failed".** Polymarket's Gamma API may simply have no energy or AI-release event open right now. That's not a routing bug; it's a market state.
- **Don't hardcode tickers as a list.** Use the principle (hyperscaler set, miner set) so additions/removals are skill edits, not Python edits.

## Calibration cadence

After every Phase 5 reconciliation:
- Per surface, compute realized PnL minus est_pnl_per_dollar × notional, summed over the trailing 14 days
- If one surface dominates the others by 2× on this metric → propose routing more aggressively to that surface
- If one surface is consistently negative → propose dropping it from the direction it underperforms on
- Edit `policy.yaml` (mapping) AND this skill (principle, if a new pattern emerged)
