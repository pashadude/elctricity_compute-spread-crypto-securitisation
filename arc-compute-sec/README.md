# arc-compute-sec

Arc-settled S-4 energy outcome desk for Polymarket-style energy candidates.

v0 is deliberately narrow. Arc is the settlement, escrow, identity,
reputation, and audit rail. Arc is not the alpha source, prediction venue,
scorer, or Polymarket executor.

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

Latest local public testnet proof: ERC-8183 job `16129` was created, funded,
submitted, completed, and given ERC-8004 feedback on Arc Testnet. Runtime logs
and credentials remain ignored under `.env` and `logs/`.

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

The Polymarket adapter is read-only. It snapshots event prices and canonical
candidate data for the Arc audit trail. It does not place Polymarket orders.

Premium-gate failures become auditable `REJECT` judgements. Off-template
non-energy events are dropped before scorer and judge. No fallback scorer path
may disable the premium gate.

## What v0 Does Not Do

Deferred out of v0:

- S-1 electricity execution
- S-2 hashrate factor
- S-3 EFU beta
- GA/Shinka threshold evolution
- LLM judge
- daemon or long-running loop mode
- real Polymarket order placement
- Hyperliquid execution
- legal securitization or tranching
- Arc Mainnet deployment

The broader IBKR, crypto, and Kalshi adapters remain in the repo for later
phases and tests, but v0 runtime execution filters to the S-4 Polymarket
surface.

## Commands

Safe offline checks:

| Command | Purpose |
|---|---|
| `npm test` | Run Python regression tests |
| `npm run typecheck` | Type-check TypeScript scripts |
| `python tests/backward_check_energy_templates.py` | Re-run energy classifier against historical fills |
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
| Polymarket read-only scanner | `adapters/polymarket.py` |
| Energy classifier | `templates/energy/classifier.py`, `templates/energy/keywords.yaml` |
| Arc/Circle adapter | `agent/on_chain.py`, `contracts/arc_addresses.py`, `contracts/arc_addresses.ts` |
| ERC-8183 jobs | `jobs/open_position.ts`, `jobs/submit_outcome.ts`, `jobs/settle_position.ts` |
| ERC-8004 identity | `identity/register_agent.ts`, `identity/agent-metadata.json` |
| Tests | `tests/` |
| Local runtime state | `logs/` ignored except `.gitkeep` |

## Verification Snapshot

Most recent local verification:

```text
npm test              -> 75 passed
npm run typecheck     -> passed
npm run s4:mock       -> 1 S-4 candidate, EXECUTE, dry-run only
git diff --check      -> passed
```
