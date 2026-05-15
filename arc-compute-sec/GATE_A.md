# Gate A — operator credential setup

Block 1 (autonomous scaffolding + offline tests + classifier validation) is complete.
The next blocks (chain operations, live feeds, IBKR paper trades) need credentials
and a running IB Gateway. Walk through these in order; resume Block 2 after.

## 1. Circle (testnet)

1. Sign in to `https://console.circle.com` — create an account if needed.
2. Go to `https://console.circle.com/keys` → **Create a key → API key → Standard Key**.
   Make sure the scope is **TESTNET**, not mainnet. Copy the key.
3. Walk through `https://developers.circle.com/wallets/dev-controlled/register-entity-secret`
   to register an Entity Secret. **Download the recovery file** and store it
   somewhere safe — Circle can't regenerate it.
4. Paste both into `arc-compute-sec/.env`:
   ```
   CIRCLE_API_KEY=<your TESTNET key>
   CIRCLE_ENTITY_SECRET=<your entity secret>
   ```

## 2. Arc Testnet USDC funding

Run `npm run smoke` once Circle creds are in `.env`. It will:
- Create one SCA wallet, print the address
- Pause and prompt you to fund it at `https://faucet.circle.com` (request ≥ 5 USDC)
- After Enter, do a 0.01 USDC self-transfer and print an `arcscan.app/tx/<hash>` link

Note: the faucet rate-limits per-IP. **One faucet call is enough** — all
downstream wallets (desk_owner, judge_validator, client_wallet) get seeded
via internal transfer from this first funded wallet.

## 3. EIA API key (free)

1. Register at `https://www.eia.gov/opendata/register.php` — you'll receive
   the key by email. No payment, no scope to choose.
2. Add to `.env`:
   ```
   EIA_API_KEY=<your key>
   ```

## 4. IBKR Paper Trading Gateway

1. You need an Interactive Brokers **Paper Trading** account. If you only
   have a live account, log in to Account Management → User Management →
   add a paper-trading sub-account.
2. Download IB Gateway (lighter than TWS) from `https://www.interactivebrokers.com/en/index.php?f=16454`.
   Log in **with the paper-trading user**, not the live one.
3. In Gateway: **Configure → Settings → API → Settings**:
   - "Enable ActiveX and Socket Clients" ✓
   - **Socket port**: 4002 (paper) — make sure this matches `IBKR_GATEWAY_PORT` in `.env`
   - "Read-Only API" should be **OFF** (otherwise paper orders are rejected)
   - "Trusted IP Addresses": add `127.0.0.1`
4. Verify: `nc -z localhost 4002` returns 0. Then `python -c "from adapters.ibkr import fetch_last_price; print(fetch_last_price('GOOGL'))"` should print a number.

## 5. Resume Block 2

Once all four prerequisites are in place, the operator says "ready" and the
next session continues with:

- `npm run smoke` — USDC round-trip
- `python -m feeds.eia` + `python -m feeds.aws_spot` — live data smoke
- `python -c "from adapters.ibkr import fetch_last_price; print(fetch_last_price('GOOGL'))"` — IBKR smoke
- `npm run register-agent` — Phase 1 ERC-8004 identity
- `npm run open-position` / `submit-outcome` / `settle-position` — Phase 2 lifecycle
- `.venv/bin/python -m agent.runtime --scan --live --max-positions 1` — v0 one-shot S-4 energy Polymarket scan; Arc wrap happens only after `judge.classify()` returns `EXECUTE`

The v0 runtime is not a daemon. `--scan` means one stateless scan, at most one
wrapped position, then exit. Do not use this repo to place real Polymarket
orders; the Polymarket adapter is read-only and snapshots event prices for the
Arc audit rail.

## What's already done (no action needed)

- Project scaffolding (npm + python deps; symlink to upstream; tsconfig; .env.template)
- Contract addresses pinned (`contracts/arc_addresses.py`) with `usdc6()` helper
- ABIs pinned for IDENTITY_REGISTRY, VALIDATION_REGISTRY, REPUTATION_REGISTRY, AGENTIC_COMMERCE, ERC-20
- `agent/`: arb_identifier (S_t z-score), surface_router, judge, pnl_probe, scorer_bridge, on_chain, runtime
- `feeds/`: eia, aws_spot, coinbase, cache
- `adapters/`: polymarket (read-only), ibkr (paper), crypto (paper), kalshi (stub)
- `templates/energy/`: keywords.yaml, classifier.py, backward_check.txt (122 fills caught, WR 97% on AI-infra)
- TypeScript scripts: register_agent.ts, open_position.ts, submit_outcome.ts, settle_position.ts, smoke.ts
- Offline pytest suite present, including gate-bypass and no-chain-without-EXECUTE regressions
- `.claude/TASK.md` rewritten to the multi-surface product vision; prior version archived
