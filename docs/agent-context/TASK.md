# TASK — Electricity-Compute Arb Securitization Rail

**Type:** Build spec for Claude Code (CLI).
**State:** Canonical (2026-05-13). Supersedes prior `compute-securitization-strategist*.md` drafts and the 2026-05-12 S-4-narrow draft of this file (archived at `.claude/TASK.archived.2026-05-13.md`).
**Build root:** `/Users/pauldudko/VSProjects/ArcHack/arc-compute-sec/`
**Plan file:** `~/.claude/plans/run-all-in-line-tender-liskov.md`

---

## 0. Product framing

This is a **securitization rail for the electricity-compute arb class** built on Circle's Arc Testnet. An autonomous agent (1) identifies dislocations in the implied electricity-vs-compute spread, (2) routes the signal to the surfaces where the dislocation is mispriced, (3) executes positions on each surface (live read + scorer gate for Polymarket via the existing `~/VSProjects/py-builder-relayer-client` rail; paper for IBKR demo equities; paper for crypto), and (4) wraps each position as an ERC-8183 job on Arc so external USDC-funding users can buy desk-vetted, judge-validated exposure to the arb. The desk's ERC-8004 reputation accrues per resolved position.

**v0 operator plays both desk and buyer seats.** v2 introduces real external buyers and spread pricing for the wrap. v0 is plumbing + a live demo, not a money-making system.

---

## 1. The arb being securitized

`S_t = compute_$_per_gpu_hr − k × electricity_$_per_MWh × kWh_per_gpu_hr`

with empirical defaults `k = 0.5` (PUE × instance-load factor) and `kWh_per_gpu_hr = 0.7` (8×H100-class node averaged draw). `S_t` mean-reverts. Dislocations beyond `|z(S_t)| > z_threshold` over a 30-day rolling window propagate to **four surfaces**:

| # | Surface | Reasoning | v0 execution |
|---|---------|-----------|--------------|
| 1 | **Crypto** | BTC/ETH and miner equities (MARA/RIOT/CLSK) — mining margin = block reward × BTC − power cost × hashrate efficiency. Compresses with electricity spike. | Paper-fill against live Coinbase ask via CCXT. |
| 2 | **Hyperscaler equities** | GOOGL, AMZN, MSFT, BABA — cloud-segment margin sensitive to electricity, capacity, and AI demand. | Paper market orders via `ib_insync` against IBKR demo Gateway (port 4002). |
| 3 | **Predictive markets on private AI/compute companies** | Polymarket / Kalshi events on Anthropic, OpenAI, SpaceX, DeepSeek (model releases, capability claims, capacity announcements). Slower releases priced when compute is expensive. | Polymarket: live read via Gamma API + scorer premium-gate filter; NO order placement (stays on `@beldghik`). Kalshi: read-only public event feed for AI/compute watchlist/direct refs; NO order placement. |
| 4 | **Direct energy events on Polymarket** | The prior S-4 narrow slice (oil/gas/electricity/policy keywords). Energy classifier filters Gamma events to this universe. | Same as #3 with the energy template universe. |

The agent picks the highest-conviction subset of surfaces per signal.

**Why this is an arb and not a directional bet:** `S_t` has empirical mean and variance. Positions taken at `|z| > 1.5σ` mean-revert within days–weeks with high hit rate. The securitization wraps each individual mean-reversion bet as a fixed-tenor ERC-8183 job, so users buy a known-tenor exposure rather than directional market beta.

---

## 2. Hard prerequisites

These must exist **before** Block 2 (any chain or live-feed work) runs. Block 1 is fully autonomous and does not depend on them. Stop and surface gaps if any of these fail at the Gate A check.

