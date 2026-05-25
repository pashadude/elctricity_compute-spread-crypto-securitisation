import { keccak256, toHex } from "viem";

export type VerdictLabel = "EXECUTE" | "CHALLENGE" | "DEFER" | "REJECT";

export type VerdictBlob = {
  label: VerdictLabel;
  reason_code: string;
  action_payload_hash?: string;
  max_notional_usdc?: number;
  confidence?: number;
  evidence_uri?: string;
};

export function readVerdictBlob(raw: string): VerdictBlob {
  const parsed = JSON.parse(raw) as VerdictBlob;
  if (!parsed.label || !parsed.reason_code) {
    throw new Error("Verdict blob must contain label and reason_code");
  }
  return parsed;
}

export function assertExecutable(verdict: VerdictBlob): void {
  if (verdict.label !== "EXECUTE") {
    throw new Error(`No Arc action: judge verdict is ${verdict.label}, reason=${verdict.reason_code}`);
  }
  if (!verdict.action_payload_hash) {
    throw new Error("No Arc action: EXECUTE verdict must include action_payload_hash");
  }
}

export function verdictReasonHash(verdict: VerdictBlob): `0x${string}` {
  return keccak256(toHex(JSON.stringify(verdict)));
}
