# Codex Implementation Plan - Arc-Settled S-4 Energy Outcome Desk

Date: 2026-05-15
Scope: plan only. No implementation, no on-chain command, no Circle/Arc/Polymarket/Hyperliquid/API calls, and no `.env` contents read.

## 1. Loaded Instruction Sources

Found and loaded:

| Source | Path | Notes |
|---|---|---|
| Parent AGENTS | `../AGENTS.md` | Canonical ArcHack invariants and skill routing. |
| Local AGENTS | `AGENTS.md` | Missing under `arc-compute-sec`. |
| Canonical TASK | `../docs/agent-context/TASK.md` | Present and loaded. |
| Claude TASK fallback | `../.claude/TASK.md` | Present, but not loaded because docs copy exists. |
| Routing skill | `../.agents/skills/routing-cross-surface-signals/SKILL.md` | Loaded explicitly for routing, scanner, and Polymarket candidate flow. |
| Judge skill | `../.agents/skills/judging-arb-candidates/SKILL.md` | Loaded explicitly for judge/runtime verdict and no-chain-side-effect invariants. |
| Arc/Canteen skill | `../.agents/skills/using-arc-canteen/SKILL.md` | Loaded explicitly for Arc/Circle, ERC-8004, ERC-8183, USDC decimals, and `agent/on_chain.py` planning. |
| PnL skill | `../.agents/skills/calibrating-pnl-estimates/SKILL.md` | Found and read during full skill inspection; not directly used for calibration in this task. |
| Skill-maintenance skill | `../.agents/skills/improving-arb-skills/SKILL.md` | Found and read during full skill inspection; metadata fix verified. |

Skill application:

| Skill | Used for |
|---|---|
| `$judging-arb-candidates` | Four-way verdict plan, `EXECUTE` gate, rejection logging, tests for no chain side effect. |
| `$routing-cross-surface-signals` | S-4 Polymarket energy routing, scanner integration, classifier-before-candidate behavior. |
| `$using-arc-canteen` | Arc/Circle adapter plan, ERC-8183 lifecycle, ERC-8004 identity/reputation, USDC 6-decimal handling. |

## 2. Current Repo Inventory

| Area | Actual files | Status | Notes |
|---|---|---|---|
| Agent runtime | `agent/runtime.py` | exists but incomplete | One-shot runtime exists. Judge runs before execute/wrap. Live `--scan` fetches EIA/AWS but uses `_mock_polymarket_events()` instead of live read-only Polymarket scanner. `--live` can submit chain calls after `EXECUTE`. |
| Judge | `agent/judge.py` | exists and usable | Four labels exist: `EXECUTE`, `REJECT`, `DEFER`, `CHALLENGE`. Premium gate failure rejects. CHALLENGE currently routes to DEFER by reason code. |
| Scorer bridge | `agent/scorer_bridge.py` | exists and usable | Loads upstream scorer via symlink. Calls `filter_candidates(..., require_non_negative_premium=True)`. No observed fallback setting the gate false. |
| Polymarket scanner | `adapters/polymarket.py` | exists but incomplete | Read-only Gamma fetch, energy classification, and scorer gate exist. Runtime does not use it for `--scan`. Event price parsing is minimal and should be hardened against actual Gamma shapes. |
| Energy classifier/templates | `templates/energy/classifier.py`, `templates/energy/keywords.yaml`, `templates/energy/backward_check.txt` | exists and usable | Standalone keyword classifier exists. Backward check is present and notes soft acceptance: 122 classified, WR pass, count threshold fail. |
| Arc/Circle on-chain adapter | `agent/on_chain.py` | exists and usable with risk | Python wrapper uses Circle SDK for contract execution and web3.py for receipts. Uses `contracts.arc_addresses.usdc6()` for USDC amounts. Needs stronger tests around call boundaries and no direct invocation before `EXECUTE`. |
| TS job scripts | `jobs/open_position.ts`, `jobs/submit_outcome.ts`, `jobs/settle_position.ts` | exists but incomplete | ERC-8183 lifecycle scripts exist. They duplicate Arc addresses rather than importing a shared source. `open_position.ts` uses `Math.round(args.notional * 1_000_000)` for USDC, which is 6-decimal but should be centralized and validated. |
| Identity scripts | `identity/register_agent.ts`, `identity/agent-metadata.json` | exists but incomplete | ERC-8004 registration and validation rehearsal exist. Script prints local identity row and writes wallet IDs to ignored logs. It duplicates addresses and depends on Circle state. |
| Tests | `tests/test_*.py` | exists but incomplete | Core tests exist for judge, scorer bridge, energy classifier, surface router, adapters, feeds, cache, and PnL. Missing explicit `test_no_gate_bypass.py` and `test_no_chain_call_without_execute.py`. |
| Logs/state/docs | `logs/*`, `README.md`, `GATE_A.md`, parent `../docs/agent-context/TASK.md` | exists but incomplete | Runtime logs exist by filename only. `.env` exists but was not read. `arc_txs.tsv` is expected by TASK but missing. Local `docs/` was missing before this plan. README points to older `../.claude/TASK.md` instead of canonical docs path. |
| Upstream reference | `upstream/py-builder-relayer-client` symlink, `upstream/PINNED_SHA.txt` | exists and usable | Upstream is a symlink to local repo. Must remain read-only. No upstream scorer files should be copied into this repo. |
| Policy config | `policy.yaml` | missing | Skills reference `policy.yaml`, but no such file was found in `arc-compute-sec`. Current thresholds are hardcoded in Python defaults. |