| # | Item | Verify |
|---|------|--------|
| 0.1 | Circle Developer Console account | `console.circle.com` — log in, no error |
| 0.2 | Circle Standard API key (TESTNET scope) | `console.circle.com/keys` — key visible |
| 0.3 | Circle Entity Secret registered + recovery file | `developers.circle.com/wallets/dev-controlled/register-entity-secret` walked through |
| 0.4 | Arc Testnet USDC ≥ 5 in a funding wallet | `faucet.circle.com` → wait 30s → balance on `testnet.arcscan.app` |
| 0.5 | Node 22+ and Python 3.11+ | `node -v && python3 --version` |
| 0.6 | Upstream `scorer.py` available | `grep -n require_non_negative_premium ~/VSProjects/py-builder-relayer-client/api/polymarket/longtail/scorer.py` returns line 47 |
| 0.7 | IBKR Paper Trading Demo account; IB Gateway or TWS running locally in paper mode | `nc -z localhost 4002 \|\| nc -z localhost 7497` returns 0 |
| 0.8 | EIA API v2 key | env var `EIA_API_KEY` set; key registered at `https://www.eia.gov/opendata/register.php` |
| 0.9 | Read-only treatment of upstream relayer; no use of any other participant's wallets, API keys, or entity secret | confirmed by operator |

---

## 3. Repo layout

```
arc-compute-sec/
├── .env                           # GITIGNORED. Circle creds + RPC + EIA key + IBKR ports + upstream path
├── .env.template                  # checked in
├── package.json                   # TS: viem, Circle SDK, tsx
├── tsconfig.json
├── requirements.txt               # Python: circle SDK, web3, ccxt, ib_insync, pandas
├── contracts/
│   ├── arc_addresses.py           # single source of truth — §4
│   └── abis/                      # ERC-8004 IDENTITY, ERC-8183 AGENTIC_COMMERCE, REPUTATION_REGISTRY
├── upstream/
│   ├── py-builder-relayer-client/ # SYMLINK (read-only). Source of scorer.py.
│   └── PINNED_SHA.txt
├── identity/
│   ├── register_agent.ts
│   └── agent-metadata.json
├── jobs/
│   ├── open_position.ts
│   ├── submit_outcome.ts
│   └── settle_position.ts         # single complete() path (no reject() in deployed ABI)
├── scripts/
│   └── smoke.ts                   # USDC round-trip test
├── feeds/
│   ├── eia.py                     # EIA v2 LMP for ERCOT/PJM/CAISO
│   ├── aws_spot.py                # AWS EC2 p4d/p5 spot pricing
│   ├── coinbase.py                # CCXT public ticker
│   └── cache.py                   # 60s in-memory + on-disk SQLite cache
├── adapters/
│   ├── polymarket.py              # Gamma read + scorer gate; NO order placement
│   ├── ibkr.py                    # ib_insync paper market orders
│   ├── crypto.py                  # paper fills at live Coinbase ask
│   └── kalshi.py                  # read-only public event feed + paper snapshot
├── agent/
│   ├── arb_identifier.py          # S_t + 30-day z-score + signal emission
│   ├── surface_router.py          # signal → candidates per surface
│   ├── judge.py                   # 4-way classifier
│   ├── pnl_probe.py               # surface-specific PnL estimates
│   ├── scorer_bridge.py           # wraps upstream scorer.py
│   ├── on_chain.py                # Circle SDK + web3.py event decode
│   └── runtime.py                 # orchestrator entry point
├── templates/
│   └── energy/
│       ├── keywords.yaml
│       ├── classifier.py          # standalone (single-gate; no upstream cat reuse — see deltas)
│       └── backward_check.txt     # output of §6.4
├── data/
│   └── master_fills_v4.tsv        # SYMLINK to upstream/.../reports/s2_multidim/master_fills_v4.tsv
├── tests/
│   ├── test_*.py                  # unit tests; HTTP mocked
│   └── backward_check_energy_templates.py
└── logs/
    ├── identity.tsv               # one row, source of truth for wallets
    ├── positions.tsv              # one row per ERC-8183 lifecycle stage
    ├── judgements.tsv             # one row per judge decision (with surface, arb_signal_id, est_pnl_per_dollar)
    ├── arb_signals.tsv            # one row per identifier signal emission
    ├── pnl_reconciliation.tsv     # one row per resolved position
    └── arc_txs.tsv                # one row per settled tx
```

