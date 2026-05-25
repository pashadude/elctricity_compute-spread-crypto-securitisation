import { createPublicClient, http, parseEventLogs } from "viem";
import { readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { AGENTIC_COMMERCE, EXPLORER, USDC } from "../arc/addresses.js";
import { circleClient, executeContract } from "../arc/circle.js";
import { arcRpc } from "../arc/env.js";
import { readIdentity, appendJob } from "../arc/state.js";
import { usdc6 } from "../arc/usdc.js";
import { assertExecutable, readVerdictBlob } from "../arc/verdict.js";

type Args = {
  verdictPath: string;
  surface: string;
  market: string;
  notional: string;
  expiresHours: number;
};

function parseArgs(argv: string[]): Args {
  const out: Args = {
    verdictPath: "examples/verdict-execute.json",
    surface: "demo",
    market: "example-market",
    notional: "1",
    expiresHours: 1,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--verdict") out.verdictPath = argv[++i];
    else if (arg === "--surface") out.surface = argv[++i];
    else if (arg === "--market") out.market = argv[++i];
    else if (arg === "--notional") out.notional = argv[++i];
    else if (arg === "--expires-hours") out.expiresHours = Number(argv[++i]);
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const verdict = readVerdictBlob(readFileSync(args.verdictPath, "utf8"));
  assertExecutable(verdict);

  const identity = readIdentity();
  if (!identity.clientWalletId || !identity.clientAddress) {
    throw new Error("Identity is missing client wallet; rerun register-agent");
  }
  const circle = circleClient();
  const arc = createPublicClient({ transport: http(arcRpc()) });
  const expiresAt = Math.floor(Date.now() / 1000) + args.expiresHours * 3600;
  const description = `${args.surface}|${args.market}|judge:${verdict.action_payload_hash}`;
  const hook = "0x0000000000000000000000000000000000000000";

  const createTx = await executeContract(
    circle,
    identity.clientWalletId,
    AGENTIC_COMMERCE,
    "createJob(address,address,uint256,string,address)",
    [identity.builderAddress, identity.validatorAddress, expiresAt, description, hook],
  );
  const commerceAbi = JSON.parse(await readFile("contracts/abis/agentic_commerce.json", "utf8"));
  const receipt = await arc.getTransactionReceipt({ hash: createTx as `0x${string}` });
  const events = parseEventLogs({ abi: commerceAbi, logs: receipt.logs });
  const created = events.find((event: any) => event.eventName === "JobCreated") as any;
  if (!created) throw new Error("JobCreated event not found");
  const jobId = String(created.args.jobId);

  const baseUnits = usdc6(args.notional);
  const budgetTx = await executeContract(
    circle,
    identity.builderWalletId,
    AGENTIC_COMMERCE,
    "setBudget(uint256,uint256,bytes)",
    [jobId, baseUnits, "0x"],
  );
  const approveTx = await executeContract(
    circle,
    identity.clientWalletId,
    USDC,
    "approve(address,uint256)",
    [AGENTIC_COMMERCE, baseUnits],
  );
  const fundTx = await executeContract(
    circle,
    identity.clientWalletId,
    AGENTIC_COMMERCE,
    "fund(uint256,bytes)",
    [jobId, "0x"],
  );

  appendJob({ ts: new Date().toISOString(), stage: "created", jobId, txHash: createTx, notionalUsdc: args.notional, verdictPath: args.verdictPath });
  appendJob({ ts: new Date().toISOString(), stage: "budgeted", jobId, txHash: budgetTx, notionalUsdc: args.notional, verdictPath: args.verdictPath });
  appendJob({ ts: new Date().toISOString(), stage: "approved", jobId, txHash: approveTx, notionalUsdc: args.notional, verdictPath: args.verdictPath });
  appendJob({ ts: new Date().toISOString(), stage: "funded", jobId, txHash: fundTx, notionalUsdc: args.notional, verdictPath: args.verdictPath });

  console.log(`jobId=${jobId}`);
  console.log(`create ${EXPLORER}/tx/${createTx}`);
  console.log(`budget ${EXPLORER}/tx/${budgetTx}`);
  console.log(`approve ${EXPLORER}/tx/${approveTx}`);
  console.log(`fund   ${EXPLORER}/tx/${fundTx}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