## 3. Gap Matrix Against v0 Target

| Required component | Current file(s) | Status | Missing work | Tests needed before implementation | Relevant skill |
|---|---|---|---|---|---|
| Energy classifier | `templates/energy/classifier.py`, `templates/energy/keywords.yaml` | exists and usable | Harden actual event title/description handling; preserve conservative `None` default. | Off-template event drops before scoring/judging; energy event maps to template id. | `$routing-cross-surface-signals` |
| Polymarket scanner | `adapters/polymarket.py`, `agent/runtime.py` | exists but incomplete | Wire `fetch_events()` and `classify_and_gate()` into `scan_once`; keep read-only and no order placement. | Mock Gamma events; positive premium admitted; non-energy dropped; negative premium not wrapped. | `$routing-cross-surface-signals` |
| Scorer bridge | `agent/scorer_bridge.py` | exists and usable | Add narrow tests around no fallback and failure propagation; keep upstream symlink read-only. | `require_non_negative_premium=True`; no false setting anywhere in S-4 code path. | `$judging-arb-candidates` |
| Four-way judge | `agent/judge.py` | exists and usable | Keep labels stable; consider explicit `CHALLENGE` label only if v0 behavior remains DEFER-equivalent. | Positive fresh candidate returns `EXECUTE`; premium fail returns `REJECT`. | `$judging-arb-candidates` |
| No-gate-bypass invariant | `agent/scorer_bridge.py`, `agent/runtime.py`, `tests/test_judge.py` | exists but incomplete | Add explicit no-bypass test file and ensure runtime cannot construct Polymarket EXECUTE without scorer result. | Negative premium must return `REJECT` and no chain side effect; no code sets gate false. | `$judging-arb-candidates`, `$routing-cross-surface-signals` |
| No-chain-without-EXECUTE invariant | `agent/runtime.py`, `agent/on_chain.py` | exists but incomplete | Add tests monkeypatching chain wrappers to prove no calls for `REJECT`, `DEFER`, or challenge-defer. | `on_chain.open_position` or wrap function cannot be reached unless verdict is `EXECUTE`. | `$judging-arb-candidates`, `$using-arc-canteen` |
| On-chain adapter / ERC-8183 lifecycle wrapper | `agent/on_chain.py`, `agent/runtime.py`, `jobs/*.ts` | exists but incomplete | Consolidate wrapper boundaries and logging; avoid direct scripts bypassing judge for runtime path. | Unit tests with monkeypatched `on_chain` only; no RPC. | `$using-arc-canteen` |
| ERC-8004 identity/reputation wiring | `identity/register_agent.ts`, `agent/on_chain.py`, `jobs/settle_position.ts` | exists but incomplete | Centralize addresses; document operator-only execution; ensure reputation feedback only after settled wrapped position. | Static/no-network checks; log schema tests if adding log writer. | `$using-arc-canteen` |
| Idempotency keys | `agent/runtime.py`, logs | missing | Add deterministic candidate/action idempotency key from canonical candidate blob and signal id; prevent duplicate wrap on rerun. | Duplicate candidate should not call wrap twice when log already records same key. | `$judging-arb-candidates`, `$using-arc-canteen` |
| Canonical outcome/verdict blobs | `agent/runtime.py` | exists but incomplete | Remove timestamp from canonical identity hash or split stable canonical blob from observed timestamp; include external venue snapshot hashes. | Same candidate/fill/signal produces stable canonical hash; mutable state not hidden. | `$using-arc-canteen`, `$routing-cross-surface-signals` |
| Logs: `judgements.tsv`, `positions.tsv`, `arc_txs.tsv` | `logs/judgements.tsv`, `logs/positions.tsv` | exists but incomplete | Add `arc_txs.tsv` writer or explicitly document not yet implemented. Normalize schemas between Python runtime and TS scripts. | Header/schema tests using temp paths. | `$judging-arb-candidates`, `$using-arc-canteen` |
| Acceptance cases A/B/C | tests and runtime | exists but incomplete | Implement tests and demo flags for A positive EXECUTE, B premium REJECT, C classifier drop. | Pytest-only first; no external calls. | `$judging-arb-candidates`, `$routing-cross-surface-signals` |
| README/RUNBOOK/demo notes | `README.md`, `GATE_A.md` | exists but incomplete | Update canonical docs path, v0 scope, scan-once mode, no daemon, no Polymarket orders. | Markdown/static review only. | `$using-arc-canteen` for Arc operator notes |

