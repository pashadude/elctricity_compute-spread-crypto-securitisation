# Demo Description

## Title

Power by Botozen: Arc-Settled Compute/Energy Spread Desk

## One-Line Description

Power by Botozen turns compute/energy spread signals into judged, auditable Arc ERC-8183 work packages with USDC escrow, ERC-8004 identity, and clear no-chain-unless-EXECUTE guardrails.

## Short Submission Description

The demo shows a live compute/energy spread desk for AI infrastructure. The agent estimates the spread between compute revenue per GPU-hour and electricity cost per MWh, searches for direct event legs and liquid proxy hedge legs, builds a proposed compute receivable hedge note, and only promotes the package after premium scoring and `judge.classify()`.

Arc is used as the settlement and audit rail: approved packages can become ERC-8183 jobs with USDC escrow, deliverable hashes, completion, and ERC-8004 reputation feedback. Polymarket, IBKR, public equities, BTC, and ETH are research or hedge surfaces; they are not hidden as the securitized object. The securitized object is the judged spread package around compute-sale or GPU-hour receivable risk.

## Demo Walkthrough

1. Open the live app:

   ```text
   https://power.botozen.com
   ```

2. Show the landing thesis:

   ```text
   all is compute
   compute is energy
   hedging compute means hedging the compute/energy spread
   ```

3. Open the dashboard:

   ```text
   https://power.botozen.com/dashboard
   ```

   Show the current electricity price, compute price, spread, z-score, mock notional, Circle test USDC ask, agent recommendation, and quote source.

4. Explain the package:

   The agent proposes a synthetic compute receivable hedge note. It starts from a commercial exposure such as a forward GPU-hour sale, invoice, or receivable, then attaches a priced hedge basket and matched direct event refs.

   The frontend shows the build path explicitly:

   ```text
   1. Compute sale / GPU-hour receivable: needs collateral
   2. Priced hedge basket: ready
   3. Direct event refs: ready or pending, depending on live discovery
   4. Judge gates: pending until scorer and judge.classify() run
   5. Arc wrap: locked until the judge returns EXECUTE
   ```

   This is the important securitization nuance. The demo is not claiming a legal ABS is already live. It is showing how an agent builds the package, identifies what collateral is missing, prices the hedge basket, and keeps Arc settlement locked until the evidentiary and judge gates pass.

5. Explain the legs:

   Direct event legs are Polymarket or IBKR ForecastTrader-style claims about grid stress, data center constraints, AI capex, or compute demand. Public stocks, BTC, and ETH are labelled as proxy hedge legs. BTC/ETH are miner-margin proxies, not the securitized asset.

6. Show the gating:

   The system must run the premium scorer and `judge.classify()` before any Arc action. REJECT, DEFER, or CHALLENGE means no Circle or Arc call. Only EXECUTE can become an Arc job.

7. Show the Arc path:

   Approved packages map to ERC-8183 jobs: create job, set USDC budget, fund escrow, submit deliverable hash, complete, and write ERC-8004 reputation feedback.

8. Show Telegram:

   ```text
   https://power.botozen.com/telegram
   https://t.me/botozen_power
   https://t.me/BotozenPowerBot
   ```

   Telegram mirrors the same desk. It does not spam repeated rejects. It posts grouped EXECUTE packages, Arc job updates, and operator-relevant alerts.

9. Show the OSS starter kit:

   ```text
   https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation/tree/main/arc-oss-builder-starter-kit
   ```

   The starter kit exposes reusable Arc primitives: ERC-8004 identity, ERC-8183 escrow, Circle Developer-Controlled Wallets, USDC 6-decimal helpers, EXECUTE/REJECT verdict fixtures, and a verifier proving the guard runs before Circle or Arc calls.

## What To Emphasize In The Video

- This is not "BTC securitizes energy." BTC/ETH are only miner-margin proxy legs.
- The actual object is a judged compute/energy spread package.
- The current note is proposed / synthetic until collateral is attached.
- Missing collateral means no legal asset-backed claim yet: the operator must attach or hash the GPU-hour invoice, receivable, delivery meter, and buyer/seller terms.
- Arc is the settlement, escrow, identity, reputation, and audit rail.
- The alpha/risk decision happens offchain through evidence, scoring, and judge verdicts.
- No chain action happens unless `judge.classify()` returns EXECUTE.
- The OSS contribution is reusable beyond this product: evidence first, verdict second, escrow third.

## Suggested Closing Line

Power by Botozen is a demo of how compute becomes finance: not by pretending GPU-hours are already standardized, but by wrapping audited compute/energy spread packages with Arc settlement and Circle USDC escrow.
