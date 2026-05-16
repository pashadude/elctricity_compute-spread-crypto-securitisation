# Commodity LLM Oracle Research

## Scope

Inspected local repos only:

- `/Users/pauldudko/VSProjects/py-builder-relayer-client`
- `/Users/pauldudko/VSProjects/brent_strategy`
- `/Users/pauldudko/VSProjects/adm`

No `.env` files were read. No Opoint, Nebius, Arc, Circle, Polymarket, broker,
or other external API calls were made.

## Findings

`py-builder-relayer-client` already has the cleanest oracle architecture:

- Opoint slug templates produce deterministic core/context queries.
- Articles are source-ranked, AND-gated, paginated, and equalgroup-deduped.
- Nebius is used through an OpenAI-compatible client with explicit model IDs,
  retry backoff, token/cost accounting, and strict JSON response mode.
- LLM edge analysis uses analyst + critic + cache + append-only JSONL audit log.
- Tests mock `chat_completion`, assert parser failures, cache behavior, critic
  failure behavior, and scorer integration without network calls.

`adm` contributes the commodity-news alpha discipline:

- Design the commodity taxonomy and Opoint configs first.
- Tag per article with relevance, summary, intensity, and traceability.
- Aggregate daily only after per-article validation.
- Verify relevance with LLM-as-judge and kNN/keyword rankers.
- Verify sentiment against forward futures returns with IC, lag scans,
  sub-period stability, and train/validation/test discipline.

`brent_strategy` contributes physical energy-market feature discipline:

- Use rolling z-scores and daily changes, not raw mixed-unit levels.
- Shift features to match real signal availability.
- Prefer a small set of interpretable physical-market features.
- Treat news/sentiment as useful context but not an unconstrained model.

## Arc Recommendation

Use the LLM oracle approach here only as an auditable evidence layer:

```text
candidate
  -> deterministic news query
  -> Opoint evidence blob
  -> Nebius analyst/critic JSON
  -> oracle_analysis_blob_hash
  -> judge metadata
  -> judge.classify()
  -> Arc wrap only if EXECUTE
```

Do not make the LLM oracle the judge, scorer, or executor. The oracle can raise
confidence, support `DEFER`, or explain a candidate; it cannot bypass:

- energy classifier
- upstream premium gate
- `judge.classify()`
- no-chain-without-`EXECUTE`

## Skills Added

- `$using-opoint-nebius-oracles`
- `$building-commodity-news-alphas`
- `$researching-energy-commodity-surfaces`

These are intentionally concise Codex skills, not copies of the Claude skills.
They preserve source-repo lessons while keeping ArcHack invariants intact.
