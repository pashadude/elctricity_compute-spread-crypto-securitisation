# Source Notes

ADM source skills inspected:

- `add-commodity-pipeline`
- `sugar-news-tagging`
- `sugar-news-knn-augmented-tagging`
- `sugar-sentiment-aggregation`
- `news-relevance-verification`
- `sentiment-futures-verification`
- `per-tag-ic`
- `alpha-building`
- `alpha-intensity-creation`

Patterns worth reusing:

- Design commodity-specific Opoint configs before code: IPTC tags, keywords,
  watchlists, trusted sources, stored searches, and priors.
- Use source IDs as opaque strings and cache Opoint resolver/search responses.
- Tag per article, then aggregate by date; do not mix trading-calendar logic
  into per-article tagging.
- Verify relevance with two independent views: LLM-as-judge and kNN/keyword
  ranker.
- Verify sentiment with futures or resolved outcomes using IC, lag scans,
  sub-periods, and tag sensitivity.
- Keep GA/search honest with train/validation/test separation.

Important source results:

- ADM sugar composite state notes a full-window Sharpe of 1.88 and test Sharpe
  of 4.27 for a news-only composite as of 2026-05-04. Treat these as project
  context, not a guarantee for energy or compute.
- Brent strategy notes that ZenPulsar sentiment was critical and dropping it
  collapsed IC materially. For Arc, this supports news as context, not as an
  execution bypass.
