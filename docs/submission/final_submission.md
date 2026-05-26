# Final Hackathon Submission Packet

## Links

- Demo app: https://power.botozen.com
- Telegram channel: https://t.me/botozen_power
- Telegram bot / Mini App: https://t.me/BotozenPowerBot
- Repository: https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation
- Arc OSS starter kit folder: https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation/tree/main/arc-oss-builder-starter-kit
- Loom / YouTube / Vimeo: `TODO: add final video link`

## 1. What Problem Is Your Project Solving?

Power by Botozen is solving the missing hedge layer between AI compute demand
and the physical energy system that has to power it.

AI infrastructure is moving from software capex into commodity-like physical
constraints: GPU capacity, data center interconnects, cooling, and electricity.
Larry Fink's recent compute-futures framing captures the destination: markets
will need instruments for future compute capacity. The immediate problem is
more practical. Compute is not yet standardized like wheat, oil, or power.
One GPU-hour is not fungible across chip generation, region, model workload,
software stack, cooling design, and power contract. That makes raw compute hard
to securitize directly.

The compelling gap is that the demand is real, but the tradable unit is not.
Data center real estate can already be financed through asset-backed
structures: TierPoint announced a $550 million data-center ABS issuance and
$1.61 billion total ABS issuance. But that is mostly infrastructure cashflow,
not the volatile service flow of compute itself. Separately, electricity futures
already show hedgeable structure, including trading-time seasonality in Nordic
and German power futures. Bitcoin mining hashrate derivatives show that a
standardized compute-output unit can become a hedging instrument. Event
contracts show how discrete infrastructure outcomes can be priced and hedged.

Power by Botozen connects those pieces. It does not claim that BTC/USD is
"securitizing energy." Instead, the securitized object is a judged
compute/energy spread package:

```text
S_t = compute_$_per_gpu_hr - k * electricity_$_per_MWh * kWh_per_gpu_hr
```

The system scans live and paper surfaces, forms a package of direct legs and
proxy hedge legs, labels the economic mechanism, runs the premium scorer and
`judge.classify()`, and only then wraps the approved package as an ERC-8183 job
on Arc. The product is closer to an audited hedge note around compute-sale or
GPU-hour receivable risk than to a legal ABS. It becomes asset-backed only when
real collateral such as invoices, GPU rental receivables, delivery meters,
power hedges, or escrowed USDC is attached.

The key insight for the demo is simple:

```text
all is compute
compute is energy
hedging compute means hedging the compute/energy spread
```

## Research Basis

This submission builds on the user's research paper,
`The Securitization of Compute: AI Infrastructure, Energy Spreads, and the New Commodity Frontier.pdf`,
plus the market precedents used in the demo narrative:

- Larry Fink / compute futures framing:
  https://finance.yahoo.com/sectors/technology/articles/blackrock-reveals-surprising-asset-class-022000793.html
- Goldman Sachs research on AI data-center electricity demand:
  https://www.goldmansachs.com/images/migrated/insights/pages/gs-research/gs-sustain-generational-growth-ai-data-centers-global-power-surge-and-the-sustainability-impact/sustain-data-center-redaction.pdf
- TierPoint data-center ABS financing precedent:
  https://www.tierpoint.com/news/tierpoint-completes-new-550-million-securitization-financing/
- Electricity futures seasonality and hedgeability:
  https://www.sciencedirect.com/science/article/pii/S2405851322000484
- Luxor / Bitnomial hashrate futures as standardized compute-output hedge:
  https://docs.luxor.tech/platform/derivatives/luxor-contract-and-market-details/luxors-bitcoin-hashrate-futures-on-bitnomial-exchange
- CFTC explanation of event contracts and prediction markets:
  https://www.cftc.gov/LearnandProtect/PredictionMarkets
- New York Fed work on tokenized markets and settlement uncertainty:
  https://www.newyorkfed.org/research/staff_reports/sr1121

## 2. Video Script

Use `docs/submission/demo_script.md`; the file now includes a 90-second cut
for the final recording. Use `docs/submission/demo_description.md` for the
video upload description.

## 3. Arc OSS: Why Should Arc Choose This Project?

Choose this project because it exposes a reusable Arc builder pattern, not just
a product demo.

