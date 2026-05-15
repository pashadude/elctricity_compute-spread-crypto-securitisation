/**
 * Phase 2 — settle a submitted job.
 *
 * IMPORTANT: ERC-8183 deployed at AGENTIC_COMMERCE does NOT expose reject().
 * Both win and loss paths call complete(). Loss path uses
 *     reasonHash = keccak256("reject:" + reason_code)
 * to distinguish offchain. Final job status is Completed(3) for both.
 *
 * Usage:
 *   npm run settle-position -- --job <id> --verdict-blob-path /tmp/verdict.json --action complete
 *   npm run settle-position -- --job <id> --verdict-blob-path /tmp/verdict.json --action reject --reason-code premium_negative
 */
import { initiateDeveloperControlledWalletsClient } from "@circle-fin/developer-controlled-wallets";
import { keccak256, toHex } from "viem";
import { existsSync, readFileSync, appendFileSync } from "node:fs";
import { AGENTIC_COMMERCE, REPUTATION_REGISTRY } from "../contracts/arc_addresses";

const IDENTITY_TSV = "logs/identity.tsv";
const POSITIONS_TSV = "logs/positions.tsv";

const circle = initiateDeveloperControlledWalletsClient({
  apiKey: process.env.CIRCLE_API_KEY!,
  entitySecret: process.env.CIRCLE_ENTITY_SECRET!,
});

type Args = { job: string; verdictBlobPath: string; action: "complete" | "reject";
               reasonCode: string; score: number };
function parseArgs(argv: string[]): Args {
  const out: Args = { job: "", verdictBlobPath: "", action: "complete",
                       reasonCode: "paper_settle", score: 95 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--job") out.job = argv[++i];
    else if (a === "--verdict-blob-path") out.verdictBlobPath = argv[++i];
    else if (a === "--action") out.action = (argv[++i] as any);
    else if (a === "--reason-code") out.reasonCode = argv[++i];
    else if (a === "--score") out.score = Number(argv[++i]);
  }
  if (!out.job || !out.verdictBlobPath) {
    console.error("Usage: --job <id> --verdict-blob-path <file> --action complete|reject");
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

async function execContract(walletId: string, addr: string, sig: string, params: any[]) {
  const r = await circle.createContractExecutionTransaction({
    walletId, contractAddress: addr, abiFunctionSignature: sig,
    abiParameters: params,
    fee: { type: "level", config: { feeLevel: "MEDIUM" } } as any,
  });
  return await pollTx((r.data as any)?.id);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const identity = readIdentity();
  const verdictBlob = readFileSync(args.verdictBlobPath, "utf8");

  let reasonHash: `0x${string}`;
  if (args.action === "reject") {
    reasonHash = keccak256(toHex(`reject:${args.reasonCode}`));
  } else {
    reasonHash = keccak256(toHex(verdictBlob));
  }
  console.log(`reason_hash = ${reasonHash} (action=${args.action})`);

  // complete() — used for BOTH paths per the deployed ABI (no reject()).
  const settleTx = await execContract(
    identity.judge_wallet_id,
    AGENTIC_COMMERCE,
    "complete(uint256,bytes32,bytes)",
    [args.job, reasonHash, "0x"]
  );
  console.log(`settle tx: https://testnet.arcscan.app/tx/${settleTx}`);

  // Reputation feedback.
  const feedbackHash = keccak256(toHex(verdictBlob + ":" + args.score));
  const feedbackTx = await execContract(
    identity.judge_wallet_id,
    REPUTATION_REGISTRY,
    "giveFeedback(uint256,int128,uint8,string,string,string,string,bytes32)",
    [identity.desk_agent_id, args.score, 0, `${args.action}:${args.reasonCode}`.slice(0, 32),
     "", "", "", feedbackHash]
  );
  console.log(`feedback tx: https://testnet.arcscan.app/tx/${feedbackTx}`);

  if (existsSync(POSITIONS_TSV)) {
    appendFileSync(POSITIONS_TSV, [
      new Date().toISOString(), `settled:${args.action}`, args.job, "", "", "", "", "",
      "", "", "", settleTx, "", reasonHash,
    ].join("\t") + "\n");
  }
}

main().catch((err) => { console.error(err); process.exit(1); });
