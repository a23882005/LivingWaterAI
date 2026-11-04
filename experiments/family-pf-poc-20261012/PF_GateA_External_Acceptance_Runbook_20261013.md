# Family PF Gate A — external acceptance execution runbook
Date: 2026-10-13. This is a **plan, not evidence of completion**.

## Authorization prerequisites
A governance owner must supply an approved isolated HTTPS test endpoint, a real externally managed OAuth issuer, two non-production synthetic test identities in different client tenants, a separated durable audit retention destination, an independent reviewer with an out-of-band pinned public-key fingerprint, and an approved evidence storage destination. No production client records or secrets in commits, screenshots, or artifacts.

## Gate A evidence requirements
1. HTTPS MCP: from an independent external network, verify DNS/public IP, TLS chain, endpoint reachability, protected resource metadata and actual MCP request behavior. Check egress/DNS policy; URL validation alone is not SSRF defense.
2. OAuth: execute real authorization with PKCE, verify issuer/audience/expiration/revocation, reject wrong audience and replay attempts; retain redacted evidence.
3. Tenant binding: establish the identity-to-client mapping server-side, prove cross-tenant denial with independent synthetic identities in both directions, including re-authorization on each data access.
4. Audit: demonstrate that both denied and allowed requests produce redacted persistent events, surviving process restart; export audit anchors to a genuinely separate trusted store, and test integrity verification with anchored history.
5. Independent reviewer: record the exact approved reviewer trust fingerprint out-of-band, sign scoped/dated evidence and verify signature; do not treat developer self-signature as independent sign-off.

## Decision rules
- All five evidence items must be externally demonstrated and independently reviewed. Missing or expired evidence => HOLD.
- A signature-verification return of ATTESTED_FOR_REVIEW is **not automatic Gate A PASS**.
- Human governance approval and documented full review precede release, branch merge, WORK13 or runtime changes.
- Synthetic GitHub CI success only proves the isolated PoC regressions.

## Current decision
Gate A HOLD; WORK13 0/29; Draft PR #2. No authorized external deployment or real OAuth test environment has been furnished.
