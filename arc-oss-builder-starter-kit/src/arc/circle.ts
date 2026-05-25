import { initiateDeveloperControlledWalletsClient } from "@circle-fin/developer-controlled-wallets";
import { requiredEnv } from "./env.js";

export function circleClient() {
  return initiateDeveloperControlledWalletsClient({
    apiKey: requiredEnv("CIRCLE_API_KEY"),
    entitySecret: requiredEnv("CIRCLE_ENTITY_SECRET"),
  });
}

export async function pollCircleTx(circle: ReturnType<typeof circleClient>, id: string, timeoutMs = 180_000): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const response = await circle.getTransaction({ id });
    const state = (response.data as any)?.transaction?.state || (response.data as any)?.state;
    if (state === "COMPLETE") {
      const txHash = (response.data as any)?.transaction?.txHash || (response.data as any)?.txHash;
      if (!txHash) throw new Error(`Circle tx ${id} completed without txHash`);
      return txHash;
    }
    if (["FAILED", "DENIED", "CANCELLED"].includes(state)) {
      throw new Error(`Circle tx ${id} ended in state ${state}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  throw new Error(`Circle tx ${id} did not complete within ${timeoutMs}ms`);
}

export async function executeContract(
  circle: ReturnType<typeof circleClient>,
  walletId: string,
  contractAddress: string,
  abiFunctionSignature: string,
  abiParameters: unknown[],
): Promise<string> {
  const response = await circle.createContractExecutionTransaction({
    walletId,
    contractAddress,
    abiFunctionSignature,
    abiParameters,
    fee: { type: "level", config: { feeLevel: "MEDIUM" } } as any,
  });
  const id = (response.data as any)?.id;
  if (!id) throw new Error("Circle contract execution did not return transaction id");
  return pollCircleTx(circle, id);
}
