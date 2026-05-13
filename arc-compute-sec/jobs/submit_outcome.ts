/**
 * Phase 2 — submit deliverable hash for a funded job.
 *
 * Usage:
 *   npm run submit-outcome -- --job <id> --outcome-blob-path /tmp/outcome.json
 */
import { initiateDeveloperControlledWalletsClient } from "@circle-fin/developer-controlled-wallets";
import { keccak256, toHex } from "viem";
import { existsSync, readFileSync, appendFileSync } from "node:fs";

const AGENTIC_COMMERCE = "0x0747EEf0706327138c69792bF28Cd525089e4583";
const IDENTITY_TSV = "logs/identity.tsv";
const POSITIONS_TSV = "logs/positions.tsv";

const circle = initiateDeveloperControlledWalletsClient({
  apiKey: process.env.CIRCLE_API_KEY!,
  entitySecret: process.env.CIRCLE_ENTITY_SECRET!,
});

type Args = { job: string; outcomeBlobPath: string };
function parseArgs(argv: string[]): Args {
  const out: Args = { job: "", outcomeBlobPath: "" };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--job") out.job = argv[++i];
    else if (a === "--outcome-blob-path") out.outcomeBlobPath = argv[++i];
  }
  if (!out.job || !out.outcomeBlobPath) {
    console.error("Usage: --job <id> --outcome-blob-path <file>");
    process.exit(1);
  }
  return out;
}

function readIdentity() {
  const txt = readFileSync(IDENTITY_TSV, "utf8");
  const lines = txt.trim().split("\n");
  const headers = lines[0].split("\t");
  const vals = lines[lines.length - 1].split("\t");
  return Object.fromEntries(headers.map((h, i) => [h, vals[i] || ""]));
}

async function pollTx(id: string): Promise<string> {
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    const r = await circle.getTransaction({ id });
    const state = (r.data as any)?.transaction?.state || (r.data as any)?.state;
    if (state === "COMPLETE") return (r.data as any)?.transaction?.txHash || (r.data as any)?.txHash;
    if (["FAILED", "DENIED", "CANCELLED"].includes(state)) throw new Error(`Tx ${id} -> ${state}`);
    await new Promise((res) => setTimeout(res, 3_000));
  }
  throw new Error("timeout");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const identity = readIdentity();
  const blob = readFileSync(args.outcomeBlobPath);
  const deliverable = keccak256(toHex(blob.toString("utf8")));
  console.log(`deliverable_hash = ${deliverable}`);

  const r = await circle.createContractExecutionTransaction({
    walletId: identity.desk_wallet_id,
    contractAddress: AGENTIC_COMMERCE,
    abiFunctionSignature: "submit(uint256,bytes32,bytes)",
    abiParameters: [args.job, deliverable, "0x"],
    fee: { type: "level", config: { feeLevel: "MEDIUM" } } as any,
  });
  const txHash = await pollTx((r.data as any)?.id);
  console.log(`submit tx: https://testnet.arcscan.app/tx/${txHash}`);

  if (existsSync(POSITIONS_TSV)) {
    appendFileSync(POSITIONS_TSV, [
      new Date().toISOString(), "submitted", args.job, "", "", "", "", "",
      "", "", txHash, "", deliverable, "",
    ].join("\t") + "\n");
  }
}

main().catch((err) => { console.error(err); process.exit(1); });
