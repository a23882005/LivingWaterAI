# Family PF — Remote evidence input and Gate A checkpoint

Date: 2026-10-14 Asia/Taipei
Repository: a23882005/LivingWaterAI
Branch: family-pf-ci-20261012
Pull request: #2, Draft, unmerged

## Completed change
File: experiments/family-pf-poc-20261012/test_remote_preflight.py
Commit: 936d95d7981633bc62917e26be34a9880ab12188
Blob SHA after change: 8d50a826e6ad3429fe9911dd221448aaff8f1015
Six new test cases: five invalid URL input types; one valid metadata response showing OAuth login, client isolation and audit logs remain NOT_TESTED, Gate A HOLD.

## Verified workflow
Run: https://github.com/a23882005/LivingWaterAI/actions/runs/38449706613
Job: 115477146078, completed SUCCESS.
Full test suite: 273 passed, 1 warning, 0 failed in 10.68 seconds.
Demo: LOCAL DEMO PASS, synthetic project A own read HTTP 200, foreign project read HTTP 403.

## Evidence maturity and governance
The full test suite runs against synthetic/local project fixtures. It is NOT an external Gate A acceptance and provides no real OAuth or independently observed tenant isolation proof.
Gate A: HOLD.
WORK13: 0/29.
Draft PR #2: unmerged. Main and Runtime not changed in this work.
Required independent evidence: approved HTTPS MCP, actual authorized OAuth exchange, two-way Joseph/mou isolation demonstration under independent supervision, independently retained denial audit logs, governance-pinned reviewer fingerprint and explicit security signoff.
Never commit OAuth tokens, secret keys, actual client holdings or personally identifying records.
