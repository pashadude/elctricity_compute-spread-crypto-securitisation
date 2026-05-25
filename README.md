# Power by Botozen

Arc-wrapped compute/energy spread desk.

This repository has two distinct surfaces:

- `arc-compute-sec/` is the product demo: the live website, API, worker,
  Telegram integration, Opoint/Nebius/IBKR/Polymarket routing, backtests, and
  Arc settlement path.
- `arc-oss-builder-starter-kit/` is a separate local git repository for the
  Arc OSS starter kit. It is not part of the product runtime and should be
  published independently at
  `https://github.com/pashadude/arc-oss-builder-starter-kit`.

The separation is intentional. The product repo explains the compute/energy
spread desk. The starter kit explains reusable Arc builder primitives without
mixing in product-specific alpha logic.

## Product Thesis

Compute is becoming a commodity, but raw GPU-hours are not yet a clean
securitizable asset. The practical v1 is a judged compute/energy spread
package:

```text
S_t = compute_$_per_gpu_hr - k * electricity_$_per_MWh * kWh_per_gpu_hr
```

The desk searches for dislocations in that spread, builds a canonical package
of direct event legs and proxy hedge legs, runs the energy classifier, premium
gate, and `judge.classify()`, and only then wraps an approved package as an
ERC-8183 job on Arc.

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
npm run test
```

The key invariant is unchanged:

```text
judge.classify() must run before any Arc action, and no chain call may happen
unless the judge verdict is EXECUTE.
```

## Arc OSS Starter Kit

The standalone starter kit exists locally at:

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

Publish it as a separate GitHub repository:

```bash
git push -u origin main
```

Then include this link in the Arc OSS submission form and Arc CLI update:

```text
https://github.com/pashadude/arc-oss-builder-starter-kit
```

Suggested CLI update:

```text
Spun out a standalone Arc OSS builder starter kit:
https://github.com/pashadude/arc-oss-builder-starter-kit

It teaches ERC-8004 identity, ERC-8183 job escrow, Circle SCA wallets,
USDC 6-decimal handling, and the no-chain-unless-EXECUTE invariant without
mixing in the product-specific compute/energy desk.
```

## Documentation Map

- Product technical details: `arc-compute-sec/README.md`
- Arc OSS starter kit docs: `arc-oss-builder-starter-kit/README.md`
- Canonical agent task context: `docs/agent-context/TASK.md`
- Product marketing notes: `docs/marketing/`
