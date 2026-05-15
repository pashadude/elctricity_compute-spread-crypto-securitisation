/**
 * Phase 2 — open one ERC-8183 job (createJob → setBudget → fund).
 *
 * Usage:
 *   npm run open-position -- --surface S4 --market mock-001 --notional 1 --expires-hours 1
 */
import { initiateDeveloperControlledWalletsClient } from "@circle-fin/developer-controlled-wallets";
import { createPublicClient, http, parseEventLogs, parseAbi } from "viem";
import { existsSync, readFileSync, writeFileSync, appendFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { AGENTIC_COMMERCE, CHAIN_NAME, RPC_HTTP, USDC, usdc6 } from "../contracts/arc_addresses";

const ARC_RPC = process.env.ARC_RPC || RPC_HTTP;
const IDENTITY_TSV = "logs/identity.tsv";
const POSITIONS_TSV = "logs/positions.tsv";

if (!process.env.CIRCLE_API_KEY || !process.env.CIRCLE_ENTITY_SECRET) {
  console.error("Missing CIRCLE_API_KEY / CIRCLE_ENTITY_SECRET.");
  process.exit(1);
}

const circle = initiateDeveloperControlledWalletsClient({
  apiKey: process.env.CIRCLE_API_KEY!,
  entitySecret: process.env.CIRCLE_ENTITY_SECRET!,
});
const arc = createPublicClient({ transport: http(ARC_RPC) });

type Args = { surface: string; market: string; notional: number; expiresHours: number };
function parseArgs(argv: string[]): Args {
  const out: Args = { surface: "S4", market: "mock-001", notional: 1, expiresHours: 1 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--surface") out.surface = argv[++i];
    else if (a === "--market") out.market = argv[++i];
    else if (a === "--notional") out.notional = Number(argv[++i]);
    else if (a === "--expires-hours") out.expiresHours = Number(argv[++i]);
  }
  return out;
}

function readIdentity(): Record<string, string> {
  if (!existsSync(IDENTITY_TSV)) throw new Error(`Missing ${IDENTITY_TSV}; run register_agent.ts first.`);
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
    if (state === "COMPLETE") {
      return (r.data as any)?.transaction?.txHash || (r.data as any)?.txHash;
    }
    if (["FAILED", "DENIED", "CANCELLED"].includes(state)) {
      throw new Error(`Tx ${id} ended in ${state}`);
    }
    await new Promise((res) => setTimeout(res, 3_000));
  }
  throw new Error(`Tx ${id} timeout`);
}

async function execContract(walletId: string, contractAddress: string, sig: string, params: any[]) {
  const r = await circle.createContractExecutionTransaction({
    walletId,
    contractAddress,
    abiFunctionSignature: sig,
    abiParameters: params,
    fee: { type: "level", config: { feeLevel: "MEDIUM" } } as any,
  });
  const id = (r.data as any)?.id;
  return await pollTx(id);
}

async function ensureClientWallet(identity: Record<string, string>) {
  if (identity.client_wallet_id && identity.client_wallet_addr) return identity;
  const sets = await circle.listWalletSets({});
  const set = (sets.data?.walletSets || []).find((w: any) => w.name === "arc-compute-sec-desk");
  if (!set) throw new Error("wallet set not found");
  const c = await circle.createWallets({
    walletSetId: set.id,
    blockchains: [CHAIN_NAME as any],
    count: 1,
    accountType: "SCA",
  });
  const w = c.data!.wallets![0];
  identity.client_wallet_id = w.id!;
  identity.client_wallet_addr = w.address!;
  // Append a new row.
  const headers = readFileSync(IDENTITY_TSV, "utf8").split("\n")[0].split("\t");
  const line = headers.map((h) => identity[h] ?? "").join("\t");
  appendFileSync(IDENTITY_TSV, line + "\n");
  // Fund from desk.
  const bal = await circle.getWalletTokenBalance({ id: identity.desk_wallet_id });
  const usdc = (bal.data?.tokenBalances || []).find(
    (t: any) => (t.token?.symbol || "").toUpperCase() === "USDC"
  );
  if (!usdc?.token?.id) throw new Error("desk has no USDC; fund at faucet.circle.com");
  const tr = await circle.createTransaction({
    walletId: identity.desk_wallet_id,
    tokenId: usdc.token.id,
    destinationAddress: identity.client_wallet_addr,
    amount: ["2"],
    fee: { type: "level", config: { feeLevel: "MEDIUM" } } as any,
  });
  await pollTx((tr.data as any)?.id);
  console.log(`Created client_wallet ${identity.client_wallet_addr} and funded with 2 USDC.`);
  return identity;
}

function ensurePositionsHeader() {
  if (existsSync(POSITIONS_TSV)) return;
  const header = [
    "ts", "stage", "job_id", "surface", "market", "notional_usdc",
    "expired_at", "description", "open_tx", "fund_tx", "submit_tx",
    "settle_tx", "deliverable_hash", "reason_hash",
  ].join("\t");
  writeFileSync(POSITIONS_TSV, header + "\n");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  let identity = readIdentity();
  identity = await ensureClientWallet(identity);

  const expiredAt = Math.floor(Date.now() / 1000) + args.expiresHours * 3600;
  const description = `${args.surface}|${args.market}|premium_gated`;
  const HOOK = "0x0000000000000000000000000000000000000000";

  // 1. createJob from client_wallet
  console.log("createJob…");
  const createHash = await execContract(
    identity.client_wallet_id,
    AGENTIC_COMMERCE,
    "createJob(address,address,uint256,string,address)",
    [identity.desk_wallet_addr, identity.judge_wallet_addr, expiredAt, description, HOOK]
  );
  console.log(`  https://testnet.arcscan.app/tx/${createHash}`);
  const commerceAbi = JSON.parse(await readFile("contracts/abis/agentic_commerce.json", "utf8"));
  const receipt = await arc.getTransactionReceipt({ hash: createHash as `0x${string}` });
  const events = parseEventLogs({ abi: commerceAbi, logs: receipt.logs });
  const created = events.find((e: any) => e.eventName === "JobCreated") as any;
  if (!created) throw new Error("JobCreated event not found in receipt");
  const jobId = (created.args as any).jobId.toString();
  console.log(`  jobId = ${jobId}`);

  // 2. setBudget from desk_owner
  console.log("setBudget…");
  const notionalBase = usdc6(args.notional);
  const budgetHash = await execContract(
    identity.desk_wallet_id,
    AGENTIC_COMMERCE,
    "setBudget(uint256,uint256,bytes)",
    [jobId, notionalBase, "0x"]
  );
  console.log(`  https://testnet.arcscan.app/tx/${budgetHash}`);

  // 3. approve + fund from client_wallet
  console.log("approve(USDC) + fund…");
  const approveHash = await execContract(
    identity.client_wallet_id,
    USDC,
    "approve(address,uint256)",
    [AGENTIC_COMMERCE, notionalBase]
  );
  console.log(`  approve: https://testnet.arcscan.app/tx/${approveHash}`);
  const fundHash = await execContract(
    identity.client_wallet_id,
    AGENTIC_COMMERCE,
    "fund(uint256,bytes)",
    [jobId, "0x"]
  );
  console.log(`  fund:    https://testnet.arcscan.app/tx/${fundHash}`);

  ensurePositionsHeader();
  appendFileSync(POSITIONS_TSV, [
    new Date().toISOString(), "funded", jobId, args.surface, args.market,
    args.notional, expiredAt, description, createHash, fundHash, "", "", "", "",
  ].join("\t") + "\n");
  console.log(`Wrote position row to ${POSITIONS_TSV}; jobId=${jobId}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