---

## 4. Network and contract addresses

Pinned in `contracts/arc_addresses.py`. Do not hardcode anywhere else.

```
CHAIN_ID = 5042002                              # 0x4CEF52
CHAIN_NAME = "ARC-TESTNET"                      # Circle SDK identifier
RPC_HTTP = "https://rpc.testnet.arc.network"
EXPLORER = "https://testnet.arcscan.app"
FAUCET   = "https://faucet.circle.com"

USDC = "0x3600000000000000000000000000000000000000"   # 6 decimals via ERC-20 interface

IDENTITY_REGISTRY    = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
REPUTATION_REGISTRY  = "0x8004B663056A597Dffe9eCcC1965A193B7388713"
VALIDATION_REGISTRY  = "0x8004Cb1BF31DAf7788923b405b754f57acEB4272"

AGENTIC_COMMERCE     = "0x0747EEf0706327138c69792bF28Cd525089e4583"
```

**USDC 6-vs-18 decimals rule:** USDC on Arc has two interfaces. Native balance is 18 decimals (gas accounting); the ERC-20 interface at `0x36…00` is 6 decimals. All application code uses 6 decimals via the ERC-20 interface. Centralize conversions in `arc_addresses.usdc6()`. A lint guard in pre-commit fails if `parseUnits(_, 18)` appears in `jobs/*.ts`.

**EVM compile target rule:** Solidity ≥0.8.20 defaults to `shanghai` which emits PUSH0. Arc Testnet rejects PUSH0 with `ESTIMATION_ERROR / Create2: Failed on deploy`. Any custom contract must compile with `evmVersion: "paris"` or earlier. v0 deploys no custom contracts.

---

## 5. Phases

### Phase 0 — Bootstrap + offline modules (autonomous Block 1)

Project scaffolding, identifier+adapter+feed modules written, unit tests green. No chain calls, no live HTTP except mocked tests. Includes:

- Phase 0.5 — pin ABIs from `github.com/circlefin/arc-escrow` to `contracts/abis/`
- Phase 3 — energy template universe + backward-window validation against the 1,301-fill TSV (soft acceptance)

**Block 1 commit:** all the above.

### Session boundary — start a fresh Claude Code session before Gate A. Block 1 skills (routing, calibration) stay loaded; Block 2+ loads arc-canteen and chain skills fresh. Each phase commit is also a good session boundary. Rationale: five skills total ~30k tokens of body; fresh sessions prevent context rot across unrelated phases.

### GATE A — operator credentials

Operator pastes Circle creds + EIA key into `.env`, starts IB Gateway (paper-trading mode) on port 4002, types "ready" to resume.

### Phase 0.6 — IBKR Gateway smoke (Block 2)

Connect via `ib_insync`, fetch GOOGL last price, print.

### Phase 0.7 — EIA + AWS feeds smoke (Block 2)

Live fetch of one ERCOT LMP point + one AWS p4d.24xlarge us-east-1 spot price.

### Phase 0 USDC smoke (Block 2)

Create one SCA wallet → operator funds at faucet → 0.01 USDC self-transfer → explorer link.

### Phase 1 — ERC-8004 desk identity (Block 3)

Register `desk_owner` identity; wire `judge_validator` via validationRequest+Response rehearsal. Write `logs/identity.tsv`.

### Phase 2 — ERC-8183 single-surface mock position (Block 4)

One mock arb signal → one Polymarket-surface candidate → wrap as ERC-8183 job → settle via `complete()` with reason-hash. Verifies the wrap rail before multi-surface complication.

### Phase 4 — Agent runtime, live multi-surface (Block 5)

`runtime.py --live` orchestrates a single pass with live feeds (v0): arb_identifier → surface_router → adapters (Polymarket live, IBKR paper, crypto paper) → judge → on_chain wrap → settle. The `--scan` loop (polling interval, idle policy, error recovery for 429/503/RPC-timeout) is deferred to v2.

