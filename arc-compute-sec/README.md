# arc-compute-sec

**Electricity-compute arb securitization rail on Circle's Arc Testnet.**

This repo builds an autonomous agent that:

1. **Identifies** dislocations in the electricity-compute spread
   `S_t = compute_$/gpu_hr − k × electricity_$/MWh × kWh_per_gpu_hr`
   from live EIA wholesale electricity + AWS EC2 GPU spot prices.
2. **Routes** the signal to four surfaces where the arb expresses:
   crypto, hyperscaler equities (IBKR demo paper), AI-company predictive markets,
   direct energy events.
3. **Executes** — paper-fills via IBKR demo + Coinbase ticker snapshots;
   Polymarket is read-only with the existing scorer's premium gate as filter.
4. **Wraps** each position as an **ERC-8183 job** on Arc Testnet, with the
   judge layer as evaluator and ERC-8004 reputation accrual.

Authoritative spec: `../docs/agent-context/TASK.md`. Codex implementation plan:
`../docs/agent-context/CODEX_PLAN.md`.

## Status

Gate A is complete in the operator-local environment: Circle testnet
credentials, Arc Testnet RPC, smoke wallet funding, and ERC-8004 agent
registration have been exercised without committing local secrets or runtime
state. `GATE_A.md` remains the bootstrap checklist for a fresh machine.

The v0 runtime target is deliberately narrow: a stateless S-4 energy
Polymarket scan that wraps at most one judge-approved position, optionally
settles it, then exits. No daemon loop, no real Polymarket order placement,
and no non-Polymarket surface execution are part of v0.

Latest public testnet proof from the operator-local run: ERC-8183 job `16129`
created, funded, submitted, completed, and given ERC-8004 feedback on Arc
Testnet. Runtime logs remain ignored under `logs/`.

## Quick references

| Command | What it does |
|---|---|
| `npm test` | Offline Python unit tests |
| `npm run typecheck` | Type-check TypeScript scripts |
| `python tests/backward_check_energy_templates.py` | Re-run energy classifier on 1,301-fill TSV |
| `npm run smoke` | USDC round-trip on Arc Testnet (needs Circle + funded wallet) |
| `npm run register-agent` | Phase 1 ERC-8004 identity |
| `npm run open-position -- --surface S4 --market mock-001 --notional 1 --expires-hours 1` | Phase 2 createJob+setBudget+fund |
| `npm run submit-outcome -- --job <id> --outcome-blob-path <file>` | Phase 2 submit |
| `npm run settle-position -- --job <id> --verdict-blob-path <file> --action complete` | Phase 2 settle (loss uses `--action reject --reason-code <code>`) |
| `npm run s4:mock` | Offline mock S-4 dry run |
| `npm run s4:scan` | One read-only live-feed S-4 scan, dry-run only |
| `npm run s4:testnet:mock` | One mock S-4 Arc Testnet wrap + settle after `EXECUTE` |

## Runtime invariant

The autonomous runtime path is:

`scan_once(max_positions=1)` -> read-only Polymarket energy classifier/scorer -> `judge.classify()` -> wrap on Arc only when verdict is `EXECUTE`.

Premium-gate failures are auditable `REJECT` rows. Off-template Polymarket
events are dropped before scorer/judge. The broader IBKR, crypto, and Kalshi
modules remain in the repo for later phases, but v0 runtime filters to the
Polymarket S-4 surface.

The live Arc wrapper also enforces the same boundary internally: a direct
`wrap_position(..., dry_run=False)` call must carry the `EXECUTE` verdict
returned by `judge.classify()` or it fails before importing the on-chain
adapter.
