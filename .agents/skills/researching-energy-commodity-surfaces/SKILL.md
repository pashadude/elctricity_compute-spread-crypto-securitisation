---
name: researching-energy-commodity-surfaces
description: Use when researching Brent, crude, natural gas, power, electricity, refinery margins, freight, futures curves, commodity spreads, or physical energy features for Arc compute/energy routing, Polymarket energy templates, IBKR paper surfaces, crypto mining-margin proxies, or future electricity/compute securitization surfaces. Emphasizes z-scores, no-lookahead feature timing, physical-market mechanisms, and avoiding kitchen-sink commodity models.
---

# Researching Energy Commodity Surfaces

## Codex Routing Header

Use for energy/commodity research that informs candidate routing or feature
design. Do not call live commodity data APIs, brokers, Arc, Circle, or external
venues unless explicitly requested. Do not read `.env`.

Read `references/source-notes.md` when adapting Brent/Sparta patterns.

## Research Workflow

1. State the economic mechanism before touching data.
2. Identify the surface where the mechanism should appear.
3. Convert raw prices/spreads into comparable features.
4. Shift features so they are available before the decision timestamp.
5. Backtest against forward returns or resolved outcomes.
6. Promote only stable, interpretable features into routing or judge metadata.

## Feature Discipline

For commodity features:

- Prefer rolling z-scores and daily changes over raw levels.
- Normalize across units: $/bbl, $/mt, cpg, Worldscale, $/MWh, and $/GPU-hr
  are not directly comparable.
- Use expanding or walk-forward training. Avoid full-sample normalization.
- Shift features for availability. Brent source material used `shift(2)` to
  protect one-hour-before-close signal timing.
- Keep feature count small. Four focused physical features can beat dozens of
  noisy correlated spreads.
- Treat missing values as market-data gaps; only forward-fill short weekend
  gaps when the data source supports it.

## Energy Mechanism Map

Use this map to connect commodity features to Arc surfaces:

- **Electricity expensive:** grid/power shock, miner margin compression,
  hyperscaler margin pressure, slower AI release/capacity delivery.
- **Compute expensive:** scarce GPU capacity, private AI company milestone
  acceleration if demand-led, or delay if supply-constrained; classify the
  mechanism before routing.
- **Oil/gas tightness:** refinery margin, gas/power substitution, LNG/export
  policy, and inflation channels can affect energy prediction-market events.
- **Freight/logistics shock:** tanker/freight spikes can convert physical
  tightness into regional price dislocations and delayed supply.

## Surface Routing Implications

- Polymarket energy outcomes need template classification and premium scoring.
- Prediction-market AI-infra outcomes need event-specific news grounding and
  canonical outcome blobs.
- IBKR equities are paper-only unless separately approved; use them for
  hyperscaler/miner exposure rehearsal.
- Crypto is a paper proxy for mining-margin stress unless a future venue is
  explicitly added.
- Direct electricity execution, Hyperliquid execution, and legal tranching are
  not implied by research alone.

## Candidate Feature Families

Energy/Brent patterns worth considering:

- Physical tightness: Dated Brent/frontline spreads, Brent time spreads.
- Product demand: gasoline and gasoil cracks/time spreads.
- Regional arbs: WTI-Brent, Brent-Dubai, transatlantic gasoline arb.
- Freight: clean tanker and crude tanker route costs.
- Promptness: CFD week spreads and front-month curve shape.
- Power/compute: electricity $/MWh, cloud GPU $/GPU-hr, mining economics.

Only promote a feature after it passes no-lookahead timing and out-of-sample
stability checks.

## Arc Desk Guardrails

Research can change candidate routing or PnL calibration only through reviewed
code and tests. It must not weaken:

- `require_non_negative_premium=True` on S-4.
- `judge.classify()` before any chain call.
- No chain call unless verdict is `EXECUTE`.
- Canonical external-state blobs and hashes.

## Test Expectations

Before implementation, define tests for:

- Unit conversion, especially MWh to kWh/GPU-hour.
- Rolling z-score and shift timing.
- No-lookahead alignment.
- Candidate routing on synthetic electricity-expensive and compute-expensive
  signals.
- Polymarket default path remains S-4-gated unless explicit multi-surface mode
  is requested.