## 4. Tests-First Plan

Before refactoring runtime, create or harden this smallest pytest suite:

| Test file | Behavior under test | Fixtures needed | Mocking required | Exact invariant protected |
|---|---|---|---|---|
| `tests/test_energy_classifier.py` | Energy titles/descriptions classify to templates; off-template non-energy returns `None`. | Existing keyword YAML; synthetic event titles. | No. | Off-template non-energy Polymarket event is dropped before scoring/judging. |
| `tests/test_scorer_bridge.py` | Positive, zero, and negative premium behavior through upstream scorer bridge. | Existing upstream symlink or monkeypatched bridge for isolation if upstream unavailable. | Existing test currently uses real local upstream import; add monkeypatch fallback only if necessary. | S-4 scorer path preserves `require_non_negative_premium=True`. |
| `tests/test_judge.py` | Four-way gate semantics and log row shape. | Synthetic candidate dicts; `tmp_path` for logs. | No network; monkeypatch log path only. | Premium gate fail returns `REJECT` with `reason_code = premium_gate_fail`; fresh positive candidate returns `EXECUTE`. |
| `tests/test_no_gate_bypass.py` | Runtime/scanner cannot admit a Polymarket candidate around the scorer gate. Repository scan forbids `require_non_negative_premium=False`. | Synthetic Polymarket events with positive/negative premiums. | Monkeypatch `adapters.polymarket.fetch_events` and optionally `score_candidate`. | Negative premium returns `REJECT` or is filtered before chain; no S-4 code path disables the premium gate. |
| `tests/test_no_chain_call_without_execute.py` | No chain wrapper is called unless judge verdict is `EXECUTE`. | Synthetic candidates and verdicts; temp log paths. | Monkeypatch `wrap_position`, `settle_position`, or `agent.on_chain` functions to count calls. | `on_chain.open_position`/runtime wrap path cannot be called unless verdict is `EXECUTE`. |

Required cases:

| Case | Test location | Expected result |
|---|---|---|
| A. Positive fresh energy candidate with positive premium returns `EXECUTE`. | `tests/test_judge.py` plus `tests/test_no_gate_bypass.py` runtime-level fixture. | Candidate passes scorer, judge returns `EXECUTE`, wrap mock is called only in EXECUTE path. |
| B. Negative premium returns `REJECT` with `reason_code = premium_gate_fail` and no chain side effect. | `tests/test_judge.py`, `tests/test_no_gate_bypass.py`, `tests/test_no_chain_call_without_execute.py`. | `REJECT`, reason `premium_gate_fail`, wrap/on_chain call count remains zero. |
| C. Off-template non-energy Polymarket event is dropped before scoring/judging. | `tests/test_energy_classifier.py`, `tests/test_no_gate_bypass.py`. | No candidate emitted, scorer mock not called, judge mock not called. |
| D. Repository contains no S-4 code path setting `require_non_negative_premium=False`. | `tests/test_no_gate_bypass.py` or keep current guard in `tests/test_judge.py`. | Static scan fails on any executable assignment/call with false gate. |
| E. `on_chain.open_position` cannot be called unless verdict is `EXECUTE`. | `tests/test_no_chain_call_without_execute.py`. | For `REJECT`, `DEFER`, and challenge-defer verdicts, no `wrap_position`/`on_chain` mock call occurs. |

