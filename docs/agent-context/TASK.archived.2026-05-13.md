# TASK — Arc-Settled Compute Securitization Agent

**Type:** Build spec for Claude Code (CLI).
**State:** Canonical. Supersedes all prior `compute-securitization-strategist*.md` drafts.
**Scope:** Stand up an agent that takes positions on **energy-themed Polymarket events** as the S-4 (outcomes) surface of the compute-securitization thesis. Reuses the existing `scorer.py` premium gate live in `~/VSProjects/py-builder-relayer-client` on `@beldghik`. Each position is represented as an ERC-8183 job on Arc Testnet with the judge layer as evaluator; reputation writes back to the desk's ERC-8004 identity. S-1 electricity execution, S-2 hashrate factor, S-3 EFU beta, GA over scorer weights, and multi-surface portfolio are **deferred** to v2.

The S-4 energy focus is deliberate: the existing scorer already runs `finance_macro / weekly` at n=40, 100% WR, +$58 in the backward window (slide 10 of `S2_BroadLongtail___Analysis_Recap.pdf`). That's the natural anchor template — broaden it into an energy-specific template universe, gate it the same way, and settle the lifecycle on Arc.

This task is sized so a Claude Code session can finish Phase 0–4 in one sitting, with green-lit Arcscan links to verify each phase.

---

## 0. Hard prerequisites

These must exist **before** the first command runs. Stop and ask if any are missing.

| # | Item | Verify |
|---|------|--------|
| 0.1 | Circle Developer Console account | https://console.circle.com — log in, no error |
| 0.2 | Standard API key created in Console (`Keys → Create a key → API key → Standard Key`) | `console.circle.com/keys` shows the key, scope **TESTNET** |
| 0.3 | Entity Secret registered | `developers.circle.com/wallets/dev-controlled/register-entity-secret` walked through; recovery file downloaded |
| 0.4 | Arc Testnet USDC in a funding wallet (≥ 5 USDC) | https://faucet.circle.com → request → wait 30s → see balance on `testnet.arcscan.app` |
| 0.5 | Node 22+ and Python 3.11+ on the build machine | `node -v && python3 --version` |
| 0.6 | Existing `scorer.py` with `require_non_negative_premium=True` available in `~/VSProjects/py-builder-relayer-client` | `grep -rn "require_non_negative_premium" ~/VSProjects/py-builder-relayer-client/` returns the kwarg line in `scorer.py:26-79` |
| 0.7 | **Do not touch** any other participant's credentials, wallet IDs, or entity secret. Generate fresh ones for this build. | Confirmed by the operator. |
| 0.8 | Upstream relayer repo is **read-only from this build's perspective**. No commits land back in `py-builder-relayer-client` from this task. | Verify by checking out a detached HEAD or pinning a commit SHA for the vendored copy. |

If 0.6 fails: this task assumes the S2 broad-longtail scorer is on hand at the documented path. Stop and surface the gap — do not reimplement. If the repo lives elsewhere, set `UPSTREAM_RELAYER_PATH` in `.env` and use that everywhere instead of the hardcoded path.

---

## 1. Repo layout

Initialize at the project root:

```
arc-compute-sec/
├── .env                           # GITIGNORED. Circle creds + RPC + upstream path.
├── .gitignore                     # node_modules, .env, __pycache__, *.tsv, upstream/
├── README.md                      # Pointer to this task spec.
├── package.json                   # TS side: viem, Circle SDK
├── tsconfig.json
├── requirements.txt               # Python side: web3, circle SDK, pandas
├── contracts/
│   └── arc_addresses.py           # Single source of truth, §2 below
├── upstream/
│   └── py-builder-relayer-client/ # SYMLINK or git submodule (read-only). Source of scorer.py.
├── identity/
│   ├── register_agent.ts          # Phase 1
│   └── agent-metadata.json        # Phase 1
├── jobs/
│   ├── open_position.ts           # Phase 2 — createJob + setBudget + fund
│   ├── submit_outcome.ts          # Phase 2 — submit deliverable
│   └── settle_position.ts         # Phase 2 — complete or reject
├── templates/
│   └── energy/                    # Phase 3 — energy-themed event keyword/classifier rules
│       ├── keywords.yaml          # Seed terms: gas, oil, lng, opec, eia, ferc, ercot, ...
│       ├── classifier.py          # Polymarket event → energy_template_id or None
│       └── catalog.tsv            # Live event candidates discovered per cycle
├── agent/
│   ├── runtime.py                 # Phase 4 — entry point
│   ├── judge.py                   # Phase 4 — four-way classifier
│   ├── scorer_bridge.py           # Phase 4 — wraps upstream/scorer.py without forking
│   ├── polymarket_scanner.py      # Phase 3 — pulls candidate events through energy classifier
│   └── on_chain.py                # Phase 4 — Python → Arc via Circle SDK
├── data/
│   └── master_fills_v4.tsv        # SYMLINK to upstream/.../master_fills_v4.tsv (read-only)
├── tests/
│   ├── test_judge.py
│   ├── test_scorer_bridge.py
│   └── test_energy_classifier.py
└── logs/
    ├── judgements.tsv             # One row per judge decision
    ├── positions.tsv              # One row per ERC-8183 lifecycle stage
    └── arc_txs.tsv                # One row per settled tx
```