Three demo cases:
- **Case A** — live signal (or `--force-signal` mock at z=2.0) → ≥1 EXECUTE, ≥1 REJECT, wrapped + settled across surfaces
- **Case B** — forced REJECT via premium-gate fail
- **Case C** — classifier drop (event outside energy scope)

### Phase 4 acceptance — three regression tests

These must pass before the Phase 4 commit:
1. Gate-fail → REJECT (already in `tests/test_judge.py::test_reject_premium_gate`)
2. Plausible candidate → EXECUTE (already in `tests/test_judge.py::test_execute_default`)
3. Off-template event filtered before judging (already in `tests/test_energy_classifier.py`)

### Phase 5 — Reconciliation

For each settled position, fetch current price, compute realized PnL, append to `logs/pnl_reconciliation.tsv`.

---

## 6. Anti-goals

- **Not running real money on IBKR.** Paper only. No live equity orders.
- **Not placing Polymarket orders from this repo.** Order placement stays on `@beldghik`. The existing scorer is used here only as a filter.
- **Not deploying any custom Solidity contract.** ERC-8183 reference is deployed at `0x0747EEf0706327138c69792bF28Cd525089e4583`. Use it.
- **Not running the upstream relayer's GA/Shinka loop.** Deferred until ≥30 days of v0 trace.
- **Not deploying to Arc Mainnet.** Mainnet doesn't exist yet.
- **Not using anyone else's wallets, API keys, or entity secret.** Fresh creds per build.
- **Not executing Kalshi orders in v0.** Kalshi is read-only watchlist/direct-reference market data; venue execution remains deferred.
- **Not including the premium-gate kwarg (`require_non_negative_premium`) in any evolutionary, GA, or automated parameter search.** The gate is the desk's only cross-validated edge. Hard-coded exclusion, enforced by `tests/test_judge.py::test_gate_kwarg_exclusion`.

---

## 7. Pinned references

| Topic | URL |
|---|---|
| Arc llms.txt index | https://docs.arc.network/llms.txt |
| Arc contract addresses | https://docs.arc.network/arc/references/contract-addresses.md |
| Arc network details (chain ID, RPC) | https://docs.arc.network/arc/references/connect-to-arc.md |
| ERC-8004 quickstart | https://docs.arc.network/arc/tutorials/register-your-first-ai-agent.md |
| ERC-8183 quickstart | https://docs.arc.network/arc/tutorials/create-your-first-erc-8183-job.md |
| Circle Skills | https://developers.circle.com/ai/skills |
| Circle MCP server | https://developers.circle.com/ai/mcp |
| `use-arc` SKILL.md | https://github.com/circlefin/skills/blob/master/plugins/circle/skills/use-arc/SKILL.md |
| arc-escrow reference repo (ABIs) | https://github.com/circlefin/arc-escrow |
| Arc faucet | https://faucet.circle.com |
| Arc Testnet explorer | https://testnet.arcscan.app |
| IBKR TWS API | https://interactivebrokers.github.io/tws-api/ |
| ib_insync docs | https://ib-insync.readthedocs.io/ |
| EIA API v2 | https://www.eia.gov/opendata/documentation.php |
| AWS Spot pricing index | https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/region_index.json |
| Coinbase public ticker | https://api.exchange.coinbase.com/products/BTC-USD/ticker |
| Upstream Polymarket scorer | `~/VSProjects/py-builder-relayer-client/api/polymarket/longtail/scorer.py` |
| Backward-window data | `~/VSProjects/py-builder-relayer-client/reports/s2_multidim/master_fills_v4.tsv` (1,301 fills) |

---

## 8. Phase summary — onchain proofs per commit

