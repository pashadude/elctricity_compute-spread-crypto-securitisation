# arc-compute-sec

Arc-settled outcome desk for the electricity-compute arb.

v0 is deliberately narrow. Arc is the settlement, escrow, identity,
reputation, and audit rail. Arc is not the alpha source, prediction venue,
scorer, or Polymarket executor.

## Thesis

Compute is becoming a commodity, but it is not yet a clean securitizable asset.
The physical data center shell can be financed like infrastructure; raw compute
cannot. GPU service flow is perishable, utilization is uncertain, hardware
depreciates technologically before it depreciates physically, and there is no
industry-standard futures unit for a fungible GPU-hour.

That leaves one practical bridge for a hackathon v0: securitize **outcomes**
that expose the same bottleneck. Larry Fink framed the destination at Milken:
["A new asset class will be buying futures of compute"](https://finance.yahoo.com/sectors/technology/articles/blackrock-reveals-surprising-asset-class-022000793.html).
This repo implements the first auditable step toward that market: find
electricity/compute dislocations, express them through prediction-market-style
events or paper liquid proxies, and wrap the judged position as an ERC-8183 job
on Arc.

Prediction markets are the viable first surface because they already solve the
hardest problem that compute futures do not yet solve: they turn messy,
bespoke infrastructure risks into discrete, externally resolvable claims. Grid
approvals, energy shocks, chip delays, model-release timing, and AI-capacity
milestones do not need a standardized GPU-hour to trade; they need a canonical
event, a price, a resolution, and an audit trail. Arc supplies the escrow,
identity, reputation, and settlement rail around that outcome. It does not
source alpha.

## How We Get Arbs

The identifier measures the electricity-compute spread:

```text
S_t = compute_$_per_gpu_hr - k * electricity_$_per_MWh * kWh_per_gpu_hr
```

with the electricity term converted from MWh to GPU-hours in
`agent/arb_identifier.py`. A signal is emitted when the rolling z-score of
`S_t` moves far enough from its local history:

- `z(S_t) > threshold`: compute is expensive relative to electricity.
- `z(S_t) < -threshold`: electricity is expensive relative to compute.

The router then expresses that one signal on the surfaces where the
mispricing should show up:

- **S-4 Polymarket energy outcomes:** oil, gas, electricity, grid, OPEC/EIA,
  and AI-infra power events are filtered through the energy template universe.
- **Prediction-market AI-infra outcomes:** model releases and capacity events
  are the direct path to outcome securitization, but v0 keeps Polymarket
  read-only.
- **IBKR paper equities:** hyperscaler margin compression/relief is rehearsed
  with paper orders only.
- **Crypto paper:** BTC/ETH proxy mining-margin stress from electricity spikes;
  no Hyperliquid execution in v0.

Every candidate must then pass the same capital gate: energy classifier,
upstream premium scorer, four-way judge, and only then Arc wrapping. The core
desk edge is not "call Arc"; it is the upstream premium gate plus a narrow
energy classifier plus `judge.classify()` refusing to spend USDC unless the
candidate returns `EXECUTE`.

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

Phase 4 then proved the rail live on Arc Testnet: one live-feed multi-surface
pass routed 11 candidates across crypto, IBKR, and Polymarket; the judge
selected `crypto/BTC/USD`; and ERC-8183 job `19091` was created, funded,
submitted, completed, and given ERC-8004 feedback.

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

- One-shot S-4 runtime: `scan_once(max_positions=1)` exits after one pass.
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
- Phase 4 / Block 5 live multi-surface one-shot is complete: `npm run
  phase4:live` fetched live feeds, routed 11 candidates across crypto, IBKR,
  and Polymarket, selected `crypto/BTC/USD`, judge returned `EXECUTE`, and one
  ERC-8183 job was wrapped, submitted, completed, and given feedback.
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

Latest Phase 4 live multi-surface proof: job `19091`, surface `crypto`,
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

## What v0 Does

Runtime path:

```text
energy signal
  -> read-only Polymarket event scan or mock S-4 candidate
  -> energy classifier
  -> upstream premium scorer
  -> judge.classify()
  -> Arc ERC-8183 wrap only if verdict == EXECUTE
  -> optional submit/complete/feedback settlement pass
```

Phase 4 adds an explicit `--multi-surface` one-shot mode for live paper
surfaces. It still exits after one pass and defaults to `max_positions=1`.

The Polymarket adapter is read-only. It snapshots event prices and canonical
candidate data for the Arc audit trail. It does not place Polymarket orders.

Premium-gate failures become auditable `REJECT` judgements. Off-template
non-energy events are dropped before scorer and judge. No fallback scorer path
may disable the premium gate.

Saved oracle receipts can be attached as candidate metadata and backtested
offline. They are evidence for the judge, not a judge replacement.

Live wraps preflight the client wallet's USDC balance and top it up from the
desk wallet when local client state is stale or underfunded. This funding
preflight runs after the judge returns `EXECUTE` and before ERC-8183 job calls.

## What v0 Does Not Do

Deferred out of v0:

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

IBKR and crypto are paper-only surfaces in the explicit Phase 4
`--multi-surface` one-shot path. Kalshi and live external venue execution remain
deferred.

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
| `python tests/backward_check_energy_templates.py` | Re-run energy classifier against historical fills |
| `npm run oracle:backtest -- --oracle-jsonl <file> [--outcomes-jsonl <file>]` | Replay saved oracle receipts against resolved outcomes; no live API calls |
| `npm run oracle:backtest -- --oracle-jsonl <file> --missing-outcomes-out <file>` | Generate fillable outcome stubs for unresolved oracle receipts; no live API calls |
| `npm run gate:energy-backtest` | Verify Phase 3 energy historical fills under the S-4 premium gate; no live API calls |
| `npm run oracle:energy-backtest -- --llm-receipts-jsonl <file>` | Score saved Opoint+Nebius energy oracle receipts against historical fills |
| `npm run s4:mock` | Offline mock S-4 dry run |
| `npm run s4:scan` | One read-only live-feed S-4 scan in dry-run mode |

Arc Testnet commands that require `.env` credentials and funded testnet wallets:

| Command | Purpose |
|---|---|
| `npm run smoke` | Circle wallet and USDC round-trip smoke test |
| `npm run register-agent` | ERC-8004 identity registration |
| `npm run open-position -- --surface S4 --market mock-001 --notional 1 --expires-hours 1` | Manual ERC-8183 create/budget/fund |
| `npm run submit-outcome -- --job <id> --outcome-blob-path <file>` | Submit a canonical outcome blob hash |
| `npm run settle-position -- --job <id> --verdict-blob-path <file> --action complete` | Complete and give feedback |
| `npm run s4:testnet:mock` | One mock S-4 Arc Testnet wrap and settle after judge `EXECUTE` |
| `npm run phase4:live` | One live-feed multi-surface pass; wraps and settles one judge-approved paper candidate |

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
npm run phase4:live   -> job 19091 wrapped/settled from live multi-surface pass
npm run oracle:backtest -- --oracle-jsonl <fixture> -> offline harness covered by tests
npm run gate:energy-backtest -> 122 baseline fills; 99 kept; WR 100.0%; PnL +152.026
npm run s4:mock       -> 1 S-4 candidate, EXECUTE, dry-run only
git diff --check      -> passed
```