All Phase 1/2 scripts are TypeScript (viem + Circle SDK is the documented happy path on Arc). All Phase 3/4 agent logic is Python (matches the existing `scorer.py` and the S2 stack already running in `py-builder-relayer-client`). The bridge between them is the `on_chain.py` module which calls the Circle SDK directly from Python — no shelling out to TS at runtime.

### 1.1 Upstream wiring rule

The `upstream/py-builder-relayer-client/` entry must be either:

- a symlink: `ln -s ~/VSProjects/py-builder-relayer-client upstream/py-builder-relayer-client`, or
- a git submodule pinned to a specific commit SHA (preferred for reproducibility)

**Never copy files out of upstream into this repo.** The scorer code lives in exactly one place. `scorer_bridge.py` adds `upstream/py-builder-relayer-client` to `sys.path` and `import scorer`. If the upstream module name differs, document the actual import path in `scorer_bridge.py` and stop.

Add to `.gitignore`:

```
upstream/
data/master_fills_v4.tsv
```

The symlinked content does not get committed here; the upstream repo is its own source of truth.

---

## 2. Network and contract addresses

Pin these in `contracts/arc_addresses.py`. **Do not** hardcode anywhere else.

```python
# Arc Testnet — verified 2026-05-12 against docs.arc.network/arc/references/contract-addresses.md
# and /arc/references/connect-to-arc.md. Do not edit without re-fetching the source.

CHAIN_ID = 5042002              # 0x4CEF52
CHAIN_NAME = "ARC-TESTNET"      # Circle SDK blockchain identifier
RPC_HTTP = "https://rpc.testnet.arc.network"
RPC_WS   = "wss://rpc.testnet.arc.network"
EXPLORER = "https://testnet.arcscan.app"
FAUCET   = "https://faucet.circle.com"

# Stablecoins
USDC = "0x3600000000000000000000000000000000000000"   # 18 decimals NATIVE / 6 decimals via ERC-20 interface — see §2.1
EURC = "0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a"   # 6 decimals
USYC = "0xe9185F0c5F296Ed1797AaE4238D26CCaBEadb86C"   # 6 decimals, allowlisted

# ERC-8004 agent identity / reputation / validation
IDENTITY_REGISTRY    = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
REPUTATION_REGISTRY  = "0x8004B663056A597Dffe9eCcC1965A193B7388713"
VALIDATION_REGISTRY  = "0x8004Cb1BF31DAf7788923b405b754f57acEB4272"

# ERC-8183 agentic commerce — job lifecycle with escrow
AGENTIC_COMMERCE = "0x0747EEf0706327138c69792bF28Cd525089e4583"

# CCTP v2 (domain 26 = Arc)
CCTP_TOKEN_MESSENGER     = "0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA"
CCTP_MESSAGE_TRANSMITTER = "0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275"
CCTP_TOKEN_MINTER        = "0xb43db544E2c27092c107639Ad201b3dEfAbcF192"
CCTP_DOMAIN_ARC          = 26

# Gateway (chain-abstracted USDC)
GATEWAY_WALLET = "0x0077777d7EBA4688BDeF3E311b846F25870A19B9"
GATEWAY_MINTER = "0x0022222ABE238Cc2C7Bb1f21003F0a260052475B"

# StableFX (used only if S-3 leg needs onchain FX)
FX_ESCROW = "0x867650F5eAe8df91445971f14d89fd84F0C9a9f8"

# Ecosystem
PERMIT2     = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
MULTICALL3  = "0xcA11bde05977b3631167028862bE2a173976CA11"
MEMO        = "0x9702466268ccF55eAB64cdf484d272Ac08d3b75b"
```

### 2.1 USDC decimal rule — read before writing any balance code

USDC on Arc has **two interfaces** with different decimals:

- Native balance — 18 decimals (gas accounting precision)
- ERC-20 interface at `0x3600000000000000000000000000000000000000` — 6 decimals

**Rule:** All application code uses the ERC-20 interface and 6 decimals. Always call `decimals()` to confirm before sending. **Never** mix the two in a single arithmetic expression. Document this rule with a comment at every spot that does an amount conversion. Bug-class to avoid: `parseUnits("5", 18)` for a 5 USDC transfer — that sends 5e12 USDC and burns testnet funds for no reason.

### 2.2 EVM compile target — read before deploying any custom contract

If `use-smart-contract-platform` is used for a custom contract in Phase 4.5+ (deferred), compile with `evmVersion: "paris"` or earlier. Solidity ≥ 0.8.20 defaults to **shanghai**, which emits PUSH0. Arc Testnet rejects PUSH0 with `ESTIMATION_ERROR / Create2: Failed on deploy`. This is the most common failure mode reported on the `circlefin/skills` repo and it has nothing to do with the contract logic.

---

## 3. Phase 0 — install and verify

### 3.1 Skills + MCP

```bash
# Claude Code plugin marketplace
/plugin marketplace add circlefin/skills
/plugin install circle-skills@circle

# Hosted Circle MCP server — ground-truth SDK signatures and addresses
claude mcp add --transport http circle https://api.circle.com/v1/codegen/mcp --scope user
claude mcp get circle   # verify
```

**Verify:** Both commands succeed. The skills appear at `~/.claude/plugins/.../circle-skills/plugins/circle/skills/` and you can `cat` `use-arc/SKILL.md` and `use-developer-controlled-wallets/SKILL.md`. If they don't, the rest of this task is built on the wrong foundation — stop and fix.

