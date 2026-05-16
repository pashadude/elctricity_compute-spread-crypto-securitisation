# AGENTS.md — ArcHack / arc-compute-sec

## Mission

This repo builds an Arc-settled compute/energy outcome desk.

Arc is the settlement, escrow, identity, and reputation rail.
The alpha source is the premium-gated scoring and energy/prediction-market workflow, not Arc itself.

## Non-negotiable invariants

1. No on-chain action may bypass `judge.classify()`.
2. No chain call may happen unless the judge verdict is `EXECUTE`.
3. The S-4 energy scorer path must preserve `require_non_negative_premium=True`.
4. Do not add fallback logic that retries the scorer with the premium gate disabled.
5. Do not modify upstream `py-builder-relayer-client` except through explicit operator-approved upstream work.
6. Credentials, wallet IDs, entity secrets, `.env`, and local identity state must never be committed.
7. External venue state must be represented through canonical blobs and hashes, not hidden mutable state.

## Skill routing

Use `$using-arc-canteen` when touching:
- Arc network config
- Circle SDK usage
- USDC amount conversion
- ERC-8004 identity or reputation
- ERC-8183 job lifecycle
- `identity/*.ts`
- `jobs/*.ts`
- `agent/on_chain.py`
- `contracts/arc_addresses.py`

Use `$judging-arb-candidates` when touching:
- `agent/judge.py`
- `agent/runtime.py`
- verdict labels: `EXECUTE`, `CHALLENGE`, `DEFER`, `REJECT`
- `logs/judgements.tsv`
- tests proving rejected candidates create no chain side effect

Use `$routing-cross-surface-signals` when touching:
- market/surface routing
- candidate selection
- Polymarket or Hyperliquid candidate flow
- cross-surface portfolio logic
- scanner/router tests

Use `$calibrating-pnl-estimates` when touching:
- `agent/pnl_probe.py`
- `policy.yaml` PnL basis settings
- `logs/pnl_reconciliation.tsv`
- `est_pnl_per_dollar`
- realized-vs-estimated PnL calibration
- new surface PnL basis constants

Use `$using-opoint-nebius-oracles` when touching:
- Opoint news grounding
- Nebius DeepSeek/Qwen analyst or critic calls
- LLM oracle evidence blobs, caches, or audit logs
- event probability vectors or news-grounded outcome metadata

Use `$building-commodity-news-alphas` when touching:
- commodity news taxonomies
- per-article relevance, intensity, or sentiment scoring
- commodity news aggregation
- futures/outcome IC verification or alpha bakeoffs

Use `$researching-energy-commodity-surfaces` when touching:
- Brent, crude, natural gas, power, freight, refinery margin, or futures-curve research
- energy physical-market features for compute/energy routing
- Polymarket energy template research
- IBKR/crypto paper surface research for energy signals

Use `$improving-arb-skills` only for skill maintenance or documented self-improvement workflows.
It must not weaken the premium gate, judge gate, credential rules, or on-chain execution rules.

## Canonical docs

For larger planning work, read:

- `docs/agent-context/TASK.md`
- `.agents/skills/*/SKILL.md`


## Verification

Before completing code changes, run the smallest relevant tests.

For judge/scorer/classifier changes, run:

```bash
pytest tests/test_judge.py tests/test_scorer_bridge.py tests/test_energy_classifier.py
