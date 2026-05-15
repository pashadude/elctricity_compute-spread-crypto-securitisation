export const CHAIN_ID = 5042002;
export const CHAIN_NAME = "ARC-TESTNET";
export const RPC_HTTP = "https://rpc.testnet.arc.network";
export const EXPLORER = "https://testnet.arcscan.app";

export const USDC = "0x3600000000000000000000000000000000000000";
export const USDC_DECIMALS = 6;

export const IDENTITY_REGISTRY = "0x8004A818BFB912233c491871b3d84c89A494BD9e";
export const REPUTATION_REGISTRY = "0x8004B663056A597Dffe9eCcC1965A193B7388713";
export const VALIDATION_REGISTRY = "0x8004Cb1BF31DAf7788923b405b754f57acEB4272";
export const AGENTIC_COMMERCE = "0x0747EEf0706327138c69792bF28Cd525089e4583";

export function usdc6(amount: number | string): string {
  const raw = String(amount);
  if (!/^\d+(\.\d+)?$/.test(raw)) {
    throw new Error(`Invalid non-negative USDC amount: ${raw}`);
  }
  const [whole, frac = ""] = raw.split(".");
  if (frac.length > USDC_DECIMALS) {
    throw new Error(`USDC amount has more than ${USDC_DECIMALS} decimal places: ${raw}`);
  }
  return (BigInt(whole) * 1_000_000n + BigInt(frac.padEnd(USDC_DECIMALS, "0"))).toString();
}
