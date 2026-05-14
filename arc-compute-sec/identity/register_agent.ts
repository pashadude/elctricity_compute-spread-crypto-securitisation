/**
 * Phase 1 — ERC-8004 desk identity registration.
 *
 * Creates desk_owner + judge_validator SCA wallets (or reuses if already in
 * logs/identity.tsv), funds the judge wallet from desk via internal transfer,
 * calls register(metadataURI) on the IDENTITY_REGISTRY, extracts the agent
 * tokenId from the Transfer event, runs the validationRequest /
 * validationResponse rehearsal, and writes logs/identity.tsv.
 *
 * Idempotent: re-running with a populated identity.tsv exits with the
 * existing addresses.
 */
import { initiateDeveloperControlledWalletsClient } from "@circle-fin/developer-controlled-wallets";
import {
  createPublicClient,
  http,
  keccak256,
  decodeEventLog,
  toHex,
  encodeFunctionData,
  parseAbi,
  parseEventLogs,
} from "viem";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { readFile } from "node:fs/promises";

const ARC = "ARC-TESTNET";
const RPC = process.env.ARC_RPC || "https://rpc.testnet.arc.network";
const IDENTITY = "0x8004A818BFB912233c491871b3d84c89A494BD9e";
const VALIDATION = "0x8004Cb1BF31DAf7788923b405b754f57acEB4272";
const METADATA_URI = "ipfs://bafkreibdi6623n3xpf7ymk62ckb4bo75o3qemwkpfvp5i25j66itxvsoei";

const IDENTITY_TSV = "logs/identity.tsv";
const SET_NAME = "arc-compute-sec-desk";

if (!process.env.CIRCLE_API_KEY || !process.env.CIRCLE_ENTITY_SECRET) {
  console.error("Missing CIRCLE_API_KEY or CIRCLE_ENTITY_SECRET. Abort.");
  process.exit(1);
}

const circle = initiateDeveloperControlledWalletsClient({
  apiKey: process.env.CIRCLE_API_KEY!,
  entitySecret: process.env.CIRCLE_ENTITY_SECRET!,
});

const arc = createPublicClient({ transport: http(RPC) });

async function loadAbi(name: string) {
  const txt = await readFile(`contracts/abis/${name}`, "utf8");
  return JSON.parse(txt);
}

async function pollTx(id: string, timeoutMs = 180_000): Promise<{ txHash: string }> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const r = await circle.getTransaction({ id });
    const state = (r.data as any)?.transaction?.state || (r.data as any)?.state;
    if (state === "COMPLETE") {
      const txHash =
        (r.data as any)?.transaction?.txHash || (r.data as any)?.txHash;
      return { txHash };
    }
    if (["FAILED", "DENIED", "CANCELLED"].includes(state))
      throw new Error(`Tx ${id} ended in state ${state}`);
    await new Promise((res) => setTimeout(res, 3_000));
  }
  throw new Error(`Tx ${id} did not complete in ${timeoutMs}ms`);
}

async function getOrCreateWalletSet(): Promise<string> {
  const list = await circle.listWalletSets({});
  const existing = (list.data?.walletSets || []).find((w: any) => w.name === SET_NAME);
  if (existing) return existing.id;
  const created = await circle.createWalletSet({ name: SET_NAME });
  return created.data!.walletSet!.id!;
}

async function createTwoSca(walletSetId: string) {
  const resp = await circle.createWallets({
    walletSetId,
    blockchains: [ARC as any],
    count: 2,
    accountType: "SCA",
  });
  const ws = resp.data!.wallets!;
  return {
    desk: { id: ws[0].id!, address: ws[0].address! },
    judge: { id: ws[1].id!, address: ws[1].address! },
  };
}

function ensureDir(path: string) {
  const d = dirname(path);
  if (!existsSync(d)) mkdirSync(d, { recursive: true });
}

function readIdentityRow() {
  if (!existsSync(IDENTITY_TSV)) return null;
  const txt = readFileSync(IDENTITY_TSV, "utf8");
  const lines = txt.trim().split("\n");
  if (lines.length < 2) return null;
  const headers = lines[0].split("\t");
  const vals = lines[lines.length - 1].split("\t");
  return Object.fromEntries(headers.map((h, i) => [h, vals[i] || ""])) as Record<string, string>;
}

function writeIdentityRow(row: Record<string, string>) {
  ensureDir(IDENTITY_TSV);
  const headers = [
    "ts",
    "desk_wallet_id",
    "desk_wallet_addr",
    "judge_wallet_id",
    "judge_wallet_addr",
    "client_wallet_id",
    "client_wallet_addr",
    "desk_agent_id",
    "register_tx_hash",
  ];
  const exists = existsSync(IDENTITY_TSV);
  const line = headers.map((h) => row[h] ?? "").join("\t");
  if (!exists) {
    writeFileSync(IDENTITY_TSV, headers.join("\t") + "\n" + line + "\n");
  } else {
    writeFileSync(IDENTITY_TSV, readFileSync(IDENTITY_TSV, "utf8") + line + "\n");
  }
}

async function execContract(
  walletId: string,
  contractAddress: string,
  abiFunctionSignature: string,
  abiParameters: any[]
): Promise<{ txHash: string }> {
  const resp = await circle.createContractExecutionTransaction({
    walletId,
    contractAddress,
    abiFunctionSignature,
    abiParameters,
    fee: { type: "level", config: { feeLevel: "MEDIUM" } } as any,
  });
  const id = (resp.data as any)?.id;
  return await pollTx(id);
}