### 3.2 Project bootstrap

```bash
mkdir arc-compute-sec && cd arc-compute-sec
git init
git branch -m main feat/arc-mvp

# TypeScript side
npm init -y
npm pkg set type=module
npm pkg set scripts.register-agent="tsx --env-file=.env identity/register_agent.ts"
npm pkg set scripts.open-position="tsx --env-file=.env jobs/open_position.ts"
npm pkg set scripts.submit-outcome="tsx --env-file=.env jobs/submit_outcome.ts"
npm pkg set scripts.settle-position="tsx --env-file=.env jobs/settle_position.ts"
npm install @circle-fin/developer-controlled-wallets viem
npm install --save-dev tsx typescript @types/node

# Python side
python3 -m venv .venv
source .venv/bin/activate
cat > requirements.txt <<'EOF'
circle-developer-controlled-wallets
web3
python-dotenv
pandas
numpy
EOF
pip install -r requirements.txt

# tsconfig
cat > tsconfig.json <<'EOF'
{
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "types": ["node"]
  }
}
EOF

# .env (template — fill in real values, do not commit)
cat > .env <<'EOF'
CIRCLE_API_KEY=
CIRCLE_ENTITY_SECRET=
ARC_RPC=https://rpc.testnet.arc.network
UPSTREAM_RELAYER_PATH=/Users/pauldudko/VSProjects/py-builder-relayer-client
EOF

# Wire upstream as a symlink (read-only consumption pattern)
mkdir -p upstream
ln -s "$(grep UPSTREAM_RELAYER_PATH .env | cut -d= -f2)" upstream/py-builder-relayer-client

# Verify the scorer is reachable
test -f upstream/py-builder-relayer-client/scorer.py && \
  grep -n "require_non_negative_premium" upstream/py-builder-relayer-client/scorer.py || \
  { echo "FAIL: scorer.py not found at upstream path. Update UPSTREAM_RELAYER_PATH in .env."; exit 1; }

# .gitignore
cat > .gitignore <<'EOF'
node_modules/
.venv/
__pycache__/
.env
*.tsv
*.log
.DS_Store
upstream/
data/master_fills_v4.tsv
EOF

git add -A && git commit -m "Phase 0: project bootstrap"
```

### 3.3 Smoke test — round-trip USDC on Arc

Write `scripts/smoke.ts` that:

1. Creates a single SCA Circle Wallet on `ARC-TESTNET`.
2. Prints its address.
3. **Pauses** for the operator to fund it from `faucet.circle.com`.
4. After Enter, queries balance via `getWalletTokenBalance`.
5. Sends 0.01 USDC back to the faucet's documented sink address (or another known wallet — the destination matters less than the transaction succeeding).
6. Polls `getTransaction` until state = `COMPLETE`.
7. Prints the txHash and `testnet.arcscan.app/tx/<hash>` link.

**Acceptance:** The smoke script returns a CONFIRMED tx whose explorer link resolves and shows ≥ 1 confirmation. If this fails the rest of the task does not run.

Commit:

```bash
git add -A && git commit -m "Phase 0: USDC round-trip smoke test passing on Arc Testnet"
```

---

## 4. Phase 1 — register the desk's onchain identity (ERC-8004)

The desk gets one ERC-8004 identity. It will be the **provider** of every job (the entity performing the work) and own its reputation history. The judge layer is a **separate validator wallet** — per ERC-8004 rules, an owner cannot record reputation for its own agent, which is exactly the separation-of-concerns property the judge needs.

### 4.1 Agent metadata

Write `identity/agent-metadata.json`:

```json
{
  "name": "Compute Securitization Desk v0",
  "description": "Agentic desk taking positions on compute-electricity spread surfaces (electricity, hashrate, financial-uncertainty beta, predictive outcomes). Settles on Arc via ERC-8183 jobs with USDC escrow.",
  "image": "ipfs://bafkreibdi6623n3xpf7ymk62ckb4bo75o3qemwkpfvp5i25j66itxvsoei",
  "agent_type": "trading",
  "capabilities": [
    "premium_gate_screening",
    "polymarket_orderflow",
    "spread_surface_pricing",
    "judge_layer_4way_classification"
  ],
  "version": "0.1.0",
  "homepage": "https://github.com/<your-handle>/arc-compute-sec",
  "code_path": "scorer.py:26-79 (premium_gate), agent/judge.py (4-way classifier)"
}
```

For Phase 1, **use the IPFS URI in the JSON above as a placeholder**. Real IPFS pinning is v2 polish.

### 4.2 Registration script