## 5. Implementation Patch Sequence

### Patch 1 - Docs/runbook cleanup only

Files to touch:

| Touch | Purpose |
|---|---|
| `README.md` | Point to `../docs/agent-context/TASK.md`; state v0 is S-4 energy Polymarket scan-once. |
| `GATE_A.md` | Clarify operator-only commands and no autonomous chain calls. |
| `docs/agent-context/CODEX_PLAN.md` | Keep plan current if review changes scope. |

Files not to touch:

| Do not touch |
|---|
| `agent/*` |
| `adapters/*` |
| `jobs/*` |
| `identity/*` |
| `.env`, logs contents, upstream symlink target |

Commands to run:

```bash
python -m pytest tests/test_judge.py tests/test_scorer_bridge.py tests/test_energy_classifier.py
```

Expected diff shape:

| Expected |
|---|
| Markdown only. No runtime behavior change. |

Rollback notes:

| Rollback |
|---|
| Revert markdown edits only. No state migration. |

### Patch 2 - Tests for gate, judge, classifier, and chain-call invariants

Files to touch:

| Touch | Purpose |
|---|---|
| `tests/test_no_gate_bypass.py` | Add scanner/runtime gate-bypass tests and static false-gate scan. |
| `tests/test_no_chain_call_without_execute.py` | Add monkeypatched no-chain-side-effect tests. |
| `tests/test_judge.py` | Add missing reason-code and challenge/defer coverage if needed. |
| `tests/test_energy_classifier.py` | Add off-template event drop behavior if not already sufficient. |

Files not to touch:

| Do not touch |
|---|
| Runtime implementation files except for test import accommodation if absolutely required. |
| `.env`, `logs/*`, upstream target. |

Commands to run:

```bash
python -m pytest tests/test_energy_classifier.py tests/test_scorer_bridge.py tests/test_judge.py tests/test_no_gate_bypass.py tests/test_no_chain_call_without_execute.py
```

Expected diff shape:

| Expected |
|---|
| Tests should initially expose current runtime gaps, especially mock Polymarket in `--scan` and missing idempotency/no-chain coverage. |

Rollback notes:

| Rollback |
|---|
| Revert new tests if they encode an incorrect invariant; otherwise keep them as blockers for implementation. |

### Patch 3 - Energy classifier/scanner hardening

Files to touch:

| Touch | Purpose |
|---|---|
| `adapters/polymarket.py` | Harden Gamma event market parsing, preserve read-only behavior, return canonical event snapshots. |
| `templates/energy/classifier.py` | Only if tests show actual event fields are mishandled. |
| `tests/test_polymarket_adapter.py` | Cover actual-ish Gamma shapes and off-template drop before scoring. |

Files not to touch:

| Do not touch |
|---|
| `agent/on_chain.py` |
| `jobs/*` |
| upstream scorer files |

Commands to run:

```bash
python -m pytest tests/test_energy_classifier.py tests/test_polymarket_adapter.py tests/test_no_gate_bypass.py
```

Expected diff shape:

| Expected |
|---|
| Adapter parsing and tests only. No order placement endpoints. No network calls in tests. |

Rollback notes:

| Rollback |
|---|
| Revert adapter changes; classifier remains conservative and may simply emit fewer candidates. |

### Patch 4 - Scorer bridge hardening

Files to touch:

| Touch | Purpose |
|---|---|
| `agent/scorer_bridge.py` | Make gate call narrow and explicit; improve error messaging without fallback to false gate. |
| `tests/test_scorer_bridge.py` | Add tests for no fallback and boundary behavior. |
| `tests/test_no_gate_bypass.py` | Keep static repository guard. |

