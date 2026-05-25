import { existsSync, mkdirSync, readFileSync, writeFileSync, appendFileSync } from "node:fs";
import { dirname } from "node:path";

export type IdentityState = {
  walletSetId: string;
  builderWalletId: string;
  builderAddress: string;
  validatorWalletId: string;
  validatorAddress: string;
  clientWalletId?: string;
  clientAddress?: string;
  agentId?: string;
  registerTxHash?: string;
};

export type JobRow = {
  ts: string;
  jobId: string;
  stage: string;
  txHash?: string;
  notionalUsdc?: string;
  verdictPath?: string;
  deliverableHash?: string;
  reasonHash?: string;
};

export const IDENTITY_PATH = "state/identity.json";
export const JOBS_PATH = "state/jobs.jsonl";

function ensureParent(path: string): void {
  const dir = dirname(path);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}

export function readIdentity(): IdentityState {
  if (!existsSync(IDENTITY_PATH)) {
    throw new Error(`Missing ${IDENTITY_PATH}; run npm run register-agent first`);
  }
  return JSON.parse(readFileSync(IDENTITY_PATH, "utf8")) as IdentityState;
}

export function writeIdentity(identity: IdentityState): void {
  ensureParent(IDENTITY_PATH);
  writeFileSync(IDENTITY_PATH, JSON.stringify(identity, null, 2) + "\n");
}

export function appendJob(row: JobRow): void {
  ensureParent(JOBS_PATH);
  appendFileSync(JOBS_PATH, JSON.stringify(row) + "\n");
}
