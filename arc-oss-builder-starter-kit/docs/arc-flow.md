# Arc Builder Flow

This starter kit keeps the Arc path small and explicit:

1. Register an ERC-8004 agent identity.
2. Build or load an offchain verdict blob.
3. Refuse every Arc job action unless the verdict is `EXECUTE`.
4. Create an ERC-8183 job.
5. Set a USDC budget using the ERC-20 6-decimal USDC interface.
6. Approve and fund escrow.
7. Submit a deliverable hash.
8. Complete the job and write ERC-8004 reputation feedback.

## Contracts

| Purpose | Contract |
| --- | --- |
| ERC-8004 identity | `0x8004A818BFB912233c491871b3d84c89A494BD9e` |
| ERC-8004 validation | `0x8004Cb1BF31DAf7788923b405b754f57acEB4272` |
| ERC-8004 reputation | `0x8004B663056A597Dffe9eCcC1965A193B7388713` |
| ERC-8183 agentic commerce | `0x0747EEf0706327138c69792bF28Cd525089e4583` |
| USDC ERC-20 interface | `0x3600000000000000000000000000000000000000` |

## The Guard

The important file is `src/arc/verdict.ts`.

`assertExecutable(verdict)` throws unless:

- `verdict.label === "EXECUTE"`
- `verdict.action_payload_hash` is present

Every chain script calls this function before creating the Circle client or
submitting an Arc transaction. That makes the invariant visible to builders:
classification comes first, Arc comes second.

## USDC Decimals

Arc exposes native balance accounting separately from the ERC-20 USDC
interface. Application escrow uses the ERC-20 address above and 6 decimals.

Use `usdc6()` from `src/arc/usdc.ts` for every budget or allowance.

Never use 18-decimal parsing for ERC-20 USDC.
