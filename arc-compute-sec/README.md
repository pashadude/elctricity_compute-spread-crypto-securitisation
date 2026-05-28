# arc-compute-sec

Product subproject for the root workspace. Start at `../README.md` for the
public project overview and use this file for the detailed desk runbook.

Arc-wrapped compute/energy spread package desk.

v1 is deliberately narrow. Arc is the settlement, escrow, identity,
reputation, and audit rail. Arc is not the alpha source, crypto venue,
prediction venue, scorer, or Polymarket executor.

## Thesis

Compute is becoming a commodity, but it is not yet a clean securitizable asset.
The physical data center shell can be financed like infrastructure; raw compute
cannot. GPU service flow is perishable, utilization is uncertain, hardware
depreciates technologically before it depreciates physically, and there is no
industry-standard futures unit for a fungible GPU-hour.

That leaves one practical bridge for a hackathon v1: wrap a **judged
compute/energy spread package**. Larry Fink framed the destination at Milken:
["A new asset class will be buying futures of compute"](https://finance.yahoo.com/sectors/technology/articles/blackrock-reveals-surprising-asset-class-022000793.html).
This repo implements the first auditable step toward that market: find
electricity/compute dislocations, canonicalize the signal and chosen legs into
one package blob, and wrap the judge-approved package as an ERC-8183 job on
Arc.

Prediction/event-contract legs are the cleanest explanation of the package:
for example, when electricity is expensive, the direct pair is long an
energy/grid-stress outcome and short an AI release/popularity/compute-demand
outcome. Those direct legs can come from read-only Polymarket research rows or
from IBKR ForecastTrader/ForecastEx event contracts when the operator supplies
eligible contract metadata. BTC or ETH is not the securitized claim. Crypto is
only a labelled miner-margin proxy: higher electricity costs compress
proof-of-work mining economics, so a short BTC/USD or ETH/USD paper leg can
express that stress when direct events are unavailable or too thin.

## How We Get Arbs

The identifier measures the electricity-compute spread:

```text
S_t = compute_$_per_gpu_hr - k * (electricity_$_per_MWh / 1000) * kWh_per_gpu_hr
```

with the electricity term converted from MWh to GPU-hours in
`agent/arb_identifier.py`. A signal is emitted when the rolling z-score of
`S_t` moves far enough from its local history:

- `z(S_t) > threshold`: compute is expensive relative to electricity.
- `z(S_t) < -threshold`: electricity is expensive relative to compute.

The dashboard also computes oil-style spread families in
`agent/spread_family_backtest.py` so one noisy scalar cannot become the whole
story:

| Family | Formula | Read |
|---|---|---|
| Compute minus power cost | `compute - k * (electricity/1000) * kWh` | high means compute rich vs power |
| Power cost share | `k * (electricity/1000) * kWh / compute` | high means power consumes more GPU-hour revenue |
| Compute / power ratio | `compute / (k * electricity/1000 * kWh)` | high means compute rich versus power input |
| Raw compute minus power | `compute - (electricity/1000) * kWh` | same spread before PUE/utilization haircut |
| Compute prompt calendar proxy | `spot GPU rental - prior 21-mark GPU rental average` | front compute tightness versus a term proxy |
| Electricity prompt calendar proxy | `front electricity - prior 21-mark electricity average` | front power tightness versus a term proxy |
| Compute-power prompt basis | `compute prompt premium % - electricity prompt premium %` | curve-shape basis between compute and power |

The catalog also names the next spread archetypes the agent is expected to
scout: regional compute-power basis, compute calendar spread, electricity
calendar spread, compute-power calendar basis, and fuel-stack compute spread.
Current electricity indexes include EIA regional power proxies, ERCOT/PJM/CAISO
physical LMP targets, IBKR ForecastTrader power-generation and price indexes,
Henry Hub, Brent/WTI, derived prompt/term power proxies, and public
merchant-power proxies. Current compute indexes include AWS GPU spot and
regional basis targets, GCP/Azure GPU rental targets, SiliconData H100 rental,
cloud GPU provider marks, IBKR/Kalshi/Polymarket AI compute events,
NVDA/VRT/ETN infrastructure proxies, BTC/ETH miner-margin proxies, derived
prompt/term compute proxies, and planned hashprice inputs.

Each family is replayed walk-forward: collapse repeated worker polls, use only
prior mark changes for the z-score, enter mean-reversion when the z gate
clears, and mark PnL at the configured horizon. A family is not promotable
unless it has enough mark-change history, enough distinct marks, enough
z-gated trades, positive replay PnL, and acceptable win rate. Flat marks
therefore show `INSUFFICIENT_VARIANCE` or `INSUFFICIENT_MARK_CHANGES` instead
of a fake profitable signal. The frontend and Telegram Mini App show this
replay gate beside the live spread.

The public hedge expression is replayed separately in
`agent/proxy_basket_backtest.py`. That replay uses Yahoo/IBKR-style public
close histories for baskets such as AI-infra scarcity, power-stress hedge,
grid-equipment load growth, miner-margin power pair, and fuel-stack power
input. Mixed calendars are handled with a union daily calendar and carried
last closes, so crypto weekends and equity holidays do not collapse the replay
to one common timestamp. It reports 5d, 1m, 3m, and 6m returns and emits a
conservative `BUY`, `HOLD`, `SELL`, or `MONITOR` profitability signal. It also
keeps a dated recent mark series: synthetic index close, daily return, return
since the recent entry date, and paper USDC PnL after scaling by the mock hedge
notional. A recent proxy `SELL` blocks a fresh mock-contract buy even if the
longer replay is otherwise promotable.

The proxy replay also emits `paper_trade_replay`: a prior-close simulated
ticket blotter with closed trades, any open ticket, realized paper PnL, open
paper PnL, hit rate, and the current ticket action (`OPEN_BUY`, `HOLD_OPEN`,
`CLOSE_OR_SELL`, `WAIT`, or `WAIT_FOR_HISTORY`). This is the operator answer
to "what would the recent proposed synthetic arb tickets have made?" It remains
paper replay, not a broker fill ledger.

Run it with:

```bash
npm run proxy:backtest -- --range 1mo --interval 1d
```

The API reads `logs/proxy_basket_backtest.json` when present and uses it as a
separate proxy-basket validation gate. Without that file, set
`PROXY_BASKET_BACKTEST_FETCH=1` to let `/api/snapshot` refresh public history
directly.

`synthetic_instrument.outputs.spread_archetype_trade_map` joins the two replay
layers. Each oil-style spread archetype now points to the expression that can
copy it: syndicated structure, proxy basket, direct-leg target, replay status,
current `BUY`/`SELL`/`MONITOR` signal, and remaining data gaps. This is the
table that explains why a spread can be `PROMOTABLE` as an index replay but
still be `SELL_OR_AVOID` if its mapped liquid proxy basket is losing. A mapped
proxy `BUY` is not enough by itself: fresh buys require a promotable spread
replay plus a constructive mapped proxy. Otherwise the trade map returns
`WAIT_FOR_SPREAD_REPLAY` or `NEEDS_INDEX_HISTORY`.

`synthetic_instrument.outputs.spread_profitability_ledger` ranks those mapped
spreads for the operator. It reports paper 5d and 1m proxy PnL, spread replay
PnL, win rate, priced symbols, recent dated paper marks, and statuses such as
`PAPER_BUY`, `SELL_OR_AVOID`, `WAIT_FOR_PROXY_CONFIRMATION`,
`WAIT_FOR_SPREAD_REPLAY`, `NEEDS_INDEX_HISTORY`, and `NEEDS_EXPRESSION`. The
dashboard, Telegram Mini App, and bot `/latest` show this ledger near the top
of the flow. Each row includes both mark-to-market PnL and ticket-level replay
PnL so an entry-day `$0.00` mark is not confused with a broken spread
calculation. It is paper/replay evidence only, not settled PnL.

The snapshot also separates realized accounting from replay evidence. `pnl`
returns `NO_SETTLED_PNL` and `display_total = "No settled PnL"` until
`logs/pnl_reconciliation.tsv` contains reconciled fills or settlements.
Spread-family replay, proxy-basket replay, and local mock ticket marks stay
labelled as replay/local state so a flat mark cannot look like real PnL.

The spread snapshot also exposes `spread.mark_source`. The base electricity
index is still EIA ERCOT/TX monthly retail power, but live scans can adjust it
with a labelled public proxy move from `NG=F`, `NRG`, `CEG`, and `BZ=F`.
Set `POWER_PROXY_ENABLED=0` to disable this layer, or configure
`POWER_PROXY_SYMBOLS`, `POWER_PROXY_WEIGHTS_JSON`, `POWER_PROXY_BETA`, and
`POWER_PROXY_MAX_MOVE_PCT`. This is a demo power/fuel mark, not an ERCOT LMP
feed.

Run `npm run spread:proxy-backtest` to build `logs/spread_proxy_history.tsv`.
It creates daily public-history electricity and compute indexes, anchored to
the latest live EIA/AWS marks, then reruns the same no-lookahead spread-family
replay. `spread_families.primary_source` tells the UI whether the active replay
comes from recorded runtime marks or proxy history. The replay evaluates both
mean-reversion and trend-following spread rules; a buy signal only appears when
one of those rules clears the trade-count, PnL, and win-rate gates.

`venue_evidence` is the operator-facing matrix for real feeds and gaps:
Polymarket Gamma, Kalshi public events, IBKR ForecastTrader/ForecastEx,
Yahoo/IBKR/Alpaca public quotes, BTC/ETH, and Opoint/Nebius receipts. It is
read-only evidence. `can_drive_arc` is false for every row; promotion still
requires premium scoring where applicable and `judge.classify() == EXECUTE`.

`synthetic_instrument.outputs.real_venue_copy_matrix` turns that feed matrix
into the product view: which real venue can copy the spread as a direct event
leg, which venue is only a liquid proxy hedge, which crypto rows are only
miner-margin proxies, and which Opoint/Nebius receipts are evidence only. It
also lists the spread archetypes each venue can copy and the blocking gate:
`NEEDS_PREMIUM_AND_JUDGE`, `NEEDS_JUDGE_PAIR`,
`DIRECT_METADATA_PROXY_PRICED`, `PROXY_LIVE`, or `EVIDENCE_ONLY`.

`oracle` exposes the Opoint/Nebius receipt ledger separately from the venue
matrix. `agent/synthetic_instrument.py` copies that state into
`outputs.oracle_judge_evidence` with a stable hash so the frontend, Mini App,
and future Arc blobs can reference the LLM/news evidence without letting it
drive execution by itself.

`agent/synthetic_instrument.py` then maps the validated baskets into several
syndicated structures:

| Structure | Spread copied | Current status rule |
|---|---|---|
| Compute scarcity receivable hedge note | compute spark spread | proxy BUY is paper-only until collateral |
| Power-stress compute receivable hedge | power cost share | electricity stress hedge, not ABS without receivable/PPA |
| Grid load-growth basket note | regional compute-power basis | public proxy expression until direct legs price |
| Miner-margin power pair | fuel-stack/miner-margin spread | BTC/ETH are labelled proxy legs only |
| Fuel-stack compute input hedge | fuel-stack compute spread | gas/Brent/power input hedge |

The runtime implements the package in four steps:

1. **Compute the spread:** `S_t` and z-score define whether compute or
   electricity is expensive.
2. **Build the package:** `agent/spread_package.py` records the signal,
   thesis, intended direct event pair, available expression legs, and a
   canonical package hash.
3. **Express the legs:** Polymarket, IBKR ForecastTrader/ForecastEx, and
   Kalshi-style event legs are direct when they match the thesis; BTC/ETH and
   IBKR stocks are labelled proxy legs only.
4. **Judge then wrap:** `judge.classify()` runs before any Arc action; only
   `EXECUTE` can become an ERC-8183 job.

The router then expresses that package on available surfaces:

- **Direct prediction/event-contract legs:** S-4 Polymarket energy outcomes,
  AI-infra events, Kalshi public AI/compute events, and configured IBKR
  ForecastTrader/ForecastEx contracts are filtered through the energy template
  universe and kept read-only/paper in v1. IBKR event contracts are a
  different surface from IBKR stocks.
- **Research inventory:** IBKR ForecastTrader and Polymarket slugs remain
  agent scouting inputs, not the main securitized-tool UI. Telegram `/latest`
  can list them as a research watchlist, but the dashboard promotes only the
  live-priced mock contract unless a priced/gated route emits an `EXECUTE`
  candidate.
- **Priced public hedge basket:** when direct events are missing or unpriced,
  the proposal uses read-only public quote snapshots from `PUBLIC_HEDGE_SYMBOLS`
  such as `NVDA`, `VRT`, `ETN`, `CEG`, `NRG`, `BTC-USD`, and `ETH-USD`.
  `PUBLIC_HEDGE_PRICE_SOURCES=yahoo` is the default; operators can set
  `PUBLIC_HEDGE_PRICE_SOURCES=ibkr,alpaca,yahoo` to try IBKR TWS and Alpaca
  market data before falling back to Yahoo. These public-market rows are liquid
  hedge proxies, not direct claims on compute or electricity.
- **IBKR terminal proxy marks:** when a ForecastTrader EC leg is visible but
  IBKR does not return a usable EC bid/ask/last, the dashboard may attach a
  separate proxy mark. `IBKR_FORECAST_PROXY_PRICE_SOURCES=ibkr,yahoo` is the
  default, so `ITNVD -> NVDA` is read through TWS first and `CRUDB -> BZ=F` /
  `NGP -> NG=F` are mapped to front-month NYMEX futures through the same
  terminal path used by the Brent strategy repo. This still does not convert
  the proxy mark into an EC contract price.
  The socket quote path accepts either `IBKR_GATEWAY_PORT` or the Brent repo's
  `IBKR_PORT` alias. Use paper ports by default: `4002` for IB Gateway paper or
  `7497` for TWS paper. Live ports are `4001` / `7496` and should not be used
  for this demo unless the operator explicitly changes the risk mode.
  If IBKR blocks live and historical market data because another session owns
  the data bridge, the adapter can fall back to the Brent repo's local
  `improm_signal/data/ibkr_energy_history.csv` file, or an explicit
  `IBKR_ENERGY_HISTORY_CSV=/path/to/ibkr_energy_history.csv`. Those marks are
  labelled `ibkr_energy_history_csv` and stale, not live EC prices.
  Docker mounts `${IBKR_ENERGY_HISTORY_DATA_DIR:-../../brent_strategy/improm_signal/data}`
  read-only at `/brent_strategy_data` so the website can use the same fallback.
  For demo reliability, energy futures proxy marks prefer that local IBKR CSV
  first; set `IBKR_PUBLIC_FUTURES_LIVE_FIRST=1` only when you want to force a
  live TWS/Gateway futures quote attempt before the CSV fallback.
- **Crypto miner-margin proxies:** BTC/USD and ETH/USD paper/live-read legs
  are used only on `electricity_expensive` signals and are labelled as proxy
  evidence, not the spread claim.
- **IBKR stock paper proxies:** hyperscaler margin compression/relief is
  rehearsed with stock paper orders only. These rows must display as stock
  proxies, not as direct event legs.

Every candidate must then pass the same capital gate: energy classifier,
upstream premium scorer when the candidate is Polymarket, four-way judge, and
only then Arc wrapping. The core desk edge is not "call Arc"; it is the
electricity-compute signal, the preserved premium gate when prediction markets
are used, and `judge.classify()` refusing to spend USDC unless the candidate
returns `EXECUTE`.

## Agent-Proposed Synthetic Instruments

The dashboard and Telegram `/latest` now include an agent-authored compute
receivable hedge note proposal for the current snapshot. This is the bridge
between "we watch slugs" and "we can structure a product":

- it starts with a commercial exposure: a forward GPU-hour sale where the
  seller wants to hedge power, utilization, and compute-capacity cost risk;
- it names the proposed hedge note and assigns a deterministic proposal id;
- it states the regional power profile, including whether the exposure is more
  about nuclear baseload, gas marginal power, renewables, congestion, PPAs, or
  another local input;
- it promotes a dynamic live-priced mock contract instead of a raw venue-leg
  browser;
- it includes a testnet mock construction that uses current public quote
  snapshots to size hedge weights, units, leg explanations, scenario checks,
  buy/monitor/sell recommendations, and a Circle test USDC funding request;
- it exposes an agent search queue for Opoint/Nebius evidence, Polymarket
  direct events, IBKR ForecastTrader pricing, public-market hedges, and
  walk-forward validation;
- it exposes a real venue copy matrix so the frontend and Mini App explain how
  Polymarket, Kalshi, IBKR, Yahoo/public quotes, crypto, and Opoint/Nebius map
  to spread archetypes before any Arc action;
- it states the collateral status. v1 is `not_asset_backed_v0`; it becomes
  asset-backed only if real collateral such as GPU rental receivables, compute
  invoices, power purchase agreements, miner power hedges, escrowed USDC, or a
  tokenized collateral claim is attached;
- it gives the next agent action: find missing direct energy/compute legs, run
  premium scoring and judge, request collateral files, fetch priced hedges, or
  backtest the exact leg pair.

This keeps the public claim precise. A compute index is a benchmark. This desk
is a discovery, scoring, hedging, and settlement layer for compute-sale
cashflows whose hedge legs should be proven to move with the compute/energy
spread. The design borrows two controls from public commodity-index practice:
daily direction/quantum/tenor decisions with transparent weights, and
search-adjusted promotion so testing many slugs does not create a false
strategy.

### Building A Demo Hedge Note

1. Define the commercial exposure: region, buyer, seller, GPU-hour quantity,
   delivery window, and price.
2. Attach evidence: invoice or rental receivable, delivery meter, PPA/power
   hedge, and optional escrow proof.
3. Freeze the priced hedge basket from public quotes; these are liquid proxies,
   not the asset-backed claim.
4. Use the mock construction to calculate weighted hedge units, entry marks,
   live PnL, and the Circle test USDC request. This request covers hedge
   notional, liquidity buffer, and Arc settlement buffer.
5. Keep Polymarket, IBKR ForecastTrader, and future event tools in the agent
   scouting queue until they are priced, thesis-matched, and useful enough to
   join the package.
6. Let the dashboard freeze a local mock ticket with **Buy Contract**, monitor
   live leg drift, and show which leg makes the package unprofitable before a
   **Sell Mock** close.
7. Run the premium scorer and `judge.classify()`. No Arc action happens unless
   the verdict is `EXECUTE`.
8. Backtest the exact basket and count every tested slug/symbol/model for
   FDR-style promotion control.

## Evidence So Far

The Phase 3 backward-window check against historical fills is intentionally
conservative and committed at `templates/energy/backward_check.txt`:

| Check | Result |
|---|---:|
| Historical fills scanned | 1,301 |
| Energy-classified fills | 122 |
| `energy_ai_infra` subset | n=70, WR=97.1%, PnL=+68.654 |
| `energy_geopolitics` subset | n=52, WR=92.3%, PnL=-12.224 |
| Soft acceptance | WR pass, gated PnL pass, count gate failed high |

The count gate failure is useful: it says the classifier is broad enough to
need the premium scorer and judge, not that the signal should bypass them. The
repo therefore treats `require_non_negative_premium=True` as a hard invariant,
tests for absence of any `False` S-4 code path, and logs premium failures as
auditable `REJECT` judgements.

`npm run package:backtest` turns that into the package-level proof. It reports
the direct prediction-event evidence and explicitly marks crypto as proxy-only:
BTC/USD and ETH/USD are never counted as proof that the spread itself was
securitized.

Phase 4 then proved the rail live on Arc Testnet: one live-feed package pass
routed 11 expression legs across direct event surfaces and proxy surfaces; the
judge selected `crypto/BTC/USD` as a miner-margin proxy leg; and ERC-8183 job
`19091` was created, funded, submitted, completed, and given ERC-8004
feedback.

Oracle backtesting is now offline-only: saved Opoint/Nebius analyst+critic
receipts can be replayed against resolved outcomes to measure calibration,
Brier score, top-1 hit rate, and whether the oracle would have vetoed winning
or losing candidates. The oracle remains evidence only; it does not replace the
premium scorer, energy classifier, judge, or Arc execution gate.

Outcome labels are joined explicitly from JSONL, not hidden state. If oracle
receipts do not carry `resolved_outcome`, run the backtest with
`--missing-outcomes-out <file>` to generate fillable stubs keyed by
`candidate_id`, `event_id`, and/or `event_slug`; fill `resolved_outcome` and,
when available, `candidate_outcome`, `side`, and `realized_pnl`, then pass that
file back through `--outcomes-jsonl`.

For the actual Phase 3 energy backward-window data, separate the hard gate
from the LLM oracle. `npm run gate:energy-backtest` replays
`data/master_fills_v4.tsv` through the current energy classifier and the S-4
non-negative premium gate. On the current local file, the baseline 122
energy-classified fills become 99 gate-kept fills with 100.0% WR and +152.026
PnL; the gate vetoes 23 fills whose combined PnL is -95.596.

The real oracle path is `npm run oracle:energy-llm`. It fetches Opoint evidence
available before the candidate entry timestamp, sends that evidence to Nebius
`deepseek-ai/DeepSeek-V3.2` as analyst, validates with
`Qwen/Qwen3-30B-A3B-Instruct-2507` as critic, and writes append-only receipts.
Backtest saved receipts with `npm run oracle:energy-backtest --
--llm-receipts-jsonl <file>`.

## Current State

Implemented and tested:

- One-shot spread-package runtime: `scan_once(max_positions=1)` exits after one pass.
- Canonical package metadata is attached to each candidate and included in the
  Arc deliverable hash.
- Energy classifier drops off-template Polymarket events before scoring.
- Scorer bridge preserves the upstream premium gate with
  `require_non_negative_premium=True`.
- Four-way judge returns `EXECUTE`, `REJECT`, `DEFER`, or `CHALLENGE`.
- Arc wrapping is allowed only after `judge.classify()` returns `EXECUTE`.
- Live `wrap_position(..., dry_run=False)` also requires the `EXECUTE` verdict
  and fails before importing `agent.on_chain` otherwise.
- ERC-8183 lifecycle scripts exist for create, budget, fund, submit, complete,
  and feedback.
- ERC-8004 identity registration script exists and has been run on Arc Testnet
  in the operator-local environment.
- Phase 0.6 / Block 2 IBKR paper Gateway smoke is complete: local Gateway
  socket `127.0.0.1:4002` was reachable outside sandbox and
  `npm run ibkr:smoke` returned a GOOGL quote.
- IBKR ForecastTrader TWS discovery is read-only and can list account-visible
  event underliers such as energy/electricity, macro, and NVIDIA compute
  events. Priced YES/NO contract legs still require authenticated IBKR Client
  Portal/Web API discovery because IBKR resolves event-contract conids through
  those endpoints.
- Phase 0.7 / Block 2 EIA + AWS feed smoke is complete: `npm run feeds:smoke`
  fetched one live ERCOT/TX EIA electricity proxy point and one AWS
  `p4d.24xlarge` `us-east-1` spot price.
- Phase 0 USDC smoke / Block 2 is complete: `npm run smoke` created one Circle
  SCA wallet, the operator funded it from the faucet, and a 0.01 USDC
  self-transfer completed on Arc Testnet.
- Phase 1 / Block 3 ERC-8004 desk identity is complete: `desk_owner` registered
  as desk agent `9931`, `judge_validator` validationRequest/Response rehearsal
  completed, and `logs/identity.tsv` is present locally.
- Phase 2 / Block 4 ERC-8183 single-surface mock position is complete:
  `npm run s4:testnet:mock` produced one mock arb signal, one Polymarket S-4
  candidate, judge `EXECUTE`, ERC-8183 wrap, submit, `complete()` settlement,
  and ERC-8004 feedback.
- Phase 4 / Block 5 live package one-shot is complete: `npm run
  phase4:live` fetched live feeds, routed 11 candidates across crypto, IBKR,
  and read-only Polymarket, selected `crypto/BTC/USD` as a miner-margin proxy,
  judge returned `EXECUTE`, and one ERC-8183 job was wrapped, submitted,
  completed, and given feedback.
- Offline oracle backtest harness exists at `agent/oracle_backtest.py`; it
  evaluates saved oracle JSONL only and makes no live Opoint/Nebius calls.
- Phase 3 energy premium-gate verifier exists at `agent/energy_oracle_backtest.py`;
  it verifies historical energy classifier results under the v0 premium gate
  and can overlay saved LLM oracle receipts.
- Opoint+Nebius energy LLM oracle exists at `agent/energy_llm_oracle.py`;
  it uses Opoint news as evidence and Nebius analyst+critic models.

Latest local public testnet proof: Phase 4 ERC-8183 job `19091` was created,
funded, submitted, completed, and given ERC-8004 feedback on Arc Testnet.
Runtime logs and credentials remain ignored under `.env` and `logs/`.

Latest Phase 0 USDC smoke tx:
`https://testnet.arcscan.app/tx/0x3fbd69c6c99211d1086d56adbc821f6e6aaaef78b48538eb943840a346069678`.

Latest Phase 1 identity proofs:

- register: `https://testnet.arcscan.app/tx/0x40c88f1c424fbaa94bd48f76f9ae6c7a001fd7cca54994eecccb9b776ebdc888`
- validationRequest: `https://testnet.arcscan.app/tx/0x1952fa34f3d1928c271a6cdfdc8823f282db40a0a55e43ca2b081c185c5ec163`
- validationResponse: `https://testnet.arcscan.app/tx/0xd3fac1597fa564b8e801613167e06175e7bc76d57e20b865a1fea6c7f44f09d4`

Latest Phase 2 mock position proof: job `17884`, deliverable hash
`0x164ab21cef572f4a8d69764d6432d0b8081c5b04f4810edd92125d80e910fcc6`,
reason hash `0x5c806b9388d86c7620b20373d03eced18f37022b6b0385f06684f0e7a7a41a7a`.

- createJob: `https://testnet.arcscan.app/tx/0x05bc9a9f5d692fb7c77384ac6a8c563062086c45405a4d7358bca92b165e9998`
- setBudget: `https://testnet.arcscan.app/tx/0x5302eb98ed0bc52af57a1c1895f33b04385cd0f15aef2a9de03bdf224ff51f23`
- fund: `https://testnet.arcscan.app/tx/0x0bb9d32c3615e860558403532275774ddf27ddd535dd91a16db78b6d4c16ebcd`
- submit: `https://testnet.arcscan.app/tx/0xcd6fd00f338d9549ddb863199879398a20eedc87139cb8879b0ba8e64ab7c0e6`
- complete: `https://testnet.arcscan.app/tx/0x6a0796757192dd5670c069e8093198495708271ad5b3d209cab29ceeb393cb76`
- feedback: `https://testnet.arcscan.app/tx/0xd10ebc83f34be7b71de95d821d14429913ee648c71ce4e217b70d5c562ab6b40`

Latest Phase 4 live package proof: job `19091`, surface `crypto`,
instrument `BTC/USD`, deliverable hash
`0x8b16ce661f18e0e3283f1a70b48550a9f34c18f157ead03f7c3b2b29cfdfa221`,
reason hash `0x5c806b9388d86c7620b20373d03eced18f37022b6b0385f06684f0e7a7a41a7a`.

- createJob: `https://testnet.arcscan.app/tx/0xee545e01fa19d60ddc268360def58db2e258cd4e767b6da4e72087495b2cbe91`
- setBudget: `https://testnet.arcscan.app/tx/0xc85c235b14a8511774e03954c9feedf5f3fcfb624745a46710db18d41937b924`
- approve: `https://testnet.arcscan.app/tx/0xc1dc8809858ecc4d616ee5fd009fd348df21f570e811e6a79d6f0d1d8a5d1856`
- fund: `https://testnet.arcscan.app/tx/0xdaa1a4d3902bb322daac8ae1773cccc7bdeb4ebde413e31292a6db7c67880513`
- submit: `https://testnet.arcscan.app/tx/0x657dec2f2cec0425c1d754c60547a531bef3b7e5ac031487090307adda42192a`
- complete: `https://testnet.arcscan.app/tx/0x10d7128b7598a41ab44b7ca02a9f3c9e3ff03e3ff329f9017e32035460ec7eb5`
- feedback: `https://testnet.arcscan.app/tx/0xe70fe81a4a2e21519cb31ce1bba5cab938ea48a6eaeea7c80ba246749842c68a`

Authoritative context:

- `../AGENTS.md`
- `../docs/agent-context/TASK.md`
- `../docs/agent-context/CODEX_PLAN.md`
- `GATE_A.md`

## Local Backend, Frontend, Worker, And Telegram

The operator app is served by a small Python HTTP API. It reads sanitized
runtime logs from `logs/`, serves the static frontend from `../frontend`, and
queues scan requests for the worker. Frontend and Telegram never call Arc
directly; scan requests still run through `agent.runtime` and the
`judge.classify()` gate.

Local API:

```bash
npm run api
```

Open `http://localhost:8080/`. The dashboard calls `/api/snapshot`; dry-run
scan buttons enqueue `/api/scans`. Python service entrypoints load
`arc-compute-sec/.env` automatically when it exists; values already exported in
the shell take precedence.

24/7 local worker:

```bash
npm run worker
```

The worker defaults to dry-run mode. Live Arc Testnet submission requires
`ENABLE_LIVE_CHAIN=1` and the existing Circle/Arc `.env` credentials.

Docker Desktop stage:

```bash
npm run docker:up
```

This starts `api` and `worker` with `restart: unless-stopped`, persists
`./logs`, and mounts `../frontend` read-only. Telegram is a separate profile:

```bash
npm run docker:telegram
```

Telegram uses the Bot API via `TELEGRAM_BOT_TOKEN`, posts channel updates to
`TELEGRAM_CHANNEL_ID`, and only lets `TELEGRAM_ADMIN_USER_IDS` trigger scans.
Bot commands are private-chat only. The public channel is broadcast-only:
`/status`, `/latest`, `/scan`, and `/scan_live` are ignored when posted in the
channel or a group.

The public channel is sparse by design. It posts mock-contract buy/monitor
recommendations, product/operator updates, and runtime errors that need
attention. It does not post repeated `REJECT`/`DEFER` rows,
`premium_gate_fail` rows, raw judge tables, raw Arc job tables, or
watchlist-only slugs. Ask the bot for `/latest` or open the Mini App when you
want the live IBKR/Polymarket/Opoint/Nebius research watchlist. Use
`npm run telegram:channel-about` to post the one-time public explainer,
`npm run telegram:feedback-update` to post the one-time feedback/new-features
announcement, and `npm run telegram:market-data-update` to post the IBKR
paper-terminal/proxy-source labelling update. Use
`npm run telegram:instrument-menu-update` for the multi-spread structure
announcement and `npm run telegram:profitability-update` for the profitability
ledger announcement. Each notification pass is capped by `TELEGRAM_NOTIFY_MAX_PER_PASS`
(default `3`) to avoid Telegram rate limits.
Use `npm run telegram:configure` after token rotation to set the bot description,
command menu, and Mini App menu button from `PUBLIC_BASE_URL`.
Polling mode works locally without ngrok. Use `ngrok http 8080` and set
`PUBLIC_BASE_URL` when configuring a Telegram Mini App URL or webhook.

IBKR Client Portal reminders are operator-only. With
`IBKR_REAUTH_REMINDER_ENABLED=1`, the bot sends the first
`TELEGRAM_ADMIN_USER_IDS` entry, or `IBKR_REAUTH_REMINDER_CHAT_ID` if set, a
reauth checklist every `IBKR_REAUTH_REMINDER_INTERVAL_HOURS` hours. This keeps
the public channel clean while reminding the operator to reopen
`https://localhost:5055`, complete paper login/2FA, run
`npm run ibkr:cp-watchdog-once`, and then keep `npm run ibkr:cp-watchdog`
running.

Webhook/ngrok mode:

```bash
ngrok http 8080
# paste the ngrok HTTPS URL into .env as PUBLIC_BASE_URL
npm run telegram:webhook:set
```

The webhook receiver is `POST /api/telegram/webhook`. If
`TELEGRAM_WEBHOOK_SECRET` is set, Telegram must send the matching
`X-Telegram-Bot-Api-Secret-Token` header. Return to polling mode with:

```bash
npm run telegram:webhook:delete
npm run telegram
```

Operator accounts:

The frontend no longer grants paid access from browser `localStorage`. Operator
access is server-owned: `POST /api/account/operator/demo-payment` creates an
account only when `ALLOW_DEMO_OPERATOR_PAYMENT=1`, stores it in
`logs/accounts.json`, and returns a signed HttpOnly `botozen_session` cookie.
`GET /api/account` restores the user account from that cookie; `POST
/api/account/logout` clears it.

For public HTTPS deployment set:

```bash
ACCOUNT_SESSION_SECRET=<long random secret>
ACCOUNT_COOKIE_SECURE=1
ALLOW_DEMO_OPERATOR_PAYMENT=0
CIRCLE_WEBHOOK_REQUIRE_SIGNATURE=1
PUBLIC_BASE_URL=https://power.botozen.com
```

Circle webhook activation uses `POST /api/circle/webhook`. Circle Wallets
webhooks send `X-Circle-Signature` and `X-Circle-Key-Id`; the backend fetches
the public key from Circle's `/v2/notifications/publicKey/{keyId}` endpoint,
verifies the ECDSA-SHA256 signature over the raw JSON body, and only then
activates an Operator account for a completed >= 5 USDC transaction. The
endpoint also answers `HEAD /api/circle/webhook` for subscriber checks.

## What v1 Does

Runtime path:

```text
energy signal
  -> canonical spread package
  -> direct prediction-event legs when available
  -> optional IBKR ForecastTrader/ForecastEx event legs
  -> optional IBKR stock paper proxies
  -> optional BTC/ETH miner-margin proxy on electricity-expensive signals
  -> energy classifier + upstream premium scorer for Polymarket only
  -> judge.classify()
  -> Arc ERC-8183 wrap only if verdict == EXECUTE
  -> optional submit/complete/feedback settlement pass
```

The default scan path is package multi-surface and still exits after one pass
with `max_positions=1`. Use `--polymarket-only` for legacy S-4 isolation.

The Polymarket adapter is read-only. It snapshots event prices and canonical
candidate data for the Arc audit trail. It does not place Polymarket orders.
The default Polymarket watchlist uses live slugs for AI data-center power
siting and AI-industry stress; replace `POLYMARKET_DIRECT_EVENT_SLUGS` when
those contracts expire.

Kalshi is also wired as a read-only direct-event research surface. The desk
polls Kalshi's public unauthenticated Trade API for open events, filters them
with `KALSHI_DIRECT_EVENT_TERMS`, and shows matched AI/compute contracts as
`kalshi` direct reference legs. These rows are watchlist evidence until priced
event-contract candidates pass the normal judge path; no Kalshi order placement
is implemented.

Premium-gate failures become auditable `REJECT` judgements. Off-template
non-energy events are dropped before scorer and judge. No fallback scorer path
may disable the premium gate.

Saved oracle receipts can be attached as candidate metadata and backtested
offline. They are evidence for the judge, not a judge replacement.

Live wraps preflight the client wallet's USDC balance and top it up from the
desk wallet when local client state is stale or underfunded. This funding
preflight runs after the judge returns `EXECUTE` and before ERC-8183 job calls.

## What v1 Does Not Do

Deferred out of v1:

- S-1 electricity execution
- S-2 hashrate factor
- S-3 EFU beta
- GA/Shinka threshold evolution
- LLM judge
- daemon or long-running loop mode
- real Polymarket order placement
- polling `--scan` loop, idle policy, and 429/503/RPC-timeout recovery
- Hyperliquid execution
- legal securitization or tranching
- Arc Mainnet deployment

Crypto and IBKR stocks remain paper/live-read proxy surfaces; no live external
venue execution happens in v1. IBKR ForecastTrader/ForecastEx contracts are
modelled separately as `ibkr_prediction` direct event legs when the operator's
IBKR demo account exposes priced eligible contract metadata. TWS can discover
event underliers, but priced YES/NO legs require Client Portal/Web API because
IBKR models ForecastEx products as option-like contracts whose conids must be
resolved before quotes or orders. When Client Portal returns EC metadata
without bid/ask/last fields, the adapter now attempts a read-only delayed TWS
EC snapshot fallback through `IBKR_GATEWAY_PORT` and marks the row
`ibkr_quote_unavailable` if both paths lack a usable price. The dashboard can
still attach a clearly labelled external proxy quote from IBKR TWS, Yahoo, or
Alpaca public-market sources (`IBKR_FORECAST_PROXY_QUOTE_FETCH=1`, default on;
`IBKR_FORECAST_PROXY_PRICE_SOURCES=ibkr,yahoo` by default), for example ITNVD
-> NVDA or CRUDB -> BZ=F front Brent. That proxy quote is not treated as the
ForecastTrader EC price. CME account data can be added later as an official
futures/settlement source, but it should not be labelled as a ForecastTrader EC
quote unless the venue contract IDs actually map. Kalshi venue execution and
other live external venue execution remain deferred, but Kalshi public events
are now read as watchlist/direct-reference market data. Crypto proxy PnL is not
counted as direct spread-securitization proof; it must be reconciled separately.

The current EIA adapter uses EIA's public electricity data as an ERCOT/TX
electricity price proxy. A true ERCOT real-time LMP adapter is still deferred
with the broader S-1 electricity execution work.

## Commands

Safe offline checks:

| Command | Purpose |
|---|---|
| `npm test` | Run Python regression tests |
| `npm run typecheck` | Type-check TypeScript scripts |
| `npm run feeds:smoke` | Fetch one live EIA ERCOT/TX electricity proxy point and one AWS p4d us-east-1 spot price |
| `npm run ibkr:smoke` | Quote one symbol through local IBKR paper Gateway |
| `npm run ibkr:forecast-smoke` | List account-visible ForecastTrader/Event Contract underliers through local TWS |
| `npm run ibkr:forecast-priced-smoke` | Try to resolve priced ForecastTrader YES/NO contracts through Client Portal/Web API |
| `npm run ibkr:cp-watchdog-once` | Tickle Client Portal and attempt a soft `/iserver/reauthenticate`; browser/2FA login is still required after a hard `401 Unauthorized` |
| `npm run ibkr:cp-watchdog` | Keep Client Portal warm in a local loop after browser login succeeds |
| `IBKR_CP_BASE_URL=https://localhost:5055/v1/api .venv/bin/python scripts/ibkr_forecast_smoke.py --priced --symbols RETXC,ITNVD,CRUDB,NGP` | Resolve known ForecastTrader symbols and write sanitized `logs/ibkr_forecast_inventory.json` for the dashboard/TG watchlist |
| `python tests/backward_check_energy_templates.py` | Re-run energy classifier against historical fills |
| `npm run package:backtest` | Backtest the canonical package story and explicitly exclude crypto proxies from direct proof |
| `npm run oracle:backtest -- --oracle-jsonl <file> [--outcomes-jsonl <file>]` | Replay saved oracle receipts against resolved outcomes; no live API calls |
| `npm run oracle:backtest -- --oracle-jsonl <file> --missing-outcomes-out <file>` | Generate fillable outcome stubs for unresolved oracle receipts; no live API calls |
| `npm run gate:energy-backtest` | Verify Phase 3 energy historical fills under the S-4 premium gate; no live API calls |
| `npm run oracle:energy-backtest -- --llm-receipts-jsonl <file>` | Score saved Opoint+Nebius energy oracle receipts against historical fills |
| `npm run proxy:backtest -- --range 1mo --interval 1d` | Build public close-history proxy basket replay for the profitability ledger |
| `npm run spread:proxy-backtest` | Build anchored public electricity/compute proxy history for spread-family replay |
| `npm run telegram:profitability-update` | Post the deduped Telegram channel explainer for the profitability ledger |
| `npm run telegram:campaign-draft` | Print the four-post Telegram campaign draft without sending |
| `npm run telegram:campaign-post` | Post the deduped four-post Telegram campaign to `TELEGRAM_CHANNEL_ID` |
| `npm run package:mock` | Offline spread-package dry run |
| `npm run package:scan` | One spread-package live-feed scan in dry-run mode |
| `npm run crypto:mock` | Alias for the package mock path; crypto remains a proxy leg |
| `npm run crypto:scan` | Alias for the package scan path; crypto remains a proxy leg |
| `npm run s4:mock` | Offline mock S-4 dry run with `--polymarket-only` |
| `npm run s4:scan` | One read-only live-feed S-4 scan in dry-run mode with `--polymarket-only` |

Arc Testnet commands that require `.env` credentials and funded testnet wallets:

| Command | Purpose |
|---|---|
| `npm run smoke` | Circle wallet and USDC round-trip smoke test |
| `npm run register-agent` | ERC-8004 identity registration |
| `npm run open-position -- --surface S4 --market mock-001 --notional 1 --expires-hours 1` | Manual ERC-8183 create/budget/fund |
| `npm run submit-outcome -- --job <id> --outcome-blob-path <file>` | Submit a canonical outcome blob hash |
| `npm run settle-position -- --job <id> --verdict-blob-path <file> --action complete` | Complete and give feedback |
| `npm run s4:testnet:mock` | One mock S-4 Arc Testnet wrap and settle after judge `EXECUTE` |
| `npm run phase4:live` | One live-feed package pass; wraps and settles one judge-approved paper candidate |

## Safety Invariants

- No on-chain action may bypass `judge.classify()`.
- No chain call may happen unless the judge verdict is `EXECUTE`.
- The S-4 scorer path must preserve `require_non_negative_premium=True`.
- Do not add fallback logic that retries the scorer with the premium gate disabled.
- Do not modify upstream `py-builder-relayer-client`.
- Do not copy upstream scorer files into this repo.
- Do not commit `.env`, credentials, wallet IDs, entity secrets, local identity
  state, or runtime logs.
- External venue state must be represented through canonical blobs and hashes,
  not hidden mutable state.

## Repo Map

| Area | Files |
|---|---|
| Runtime and judge | `agent/runtime.py`, `agent/judge.py` |
| Signal and routing | `agent/arb_identifier.py`, `agent/surface_router.py` |
| Scorer bridge | `agent/scorer_bridge.py` |
| Oracle backtest | `agent/oracle_backtest.py` |
| Polymarket read-only scanner | `adapters/polymarket.py` |
| Energy classifier | `templates/energy/classifier.py`, `templates/energy/keywords.yaml` |
| Arc/Circle adapter | `agent/on_chain.py`, `contracts/arc_addresses.py`, `contracts/arc_addresses.ts` |
| Live/paper adapters | `adapters/polymarket.py`, `adapters/ibkr.py`, `adapters/crypto.py` |
| ERC-8183 jobs | `jobs/open_position.ts`, `jobs/submit_outcome.ts`, `jobs/settle_position.ts` |
| ERC-8004 identity | `identity/register_agent.ts`, `identity/agent-metadata.json` |
| Tests | `tests/` |
| Local runtime state | `logs/` ignored except `.gitkeep` |

## Verification Snapshot

Most recent local verification:

```text
npm test              -> 78 passed
npm run typecheck     -> passed
npm run ibkr:smoke    -> GOOGL quote returned through local paper Gateway
npm run feeds:smoke   -> EIA ERCOT/TX proxy + AWS p4d us-east-1 spot returned
npm run smoke         -> 0.01 USDC self-transfer completed on Arc Testnet
npm run register-agent -> desk_agent_id 9931 confirmed; logs/identity.tsv present
npm run s4:testnet:mock -> job 17884 wrapped, submitted, completed, feedback sent
npm run phase4:live   -> job 19091 wrapped/settled from live package pass
npm run oracle:backtest -- --oracle-jsonl <fixture> -> offline harness covered by tests
npm run gate:energy-backtest -> 122 baseline fills; 99 kept; WR 100.0%; PnL +152.026
npm run s4:mock       -> 1 S-4 candidate, EXECUTE, dry-run only
git diff --check      -> passed
```
