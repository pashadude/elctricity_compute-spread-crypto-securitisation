import { keccak256, toHex } from "viem";
import { readFileSync } from "node:fs";
import { AGENTIC_COMMERCE, EXPLORER } from "../arc/addresses.js";
import { circleClient, executeContract } from "../arc/circle.js";
import { readIdentity, appendJob } from "../arc/state.js";
import { assertExecutable, readVerdictBlob } from "../arc/verdict.js";

type Args = { job: string; verdictPath: string; deliverablePath: string };

function parseArgs(argv: string[]): Args {
  const out: Args = { job: "", verdictPath: "examples/verdict-execute.json", deliverablePath: "examples/deliverable.json" };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--job") out.job = argv[++i];
    else if (arg === "--verdict") out.verdictPath = argv[++i];
    else if (arg === "--deliverable") out.deliverablePath = argv[++i];
  }
  if (!out.job) throw new Error("Usage: npm run submit-deliverable -- --job <id> --verdict <file> --deliverable <file>");
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const verdict = readVerdictBlob(readFileSync(args.verdictPath, "utf8"));
  assertExecutable(verdict);

  const deliverable = readFileSync(args.deliverablePath, "utf8");
  const deliverableHash = keccak256(toHex(deliverable));
  const identity = readIdentity();
  const circle = circleClient();
  const txHash = await executeContract(
    circle,
    identity.builderWalletId,
    AGENTIC_COMMERCE,
    "submit(uint256,bytes32,bytes)",
    [args.job, deliverableHash, "0x"],
  );
  appendJob({ ts: new Date().toISOString(), stage: "submitted", jobId: args.job, txHash, deliverableHash, verdictPath: args.verdictPath });
  console.log(`deliverableHash=${deliverableHash}`);
  console.log(`submit ${EXPLORER}/tx/${txHash}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
