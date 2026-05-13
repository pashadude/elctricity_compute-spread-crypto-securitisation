---
name: using-arc-canteen
description: Use the hackathon organisers' arc-canteen CLI for traction/product updates (visibility on the judging dashboard), Arc Testnet RPC proxy, and coding-puzzle submissions. Invoke when work in /Users/pauldudko/VSProjects/ArcHack/ reaches a milestone worth surfacing (phase commit, first onchain tx, completed feature) or when our code needs an authenticated Arc Testnet RPC URL. Audited and pinned at SHA 541810fcc88e859c0c9367b9abf8ec8602c0e48a.
---

# Using `arc-canteen` (hackathon CLI)

`arc-canteen` is the hackathon organisers' Python CLI bundled with `the-canteen-dev/ARC-cli`. It serves three purposes:

1. **Visibility on the judging dashboard** — submit `update_product` and `update_traction` events that organisers see. Skipping this means our build is invisible to scoring.
2. **Authenticated Arc Testnet RPC** — proxy at `https://rpc.testnet.arc-node.thecanteenapp.com/v1/<token>`, less rate-limited than the public `rpc.testnet.arc.network`.
3. **Coding puzzles / easter eggs** — bonus-point challenges (e.g. cUSDC wrapper); `arc-canteen submit-puzzle` posts the answer.

## Install (pinned to audited SHA)

```bash
uv tool install git+https://github.com/the-canteen-dev/ARC-cli.git@541810fcc88e859c0c9367b9abf8ec8602c0e48a
```

Places the binary at `~/.local/bin/arc-canteen`. If `uv` is missing, install via `curl -LsSf https://astral.sh/uv/install.sh | sh`.

To bump: re-audit the new SHA before changing the pin. Re-install with `uv tool install --reinstall git+…@<new-sha>`.

## First-time setup (operator, interactive)

```bash
arc-canteen login                  # GitHub Device Flow OAuth (no repo scope)
arc-canteen profile-edit            # Discord/Telegram/Luma email
arc-canteen rpc-url --export        # prints: export RPC='https://rpc.testnet.arc-node.thecanteenapp.com/v1/<token>'
```

Paste the printed URL into `arc-compute-sec/.env` as both `ARC_RPC` and `RPC` (the second is what TS scripts pick up when they read `process.env.RPC`):

```
ARC_RPC=https://rpc.testnet.arc-node.thecanteenapp.com/v1/<token>
RPC=https://rpc.testnet.arc-node.thecanteenapp.com/v1/<token>
```

Verify auth:
```bash
arc-canteen rpc eth_chainId        # → 0x4cef52 (== 5042002)
arc-canteen rpc eth_blockNumber
arc-canteen status                  # show dashboard
```

## Commands we use

| When | Command | What it does |
|---|---|---|
| Once at session start | `arc-canteen login` | Auth, mints 90-day server token |
| Once at session start | `arc-canteen rpc-url --export` | Returns the per-user RPC URL with token embedded |
| **After every phase commit** | `arc-canteen update-product` | Free-text update — paste the commit headline + onchain proof URL |
| When a position settles onchain | `arc-canteen update-traction` | Free-text update describing the milestone with arcscan link |
| When a puzzle drops | `arc-canteen submit-puzzle` | Submit answer to the active challenge |
| For diagnostics | `arc-canteen status` | Dashboard view of submitted events |
| Periodically | `arc-canteen push` | Drain queued events (auto-runs after each event; safety flush) |

## Commands NOT to run

| Command | Why we skip |
|---|---|
| `arc-canteen context sync` | Clones ~150 MB of context docs we already have via `.claude/TASK.md` + `~/.claude/projects/.../memory/` |
| `arc-canteen shell-init >> ~/.zshrc` | Pollutes every shell with a global `$RPC`. We scope it to the project `.env` only |

## When to invoke this skill

- **After every `git commit` that closes a phase** (Phase 0 bootstrap, Phase 0.5 ABIs, Phase 3 classifier, Phase 1 identity, Phase 2 wrap, Phase 4+5 multi-surface): run `arc-canteen update-product` with the commit headline and any arcscan link.
- **When the agent runtime executes its first live wrap on Arc** (a real ERC-8183 job lands with `getJob.status == 3`): run `arc-canteen update-traction` with the explorer URL.
- **When `arc-canteen status` lists an active puzzle**: solve it locally, then `arc-canteen submit-puzzle`. Puzzles in scope this hackathon include the cUSDC wrapper (Part 1 of the slides).

NEVER auto-invoke just to ping the dashboard. Updates are user-meaningful only — empty or spammy submissions hurt visibility.

## Where state lives

`~/.arc-canteen/` — directory mode `0700`, files mode `0600`. Contains:

- `config.yaml` — auth token + profile + cached updates
- `settings.yaml` — chain + event_name
- `queue.yaml` — append-only event queue (idempotent on retry)
- `env` — `export RPC='...'` (we source this only inside the project, not globally)

`arc-canteen logout` invalidates the server token and clears local auth. `arc-canteen rotate-rpc-key` mints a fresh token and invalidates the old one — run after a suspected leak.

## Trust model (audited 2026-05-13 at SHA 541810fcc88e859c0c9367b9abf8ec8602c0e48a)

- POSTs **only** what you type (traction/product update text, puzzle answers, profile fields you entered, login/logout events). No `cwd` reads, no `glob`, no `os.environ` scraping, no `.env` parsing.
- GitHub OAuth requests `scope=""` — they see your username only, not your repos.
- All filesystem state is `0700`/`0600` and created via `os.open(... , 0o600)` (no world-readable race window).
- RPC proxy enforces a server-side method allowlist (returns 403 for disallowed methods). They can see signed tx payloads — same risk as Alchemy/Infura — but cannot modify them.
- Deps are 4 standard PyPI packages: `typer`, `rich`, `httpx`, `pyyaml`.
- Two and only two outbound hostnames: `arc-cli-server.thecanteenapp.com` and `rpc.testnet.arc-node.thecanteenapp.com`.

## Failure modes the user should know about

- **Server down** — `push_event` queues locally and silently retries on next invocation. No hang.
- **Token expired** (90-day max) — `arc-canteen rpc <method>` returns "token rejected"; rerun `arc-canteen login`.
- **Hostile-RPC censorship risk** — if the proxy refuses to forward `eth_sendRawTransaction`, swap `ARC_RPC` back to the public `https://rpc.testnet.arc.network` in `.env`. Our code reads `ARC_RPC`; one line of `.env` swaps the entire stack.

## Integration with our project

- The skill is auto-loaded for any session opened in `/Users/pauldudko/VSProjects/ArcHack/`.
- The plan file at `~/.claude/plans/run-all-in-line-tender-liskov.md` features arc-canteen explicitly in:
  - Block 1 step 1.11 — autonomous install
  - Gate A step 6 — operator-interactive `login` + paste RPC into `.env`
  - Each subsequent phase commit — `arc-canteen update-product`
- `arc-compute-sec/.env.template` carries an `RPC=` slot to be filled from `arc-canteen rpc-url --export`.
