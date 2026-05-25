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

AI infrastructure is turning compute into a commodity-like input, but it is not
yet standardized enough to trade like wheat, oil, or power. A GPU-hour is
different across chips, regions, workloads, cooling, and power contracts. So
instead of pretending that raw compute is already a perfect futures market, we
wrap judged compute/energy spread packages.

Here is the live desk. The system estimates the spread between compute dollars
per GPU-hour and electricity dollars per megawatt-hour. When electricity is
expensive or compute is expensive, the agent builds a package with direct event
legs and clearly labelled proxy hedge legs.

Direct legs can be prediction or forecast contracts about grid stress, data
center constraints, or AI compute demand. Public equities and BTC or ETH are
not the securitized asset. They are labelled proxies. For example, BTC can
represent miner-margin stress because mining revenue is crypto-linked and
electricity is the main variable cost.

Now look at the proposed note. It starts from a real commercial exposure: a
forward compute sale or GPU-hour receivable. The dashboard shows what
collateral is missing, which hedge basket is priced, which event refs are
matched, and what the agent still needs before promotion.

The key safety rule is here: judge first, Arc second. The premium scorer and
`judge.classify()` run before any settlement action. If the verdict is REJECT
or DEFER, nothing touches Circle or Arc. Only EXECUTE can create an ERC-8183
job.

Here is the Arc side. The approved package becomes an ERC-8183 job with USDC
escrow, a deliverable hash, completion, and ERC-8004 reputation feedback. Arc
is not the alpha source. Arc is the settlement, escrow, identity, reputation,
and audit rail.

The Telegram surface mirrors the same product. It does not spam rejected rows.
It posts grouped EXECUTE packages, Arc job updates, and operator-relevant
alerts. The Mini App gives a mobile version of the same spread desk.

Finally, the repo includes an Arc OSS starter-kit folder for other builders.
It exposes ERC-8004 identity, ERC-8183 escrow, Circle SCA wallets, USDC
six-decimal helpers, example EXECUTE and REJECT verdict blobs, and a verifier
that proves the verdict guard runs before any Circle or Arc call.

So the product story is: all is compute, compute is energy, and Power by
Botozen is the first audited path toward hedging compute as a financial
primitive on Arc.

## Subtitles

Use the voiceover text above as subtitles. Keep the screen text sparse and let
the dashboard, Arc job state, Telegram Mini App, and GitHub starter kit carry
the proof.