Files not to touch:

| Do not touch |
|---|
| `upstream/py-builder-relayer-client/*` |
| copied scorer files |
| `agent/pnl_probe.py` unless a test-only import dependency requires no-op handling |

Commands to run:

```bash
python -m pytest tests/test_scorer_bridge.py tests/test_no_gate_bypass.py tests/test_judge.py
```

Expected diff shape:

| Expected |
|---|
| Small bridge/test edits only. No scorer copy, no upstream mutation, no false-gate retry. |

Rollback notes:

| Rollback |
|---|
| Revert bridge hardening if it breaks local upstream import; keep tests describing desired invariant. |

### Patch 5 - Judge/runtime gating and idempotency

Files to touch:

| Touch | Purpose |
|---|---|
| `agent/runtime.py` | Introduce `scan_once(max_positions=1)` one-shot path; wire read-only Polymarket scanner; enforce judge-before-wrap; add idempotency checks. |
| `agent/judge.py` | Only if verdict fields need stable serialization or explicit challenge label handling. |
| `tests/test_no_chain_call_without_execute.py` | Verify no chain calls for non-EXECUTE. |
| `tests/test_no_gate_bypass.py` | Verify negative premium and off-template paths. |

Files not to touch:

| Do not touch |
|---|
| `jobs/*` |
| `identity/*` |
| upstream scorer |
| `.env`, real logs |

Commands to run:

```bash
python -m pytest tests/test_energy_classifier.py tests/test_scorer_bridge.py tests/test_judge.py tests/test_no_gate_bypass.py tests/test_no_chain_call_without_execute.py tests/test_polymarket_adapter.py tests/test_surface_router.py
```

Expected diff shape:

| Expected |
|---|
| Runtime refactor remains one-shot. `--scan` means stateless `scan_once(max_positions=1)` and exits. No daemon loop. |

Rollback notes:

| Rollback |
|---|
| Revert runtime changes while keeping tests if they still express accepted invariants. |

### Patch 6 - Arc/Circle adapter consolidation

Files to touch:

| Touch | Purpose |
|---|---|
| `contracts/arc_addresses.py` | Remains Python source of truth. |
| New TS constants helper if needed | Share Arc addresses and USDC decimal conversion for `jobs/*.ts` and `identity/*.ts`. |
| `jobs/open_position.ts`, `jobs/submit_outcome.ts`, `jobs/settle_position.ts` | Replace hardcoded addresses/amount conversion with shared constants. |
| `agent/on_chain.py` | Add log writer boundaries and `arc_txs.tsv` support if implemented. |
| Tests for static TS/Python constants if practical | Prevent 18-decimal USDC regression. |

Files not to touch:

| Do not touch |
|---|
| `.env` |
| local identity state contents |
| upstream repo |

Commands to run:

```bash
python -m pytest tests/test_no_chain_call_without_execute.py tests/test_judge.py
npx tsc --noEmit
```

Expected diff shape:

| Expected |
|---|
| Address/USDC consolidation only. No actual Circle/Arc calls. No change to alpha/scoring. |

Rollback notes:

| Rollback |
|---|
| Revert TS consolidation if build tooling blocks it; Python runtime still has centralized `usdc6()`. |

### Patch 7 - Demo flow and README/RUNBOOK

Files to touch:

| Touch | Purpose |
|---|---|
| `README.md` | Document v0 demo: scan once, max one position, Polymarket read-only, Arc wrap only after `EXECUTE`. |
| `GATE_A.md` | Update operator steps and explicit commands not run by Codex without approval. |
| Optional local runbook under `docs/agent-context/` | Add demo checklist if useful. |

Files not to touch:

| Do not touch |
|---|
| Runtime logic except correcting command names if already implemented. |
| `.github/skills/` must not be created. |

Commands to run:

```bash
python -m pytest tests/test_energy_classifier.py tests/test_scorer_bridge.py tests/test_judge.py tests/test_no_gate_bypass.py tests/test_no_chain_call_without_execute.py
```

Expected diff shape:

| Expected |
|---|
| Docs only. Commands clearly separate offline tests from operator-only live commands. |

Rollback notes:

| Rollback |
|---|
| Revert docs if command names or flow change. |

### Patch 8 - Optional weekly recap, only if trivial and no runtime risk

