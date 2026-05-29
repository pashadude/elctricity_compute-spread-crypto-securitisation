# Arc OSS Builder Starter Kit

Self-contained starter kit for Arc builders.

This folder is tracked in the Power by Botozen repo but intentionally isolated
from the product runtime. It focuses only on the Arc builder flow: ERC-8004
identity, ERC-8183 job escrow, Circle Developer-Controlled Wallets, and USDC
budgeting. The core invariant is that no Arc action happens unless the
offchain judge returns `EXECUTE` (`no-chain-unless-EXECUTE`).

Arc OSS folder link to include in the submission form / CLI:

```text
https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation/tree/main/arc-oss-builder-starter-kit
```

## What You Get

- Minimal TypeScript scripts for Arc Testnet.
- ERC-8004 identity registration.
- ERC-8183 job create, budget, fund, submit, complete.
- Circle SCA wallet setup.
- USDC 6-decimal conversion helpers.
- Example verdict and deliverable blobs.
- A verifier that checks this kit keeps the Arc guardrails visible.

## Quickstart

```bash
cp .env.example .env
npm install
npm run check
```

Fill `.env`:

```bash
ARC_RPC=https://rpc.testnet.arc.network
CIRCLE_API_KEY=...
CIRCLE_ENTITY_SECRET=...
ARC_OSS_REPO_URL=https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation/tree/main/arc-oss-builder-starter-kit
```

Optional, for the hackathon authenticated RPC when the Canteen proxy is healthy:

```bash
arc-canteen login
arc-canteen rpc-url --export
```

Paste the printed URL into `.env` as `ARC_RPC`. If `arc-canteen rpc eth_chainId`
fails with DNS/server errors, switch back to:

```bash
ARC_RPC=https://rpc.testnet.arc.network
```

## Run The Arc Flow

Register an ERC-8004 builder identity:

```bash
npm run register-agent
```

The script creates three Circle SCA wallets:

- `builder`: owns the registered ERC-8004 identity and submits deliverables
- `validator`: completes jobs and gives reputation feedback
- `client`: creates and funds ERC-8183 jobs

Open a funded ERC-8183 job. This refuses to run unless the verdict is
`EXECUTE`:

```bash
npm run open-job -- --verdict examples/verdict-execute.json --surface demo --market example --notional 1 --expires-hours 1
```

Submit a deliverable hash:

```bash
npm run submit-deliverable -- --job <jobId> --verdict examples/verdict-execute.json --deliverable examples/deliverable.json
```

Settle and write ERC-8004 reputation feedback:

```bash
npm run settle-job -- --job <jobId> --verdict examples/verdict-execute.json --score 95
```

Try a reject verdict to confirm the guard:

```bash
npm run open-job -- --verdict examples/verdict-reject.json --notional 1
```

Expected result: the script exits before creating a Circle client or Arc
transaction.

## Files

```text
src/arc/addresses.ts       Arc Testnet contract addresses
src/arc/usdc.ts            USDC 6-decimal conversion
src/arc/verdict.ts         EXECUTE guard
src/arc/circle.ts          Circle transaction helpers
src/arc/state.ts           local state writer
src/scripts/*.ts           builder-facing Arc scripts
contracts/abis/*.json      minimal ABIs used by the scripts
examples/*.json            verdict and deliverable fixtures
docs/arc-flow.md           detailed Arc flow
docs/submission.md         submission form / CLI copy
```

## Invariants

1. `assertExecutable()` must run before every job action script touches Circle
   or Arc.
2. Only `EXECUTE` verdicts can open, submit, or settle a job.
3. USDC escrow values use the ERC-20 interface and 6 decimals.
4. Local state files are operational artifacts and must not be committed.
5. Product-specific alpha logic does not belong in this repo.

## Submission Link

```bash
npm run submission-link
```

Paste the printed URL into the Arc OSS submission form and any `arc-canteen`
product update.

The main repository includes a GitHub Actions check at
`.github/workflows/starter-kit-check.yml`; after pushing, GitHub should run
`npm ci`, `npm run check`, and `npm audit --omit=dev` in this folder.
