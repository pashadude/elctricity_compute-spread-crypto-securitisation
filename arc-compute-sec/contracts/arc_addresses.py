"""Arc Testnet network + contract addresses. Single source of truth.

Verified 2026-05-13 against docs.arc.network/arc/references/contract-addresses.md
and /arc/references/connect-to-arc.md. Do not edit without re-fetching the source.
"""
from __future__ import annotations
from decimal import Decimal

CHAIN_ID = 5042002              # 0x4CEF52
CHAIN_NAME = "ARC-TESTNET"      # Circle SDK blockchain identifier
RPC_HTTP = "https://rpc.testnet.arc.network"
RPC_WS   = "wss://rpc.testnet.arc.network"
EXPLORER = "https://testnet.arcscan.app"
FAUCET   = "https://faucet.circle.com"

# Stablecoins
# USDC on Arc has TWO interfaces:
#   - Native balance:  18 decimals (gas accounting precision)
#   - ERC-20 interface 0x3600000000000000000000000000000000000000:  6 decimals
# All application code uses the ERC-20 interface and 6 decimals.
# Always confirm via decimals() on first session use. Never mix the two in arithmetic.
USDC = "0x3600000000000000000000000000000000000000"
USDC_DECIMALS = 6
EURC = "0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a"
USYC = "0xe9185F0c5F296Ed1797AaE4238D26CCaBEadb86C"

# ERC-8004 agent identity / reputation / validation
IDENTITY_REGISTRY    = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
REPUTATION_REGISTRY  = "0x8004B663056A597Dffe9eCcC1965A193B7388713"
VALIDATION_REGISTRY  = "0x8004Cb1BF31DAf7788923b405b754f57acEB4272"

# ERC-8183 agentic commerce — job lifecycle with escrow
AGENTIC_COMMERCE = "0x0747EEf0706327138c69792bF28Cd525089e4583"

# CCTP v2 (domain 26 = Arc) — reference only; v0 does not use cross-chain
CCTP_TOKEN_MESSENGER     = "0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA"
CCTP_MESSAGE_TRANSMITTER = "0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275"
CCTP_TOKEN_MINTER        = "0xb43db544E2c27092c107639Ad201b3dEfAbcF192"
CCTP_DOMAIN_ARC          = 26

# Gateway (chain-abstracted USDC) — reference only
GATEWAY_WALLET = "0x0077777d7EBA4688BDeF3E311b846F25870A19B9"
GATEWAY_MINTER = "0x0022222ABE238Cc2C7Bb1f21003F0a260052475B"

# StableFX (reference only; v0 unused)
FX_ESCROW = "0x867650F5eAe8df91445971f14d89fd84F0C9a9f8"

# Ecosystem
PERMIT2     = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
MULTICALL3  = "0xcA11bde05977b3631167028862bE2a173976CA11"
MEMO        = "0x9702466268ccF55eAB64cdf484d272Ac08d3b75b"


def usdc6(amount: Decimal | float | str | int) -> int:
    """Convert a human USDC amount to the 6-decimals ERC-20 base unit (integer).

    USE THIS at every spot a USDC amount is sent. Never write parseUnits(amount, 18)
    for USDC — that bug burns 1e12 USDC per dollar. The 18-decimals interface is
    for native balance accounting only and is not used in this build.
    """
    d = Decimal(str(amount))
    if d < 0:
        raise ValueError(f"usdc6() does not accept negative amounts: {amount!r}")
    base = d * (Decimal(10) ** USDC_DECIMALS)
    if base != base.to_integral_value():
        raise ValueError(
            f"usdc6({amount!r}) has sub-micro-cent precision; truncation would lose data"
        )
    return int(base)


def usdc6_to_decimal(base_units: int) -> Decimal:
    """Inverse of usdc6() — turns ERC-20 base units back into a human Decimal."""
    return Decimal(base_units) / (Decimal(10) ** USDC_DECIMALS)


# Convenience: surfaces the agent's runtime knows about
SURFACES = ("polymarket", "ibkr", "crypto", "kalshi")
