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

Block 1 (autonomous scaffolding + offline tests + classifier validation) is **complete**.
The v0 runtime target is deliberately narrow: a stateless S-4 energy
Polymarket scan that wraps at most one judge-approved position, then exits.
No daemon loop, no real Polymarket order placement, and no non-Polymarket
surface execution are part of v0.

Next: Gate A (operator credential setup) — see `GATE_A.md`.

## Quick references

| Command | What it does |
|---|---|
| `.venv/bin/python -m pytest tests/` | Offline unit tests |
| `python tests/backward_check_energy_templates.py` | Re-run energy classifier on 1,301-fill TSV |
| `npm run smoke` | USDC round-trip on Arc Testnet (needs Circle + funded wallet) |
| `npm run register-agent` | Phase 1 ERC-8004 identity |
| `npm run open-position -- --surface S4 --market mock-001 --notional 1 --expires-hours 1` | Phase 2 createJob+setBudget+fund |
| `npm run submit-outcome -- --job <id> --outcome-blob-path <file>` | Phase 2 submit |
| `npm run settle-position -- --job <id> --verdict-blob-path <file> --action complete` | Phase 2 settle (loss uses `--action reject --reason-code <code>`) |
| `.venv/bin/python -m agent.runtime --scan --live --max-positions 1` | v0 one-shot S-4 Polymarket scan + Arc wrap after `EXECUTE` |
| `.venv/bin/python -m agent.runtime --once --dry-run --no-persist` | Offline mock S-4 dry run |

## Runtime invariant

The autonomous runtime path is:

`scan_once(max_positions=1)` -> read-only Polymarket energy classifier/scorer -> `judge.classify()` -> wrap on Arc only when verdict is `EXECUTE`.

Premium-gate failures are auditable `REJECT` rows. Off-template Polymarket
events are dropped before scorer/judge. The broader IBKR, crypto, and Kalshi
modules remain in the repo for later phases, but v0 runtime filters to the
Polymarket S-4 surface.
