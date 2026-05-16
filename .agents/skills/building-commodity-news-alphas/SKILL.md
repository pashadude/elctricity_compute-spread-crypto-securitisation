---
name: building-commodity-news-alphas
description: "Use when building, adapting, or verifying commodity news alpha pipelines: Opoint commodity search profiles, commodity macro-tag taxonomies, per-article relevance/intensity scoring, daily sentiment aggregation, futures-return verification, information coefficient analysis, alpha bakeoffs, or train/validation/test discipline for commodity signals. Applies to sugar, Brent, oil, gas, power, agriculture, metals, and compute-energy outcome desks."
---

# Building Commodity News Alphas

## Codex Routing Header

Use for commodity news alpha design and validation. Do not call live APIs unless
the user explicitly requests it. Do not read `.env` or commit credentials.

Read `references/source-notes.md` when adapting patterns from ADM or Brent.

## Pipeline

Use this sequence:

```text
raw news
  -> commodity relevance filter
  -> per-article tag/relevance/summary/intensity
  -> daily aggregation
  -> futures or outcome verification
  -> shadow run
  -> runtime metadata only after tests
```

Do not wire a commodity news signal into execution before the verification and
shadow-run steps exist.

## Commodity Taxonomy

Define a closed macro-tag taxonomy before tagging. For each tag, specify:

- Economic mechanism.
- Bullish/bearish sign convention for the target commodity or outcome.
- Typical source types and trusted geographies.
- Common false positives and negative keywords.

Do not invent tags during tagging. Use `Other` sparingly and surface repeated
`Other` cases as taxonomy-review items.

## Per-Article Fields

Every tagged article should preserve traceability:

```json
{
  "article_id": "...",
  "published_at": "...",
  "source": "...",
  "url": "...",
  "primary_tag": "...",
  "secondary_tags": [],
  "relevance": 0,
  "summary": "...",
  "intensity": 0.0
}
```

Use one fixed sign convention per commodity. Positive should mean bullish for
the target price or outcome. Never use `intensity` as a relevance proxy.

## Daily Aggregation

Default daily intensity:

```text
Intensity_d = sum(relevance_i * intensity_i) / sum(relevance_i)
```

Default daily relevance is the mean of the top 3 article relevance scores. Keep
publication timestamps; trading-day alignment belongs in verification, not in
tagging.

## Verification

Verify against forward returns or resolved outcomes:

- Align news available at time `t` with next tradable return or future outcome.
- For futures files where `px_delta[t] = price[t+1] - price[t]`, do not shift
  again.
- Check Pearson, Spearman, IC by year/quarter, lag scan, sub-period stability,
  and tag drop-one sensitivity.
- Use train/validation/test splits for any GA, ridge, threshold, or component
  search. Never let the test window influence tuning.
- Treat stable `r=0.05` to `0.10` as meaningful in daily commodity sentiment;
  do not expect equity-style large correlations.

## Alpha Bakeoff Discipline

When proposing alphas:

- Start with simple per-tag IC before multivariate models.
- Prefer event severity, breadth, attention spikes, lagged intensity, and
  cross-tag interactions over opaque LLM scores.
- Avoid overlapping-window Sharpe inflation; evaluate honest daily-rebalance
  PnL.
- Require sign stability across train and test.
- Mix horizons and alpha families; do not stack five variants of the same idea.

## Arc Desk Guardrails

Commodity news alpha can help route or annotate candidates, but it must not:

- Disable the S-4 premium gate.
- Replace the energy classifier.
- Replace `judge.classify()`.
- Call Arc/Circle/on-chain adapters directly.
- Store external venue state as hidden mutable state.

When used inside ArcHack, write canonical evidence blobs and hashes so the
judge/verdict trail can be audited.

## Test Expectations

Before runtime integration, add offline tests for:

- Closed taxonomy validation.
- Sign convention examples.
- Aggregation math.
- No-lookahead alignment.
- IC computation on synthetic data.
- Mocked LLM output schema failures.
- No network or credential dependency in tests.
