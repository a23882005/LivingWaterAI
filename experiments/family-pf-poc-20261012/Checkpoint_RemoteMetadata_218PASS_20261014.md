# Family PF — Remote metadata negative-test checkpoint (2026-10-14)

Repository: a23882005/LivingWaterAI
Branch: family-pf-ci-20261012
Draft PR: #2 (not merged)

## Changed
- File: experiments/family-pf-poc-20261012/test_remote_preflight.py
- Three additional fail-closed tests: HTTP 500 server error, malformed JSON metadata, empty metadata.
- Code correction commit: 554b13f780e0a3c63505f29d57a5625ba13a7b3e
- Read-back blob SHA: ed68dc59ea6f9bd10a4deb5ff2ac94d2fc35d724

## GitHub CI evidence
- Run URL: https://github.com/a23882005/LivingWaterAI/actions/runs/38440058906
- Job: verify-pf-full-suite — SUCCESS
- pytest: 218 passed, 1 warning in 10.26s; 0 failed
- Demo: SUCCESS; LOCAL DEMO PASS; permitted A->A read 200; unauthorized A->B read 403.
- Warning is a dependency deprecation warning, not a failing assertion.

## Governance
- Gate A remains HOLD.
- WORK13 remains 0/29.
- Synthetic CI is evidence of isolated testing, not external-live Gate A authorization.
- PR #2 must remain Draft and unmerged; main and formal Runtime unchanged.
- Live HTTPS MCP, OAuth, Joseph↔mou bilateral isolation evidence, independent audit records and an independent security review still required before Gate A disposition.