async function main() {
  let row = readIdentityRow();
  if (row && row.desk_agent_id) {
    console.log("Identity row already present — using existing wallets:");
    console.log(row);
    return;
  }

  const setId = await getOrCreateWalletSet();
  const { desk, judge } = await createTwoSca(setId);
  console.log(`Created wallets:\n  desk_owner      = ${desk.address}\n  judge_validator = ${judge.address}`);

  // Auto-fund desk_owner from the smoke wallet set if one exists. This
  // avoids a second faucet call: the smoke wallet already has USDC from
  // Gate B, and Circle's internal transfer is free + instant. If no
  // smoke wallet (or insufficient balance) is found, we fall back to
  // asking the operator to faucet-fund desk_owner directly.
  const SMOKE_SET_NAME = "arc-compute-sec-smoke";
  const DESK_SEED_USDC = "3";
  const sets = await circle.listWalletSets({});
  const smokeSet = (sets.data?.walletSets || []).find((w: any) => w.name === SMOKE_SET_NAME);
  let funded = false;
  if (smokeSet) {
    const smokeWallets = await circle.listWallets({ walletSetId: smokeSet.id });
    for (const w of smokeWallets.data?.wallets || []) {
      const bal = await circle.getWalletTokenBalance({ id: w.id! });
      const usdc = (bal.data?.tokenBalances || []).find(
        (t: any) => (t.token?.symbol || "").toUpperCase() === "USDC"
      );
      const amount = parseFloat(usdc?.amount || "0");
      if (usdc?.token?.id && amount >= parseFloat(DESK_SEED_USDC) + 0.1) {
        console.log(`Auto-funding desk_owner with ${DESK_SEED_USDC} USDC from smoke wallet ${w.address}`);
        const tr = await circle.createTransaction({
          walletId: w.id!,
          tokenId: usdc.token.id,
          destinationAddress: desk.address,
          amounts: [DESK_SEED_USDC],
          fee: { type: "level", config: { feeLevel: "MEDIUM" } } as any,
        });
        const fundTx = await pollTx((tr.data as any)?.id);
        console.log(`  smoke → desk tx: https://testnet.arcscan.app/tx/${fundTx.txHash}`);
        funded = true;
        break;
      }
    }
  }
  if (!funded) {
    console.log(`\nNo funded smoke wallet found in set '${SMOKE_SET_NAME}'.`);
    console.log(`Fund desk_owner with ≥3 USDC at https://faucet.circle.com manually.`);
    console.log(`Then check: https://testnet.arcscan.app/address/${desk.address}`);
    console.log(`Waiting for operator… press Enter when funded.`);
    await new Promise<void>((res) => process.stdin.once("data", () => res()));
  }

  // Internal transfer 0.5 USDC desk -> judge so judge can pay gas later.
  const bal = await circle.getWalletTokenBalance({ id: desk.id });
  const usdc = (bal.data?.tokenBalances || []).find(
    (t: any) => (t.token?.symbol || "").toUpperCase() === "USDC"
  );
  if (!usdc?.token?.id) throw new Error("USDC tokenId not found on desk wallet");
  const transferRes = await circle.createTransaction({
    walletId: desk.id,
    tokenId: usdc.token.id,
    destinationAddress: judge.address,
    amounts: ["0.5"],
    fee: { type: "level", config: { feeLevel: "MEDIUM" } } as any,
  });
  await pollTx((transferRes.data as any)?.id);
  console.log(`Transferred 0.5 USDC: desk → judge.`);

  const identityAbi = await loadAbi("identity_registry.json");
  const validationAbi = await loadAbi("validation_registry.json");

  // register(metadataURI)
  console.log(`Registering desk identity with metadataURI=${METADATA_URI}`);
  const { txHash: registerHash } = await execContract(
    desk.id,
    IDENTITY,
    "register(string)",
    [METADATA_URI]
  );
  console.log(`register tx: https://testnet.arcscan.app/tx/${registerHash}`);

  // Decode the Transfer event to recover the agent tokenId.
  const receipt = await arc.getTransactionReceipt({ hash: registerHash as `0x${string}` });
  const events = parseEventLogs({ abi: identityAbi, logs: receipt.logs });
  const transfer = events.find((e: any) => e.eventName === "Transfer" && e.address.toLowerCase() === IDENTITY.toLowerCase());
  if (!transfer) throw new Error("Transfer event not found in register receipt");
  const tokenId = (transfer.args as any).tokenId.toString();
  console.log(`desk_agent_id = ${tokenId}`);

  // Validation rehearsal.
  const reqHash = keccak256(toHex("phase1-rehearsal-request"));
  const { txHash: vReqTx } = await execContract(
    desk.id, VALIDATION,
    "validationRequest(address,uint256,string,bytes32)",
    [judge.address, tokenId, "ipfs://placeholder", reqHash]
  );
  console.log(`validationRequest tx: https://testnet.arcscan.app/tx/${vReqTx}`);

  const respHash = keccak256(toHex("phase1-rehearsal-response"));
  const { txHash: vRespTx } = await execContract(
    judge.id, VALIDATION,
    "validationResponse(bytes32,uint8,string,bytes32,string)",
    [reqHash, 100, "ipfs://placeholder", respHash, "phase1-rehearsal"]
  );
  console.log(`validationResponse tx: https://testnet.arcscan.app/tx/${vRespTx}`);

  writeIdentityRow({
    ts: new Date().toISOString(),
    desk_wallet_id: desk.id,
    desk_wallet_addr: desk.address,
    judge_wallet_id: judge.id,
    judge_wallet_addr: judge.address,
    client_wallet_id: "",
    client_wallet_addr: "",
    desk_agent_id: tokenId,
    register_tx_hash: registerHash,
  });
  console.log(`Wrote ${IDENTITY_TSV}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
