# User Feedback To Synthetic Instrument Plan

## User Feedback

- Users compare this with a compute index. The answer must be clear: an index is
  a benchmark; this desk is a discovery, routing, and settlement layer for
  assets that are actually driven by the compute/energy spread.
- Users ask whether it is asset-backed. The honest v1 answer is no: it is a
  compute receivable hedge note proposal with priced public hedge legs, venue
  evidence, judge verdicts, hashes, and optional Arc/Circle settlement. It
  becomes asset-backed only when real collateral such as GPU rental
  receivables, compute invoices, PPAs, miner power hedges, or escrowed claims
  are attached.
- Users correctly point out that "energy" is not generic. Compute sites can be
  exposed to nuclear baseload, gas marginal generation, hydro, renewables,
  congestion, and local PPAs. The proposal must be regional and source-aware.
- Users ask how monetization works. The product should not invent top-down
  securitizations; it should use LLMs, users, Opoint evidence, IBKR, Polymarket,
  and backtests to discover assets/slugs genuinely driven by the spread.
- The agent should feel more agentic: each scan should propose a new synthetic
  instrument or research note, identify missing direct legs/collateral, and tell
  the operator what it will test next.

## Current Desk

- The current backend builds canonical compute/energy spread packages and a
  forward GPU-hour sale style proposal.
- Direct event/forecast legs come from Polymarket and IBKR ForecastTrader style
  metadata when available.
- IBKR/Polymarket rows without live venue quotes remain pricing gaps; they are
  not hedge basket legs and cannot be marketed as priced exposure.
- A Yahoo-style public quote basket can provide priced proxy hedge rows such as
  NVDA, VRT, ETN, CEG, NRG, BTC-USD, and ETH-USD.
- BTC/ETH and IBKR stocks are labelled proxy legs, not direct claims.
- The judge gate is intact: no Arc action may bypass `judge.classify()`, and no
  chain call may happen unless the verdict is `EXECUTE`.
- Telegram and channel policy are sparse: `/latest` and the Mini App show the
  watchlist, while the public channel posts only EXECUTE packages, Arc jobs, and
  runtime errors.

## New Solution

Add an agent-authored compute receivable hedge note proposal to every snapshot.

The proposal is not a trade instruction and not a legal ABS. It is a term-sheet
shaped object that says what the agent would try to securitize next:

- proposed instrument name and deterministic proposal id;
- underlying commercial exposure: forward GPU-hour sale, invoice, or rental
  receivable;
- region/source-aware energy profile;
- direction and payoff thesis;
- real-world inputs: electricity, compute, z-score, power stack, oracle role;
- outputs: priced hedge basket, direct reference legs, proxy reference legs,
  pricing gaps, guardrails, schematic build steps, and next agent actions;
- agent search plan: Opoint/Nebius evidence, Polymarket direct-event slugs,
  IBKR ForecastTrader pricing refresh, public hedge basket expansion, and
  walk-forward validation;
- search-adjusted validation: every tested slug, symbol, prompt, model, and
  feature counts before a strategy is called robust;
- collateral status: `not_asset_backed_v0` unless real collateral hashes are
  present;
- RWA upgrade path: compute invoices, GPU rental receivables, PPAs, miner power
  hedges, escrowed USDC, or tokenized collateral claims;
- monetization path: discovery feed, verdict/backtest reports, structuring/API
  fees, and future RWA lending support when collateral exists.

This makes the product more securitizing without lying about the legal state:
the current object is a synthetic hedge note around a compute sale; the future
RWA product requires real collateral.

## Verification

The new proposal layer is covered by:

- `tests/test_synthetic_instrument.py`
- `tests/test_services_state.py`
- `tests/test_telegram_bot.py`

The tests prove that:

- the proposal is explicitly synthetic and not asset-backed in v1;
- regional/source-aware energy notes are included;
- rows without live venue quotes are kept out of the hedge basket and shown as
  pricing gaps;
- direct event legs are separated from priced public hedge and proxy legs;
- package EXECUTE legs outrank passive watchlist legs;
- `/latest` shows the proposal and next agent action;
- the existing judge/Arc guardrails remain visible.