| Commit | When | Proof |
|---|---|---|
| `Phase 0: project bootstrap` | After Block 1 step 1 | Files. Symlink to upstream verified. |
| `Spec: rewrite TASK.md to multi-surface securitization` | After Block 1 step 2 | Diff vs archived TASK.md. |
| `Phase 0.5: pinned ABIs from arc-escrow` | After Block 1 step 3 | Three JSON files under `contracts/abis/`. |
| `Phase 3: energy template universe + backward-window check` | After Block 1 step 4 | `backward_check.txt` committed. |
| `Phase 1-prep: arb identifier + surface router + adapters` | After Block 1 step 5 | All offline tests pass. |
| `Phase 0: USDC + IBKR + EIA smoke tests passing` | After Block 2 | 1 USDC transfer tx + printed feeds. |
| `Phase 1: ERC-8004 desk identity registered` | After Block 3 | 3 txs (register + validation rehearsal). |
| `Phase 2: ERC-8183 single-surface mock position settled` | After Block 4 | 5–6 txs (createJob, setBudget, fund, submit, complete). |
| `Phase 4+5: agent runtime live multi-surface with reconciliation` | After Block 5 | ≥3 wrapped positions across surfaces; reconciliation log. |

Total expected onchain footprint after a clean v0: **~12–18 transactions** on `testnet.arcscan.app`, all attributable to the desk's `desk_owner` / `judge_validator` / `client_wallet`, all tagged in `logs/judgements.tsv` with `arb_signal_id`, `surface`, `instrument`, and `est_pnl_per_dollar`.

Anything beyond this is v1+.

---

## 9. Drift from prior TASK.md (archived)

| Δ | Prior version | This version | Reason |
|---|---|---|---|
| Δ1 | Narrow to Polymarket S-4 energy events only | Four execution surfaces (crypto + equities + AI predictive + energy) | Aligns spec with actual product per user reframe 2026-05-13 |
| Δ2 | Treats `scorer.py` premium gate as the arb identifier | New `agent/arb_identifier.py` computes `S_t` z-score; scorer is a Polymarket-surface gate only | Per product reframe |
| Δ3 | Says "find the upstream classifier; do not fork it" | No callable upstream classifier exists; the energy classifier IS the standalone classifier (single-gate keywords, no `upstream_category` precondition) | Verified against upstream repo |
| Δ4 | Refers to TSV columns `outcome_win`, `face_value_pnl`, `title`, `description` | Real columns are `resolution_outcome` (WIN/LOSS), `realized_pnl`, `slug`, `event_slug`; pseudo-title derived from `slug + event_slug` | Verified `head -1 master_fills_v4.tsv` |
| Δ5 | Refers to upstream branch `@beldghik` | Actual is `feat/longtail-premium-gate` (SHA pinned in `upstream/PINNED_SHA.txt`) | Verified `git log` |
| Δ6 | Scorer at `~/VSProjects/py-builder-relayer-client/scorer.py:26-79` | At `api/polymarket/longtail/scorer.py:47` | Verified `find . -name scorer.py` |
| Δ7 | ERC-8183 `reject()` mentioned as possible | `reject()` is NOT in the deployed ABI; loss path is `complete(jobId, keccak256("reject:"+reason), "0x")` with final status 3 for both win and loss | Verified against arc-escrow ABI |
| Δ8 | `submit()` / `complete()` may need to wait for `expiredAt` | NOT gated on `expiredAt`; gated on state (Funded → Submitted → Completed); `expiredAt` only governs the Expired(5) failure path | Verified ERC-8183 tutorial |
| Δ9 | 4 hard prerequisites | 8 (add IBKR Gateway + EIA API key + read-only upstream rule) | Multi-surface requires new accounts |
| Δ10 | No paper-PnL probe | New `agent/pnl_probe.py` attaches `est_pnl_per_dollar` to every judgement row + outcome blob; v0-visible without expanding scope past §6 anti-goals | Per user request to make arb numerically legible |

---

## 10. Deferred to v2

- LLM judge (Phase 4.5) — compaction strategy + harness shape to be specified when judge volume justifies stochastic classification
- Scan-loop mode (`--scan` with polling, idle policy, 429/503/RPC-timeout recovery)
- Weekly auto-recap (`reports/weekly/<YYYY-WW>.md` following S2 deck structure)
- GA / Shinka on judge thresholds (after ≥30 days of v0 trace; gate kwarg excluded per §6)
- `skill-reviewer` slash command (when skill count exceeds ~8)
