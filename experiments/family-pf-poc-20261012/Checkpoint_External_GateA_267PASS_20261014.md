# Family PF — external Gate A evidence readiness checkpoint

Date: 2026-10-14 (Asia/Taipei)
Repo: a23882005/LivingWaterAI
Branch: family-pf-ci-20261012
PR: #2 Draft (not merged)

## Completed this cycle
One isolated test-file change in test_remote_preflight.py:
- Four reserved documentation IPs (192.0.2.1, 198.51.100.1, 203.0.113.1, 2001:db8::1) are not accepted as live endpoint evidence.
- Non-JSON metadata stays NOT_VERIFIED; external OAuth remains NOT_TESTED; Gate A stays HOLD.
Commit: d246d82d1130fe550f188cf213beba91ad98feea
Test-file blob SHA: 9b0253e06cee7cde64ef7b7f7d38875a0a0ba795

## Independent CI record
https://github.com/a23882005/LivingWaterAI/actions/runs/38446984039
Job 115467830171, SUCCESS.
267 passed, 1 warning, 0 failed (7.71s).
LOCAL DEMO PASS: synthetic Project A reading own resource HTTP 200, foreign resource HTTP 403.

## Evidence acquisition responsibilities before release
1. Approved live HTTPS resource endpoint: deployment owner supplies hostname, TLS check, resource metadata, exact verified UTC timestamp. Never put access tokens in GitHub.
2. External OAuth authority: approved operator uses separate, consented test identities, verifies authentication / issuer / audience / subject and binds tokens to correct MCP resource.
3. Tenant isolation review: independent security tester repeats own-resource allow and foreign-resource deny in BOTH directions, confirms deny events and non-disclosure.
4. Audit witness: reviewer validates request-id correlations and pseudonymous, independently retained tamper-evident hash anchor. Protect client personal information and credentials.
5. Independent security signoff: governance pins reviewer public-key fingerprint outside this repo; reviewer verifies original evidence before signing. A signed synthetic record remains only ATTESTED_FOR_REVIEW.
Each evidence item must identify approver, environment, test time, evidence reference, and disposition. Do not represent a mock as a real endpoint.

## Controls
Gate A: HOLD; WORK13: 0/29.
PR #2: Draft / unmerged; main and formal Runtime unchanged.
No real customer holdings, secrets, or customer OAuth tokens should enter code, test fixtures, checkpoints, CI logs or evidence package.
Passing synthetic CI does not authorize deployment, merge or release.
