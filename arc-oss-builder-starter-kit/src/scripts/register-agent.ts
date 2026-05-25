import { createPublicClient, http, parseEventLogs } from "viem";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { createInterface } from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { CHAIN_NAME, EXPLORER, FAUCET, IDENTITY_REGISTRY } from "../arc/addresses.js";
import { circleClient, executeContract, pollCircleTx } from "../arc/circle.js";
import { arcRpc, walletSetName } from "../arc/env.js";
import { IDENTITY_PATH, writeIdentity } from "../arc/state.js";

type WalletRef = { id: string; address: string };

const METADATA_URI = process.env.ARC_AGENT_METADATA_URI || "ipfs://replace-with-your-agent-metadata";

async function prompt(message: string): Promise<void> {
  if (!process.stdin.isTTY) {
    throw new Error(`${message} Re-run in an interactive terminal after funding.`);
  }
  const rl = createInterface({ input, output });
  await rl.question(`${message}\nPress Enter to continue.`);
  rl.close();
}

async function getOrCreateWalletSet(circle: ReturnType<typeof circleClient>): Promise<string> {
  const sets = await circle.listWalletSets({});
  const existing = (sets.data?.walletSets || []).find((set: any) => set.name === walletSetName());
  if (existing?.id) return existing.id;
  const created = await circle.createWalletSet({ name: walletSetName() });
  const id = created.data?.walletSet?.id;
  if (!id) throw new Error("Circle did not return walletSet id");
  return id;
}

async function createWallets(circle: ReturnType<typeof circleClient>, walletSetId: string): Promise<{
  builder: WalletRef;
  validator: WalletRef;
  client: WalletRef;
}> {
  const response = await circle.createWallets({
    walletSetId,
    blockchains: [CHAIN_NAME as any],
    count: 3,
    accountType: "SCA",
  });
  const wallets = response.data?.wallets || [];
  if (wallets.length < 3) throw new Error("Circle did not create three SCA wallets");
  return {
    builder: { id: wallets[0].id!, address: wallets[0].address! },
    validator: { id: wallets[1].id!, address: wallets[1].address! },
    client: { id: wallets[2].id!, address: wallets[2].address! },
  };
}

async function usdcTokenId(circle: ReturnType<typeof circleClient>, walletId: string): Promise<string | null> {
  const balance = await circle.getWalletTokenBalance({ id: walletId });
  const usdc = (balance.data?.tokenBalances || []).find(
    (entry: any) => (entry.token?.symbol || "").toUpperCase() === "USDC",
  );
  return usdc?.token?.id || null;
}

async function transferUsdc(circle: ReturnType<typeof circleClient>, fromWalletId: string, tokenId: string, toAddress: string, amount: string): Promise<string> {
  const response = await circle.createTransaction({
    walletId: fromWalletId,
    tokenId,
    destinationAddress: toAddress,
    amount: [amount],
    fee: { type: "level", config: { feeLevel: "MEDIUM" } } as any,
  });
  const id = (response.data as any)?.id;
  if (!id) throw new Error("Circle transfer did not return transaction id");
  return pollCircleTx(circle, id);
}

async function main() {
  if (existsSync(IDENTITY_PATH)) {
    console.log(`${IDENTITY_PATH} already exists. Delete it only if you intentionally want a new starter identity.`);
    return;
  }

  const circle = circleClient();
  const arc = createPublicClient({ transport: http(arcRpc()) });
  const walletSetId = await getOrCreateWalletSet(circle);
  const { builder, validator, client } = await createWallets(circle, walletSetId);

  console.log("Created Arc SCA wallets:");
  console.log(`  builder  ${builder.address}`);
  console.log(`  validator ${validator.address}`);
  console.log(`  client    ${client.address}`);
  console.log("");
  console.log(`Fund builder with at least 4 USDC: ${FAUCET}`);
  console.log(`Explorer: ${EXPLORER}/address/${builder.address}`);
  await prompt("Funding needed before registration and wallet seeding.");

  const tokenId = await usdcTokenId(circle, builder.id);
  if (!tokenId) throw new Error("Builder wallet has no USDC token balance after funding");

  const validatorTx = await transferUsdc(circle, builder.id, tokenId, validator.address, "0.5");
  const clientTx = await transferUsdc(circle, builder.id, tokenId, client.address, "2");
  console.log(`Seeded validator: ${EXPLORER}/tx/${validatorTx}`);
  console.log(`Seeded client:    ${EXPLORER}/tx/${clientTx}`);

  const registerTxHash = await executeContract(circle, builder.id, IDENTITY_REGISTRY, "register(string)", [METADATA_URI]);
  console.log(`register tx: ${EXPLORER}/tx/${registerTxHash}`);

  const identityAbi = JSON.parse(await readFile("contracts/abis/identity_registry.json", "utf8"));
  const receipt = await arc.getTransactionReceipt({ hash: registerTxHash as `0x${string}` });
  const events = parseEventLogs({ abi: identityAbi, logs: receipt.logs });
  const transfer = events.find(
    (event: any) => event.eventName === "Transfer" && event.address.toLowerCase() === IDENTITY_REGISTRY.toLowerCase(),
  ) as any;
  if (!transfer) throw new Error("Transfer event not found in identity register receipt");
  const agentId = String(transfer.args.tokenId);

  writeIdentity({
    walletSetId,
    builderWalletId: builder.id,
    builderAddress: builder.address,
    validatorWalletId: validator.id,
    validatorAddress: validator.address,
    clientWalletId: client.id,
    clientAddress: client.address,
    agentId,
    registerTxHash,
  });
  console.log(`agentId=${agentId}`);
  console.log(`Wrote ${IDENTITY_PATH}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
