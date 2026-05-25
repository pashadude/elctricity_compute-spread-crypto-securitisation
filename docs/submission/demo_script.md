# Three-Minute Demo Script

Target length: 2:30-3:00.

## Screen Plan

1. Open `https://power.botozen.com`
2. Show the main spread package / dashboard
3. Show the proposed hedge note and direct/proxy legs
4. Show judge verdict and Arc job status
5. Open Telegram Mini App or channel
6. Open the GitHub `arc-oss-builder-starter-kit/` folder

## Voiceover

Hi, this is Power by Botozen.

The thesis is simple: all is compute, compute is energy, and hedging compute
means hedging the compute/energy spread.

AI infrastructure is becoming commodity-like, but raw GPU-hours are not yet
standardized enough to trade like oil, power, or wheat. A GPU-hour changes by
chip, region, workload, cooling setup, software stack, and power contract. So
instead of pretending compute is already a clean futures market, we wrap judged
compute/energy spread packages.

Here is the live desk. The system estimates the spread between compute dollars
per GPU-hour and electricity dollars per megawatt-hour. When the spread moves,
the agent builds a package with direct event legs and clearly labelled proxy
hedge legs.

Direct legs can be prediction or forecast contracts about grid stress, data
center constraints, AI capex, or compute demand. Public equities, BTC, and ETH
are not the securitized asset. They are proxy hedge legs. For example, BTC can
represent miner-margin stress because mining revenue is crypto-linked while
electricity is the main variable cost.

Now look at the proposed note. It starts from a commercial exposure: a forward
compute sale or GPU-hour receivable. The dashboard shows the build path. The
compute sale still needs collateral: an invoice, receivable, delivery meter, or
buyer and seller terms. The priced hedge basket is ready. Some direct event
refs may be matched. The judge gates are still pending. The Arc wrap stays
locked until the judge returns EXECUTE.

That distinction matters. This is not claiming a legal asset-backed security is
already live. It is showing how an agent assembles the package, identifies the
missing collateral, prices the hedge basket, and prepares an auditable route to
settlement.

The key safety rule is judge first, Arc second. The premium scorer and
`judge.classify()` run before any settlement action. If the verdict is REJECT,
DEFER, or CHALLENGE, nothing touches Circle or Arc. Only EXECUTE can create an
ERC-8183 job.

Here is the Arc side. An approved package becomes an ERC-8183 job with USDC
escrow, a deliverable hash, completion, and ERC-8004 reputation feedback. Arc
is not the alpha source. Arc is the settlement, escrow, identity, reputation,
and audit rail.

The Telegram surface mirrors the same product. It does not spam repeated
rejects. It posts grouped EXECUTE packages, Arc job updates, and alerts that
need operator attention. The Mini App gives a mobile version of the same spread
desk.

Finally, the repo includes an Arc OSS starter-kit folder for other builders. It
exposes ERC-8004 identity, ERC-8183 escrow, Circle SCA wallets, USDC
six-decimal helpers, EXECUTE and REJECT verdict fixtures, and a verifier that
proves the verdict guard runs before any Circle or Arc call.

So the product story is: all is compute, compute is energy, and Power by
Botozen is an audited path toward hedging compute as a financial primitive on
Arc.

## Subtitles

Use the voiceover text above as subtitles. Keep the screen text sparse and let
the dashboard, Arc job state, Telegram Mini App, and GitHub starter kit carry
the proof.
