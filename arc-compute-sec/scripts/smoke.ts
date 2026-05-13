/**
 * USDC round-trip smoke test on Arc Testnet.
 *
 * Steps:
 *  1. Create a single SCA Circle Wallet on ARC-TESTNET.
 *  2. Print its address; pause for the operator to fund via faucet.circle.com.
 *  3. After Enter, transfer 0.01 USDC back to itself (any address would do,
 *     but self-transfer keeps the script idempotent against drift).
 *  4. Poll until COMPLETE; print explorer link.
 *
 * Requires `.env` with CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET.
 */
import { initiateDeveloperControlledWalletsClient } from "@circle-fin/developer-controlled-wallets";
import { parseUnits } from "viem";
import { createInterface } from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { writeFileSync, existsSync, readFileSync } from "node:fs";

const ARC = "ARC-TESTNET";
const USDC_TOKEN_ID_MAP_PATH = "logs/usdc_token_id.txt"; // cache resolved token id between runs

if (!process.env.CIRCLE_API_KEY || !process.env.CIRCLE_ENTITY_SECRET) {
  console.error("Missing CIRCLE_API_KEY or CIRCLE_ENTITY_SECRET in .env. Aborting.");
  process.exit(1);
}

const client = initiateDeveloperControlledWalletsClient({
  apiKey: process.env.CIRCLE_API_KEY!,
  entitySecret: process.env.CIRCLE_ENTITY_SECRET!,
});

async function pause(prompt: string): Promise<void> {
  const rl = createInterface({ input, output });
  await rl.question(prompt);
  rl.close();
}

async function getOrCreateWalletSet(): Promise<string> {
  const setName = "arc-compute-sec-smoke";
  const list = await client.listWalletSets({});
  const existing = (list.data?.walletSets || []).find((w: any) => w.name === setName);
  if (existing) return existing.id;
  const created = await client.createWalletSet({ name: setName });
  return created.data!.walletSet!.id!;
}

async function createOne(walletSetId: string) {
  const resp = await client.createWallets({
    walletSetId,
    blockchains: [ARC as any],
    count: 1,
    accountType: "SCA",
  });
  const w = resp.data!.wallets![0];
  return { id: w.id!, address: w.address! };
}

async function getUsdcTokenId(walletId: string): Promise<string> {
  // Circle assigns a per-network tokenId for USDC. We discover it once via
  // getWalletTokenBalance and cache it locally.
  if (existsSync(USDC_TOKEN_ID_MAP_PATH)) {
    return readFileSync(USDC_TOKEN_ID_MAP_PATH, "utf8").trim();
  }
  const bal = await client.getWalletTokenBalance({ id: walletId });
  const usdc = (bal.data?.tokenBalances || []).find(
    (t: any) => (t.token?.symbol || "").toUpperCase() === "USDC"
  );
  if (!usdc?.token?.id) {
    throw new Error(
      "Could not resolve USDC tokenId on this wallet's network. " +
        "Did the operator fund the wallet at faucet.circle.com yet?"
    );
  }
  writeFileSync(USDC_TOKEN_ID_MAP_PATH, usdc.token.id);
  return usdc.token.id;
}

async function pollTx(id: string): Promise<any> {
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    const r = await client.getTransaction({ id });
    const state = (r.data as any)?.transaction?.state || (r.data as any)?.state;
    if (state === "COMPLETE") return r.data;
    if (["FAILED", "DENIED", "CANCELLED"].includes(state)) {
      throw new Error(`Tx ${id} ended in state ${state}`);
    }
    await new Promise((res) => setTimeout(res, 3_000));
  }
  throw new Error(`Tx ${id} did not complete in 180s`);
}

async function main() {
  const setId = await getOrCreateWalletSet();
  const { id, address } = await createOne(setId);
  console.log(`\nCreated wallet:\n  id      = ${id}\n  address = ${address}`);
  console.log(`\nFund this address with ≥5 USDC from https://faucet.circle.com`);
  console.log(`Then check the balance: https://testnet.arcscan.app/address/${address}`);

  await pause("\nPress Enter once the faucet shows balance ≥ 5 USDC… ");

  const tokenId = await getUsdcTokenId(id);
  console.log(`USDC tokenId on this network: ${tokenId}`);

  const bal = await client.getWalletTokenBalance({ id });
  console.log(
    `Wallet balances:`,
    (bal.data?.tokenBalances || []).map((t: any) => ({
      sym: t.token?.symbol,
      amount: t.amount,
    }))
  );

  // 0.01 USDC self-transfer (6 decimals via the ERC-20 interface).
  const amount = "0.01";
  const tx = await client.createTransaction({
    walletId: id,
    tokenId,
    destinationAddress: address,
    amounts: [amount],
    fee: { type: "level", config: { feeLevel: "MEDIUM" } } as any,
  });
  const txId = (tx.data as any)?.id;
  console.log(`Submitted transfer; Circle id = ${txId}`);

  const final = await pollTx(txId);
  const txHash = (final as any)?.transaction?.txHash || (final as any)?.txHash;
  console.log(`\nCOMPLETE`);
  console.log(`  txHash      = ${txHash}`);
  console.log(`  explorer    = https://testnet.arcscan.app/tx/${txHash}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
