# Compute Securitization Reference Notes

## Why The Product Must Start From A Cashflow

The better analogy is a commodity shipment hedge, not a pure index.

If an operator ships meat from Kalmykia to Saudi Arabia, the securitized or
financed product can reference a real commercial transaction:

- sale contract or invoice;
- delivery route and timing;
- FX, freight, insurance, temperature, and commodity-price hedges;
- receivable/collateral documents;
- settlement and audit trail.

For compute, the equivalent underlying is a forward compute sale:

- signed GPU-hour invoice or rental receivable;
- delivery/metering record for the compute service;
- location-specific power exposure or PPA;
- public hedge basket for AI compute demand, grid equipment, merchant power,
  nuclear baseload, and miner-margin risk;
- Arc/Circle settlement and canonical hashes.

Without those collateral files, v1 must be honest: it is a synthetic hedge note
around a compute sale, not a legal asset-backed securitization.

## Lessons From AiLA-X

AiLA describes commodity strategies as opportunistic, daily rebalanced, and
driven by both micro and macro factors. Their process separates:

- when to allocate;
- how much to allocate;
- which asset to allocate;
- long/short direction;
- daily actual weights;
- liquid futures/commodity market constraints.

Their FAQ also states that strategy products can be delivered through swaps,
ETFs, funds, or direct sourcing by trading desks. The useful design lesson for
Power by Botozen is that the product should publish transparent direction,
quantum, tenor, weights, and data hierarchy instead of only showing raw slugs.

The local AILA daily report dated 2025-11-22 lists commodity strategies with
direction, 1D/YTD returns, volatility, 1M/2024/3Y/5Y returns, and 3Y/5Y Sharpe.
Energy-relevant rows include:

- `AILAS032`: large diversified commodities including European Power and Gas;
- `AILAS034`: large diversified commodities including European Gas;
- `AILAS002`: factor-based, volatility-weighted European Power and Gas;
- `AILAS020`: factor-based diversified Oil & Gas;
- `AILAF012`: event-driven diversified commodity strategy;
- `AILAS109`: global commodities relative value.

The implementation implication: the compute product should expose a benchmark
style table with direction, tenor, price source, hedge basket, collateral
status, and search-adjusted validation, not just a dashboard of candidates.

Sources reviewed:

- https://aila-x.com/
- https://aila-x.com/faq.php
- https://aila-x.com/aila-investment-strategies.php
- local file: `/Users/pauldudko/Downloads/AILA Daily Performance Report - November 22, 2025.pdf`

## Lessons From FDR In Finance

The referenced FDR repository implements López de Prado-style false-discovery
analysis and emphasizes that testing many strategies and selecting the best can
make observed performance look much stronger than it is. The README describes a
maximum-of-mixtures model and shows search-adjusted FDR can rise above 80% when
effective search intensity is high.

The implementation implication: every tested slug, symbol, model, prompt, and
feature definition must count toward promotion risk. The agent can propose many
synthetic instruments, but a proposal should not be marketed as robust until it
passes search-adjusted validation.

Source reviewed:

- https://github.com/algomaschine/FDR-in-Finance

## Product Rule

Unpriced rows are useful only as discovery gaps. They must not appear in the
core hedge basket. The proposal should prioritize:

1. commercial compute exposure;
2. priced public hedge basket;
3. local buy/monitor/sell mock ticket;
4. optional direct event contracts as research inputs;
5. proxy/context rows and pricing gaps that still need live venue quotes.

This is now represented in `agent/synthetic_instrument.py` as:

- `inputs.underlying_contract`;
- `outputs.priced_hedge_basket`;
- `outputs.mock_hedge_construction`;
- `outputs.direct_reference_legs`;
- `outputs.proxy_reference_legs`;
- `outputs.discovery_gaps`;
- `outputs.build_instructions`;
- `outputs.agent_search_plan`;
- `inputs.search_adjustment`;
- `structure.index_governance`;
- `structure.schematic_steps`.

The mock construction is testnet-only. It uses the latest public quote
snapshots and current spread inputs to size hedge weights, units, leg
explanations, simple stress scenarios, buy/monitor/sell recommendations, and a
Circle test USDC funding request. It must not be treated as a live order or
automatic Circle transfer. IBKR ForecastTrader and Polymarket rows are research
scouting inputs unless they become priced, thesis-matched, gated candidates.
