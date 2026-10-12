# Family PF — Verified Audit Principal Wiring Checkpoint
Date: 2026-10-13 Asia/Taipei
Scope: isolated GitHub branch `family-pf-ci-20261012` only.

## Completed
- `pf_mcp_protocol.py`: resource ALLOW/DENY audit events now derive `actor_ref` from `persistent_audit.pseudonymize(principal)`, using server-verified JWT identity rather than static synthetic_subject.
- `test_mcp_audit_wiring.py`: verifies two distinct pseudonyms with stable association across bidirectional synthetic access denials and same-user allowed reads; no raw client label leakage; tests audit sink failure.
- Commits: `aeef2fd7bf5bfd09b1b238b9eebaf63ea88ada04`, `fc0cb151c7709ef660f68ab0211d0a5a545d514f`, `7c45eaca56fc55ce7cde95d65a31057c022ef5b5`.
- Initial run 38324331103: 167 passed, 2 failed. Failures were a test assumption about token principal representation and mock audit sink lacking pseudonymize; test fixtures corrected.
- [GitHub Actions 38324401904](https://github.com/a23882005/LivingWaterAI/actions/runs/38324401904): full test step and Demo PASS; final job completed SUCCESS. Expected suite 169 checks based on initial failure log showing 167 passed + 2 failed, now both repaired. Exact passing count ideally archive fresh full pytest summary for final governance register.
- No change to production Runtime, main branch, real customer data or paid infrastructure.

## Outstanding Gate A
- Actual public HTTPS MCP endpoint, external OAuth login, remote dual-customer request authorization and durable external audit E2E have not been performed.
- Stable pseudonym implementation uses the AuditStore HMAC integrity key also for pseudonymization. Before production, use separate keys, define rotation and operational audit retention.
- No independent preapproved reviewer signing evidence.
- Gate A: HOLD; WORK13: 0/29; PR #2 Draft. Hosting surcharge NT$0.

## Governance
- Supervising PM to register checkpoint/CI/commit in central ABC工程檔 under root `檔案管理.md` backup and read-back SOP. This working branch does not mutate Drive governance assets.
