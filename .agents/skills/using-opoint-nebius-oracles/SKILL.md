---
name: using-opoint-nebius-oracles
description: "Use when designing or editing Opoint news grounding, Nebius DeepSeek/Qwen LLM analyst+critic calls, LLM oracle outputs, event probability vectors, cached or audited reasoning receipts, or commodity/prediction-market news evidence for Arc outcome desks. Enforces that LLM oracle output is evidence only: it must not replace the premium scorer, judge.classify(), or no-chain-unless-EXECUTE invariants; do not read or commit API keys, .env, credentials, wallet IDs, or identity state."
---

# Using Opoint + Nebius Oracles

## Codex Routing Header

Open relevant oracle, scanner, judge, runtime, and test files before editing.
Do not call Opoint, Nebius, Arc, Circle, Polymarket, or any external API unless
the user explicitly asks for a live run. Never read or print `.env`.

An LLM oracle is an evidence source, not the alpha gate, scorer, judge, or chain
executor. It may enrich candidate metadata and canonical blobs; it must not
cause an on-chain action without `judge.classify()` returning `EXECUTE`.

Read `references/source-notes.md` when adapting patterns from the source repos.

## Oracle Shape

Use this pattern for commodity or prediction-market events:

1. Build a deterministic event query from the candidate/event slug.
2. Fetch or accept news snippets from Opoint with source metadata.
3. Deduplicate by Opoint `equalgroup` when available, otherwise stable text hash.
4. Apply an AND gate: at least one core term and one context term must match.
5. Pass compact evidence into an analyst LLM using strict JSON output.
6. Validate with local schema checks and, if configured, a cheaper critic LLM.
7. Persist an append-only oracle analysis blob and reference only its hash from
   candidate/verdict/outcome records.

## Opoint Grounding Rules

Prefer build-time templates over ad hoc search prompts:

- Use core terms for the thing being resolved, e.g. `ERCOT`, `WTI`, `EIA`,
  `OpenAI`, `Blackwell`, `grid interconnect`, or a named commodity region.
- Use context terms for the economic mechanism, e.g. `power`, `outage`,
  `approval`, `export`, `inventory`, `freight`, `shutdown`, `capacity`.
- Treat Opoint site/source IDs as opaque strings; do not parse as integers.
- Keep coverage stats: raw count, after dedupe, after filter, pages used.
- Cache query results by normalized query and date window. Do not hide mutable
  state from the Arc audit path; include source ids and retrieval timestamps in
  canonical evidence blobs.

## Nebius LLM Rules

Use OpenAI-compatible Nebius clients with explicit model IDs and low
temperature. The source repos use:

- Analyst: `deepseek-ai/DeepSeek-V3.2`; DeepSeek V4 variants can be configured
  when cost/latency is acceptable.
- Critic: `Qwen/Qwen3-30B-A3B-Instruct-2507`.

Require strict JSON. For probability-vector outputs:

- Require exactly one probability per bucket/outcome.
- Require every probability in `[0, 1]`.
- Require a sum near 1 for mutually exclusive buckets.
- Include `reasoning`, `confidence`, model id, token counts if available, and
  evidence/source ids.
- Clamp or reject malformed confidence values; never silently accept malformed
  probability coverage.

## Failure Policy

Separate optional evidence from mandatory evidence:

- If the oracle is optional context, missing Opoint/Nebius data means continue
  without that evidence; do not fabricate a verdict.
- If the strategy design marks oracle evidence mandatory, failure should lead to
  `DEFER`, not `EXECUTE`.
- Critic rejection means do not use the analyst output for positive execution
  evidence. It can still be logged for audit and calibration.
- Never let an oracle exception bypass the premium gate, energy classifier, or
  judge gate.

## Arc Desk Integration

Represent oracle state through canonical blobs and hashes:

- `oracle_input_blob`: candidate, market prices, query template, source window.
- `oracle_evidence_blob`: article snippets, source ids, timestamps, coverage.
- `oracle_analysis_blob`: analyst JSON, critic JSON, confidence, model ids.
- `oracle_blob_hash`: stable hash referenced from candidate or verdict metadata.

The judge may read oracle fields as evidence, but the final capital decision
must still be `judge.classify()`. On-chain adapters must not import or call
oracle clients directly.

## Test Expectations

Before wiring into runtime, add offline tests with mocked Opoint and mocked
`chat_completion`:

- Query template maps event slugs to core/context terms.
- AND gate rejects noisy articles.
- Parser rejects malformed JSON, missing buckets, extra buckets, and invalid
  probabilities.
- Critic rejection prevents oracle-positive execution evidence.
- Cache hit skips LLM call.
- No chain call happens unless judge verdict is `EXECUTE`.
- Repository tests do not require real API keys or network.