`identity/register_agent.ts` follows the ERC-8004 quickstart exactly (Circle's published flow at `docs.arc.network/arc/tutorials/register-your-first-ai-agent.md`). Key requirements:

- Create **two** SCA wallets via `createWallets({ blockchains: ["ARC-TESTNET"], count: 2, accountType: "SCA" })`. Wallet 0 = `desk_owner`, Wallet 1 = `judge_validator`.
- Pause and prompt operator to fund `desk_owner` with ≥ 2 USDC. (Faucet rate limit: don't fund both — Phase 2 will transfer starter USDC from `desk_owner` to `judge_validator`.)
- Call `register(string)` on `IDENTITY_REGISTRY` from `desk_owner`. metadataURI = the IPFS URI in `agent-metadata.json`.
- Poll the Circle transaction until `COMPLETE`. Extract the txHash.
- Query `IDENTITY_REGISTRY` for the `Transfer` event with `to: desk_owner.address` over the last 10000 blocks. The `tokenId` argument is the `desk_agent_id`.
- Verify `ownerOf(desk_agent_id) == desk_owner.address` and `tokenURI(desk_agent_id) == METADATA_URI`.
- Write all output to `logs/identity.tsv`:

```
ts | desk_owner_addr | desk_owner_id | judge_validator_addr | judge_validator_id | desk_agent_id | register_tx_hash
```

This file is the source of truth for every later phase. The Python runtime reads it on startup.

### 4.3 Validation rehearsal (proves the judge wallet is wired)

In the same script, after registration:

- From `desk_owner`, call `validationRequest(judge_validator.address, desk_agent_id, "ipfs://...", keccak256("phase1-rehearsal"))`.
- From `judge_validator`, call `validationResponse(requestHash, 100, "", 0x0...0, "phase1-rehearsal")`.
- Read back `getValidationStatus(requestHash)` and assert `response == 100`.

**Acceptance:** All three transactions visible on `testnet.arcscan.app`. `logs/identity.tsv` contains exactly one row. Re-running the script does not create duplicates (guard with: if file exists, exit with the existing addresses).

Commit:

```bash
git add -A && git commit -m "Phase 1: ERC-8004 desk identity registered; judge validator wired"
```

---

## 5. Phase 2 — represent one position as an ERC-8183 job

**The mapping:** every position the desk takes on a spread surface is one job.

| ERC-8183 role | Compute-securitization meaning |
|---|---|
| `client` | The capital owner buying spread exposure. Phase 2 uses a third Circle Wallet (`client_wallet`) standing in for an external buyer. |
| `provider` | The desk (`desk_owner` wallet). Sets the budget = the spread's notional. |
| `evaluator` | The judge layer (`judge_validator` wallet). Decides `complete` vs `reject` based on outcome + premium gate signal. |
| `description` | Human-readable surface identifier: e.g. `"S-4 outcome | polymarket | <market_id> | premium_gated"`. |
| `expiredAt` | Position expiry (Polymarket resolution time + buffer for S-4; weekly rebal cutoff for S-2/S-3). |
| `hook` | `address(0)` in v0. Real hook for post-settle PnL writeback is v2. |
| `budget` | Notional in USDC (6 decimals). |
| `deliverable (bytes32)` | `keccak256(canonical_outcome_blob)` where the blob is the resolved market state + scorer's premium check result. Stored offchain; chain only sees the hash. |
| `reason (bytes32)` | `keccak256(judge_verdict_blob)` where the blob is the 4-way classification + reason code. |

States the desk cares about: `Open(0) → Funded(1) → Submitted(2) → Completed(3)` for a winning position; `Open → Funded → Submitted → Rejected(4)` for a losing one; `Expired(5)` if the deliverable never lands.

### 5.1 Scripts

Three scripts. Each reads `logs/identity.tsv` for the wallet addresses. None of them re-create wallets.

**`jobs/open_position.ts`** — argv: `--surface S4 --market <id> --notional <usdc> --expires-hours <n>`

1. Read identity.tsv. Resolve `client_wallet` (Phase 2 creates a third wallet on first run, persisted in `logs/identity.tsv`).
2. Compute `expiredAt = block.timestamp + expires_hours * 3600`.
3. From `client_wallet`: `createJob(desk_owner, judge_validator, expiredAt, description, address(0))`.
4. Wait for COMPLETE. Extract `jobId` from `JobCreated` event.
5. From `desk_owner`: `setBudget(jobId, notional_usdc_6dec, "0x")`.
6. From `client_wallet`: `approve(USDC, AGENTIC_COMMERCE, notional)` then `fund(jobId, "0x")`.
7. Verify `getJob(jobId).status == 1` (Funded).
8. Append to `logs/positions.tsv`:

```
ts | jobId | surface | market_id | notional | expiredAt | description | open_tx | fund_tx
```

**`jobs/submit_outcome.ts`** — argv: `--job <id> --outcome-blob-path <file>`

1. Read the outcome blob from disk (Python runtime writes it — see §7.3).
2. `deliverableHash = keccak256(outcomeBlob)`.
3. From `desk_owner`: `submit(jobId, deliverableHash, "0x")`.
4. Verify `getJob(jobId).status == 2` (Submitted).
5. Append to `logs/positions.tsv` (new column or new row, your choice — be consistent).

**`jobs/settle_position.ts`** — argv: `--job <id> --verdict-blob-path <file> --action complete|reject`

1. Read the verdict blob (judge writes it).
2. `reasonHash = keccak256(verdictBlob)`.
3. If `action == complete`: from `judge_validator`, call `complete(jobId, reasonHash, "0x")`. If `reject`: call `reject(jobId, reasonHash, "0x")` (assuming the reference contract exposes it; if not, the v0 path is `complete` with `reasonHash = keccak256("reject:<reason>")` — verify against the deployed ABI first).
4. Optionally write reputation: from `judge_validator`, `giveFeedback(desk_agent_id, score_int128, kind_uint8, tag_string, "", "", "", feedbackHash)` where score is derived from outcome (e.g., `loanRepaidOnTime ? 100 : 20` analog → `position_in_money ? 95 : 25`).
5. Verify final state. Append to `logs/positions.tsv`.

### 5.2 Manual end-to-end on one mock position

```bash
npm run open-position -- --surface S4 --market mock-001 --notional 1 --expires-hours 1
# Note the jobId from the output

# Pretend the outcome resolved
echo '{"market":"mock-001","outcome":"YES","resolved_at":"<ISO>","premium_at_open":0.04}' > /tmp/outcome.json
npm run submit-outcome -- --job <jobId> --outcome-blob-path /tmp/outcome.json

# Pretend the judge said complete
echo '{"verdict":"EXECUTE","reason_code":"premium_positive_outcome_yes","score":95}' > /tmp/verdict.json
npm run settle-position -- --job <jobId> --verdict-blob-path /tmp/verdict.json --action complete
```

**Acceptance:** All 4 transactions land. `getJob(<jobId>).status == 3`. `client_wallet` balance is down by `notional`, `desk_owner` balance is up by `notional` (or `notional - platform_fee` if the reference contract takes one). All txs visible on `testnet.arcscan.app`. `logs/positions.tsv` reflects the full lifecycle.

Commit:

```bash
git add -A && git commit -m "Phase 2: ERC-8183 job lifecycle end-to-end on Arc Testnet (mock position)"
```

---

## 6. Phase 3 — energy-themed Polymarket template universe

The compute-securitization thesis frames the S-4 (outcomes) surface around AI-infrastructure bottlenecks. The cleanest first cut of that surface on Polymarket is **energy** — gas prices, oil prices, OPEC/EIA/FERC/ERCOT events, LNG export decisions, grid interconnect approvals. The existing scorer already runs `finance_macro / weekly` cleanly (n=40, 100% WR, +$58, gate not engaged because zero negative-premium fills). Phase 3 widens that template to capture more energy events without breaking the existing categorization.

### 6.1 Reuse the existing categorizer; do not rewrite it

The upstream relayer already has a category classifier that produces labels like `social_media`, `entertainment`, `finance_equity`, `finance_macro`, `finance_crypto_corridor`, `other`. Find it:

```bash
grep -rn "finance_macro\|finance_crypto_corridor" upstream/py-builder-relayer-client/ | head -20
```

The classifier is the source of truth for category assignment. **Do not fork it.** Instead, build a **subclassifier** that runs after the upstream classifier returns a label, and assigns an `energy_template_id` only when the event passes both:

1. Upstream category ∈ {`finance_macro`, `finance_crypto_corridor`, `other`} (where energy events most plausibly land)
2. Event title / description matches at least one entry in `templates/energy/keywords.yaml`

If either fails, `energy_template_id` is `None` and the event is not in scope for Phase 3/4. The upstream scorer continues to handle it through its normal flow on `@beldghik` — this build does not interfere.

### 6.2 `templates/energy/keywords.yaml`

Seed list. Start narrow, widen only when the live trace justifies it. Each top-level key is a template_id; each value is a list of case-insensitive substrings or regex patterns.

```yaml
# Phase 3 seed. v1. Add new templates only after backward-window check (§6.4).
energy_oil_price:
  - "wti"
  - "brent"
  - "crude oil"
  - "oil price"
  - "barrel"
  - "opec"

energy_gas_price:
  - "natural gas"
  - "henry hub"
  - "ttf"
  - "lng"
  - "gas price"

energy_electricity:
  - "electricity price"
  - "power price"
  - "megawatt"
  - "mwh"
  - "eex"
  - "nordpool"
  - "ercot"
  - "pjm"
  - "grid"
  - "blackout"
  - "interconnect"

energy_policy:
  - "ferc"
  - "eia"
  - "doe"
  - "iea"
  - "spr"          # strategic petroleum reserve
  - "export ban"
  - "sanctions"

energy_ai_infra:   # the compute-securitization spread, narrow form
  - "data center"
  - "data-center"
  - "hyperscaler"
  - "gpu power"
  - "ai power demand"
```

### 6.3 `templates/energy/classifier.py`

```python
"""Energy subclassifier. Runs after upstream category assignment.

Returns one of the template_ids in keywords.yaml, or None.
Conservative: prefers None over a false-positive match.
"""
import re
from pathlib import Path
import yaml

_KW_PATH = Path(__file__).parent / "keywords.yaml"
_KEYWORDS: dict[str, list[str]] = yaml.safe_load(_KW_PATH.read_text())

# Categories from upstream where energy events plausibly land.
# Found empirically — slide 12 of the S2 deck lists the active categories.
_PLAUSIBLE_UPSTREAM_CATS = {"finance_macro", "finance_crypto_corridor", "other"}


def classify_energy(
    title: str,
    description: str,
    upstream_category: str,
) -> str | None:
    """Return energy_template_id or None.

    Two gates, both must pass:
      1. upstream_category in the plausible set
      2. at least one keyword match across title + description
    """
    if upstream_category not in _PLAUSIBLE_UPSTREAM_CATS:
        return None

    blob = f"{title}\n{description}".lower()
    for template_id, patterns in _KEYWORDS.items():
        for p in patterns:
            # Treat patterns as substrings unless they contain regex metachars.
            if re.search(r"[.\\*+?\[\]()|]", p):
                if re.search(p, blob, re.IGNORECASE):
                    return template_id
            else:
                if p.lower() in blob:
                    return template_id
    return None
```

### 6.4 Backward-window dry run — **mandatory** before any live use

Before any Phase 3 candidate touches the chain, run the classifier offline against the existing `master_fills_v4.tsv` (1,296 resolved fills) to see how many would have been picked up and what the WR / face-value would have been.

```python
# tests/backward_check_energy_templates.py — run once, paste result into Phase 3 commit
import pandas as pd
from templates.energy.classifier import classify_energy

df = pd.read_csv("data/master_fills_v4.tsv", sep="\t")
df["energy_template_id"] = df.apply(
    lambda r: classify_energy(r["title"], r.get("description", ""), r["category"]),
    axis=1,
)
caught = df[df["energy_template_id"].notna()]
print(f"n_caught = {len(caught)} / {len(df)}")
print(caught.groupby("energy_template_id").agg(
    n=("title", "count"),
    wr=("outcome_win", "mean"),
    pnl=("face_value_pnl", "sum"),
))
```

**Acceptance criteria for Phase 3:**

| Check | Pass condition | What it rules out |
|---|---|---|
| Total caught | `n_caught` in `[10, 100]` against the 1,296-fill backward window | < 10: classifier too narrow, no signal. > 100: too broad, will pollute. |
| Per-template floor | every template_id with `n >= 5` has `wr >= 0.85` | Loose templates that would drag the gate-net positive WR down |
| Premium gate behavior | re-run scorer on the caught subset with `require_non_negative_premium=True`; rejection rate > 0 | Confirms gate engages on the new template universe just like it does on existing ones |
| Backward face-value | gated subset PnL > 0 | If gating hurts here, do not promote the template. Same logic as the slide-10 social_media/daily flip. |

If any check fails, **iterate on `keywords.yaml`** (tighten or widen) until all four pass. Do not deploy until they do. Same five-check methodology as the deck's pre-deployment validation, scaled to template-launch.

### 6.5 Polymarket scanner

`agent/polymarket_scanner.py` polls the same Polymarket CLOB endpoint the relayer uses (find the exact endpoint by `grep -rn "clob.polymarket.com\|gamma-api" upstream/`). For each candidate event:

1. Pull title, description, outcomes, current YES prices, resolution time.
2. Get `upstream_category` by calling the upstream classifier (do not duplicate logic).
3. Call `classify_energy(title, description, upstream_category)`.
4. If `energy_template_id is not None`, append to `templates/energy/catalog.tsv`:

```
ts | event_id | upstream_category | energy_template_id | title | resolution_time | yes_prices
```

5. Return only the energy-tagged candidates to the runtime in Phase 4.

### 6.6 Phase 3 acceptance

- `templates/energy/keywords.yaml` exists, seeded with the categories in §6.2.
- `classify_energy()` has at least 6 passing unit tests (positive match on every template, negative match on a non-energy event in a plausible upstream category, negative match on an energy keyword in an implausible upstream category like `social_media`).
- Backward-window dry run passes all 4 acceptance checks. Output committed at `templates/energy/backward_check.txt`.
- Scanner runs against live Polymarket and produces ≥ 1 row in `catalog.tsv` (Polymarket usually has at least one energy-themed event open at any time).

Commit:

```bash
git add -A && git commit -m "Phase 3: energy-themed S-4 template universe; backward-window validation passing"
```

---

## 7. Phase 4 — wire the agent runtime

Now the Python agent calls the chain. No more manual invocations.

### 7.1 `agent/scorer_bridge.py`

Wraps the existing `scorer.py` (lives in `upstream/py-builder-relayer-client/`) so it can be called as a function with structured arguments, **without modifying** the original file. The bridge:

- Adds `upstream/py-builder-relayer-client` to `sys.path` at import time.
- Imports the upstream `scorer` module.
- Exposes `score_candidate(candidate, event_avg_yes_price) -> dict` returning `{"passes_gate": bool, "premium": float, "rejection_reason": str|None, "raw_score": float}`.
- Calls the gate with `require_non_negative_premium=True` (default-on, never set False from this codepath — the S1/S3 corridor's `False` call site lives elsewhere and is not this build's concern).
- If the upstream module name differs from `scorer` (e.g. it's `src.scorer` or `pmm.scoring.scorer`), document the actual import path at the top of `scorer_bridge.py` and stop. Do not paper over by guessing.

### 7.2 `agent/judge.py`

The 4-way classifier. Pure Python — no LLM call inside the judge itself yet (v0 uses rule-based; LLM judge is Phase 4.5). The rules:

```python
def classify(action: dict, state: dict, scorer_result: dict) -> dict:
    """
    Returns {"label": "EXECUTE"|"CHALLENGE"|"DEFER"|"REJECT",
             "reason_code": str,
             "confidence": float}
    """
    # REJECT — hard gates first
    if not scorer_result["passes_gate"]:
        return {"label": "REJECT", "reason_code": "premium_gate_fail", "confidence": 1.0}
    if action["notional_usdc"] > state["max_position_usdc"]:
        return {"label": "REJECT", "reason_code": "size_cap_breach", "confidence": 1.0}
    if state["positions_open"] >= state["max_concurrent_positions"]:
        return {"label": "REJECT", "reason_code": "concurrency_cap", "confidence": 1.0}

    # DEFER — data freshness / under-sampled surface
    if state["surface_resolutions_30d"] < state["min_resolutions_for_execute"]:
        return {"label": "DEFER", "reason_code": "surface_under_sampled", "confidence": 0.8}
    if action["data_age_seconds"] > state["max_data_age_seconds"]:
        return {"label": "DEFER", "reason_code": "stale_data", "confidence": 0.9}

    # CHALLENGE — non-trivial size with conviction asymmetry
    if action["notional_usdc"] > state["challenge_threshold_usdc"]:
        return {"label": "CHALLENGE", "reason_code": "size_above_challenge_threshold", "confidence": 0.6}

    # EXECUTE
    return {"label": "EXECUTE", "reason_code": "all_gates_passed", "confidence": 0.95}
```

Every call writes a row to `logs/judgements.tsv`:

```
ts | action_kind | action_payload_hash | energy_template_id | label | reason_code | confidence | scorer_premium | scorer_passes_gate
```

The `energy_template_id` column is populated from the candidate's classifier output in Phase 3 — every chain action is traceable back to a template, which is what enables the per-template gate behavior monitoring (§7.5).

`CHALLENGE` in v0 routes to `DEFER` (no debate loop yet — that's Phase 4.5). Document the deferral so the v2 work picks it up.

### 7.3 `agent/on_chain.py`

Python calls to the Circle SDK. Mirrors the TS scripts in §5 but driven from the agent loop:

- `open_position(surface, market_id, notional, expires_hours) -> jobId`
- `submit_outcome(jobId, outcome_dict) -> tx_hash` — writes the dict as JSON to a temp file, hashes it, calls `submit`, returns the tx hash.
- `settle_position(jobId, verdict_dict, action: Literal["complete","reject"]) -> tx_hash`
- `write_reputation(score: int, tag: str, kind: int = 0) -> tx_hash`

Critical: every chain call goes **through the judge first**. The bridge function looks like:

```python
def open_position_judged(surface, market_id, notional, expires_hours):
    action = {"kind": "open_position", "surface": surface, "market_id": market_id,
              "notional_usdc": notional, "expires_hours": expires_hours,
              "data_age_seconds": _get_data_age(market_id)}
    state = _load_state()
    scorer_result = scorer_bridge.score_candidate(_market_to_candidate(market_id), _event_avg(market_id))
    verdict = judge.classify(action, state, scorer_result)
    judge.log(verdict, action)
    if verdict["label"] != "EXECUTE":
        return {"executed": False, "verdict": verdict}
    job_id = on_chain.open_position(surface, market_id, notional, expires_hours)
    return {"executed": True, "verdict": verdict, "job_id": job_id}
```

No on-chain action ever bypasses the judge. This is non-negotiable — same rule as `require_non_negative_premium=True` is the default in `scorer.py`.

### 7.4 `agent/runtime.py`

Minimal v0 entry point. Two run modes:

```python
# Mock mode — manual market id, useful for the acceptance test cases below
# python -m agent.runtime --once --market <id> --notional 1

# Scan mode — pull live energy candidates from Phase 3 classifier, judge each, execute survivors
# python -m agent.runtime --scan --max-positions 1 --notional 1
```

Output per executed candidate: one `jobId` on Arc, one row in `logs/positions.tsv`, one row in `logs/judgements.tsv` with `energy_template_id` populated. For rejected candidates: no `jobId` and only the judgement row.

### 7.5 Acceptance for Phase 4

Run on **three test cases** and verify the explorer:

**Case A — should EXECUTE.** Mock an energy event with `energy_template_id = "energy_oil_price"`, `premium = +0.03`, notional = 1 USDC, fresh data.

Expected: judge returns EXECUTE → `open_position` called → `jobId` created → `submit_outcome` called on the resolved mock outcome → `settle_position --action complete` called → reputation row written with score ≥ 90. `logs/judgements.tsv` has 1 EXECUTE row with the template_id.

**Case B — should REJECT on premium gate.** Same energy template, but `premium = -0.02` (gate fails).

Expected: judge returns REJECT with `reason_code = premium_gate_fail` → no chain call → `logs/judgements.tsv` has 1 REJECT row. **Verify the rejection counter increments** — this is the same live-trace property the S2 deck flagged (if rejection counter is zero for two consecutive days, the gate isn't engaging).

**Case C — should be filtered by classifier before reaching the judge.** Mock a Polymarket event whose title is "Will Taylor Swift release an album in Q4?" — `upstream_category = social_media`. Even if you craft a positive premium, the energy classifier returns `None` and the runtime drops the candidate before scoring.

Expected: no row in `logs/judgements.tsv`, no chain action, one row in `templates/energy/catalog.tsv` is **absent** because the event never qualified. Verifies the classifier is doing real work.

Commit:

```bash
git add -A && git commit -m "Phase 4: agent runtime with 4-way judge gating every Arc tx (energy-themed candidates)"
```

---

## 8. Output of this build

When all four phases are green:

| Artifact | Path | Verification |
|---|---|---|
| Desk identity | ERC-8004 token on Arc Testnet | Visible at `testnet.arcscan.app/address/<desk_owner>` and `address/<IDENTITY_REGISTRY>` |
| At least one completed job | ERC-8183 job, status = Completed | `testnet.arcscan.app/address/0x0747EEf0706327138c69792bF28Cd525089e4583` shows the txs |
| At least one rejected candidate | Row in `logs/judgements.tsv`, no chain side-effect | `wc -l logs/judgements.tsv` ≥ 2, no orphan job onchain |
| Reputation row written by judge | ReputationRegistry event | `testnet.arcscan.app/address/0x8004B663056A597Dffe9eCcC1965A193B7388713` filtered by validator |
| All credentials in `.env`, never committed | `git log --all --full-history -- .env` is empty | OK |

---

## 9. Anti-goals — what this task is not

- **Not building a custom Solidity contract.** ERC-8183 reference is deployed at `0x0747EEf0706327138c69792bF28Cd525089e4583`. Use it. Custom escrow logic is v2.
- **Not implementing Polymarket execution.** The Polymarket leg uses the existing scorer's premium gate; the desk represents the *outcome* of that leg as an ERC-8183 deliverable. Polymarket order placement stays on `@beldghik` exactly as it runs today.
- **Not touching the upstream `py-builder-relayer-client` repo.** Read-only. The energy classifier is a sidecar in this repo, not a fork.
- **Not touching the S1/S3 crypto-corridor desks.** They run with `require_non_negative_premium=False` at their call site — Phase 0 must not regress that.
- **Not running the full S-4 universe through the agent.** Phase 3 narrows to energy-themed events only. Other S-4 templates (chip delivery, hyperscaler capex, etc.) come in v2 after the energy template universe has live trace.
- **Not running the GA (Shinka) loop.** Deferred until ≥ 30 days of v0 trace.
- **Not deploying to Arc Mainnet.** Mainnet doesn't exist yet. When it does, the cutover is a new task, not an addendum.
- **Not building an LLM-based judge.** v0 judge is rule-based. LLM judge for `CHALLENGE` debate is Phase 4.5 — a separate task with its own acceptance criteria.
- **Not using anyone else's wallets, entity secret, or wallet IDs.** Fresh credentials per the operator's rule. The other participant's Arc indexer screenshot (~63k txs across `traces` / `crosschain_events` / `agents` / `agent_jobs`) is a reference for *what's possible*, not a substrate to plug into.

---

## 10. Pinned references

These pages are checked against the spec on 2026-05-12. If a reference changes in a way that breaks the spec, update the spec — don't patch around it.

| Topic | URL |
|---|---|
| Arc llms.txt index | https://docs.arc.network/llms.txt |
| Arc contract addresses | https://docs.arc.network/arc/references/contract-addresses.md |
| Arc network details (chain ID, RPC) | https://docs.arc.network/arc/references/connect-to-arc.md |
| ERC-8004 quickstart (agent identity) | https://docs.arc.network/arc/tutorials/register-your-first-ai-agent.md |
| ERC-8183 quickstart (job lifecycle) | https://docs.arc.network/arc/tutorials/create-your-first-erc-8183-job.md |
| Circle Skills (canonical list) | https://developers.circle.com/ai/skills |
| Circle MCP server | https://developers.circle.com/ai/mcp |
| `use-arc` SKILL.md | https://github.com/circlefin/skills/blob/master/plugins/circle/skills/use-arc/SKILL.md |
| `use-developer-controlled-wallets` SKILL.md | https://github.com/circlefin/skills/blob/master/plugins/circle/skills/use-developer-controlled-wallets/SKILL.md |
| `use-smart-contract-platform` SKILL.md | https://github.com/circlefin/skills/blob/master/plugins/circle/skills/use-smart-contract-platform/SKILL.md |
| Calling contracts with Circle Wallets (createContractExecutionTransaction) | https://www.circle.com/blog/calling-smart-contracts-with-circle-wallets |
| Consolidating crosschain USDC (CCTP + Gateway on Arc) | https://www.circle.com/blog/consolidate-crosschain-usdc-fast-low-cost-transfers-with-cctp-and-gateway |
| Arc faucet | https://faucet.circle.com |
| Arc Testnet explorer | https://testnet.arcscan.app |
| arc-escrow reference repo (when needed) | https://github.com/circlefin/arc-escrow |
| Upstream Polymarket scorer (this build's source) | `~/VSProjects/py-builder-relayer-client/scorer.py` |
| Backward-window data | `~/VSProjects/py-builder-relayer-client/.../master_fills_v4.tsv` (1,296 fills) |

---

## 11. Phase summary — what gets committed when

| Commit | When | Onchain proof |
|---|---|---|
| `Phase 0: project bootstrap` | After §3.2 | None — just files. Symlink to upstream verified. |
| `Phase 0: USDC round-trip smoke test passing on Arc Testnet` | After §3.3 | 1 USDC transfer tx |
| `Phase 1: ERC-8004 desk identity registered; judge validator wired` | After §4.3 | 3 txs (register + validationRequest + validationResponse) |
| `Phase 2: ERC-8183 job lifecycle end-to-end on Arc Testnet (mock position)` | After §5.2 | 6 txs (createJob + setBudget + approve + fund + submit + complete) |
| `Phase 3: energy-themed S-4 template universe; backward-window validation passing` | After §6.6 | None — offline classifier validation. `templates/energy/backward_check.txt` committed. |
| `Phase 4: agent runtime with 4-way judge gating every Arc tx (energy-themed candidates)` | After §7.5 | Case A: full lifecycle txs with `energy_template_id` populated. Case B: zero new chain txs. Case C: zero new chain txs and no judgement row. |

Total expected onchain footprint after a clean v0: ~12–15 transactions, all on `testnet.arcscan.app`, all attributable to the desk's `desk_owner` and `judge_validator` wallets, all tagged in `logs/judgements.tsv` with the energy template that produced them.

Anything beyond this is v2.
