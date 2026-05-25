import { RPC_HTTP } from "./addresses.js";

export function requiredEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Missing required env var ${name}`);
  return value;
}

export function arcRpc(): string {
  return process.env.ARC_RPC || process.env.RPC || RPC_HTTP;
}

export function walletSetName(): string {
  return process.env.CIRCLE_WALLET_SET_NAME || "arc-oss-builder-starter-kit";
}
