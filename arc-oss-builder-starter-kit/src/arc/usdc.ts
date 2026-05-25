import { USDC_DECIMALS } from "./addresses.js";

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