Files to touch:

| Touch | Purpose |
|---|---|
| Optional docs or pure log summarizer | Summarize counts from existing TSVs without network or chain calls. |

Files not to touch:

| Do not touch |
|---|
| `agent/runtime.py` if not necessary. |
| `agent/judge.py`, scorer bridge, Arc adapter. |

Commands to run:

```bash
python -m pytest tests/test_judge.py
```

Expected diff shape:

| Expected |
|---|
| Optional, low-risk reporting only. Skip if it adds runtime coupling. |

Rollback notes:

| Rollback |
|---|
| Delete optional summarizer/docs; no product path depends on it. |

## 6. Explicit Deferrals

Deferred to v2 or later:

| Deferred item | Status |
|---|---|
| S-1 electricity execution | v2. |
| S-2 hashrate factor | v2. |
| S-3 EFU beta | v2. |
| GA/Shinka threshold evolution | v2 after enough trace and operator approval. |
| LLM judge | v2+. v0 uses deterministic four-way judge only. |
| Long-running daemon mode | v2. |
| Real Polymarket order placement | Out of scope; order placement stays outside this repo. |
| Hyperliquid execution | v2+. |
| Legal securitization/tranching | v2+ and requires legal/product review. |
| Arc Mainnet | Deferred; Arc Testnet only. |

`--scan` decision:

| Decision | Meaning |
|---|---|
| v0 implements `scan_once(max_positions=1)` only | `--scan` is a stateless one-shot scan that exits. It may read feeds and read-only Polymarket events when the operator explicitly runs it, but it must not become a daemon loop. No retry loop, no background scheduler, no automatic repeated chain submissions. |

## 7. Risk Register

| Risk | Current exposure | Mitigation in plan |
|---|---|---|
| Secrets leakage risk | `.env` exists; logs contain wallet IDs/identity state and are ignored. TS scripts print local identity rows. | Never read/print `.env`; keep `.env`, wallet IDs, entity secret, recovery files, and logs ignored; avoid committing local identity state. |
| Duplicate tx/idempotency risk | Runtime can rerun a candidate and wrap again because no durable idempotency key is enforced. | Add deterministic idempotency key and pre-wrap log check before any chain call. |
| USDC decimal risk | Python uses `usdc6()`. TS scripts use manual `1_000_000` conversion and hardcoded addresses. `scripts/smoke.ts` imports `parseUnits` but does not use it for the shown transfer amount. | Centralize TS constants/conversion; add static guard against `parseUnits(_, 18)` for USDC and against ad hoc decimal conversions in job scripts. |
| Judge bypass risk | Runtime path calls judge before wrap, but TS job scripts can open jobs directly as operator scripts. | Define runtime as the only autonomous path; document TS scripts as operator-only; add tests proving runtime cannot call chain for non-EXECUTE. |
| Scorer gate bypass risk | `scorer_bridge.py` uses `require_non_negative_premium=True`; runtime currently uses mock events and re-scores Polymarket candidates. | Wire live scanner through `classify_and_gate`; add no-false-gate static test; no fallback retry with false gate. |
| Upstream repo mutation risk | Upstream is symlinked and loaded directly. | Do not modify upstream or copy scorer files; treat symlink target read-only. |
| Overbuilding beyond hackathon scope | Current TASK includes multi-surface ambitions, but user target is v0 S-4 energy Polymarket outcome desk. | Limit implementation to `scan_once(max_positions=1)`, read-only Polymarket, deterministic judge, Arc wrap after EXECUTE. Defer daemon, Hyperliquid, real Polymarket orders, and legal tranching. |
| Hidden network/API dependency risk | Runtime live `--scan` would hit EIA/AWS and planned Polymarket Gamma; tests must not require network. | Mock all external feeds/scanners in pytest; document live commands as operator-run only. |
| Canonical blob drift risk | Current canonical outcome blob includes a timestamp, which makes hashes non-repeatable. | Split stable canonical external venue snapshot from observation timestamps; hash sorted JSON blobs for idempotency and audit. |
| Log schema drift risk | Python runtime and TS scripts append different `positions.tsv` schemas; `arc_txs.tsv` missing. | Normalize log schemas and add header/schema tests before relying on logs as audit rail. |
