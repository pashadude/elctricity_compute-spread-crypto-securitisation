# Frontend, Backend, Telegram, And 24/7 Runtime Plan

Date: 2026-05-21
Scope: implementation plan only. No credentials, no `.env` reads, no chain calls.

## Current State

- `frontend/` is a static React-by-CDN prototype. `dashboard.jsx` and
  `telegram.jsx` use generated mock data, not the backend.
- `arc-compute-sec/` has the working Python runtime, feed adapters, judge,
  scorer bridge, Arc wrapper, tests, and TypeScript Arc utility scripts.
- `agent/runtime.py` is intentionally one-shot today. It writes TSV logs and
  only imports/calls Arc after `judge.classify()` returns `EXECUTE`.
- There is no HTTP API, no Dockerfile/Compose setup, no Telegram Bot API
  integration, and no long-running scheduler service yet.

## Non-Negotiable Boundaries

- Frontend and Telegram must not call Arc directly.
- API-triggered scans must enter through the existing runtime path:
  signal -> route -> scorer/classifier -> `judge.classify()` -> wrap only on
  `EXECUTE`.
- Live chain mode must be opt-in by environment, not the default.
- The backend must never expose `.env`, Circle wallet IDs, entity secrets,
  local identity state, or raw credential-bearing logs.
- Polymarket remains read-only in this repo.
- The S-4 scorer path must keep `require_non_negative_premium=True`; no
  fallback may retry with the premium gate disabled.

## Target Architecture

Use one Python backend package inside `arc-compute-sec`, with three runnable
processes sharing the same code and persisted `logs/` volume:

| Process | Purpose | Local command |
|---|---|---|
| API | Serves frontend assets and JSON endpoints | `python -m services.api` |
| Worker | Runs the 24/7 scan loop with backoff and idempotency | `python -m services.worker` |
| Telegram | Handles bot commands and channel notifications | `python -m integrations.telegram_bot` |

Docker Compose will run those as separate services from one image. This keeps
restart policy, health checks, and local development simple while preserving
the existing runtime gate boundary.

## Backend API

Start with a dependency-light stdlib HTTP server plus small state-reader
modules. FastAPI can be swapped in later if the API surface grows enough to
justify the extra framework dependency.

Proposed files:

| File | Responsibility |
|---|---|
| `services/state.py` | Read TSV/JSONL logs and return sanitized snapshots. |
| `services/api.py` | HTTP API app, static frontend serving, CORS, health, scan endpoints. |
| `services/scan_requests.py` | File-backed queue/lock for API and Telegram scan requests. |
| `services/events.py` | Append-only event stream for UI/Telegram dedupe. |

Initial endpoints:

| Endpoint | Behavior |
|---|---|
| `GET /api/health` | Process status, mode, last scan time, last error, version. |
| `GET /api/snapshot` | Single dashboard payload: spread, latest signal, verdicts, positions, Arc txs, PnL/oracle summary. |
| `GET /api/verdicts` | Sanitized `logs/judgements.tsv`. |
| `GET /api/positions` | Sanitized `logs/positions.tsv` with Arcscan links. |
| `GET /api/signals` | Sanitized `logs/arb_signals.tsv` and spread history summary. |
| `POST /api/scans` | Enqueue a dry-run scan request by default. |
| `POST /api/scans/live` | Disabled unless `ENABLE_LIVE_CHAIN=1` and operator auth passes. |

The API must not expose `logs/identity.tsv`. Wallet IDs stay server-side only.

## Frontend Mapping

Keep the current static frontend for the first implementation pass and serve it
from FastAPI. Replace generated mock data with backend fetches.

Planned edits:

| File | Change |
|---|---|
| `frontend/dashboard.jsx` | Replace `useLiveData()` with `useBackendData()` polling `/api/snapshot`; show API-unavailable/stale state instead of fake live data. |
| `frontend/telegram.jsx` | Use the same backend snapshot and `POST /api/scans` for Mini App actions. |
| `frontend/Arc Compute Sec.html` | Load under the backend root and preserve `/api/*` relative fetches. |
| `frontend/theme.jsx` | Keep navigation; optionally route directly to dashboard first if this becomes operator app rather than landing page. |

No Vite migration is needed for the first pass. If the static/CDN setup becomes
too fragile for deployment, migrate later to a normal React build.

## 24/7 Worker

The worker should wrap the existing one-shot runtime, not duplicate it.

Behavior:

- Default mode is dry-run.
- Live mode requires `ENABLE_LIVE_CHAIN=1` plus the existing `.env` credentials.
- Poll interval defaults to 300 seconds.
- A file lock prevents overlapping scans from API, Telegram, and scheduler.
- Backoff handles feed errors, Gamma 429/503, RPC/Circle timeouts, and IBKR
  socket failures without spinning.
- `restart: unless-stopped` in Docker Compose handles process crashes.
- A status file, for example `logs/runtime_status.json`, records last scan,
  last success, last error, mode, and counters for health checks.

The worker must keep using `runtime.run_once()` or `runtime.process_candidates()`
so no chain side effect can occur outside the tested judge boundary.

## Telegram Bot And Channel

