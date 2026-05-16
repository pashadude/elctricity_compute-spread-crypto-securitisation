# Source Notes

Source repos inspected:

- `/Users/pauldudko/VSProjects/py-builder-relayer-client`
- `/Users/pauldudko/VSProjects/adm`
- `/Users/pauldudko/VSProjects/brent_strategy`

Relevant source patterns:

- `py-builder-relayer-client/api/polymarket/longtail/data_sources/opoint_news.py`
  maps slugs to Opoint query templates, paginates Search API responses, filters
  by core/context terms, source rank, and equalgroup dedupe.
- `py-builder-relayer-client/api/polymarket/longtail/llm_client.py` wraps Nebius
  through an OpenAI-compatible endpoint, with explicit model IDs, retry backoff,
  token counts, and cost accounting.
- `py-builder-relayer-client/api/polymarket/longtail/llm_edge.py` implements the
  analyst/critic/cache/audit-log pattern for multi-bucket probability vectors.
- `adm/.claude/skills/add-commodity-pipeline/SKILL.md` provides commodity
  Opoint pipeline design discipline: design doc first, keyword/source/watchlist
  configs, StoredSearch shadow run, and Opoint ID gotchas.
- `adm/.claude/skills/news-relevance-verification/SKILL.md` separates LLM judge
  relevance from kNN/keyword relevance and compares both with Spearman and
  precision-at-k.

Transfer to Arc:

- Use Opoint/Nebius as a news-grounded oracle for candidate metadata and audit
  blobs.
- Do not copy upstream source files into ArcHack.
- Do not mutate `py-builder-relayer-client` without explicit operator approval.
- Do not let oracle outputs disable `require_non_negative_premium=True` or
  bypass `judge.classify()`.
