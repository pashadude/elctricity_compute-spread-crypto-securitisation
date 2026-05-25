import { keccak256, toHex } from "viem";
import { readFileSync } from "node:fs";
import { AGENTIC_COMMERCE, EXPLORER, REPUTATION_REGISTRY } from "../arc/addresses.js";
import { circleClient, executeContract } from "../arc/circle.js";
import { readIdentity, appendJob } from "../arc/state.js";
import { assertExecutable, readVerdictBlob, verdictReasonHash } from "../arc/verdict.js";

type Args = { job: string; verdictPath: string; score: number };

function parseArgs(argv: string[]): Args {
  const out: Args = { job: "", verdictPath: "examples/verdict-execute.json", score: 95 };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--job") out.job = argv[++i];
    else if (arg === "--verdict") out.verdictPath = argv[++i];
    else if (arg === "--score") out.score = Number(argv[++i]);
  }
  if (!out.job) throw new Error("Usage: npm run settle-job -- --job <id> --verdict <file> --score 95");
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const raw = readFileSync(args.verdictPath, "utf8");
  const verdict = readVerdictBlob(raw);
  assertExecutable(verdict);

  const identity = readIdentity();
  if (!identity.agentId) throw new Error("Identity is missing agentId; rerun register-agent");
  const circle = circleClient();
  const reasonHash = verdictReasonHash(verdict);
  const settleTx = await executeContract(
    circle,
    identity.validatorWalletId,
    AGENTIC_COMMERCE,
    "complete(uint256,bytes32,bytes)",
    [args.job, reasonHash, "0x"],
  );
  const feedbackHash = keccak256(toHex(`${raw}:${args.score}`));
  const feedbackTx = await executeContract(
    circle,
    identity.validatorWalletId,
    REPUTATION_REGISTRY,
    "giveFeedback(uint256,int128,uint8,string,string,string,string,bytes32)",
    [identity.agentId, args.score, 0, `execute:${verdict.reason_code}`.slice(0, 32), "", "", "", feedbackHash],
  );

  appendJob({ ts: new Date().toISOString(), stage: "settled", jobId: args.job, txHash: settleTx, reasonHash, verdictPath: args.verdictPath });
  appendJob({ ts: new Date().toISOString(), stage: "feedback", jobId: args.job, txHash: feedbackTx, reasonHash, verdictPath: args.verdictPath });
  console.log(`reasonHash=${reasonHash}`);
  console.log(`settle   ${EXPLORER}/tx/${settleTx}`);
  console.log(`feedback ${EXPLORER}/tx/${feedbackTx}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
