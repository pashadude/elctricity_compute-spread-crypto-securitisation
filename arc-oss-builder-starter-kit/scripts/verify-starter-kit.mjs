import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();

function read(path) {
  return readFileSync(join(root, path), "utf8");
}

function assert(condition, message) {
  if (!condition) {
    console.error(`verify failed: ${message}`);
    process.exitCode = 1;
  }
}

const requiredFiles = [
  "README.md",
  ".env.example",
  "docs/arc-flow.md",
  "docs/submission.md",
  "src/arc/verdict.ts",
  "src/arc/usdc.ts",
  "src/scripts/open-job.ts",
  "src/scripts/submit-deliverable.ts",
  "src/scripts/settle-job.ts",
  "examples/verdict-execute.json",
  "examples/verdict-reject.json",
];

for (const path of requiredFiles) {
  assert(existsSync(join(root, path)), `${path} is missing`);
}

const readme = read("README.md");
assert(
  readme.includes(
    "https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation/tree/main/arc-oss-builder-starter-kit",
  ),
  "README must include starter kit folder link",
);
assert(readme.includes("no Arc action happens unless"), "README must document no-chain-unless-EXECUTE");
assert(readme.includes("USDC 6-decimal"), "README must mention USDC 6 decimals");

const verdict = read("src/arc/verdict.ts");
assert(verdict.includes('verdict.label !== "EXECUTE"'), "verdict guard must reject non-EXECUTE labels");
assert(verdict.includes("action_payload_hash"), "verdict guard must require action_payload_hash");

for (const path of ["src/scripts/open-job.ts", "src/scripts/submit-deliverable.ts", "src/scripts/settle-job.ts"]) {
  const source = read(path);
  const guardIndex = source.indexOf("assertExecutable(verdict)");
  const circleIndex = source.indexOf("circleClient()");
  assert(guardIndex >= 0, `${path} must call assertExecutable(verdict)`);
  assert(circleIndex >= 0, `${path} must create a Circle client`);
  assert(guardIndex < circleIndex, `${path} must guard before creating Circle client`);
}

const usdc = read("src/arc/usdc.ts");
assert(usdc.includes("1_000_000n"), "usdc6 must use 6-decimal base units");

if (!process.exitCode) {
  console.log("starter kit verification passed");
}
