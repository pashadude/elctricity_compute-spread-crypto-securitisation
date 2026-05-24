# User Feedback To Synthetic Instrument Plan

## User Feedback

- Users compare this with a compute index. The answer must be clear: an index is
  a benchmark; this desk is a discovery, routing, and settlement layer for
  assets that are actually driven by the compute/energy spread.
- Users ask whether it is asset-backed. The honest v1 answer is no: it is a
  synthetic reference package with venue legs, evidence, judge verdicts, hashes,
  and optional Arc/Circle settlement. It becomes asset-backed only when real
  collateral such as GPU rental receivables, compute invoices, PPAs, miner power
  hedges, or escrowed claims are attached.
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

- The current backend builds canonical compute/energy spread packages.
- Direct event/forecast legs come from Polymarket and IBKR ForecastTrader style
  metadata when available.
- BTC/ETH and IBKR stocks are labelled proxy legs, not direct claims.
- The judge gate is intact: no Arc action may bypass `judge.classify()`, and no
  chain call may happen unless the verdict is `EXECUTE`.
- Telegram and channel policy are sparse: `/latest` and the Mini App show the
  watchlist, while the public channel posts only EXECUTE packages, Arc jobs, and
  runtime errors.

## New Solution

Add an agent-authored synthetic instrument proposal to every snapshot.

The proposal is not a trade instruction and not a legal ABS. It is a term-sheet
shaped object that says what the agent would try to securitize next:

- proposed instrument name and deterministic proposal id;
- region/source-aware energy profile;
- direction and payoff thesis;
- real-world inputs: electricity, compute, z-score, power stack, oracle role;
- outputs: direct reference legs, proxy reference legs, guardrails, and next
  agent actions;
- collateral status: `not_asset_backed_v0` unless real collateral hashes are
  present;
- RWA upgrade path: compute invoices, GPU rental receivables, PPAs, miner power
  hedges, escrowed USDC, or tokenized collateral claims;
- monetization path: discovery feed, verdict/backtest reports, structuring/API
  fees, and future RWA lending support when collateral exists.

This makes the product more securitizing without lying about the legal state:
the current object is a synthetic reference instrument; the future RWA product
requires real collateral.

## Verification

The new proposal layer is covered by:

- `tests/test_synthetic_instrument.py`
- `tests/test_services_state.py`
- `tests/test_telegram_bot.py`

The tests prove that:

- the proposal is explicitly synthetic and not asset-backed in v1;
- regional/source-aware energy notes are included;
- direct event legs are separated from proxy legs;
- package EXECUTE legs outrank passive watchlist legs;
- `/latest` shows the proposal and next agent action;
- the existing judge/Arc guardrails remain visible.
