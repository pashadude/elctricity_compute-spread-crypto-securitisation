# Source Notes

Brent source docs inspected:

- `/Users/pauldudko/VSProjects/brent_strategy/CLAUDE.md`
- `.claude/agents/brent-strategist.md`
- `.claude/agents/commodity-strategist.md`
- `.claude/agents/oil-news-pipeline.md`
- `.claude/agents/sparta-brent-features.md`

Reusable patterns:

- Brent Gen278 used walk-forward Ridge regression and improved from sentiment
  plus PCA/fundamentals to physical-market z-score features.
- The strongest Brent feature family was small and physical: DFL, Brent time
  spreads, gasoline/gasoil time spreads, and selected cracks/arbs.
- All commodity features need unit normalization and lookahead-safe shifts.
- ZenPulsar/news sentiment was materially useful in the Brent setup, but source
  docs emphasize filtering and summarization over unconstrained LLM modelling.
- Oil-news pipeline patterns include source ranking, timezone correction,
  numeric extraction, trend classification, trading-day calculation, and
  shadow-fleet/sanctions context.

Transfer to Arc:

- Use energy physical features to inform routing and evidence, not as direct
  execution permission.
- Keep v0 narrow: Polymarket read-only, IBKR/crypto paper, no direct
  electricity execution.
- Future S-1/S-2/S-3 work should begin with research and no-lookahead tests, not
  live trading adapters.