Add `python-telegram-bot` integration.

Environment:

| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather. |
| `TELEGRAM_CHANNEL_ID` | Channel username or numeric `-100...` id. |
| `TELEGRAM_ADMIN_USER_IDS` | Comma-separated user IDs allowed to trigger scans. |
| `PUBLIC_BASE_URL` | HTTPS URL for Mini App/webhook, usually ngrok locally. |
| `TELEGRAM_MODE` | `polling` locally by default, optional `webhook`. |

Bot commands:

| Command | Behavior |
|---|---|
| `/start` | Intro plus button to open the Mini App. |
| `/status` | Health, mode, last scan, last verdict. |
| `/latest` | Latest signal/verdict/position summary. |
| `/positions` | Recent ERC-8183 jobs and Arcscan links. |
| `/scan` | Admin-only dry-run scan request. |
| `/scan_live` | Admin-only and disabled unless live env gate is enabled. |

Channel functionality:

- Post new signals, `EXECUTE` verdicts, premium-gate `REJECT`s, wrapped jobs,
  settlements, and serious runtime errors.
- Use `logs/telegram_sent.tsv` or `logs/telegram_sent.jsonl` for dedupe.
- Rate-limit noisy status/error messages.
- Include concise Arcscan links when tx hashes exist.

For local development, long polling does not require ngrok. For Telegram Mini
App and webhook mode, run `ngrok http 8080` and set `PUBLIC_BASE_URL` to the
HTTPS forwarding URL.

## Docker Desktop Stage

Add:

| File | Purpose |
|---|---|
| `arc-compute-sec/Dockerfile` | Python 3.11 + Node 22-capable image, install Python and npm deps. |
| `arc-compute-sec/docker-compose.yml` | `api`, `worker`, and `telegram` services. |
| `arc-compute-sec/.dockerignore` | Exclude `.env`, logs, node_modules, venv, caches. |
| `arc-compute-sec/.env.template` | Add Telegram/API/worker variables, no secrets. |

Compose defaults:

- Mount `./logs:/app/logs` for durable local state.
- Mount `../frontend:/app/frontend:ro` so frontend changes do not require image
  rebuilds.
- Expose one local port, `8080`, for API and frontend.
- Use `host.docker.internal` for host services such as IBKR Gateway.
- Keep `ENABLE_LIVE_CHAIN=0` by default.

Example local flow:

```bash
cd arc-compute-sec
docker compose up --build api worker
curl http://localhost:8080/api/health
curl http://localhost:8080/api/snapshot
```

Telegram local flow:

```bash
cd arc-compute-sec
docker compose --profile telegram up --build telegram
ngrok http 8080
```

Then set the bot Mini App/webhook URL to `https://<ngrok-host>/telegram` or the
webhook endpoint, depending on mode.

## Implementation Phases

1. Backend API foundation
   - Add `services/state.py`, `services/api.py`, tests for sanitized log
     parsing and `/api/snapshot`.
   - Serve `frontend/Arc Compute Sec.html` and assets from the API.

2. Frontend-to-backend mapping
   - Replace mock dashboard/Telegram Mini App data with `/api/snapshot`.
   - Add stale/error/loading states and dry-run scan action.
   - Verify the static app works at `http://localhost:8080/`.

3. Worker and 24/7 loop
   - Add scheduler loop, file lock, status JSON, request queue, backoff.
   - Keep dry-run as default; live mode requires explicit env gate.
   - Add tests proving worker-triggered runs still call the existing runtime
     boundary.

4. Docker Desktop stage
   - Add Dockerfile, Compose, `.dockerignore`, env template additions.
   - Verify `docker compose up --build api worker` and health/snapshot endpoints.

5. Telegram bot and channel
   - Add bot commands, Mini App button, channel notifier, dedupe state.
   - Add mocked Telegram tests; do not hit Telegram in unit tests.
   - Verify locally in polling mode, then optionally with ngrok/webhook.

6. Live operator smoke
   - Only after dry-run works: set `.env`, run with `ENABLE_LIVE_CHAIN=1`, and
     execute one controlled scan.
   - Run the invariant tests before and after.

## Verification Gates

Before merging implementation:

```bash
cd arc-compute-sec
.venv/bin/python -m pytest \
  tests/test_judge.py \
  tests/test_scorer_bridge.py \
  tests/test_energy_classifier.py \
  tests/test_no_gate_bypass.py \
  tests/test_no_chain_call_without_execute.py
```

Additional tests to add during implementation:

- API snapshot sanitization does not expose identity/wallet IDs.
- Frontend scan button hits dry-run endpoint only.
- Worker does not overlap scans when lock is held.
- Telegram `/scan` is rejected for non-admin users.
- Telegram channel dedupe prevents repeat messages.
- Docker health check fails when API cannot read status.

Completion evidence:

- Frontend dashboard and Telegram Mini App read live backend JSON, not generated
  mock data.
- API, worker, and Telegram services run under Docker Compose.
- Worker can run continuously in dry-run mode and recover from simulated errors.
- Telegram bot can answer commands and channel posting is deduped.
- All judge/scorer/no-chain invariant tests remain green.
