# Submission Notes

This folder is intentionally self-contained inside the Power by Botozen repo.
It is for Arc OSS builders who want a minimal, pedagogical starting point for:

- ERC-8004 agent identity
- ERC-8183 job escrow
- Circle Developer-Controlled Wallets
- USDC 6-decimal budget handling
- no-chain-unless-EXECUTE guardrails

## Link To Include

Use this folder link in the Arc OSS submission form and CLI update:

```text
https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation/tree/main/arc-oss-builder-starter-kit
```

The same link is printed by:

```bash
npm run submission-link
```

## Suggested Arc CLI Update

After the main GitHub repo is pushed, run:

```bash
arc-canteen update-product
```

Paste:

```text
Added a self-contained Arc OSS builder starter kit folder:
https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation/tree/main/arc-oss-builder-starter-kit

It teaches ERC-8004 identity, ERC-8183 job escrow, Circle SCA wallets,
USDC 6-decimal handling, and the no-chain-unless-EXECUTE invariant without
mixing in the product-specific compute/energy desk.
```

Do not submit this update before the main repository push includes the folder.