Circle and Arc already provide strong primitives and examples: Arc docs show
how to create an ERC-8183 job, fund escrow with USDC, submit a deliverable
hash, and complete settlement on Arc Testnet. Circle's public skills and sample
apps cover wallets, USDC, CCTP, Gateway, App Kit, and general Arc setup.

Power by Botozen adds the missing opinionated workflow for agentic financial
products:

- A self-contained Arc OSS starter-kit folder in the repo.
- ERC-8004 identity plus ERC-8183 escrow in one builder-facing flow.
- Circle Developer-Controlled SCA wallets for builder, validator, and client
  roles.
- A hard `no-chain-unless-EXECUTE` guard: scripts refuse to touch Circle or Arc
  unless the offchain judge verdict is `EXECUTE`.
- Example `EXECUTE` and `REJECT` verdict blobs, so builders can test both the
  happy path and the refusal path.
- A `usdc6()` helper that prevents 18-decimal/native-gas confusion when using
  ERC-20 USDC escrow.
- A verifier script that checks guard ordering: `assertExecutable(verdict)`
  must run before `circleClient()`.
- A root GitHub Action that runs `npm ci`, `npm run check`, and
  `npm audit --omit=dev` inside the starter kit.
- Submission helper output via `npm run submission-link`.

Compared with a generic quickstart, this repo teaches the pattern that matters
for agentic commerce: evidence first, verdict second, escrow third. Builders
can reuse that pattern for any audited work package, not only compute/energy.

## 4. Circle / Arc Feedback

What worked well:

- Arc Testnet is fast enough for demoable agentic escrow: create, fund, submit,
  complete, and reputation feedback all fit a short story.
- USDC-as-gas makes the economics legible. Builders do not have to explain a
  separate volatile gas token.
- Circle Developer-Controlled Wallets were a good fit for an autonomous agent
  flow because the backend can create role-specific wallets and execute contract
  calls without asking a user to click every step.
- ERC-8183 maps naturally to paid agent work: a client funds escrow, a provider
  submits a deliverable hash, and an evaluator completes the job.
- ERC-8004 identity/reputation gives the demo a clean audit trail beyond "we
  emitted a transaction."
- `arc-canteen` is useful for hackathon visibility and for authenticated RPC
  URLs. The local queue behavior is helpful when the server is temporarily
  unreachable.

Where Circle / Arc could improve:

- Provide one canonical TypeScript package for Arc Testnet addresses, ABIs,
  USDC decimals, and chain config. Hackathon teams should not copy ABIs and
  addresses across repos.
- The docs should include a combined ERC-8004 plus ERC-8183 flow. Today the
  job escrow path and agent identity path feel separate, but agentic products
  need both.
- Circle SDK examples should be kept closer to the current SDK typing. Some
  examples use `walletAddress`, others use wallet IDs or slightly different
  transaction shapes; that creates avoidable TypeScript friction.
- Add an official "no-chain-before-policy-gate" pattern. Financial and AI-agent
  use cases need a standard way to prove that an offchain judge, compliance
  gate, or risk engine ran before settlement.
- Improve faucet and funding UX. The common demo failure is not contract logic;
  it is getting the right SCA wallet funded with the right test USDC.
- Add better explorer affordances for ERC-8183 jobs: job id, state transition,
  budget, submit hash, completion hash, and reputation event should be visible
  as one object.
- Give `arc-canteen` an edit/delete command for queued updates. During a live
  hackathon, it is easy to paste too much into the interactive prompt.
- Add a local deterministic simulator for the ERC-8183 lifecycle so builders
  can test create/fund/submit/complete without waiting on faucet/RPC state.

## 5. Arc CLI Update

Use this after the final commit is pushed:

```text
Final submission materials are live. Power by Botozen wraps judged compute/energy spread packages as Arc ERC-8183 jobs after premium scoring and judge.classify(); no chain call can happen unless the verdict is EXECUTE.

Repo: https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation
Arc OSS starter kit folder: https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation/tree/main/arc-oss-builder-starter-kit
Demo: https://power.botozen.com

The OSS folder exposes reusable ERC-8004 identity + ERC-8183 escrow + Circle SCA wallet scripts, USDC 6-decimal helpers, example EXECUTE/REJECT verdict blobs, and a verifier proving the Arc guard runs before Circle/Arc calls.
```
