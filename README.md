# Power by Botozen

Arc-wrapped compute/energy spread desk.

This repository has two distinct surfaces:

- `arc-compute-sec/` is the product demo: the live website, API, worker,
  Telegram integration, Opoint/Nebius/IBKR/Polymarket routing, backtests, and
  Arc settlement path.
- `arc-oss-builder-starter-kit/` is a self-contained Arc OSS starter kit
  folder tracked in this same repo. It is not part of the product runtime.

The separation is intentional. The product repo explains the compute/energy
spread desk. The starter kit explains reusable Arc builder primitives without
mixing in product-specific alpha logic.

## Product Thesis

Compute is becoming a commodity, but raw GPU-hours are not yet a clean
securitizable asset. The practical v1 is a judged compute/energy spread
package:

```text
S_t = compute_$_per_gpu_hr - k * (electricity_$_per_MWh / 1000) * kWh_per_gpu_hr
```

The desk searches for dislocations in that spread, builds a canonical package
of direct event legs and proxy hedge legs, runs the energy classifier, premium
gate, and `judge.classify()`, and only then wraps an approved package as an
ERC-8183 job on Arc.

The live dashboard now also runs a walk-forward replay over several
compute/energy spread families: compute minus power cost, power-cost share,
compute/power ratio, and raw compute minus power. Repeated worker polls are
collapsed first, so a slow-moving mark cannot create fake zero-PnL trades. A
spread family is not promoted to a user-facing buy signal unless the replay has
enough mark-change history, enough distinct marks, enough z-gated trades,
positive PnL, and acceptable win rate.

The index universe is no longer one scalar. The API now catalogues electricity
indexes, compute indexes, and oil-style spread archetypes: compute spark
spread, power-cost share, regional compute-power basis, compute calendar
spread, and fuel-stack compute spread.

The liquid expression is tested separately with a public proxy basket replay:
`NVDA`, `VRT`, `ETN`, `CEG`, `NRG`, `BTC-USD`, `ETH-USD`, gas, and Brent where
available. This answers a different question from the raw spread: if the desk
expressed the thesis through tradable proxies, did that basket make money over
recent public closes? The replay now reports 5d, 1m, 3m, and 6m returns plus a
conservative `BUY`, `HOLD`, `SELL`, or `MONITOR` signal. A recent proxy `SELL`
can block a fresh mock-contract buy even when the longer replay is promotable.

The proposal output also includes several syndicated structures that copy the
spread differently: compute receivable hedge note, power-stress receivable
hedge, grid load-growth note, miner-margin power pair, and fuel-stack compute
input hedge. They are synthetic until collateral is attached and no Arc action
can happen before `judge.classify()` returns `EXECUTE`.

The dashboard now separates settled PnL from replay evidence. If there are no
reconciliation rows, the ledger says `No settled PnL` instead of showing a
misleading `$0.00` performance number. Spread replay, proxy-basket replay, and
local mock tickets are labelled separately.

The live spread mark now labels the electricity input. EIA remains the monthly
ERCOT/TX anchor, but the worker can apply a public power/fuel proxy move from
`NG=F`, `NRG`, `CEG`, and `BZ=F` so the spread is not flat between EIA releases.
The UI shows `EIA anchor + public power/fuel proxy`, the base EIA value, and the
proxy move; if quotes fail, it falls back to `EIA monthly retail anchor`.

For historical replay, `npm run spread:proxy-backtest` builds
`logs/spread_proxy_history.tsv`: a public electricity proxy index anchored to
the current EIA/power mark and a public compute-infra proxy index anchored to
the current AWS GPU mark. The API can then use that replay when recorded worker
marks are too flat, while still labelling it as proxy-history evidence. The
spread-family replay now tests both mean-reversion and trend-following rules
because public proxy spreads can trend instead of snapping back over the demo
horizon.

The API also exposes a venue evidence matrix for Polymarket, Kalshi, IBKR
ForecastTrader/ForecastEx, Yahoo/IBKR/Alpaca public quotes, BTC/ETH, and
Opoint/Nebius oracle receipts. Every row is explicitly evidence or watchlist
state; the matrix reports zero Arc-ready surfaces until the judge returns
`EXECUTE`.

`snapshot.oracle` now exposes the Opoint/Nebius receipt ledger directly, and
the synthetic proposal includes an `oracle_judge_evidence` hash. This is
LLM/news judge context only: it can support or criticize a leg, but it cannot
replace the premium scorer, `judge.classify()`, or the no-chain-unless-EXECUTE
rule.

Arc is the settlement, escrow, identity, reputation, and audit rail. Arc is not
the alpha source, crypto venue, prediction venue, scorer, or Polymarket
executor.

## Surfaces

- Direct forecast legs: thesis-matched Polymarket or IBKR ForecastTrader /
  ForecastEx event contracts when priced and eligible.
- Public hedge basket: liquid proxies such as `NVDA`, `VRT`, `ETN`, `CEG`,
  `NRG`, `BTC-USD`, and `ETH-USD`.
- Crypto miner-margin proxies: BTC/ETH are proxy evidence only, not the
  securitized claim.
- Agent-proposed notes: synthetic compute receivable hedge note proposals that
  become asset-backed only when real collateral is attached.

## Run The Product Demo

```bash
cd arc-compute-sec
docker compose up -d --build api worker
curl -fsS http://localhost:8080/api/health
```

Local web routes:

```text
http://localhost:8080/
http://localhost:8080/dashboard
http://localhost:8080/tg
http://localhost:8080/account
```

Production demo:

```text
https://power.botozen.com
https://t.me/botozen_power
https://t.me/BotozenPowerBot
```

## Product Checks

```bash
cd arc-compute-sec
npm run typecheck
npm run package:backtest
npm run proxy:backtest
npm run test
```

The key invariant is unchanged:

```text
judge.classify() must run before any Arc action, and no chain call may happen
unless the judge verdict is EXECUTE.
```

## Arc OSS Starter Kit

The Arc OSS starter kit lives in this repo at:

```bash
cd arc-oss-builder-starter-kit
```

It contains:

- ERC-8004 identity registration.
- ERC-8183 job create, budget, fund, submit, complete.
- Circle Developer-Controlled Wallet helpers.
- USDC 6-decimal conversion.
- Example `EXECUTE` and `REJECT` verdict blobs.
- A verifier proving the scripts guard before touching Circle or Arc.

Verify it:

```bash
npm run check
npm run submission-link
```

Include this folder link in the Arc OSS submission form and Arc CLI update:

```text
https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation/tree/main/arc-oss-builder-starter-kit
```

Suggested CLI update:

```text
Added a self-contained Arc OSS builder starter kit folder:
https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation/tree/main/arc-oss-builder-starter-kit

It teaches ERC-8004 identity, ERC-8183 job escrow, Circle SCA wallets,
USDC 6-decimal handling, and the no-chain-unless-EXECUTE invariant without
mixing in the product-specific compute/energy desk.
```

## Documentation Map

- Product technical details: `arc-compute-sec/README.md`
- Arc OSS starter kit docs: `arc-oss-builder-starter-kit/README.md`
- Final hackathon submission packet: `docs/submission/final_submission.md`
- Three-minute demo script: `docs/submission/demo_script.md`
- Programmatic submission packet: `scripts/print_submission_packet.py`
- Canonical agent task context: `docs/agent-context/TASK.md`
- Product marketing notes: `docs/marketing/`
