# Family PF — Evidence URL whitespace hardening checkpoint

Date: 2026-10-14 (Asia/Taipei)
Repository: a23882005/LivingWaterAI
Branch: family-pf-ci-20261012
PR #2: Draft / unmerged

## Completed
- pf_external_evidence_inventory.py now rejects Unicode whitespace in external evidence URLs, in addition to already rejected control characters, backslashes, non-public and placeholder hosts, credentials, queries and fragments.
- test_external_evidence_inventory.py adds one parametrized test covering ordinary space, NBSP and EM SPACE.
Code commit: 4cad990f2fa41c37d8ce96f6ae06fd19fd71dfab
Test commit: d8dd73b52b03a8da0df3d86ad45259adae5eac1b
Source blob: bc6572389315f3674ffb76bacb3077bc16b3389c
Test blob: f0e01b04c50767000202484416c32f82b43a3825

## Validation
Workflow: https://github.com/a23882005/LivingWaterAI/actions/runs/38456562585
Job: 115500707928, suite SUCCESS, demo SUCCESS.
Pytest: 289 passed, 1 warning, 0 failed in 6.79 seconds.
LOCAL DEMO PASS: synthetic authorized same-client read 200 and cross-client denial 403.

## Security release boundary
Gate A remains HOLD, WORK13 0/29.
PR #2 remains Draft and unmerged. Main and formal Runtime unchanged.
These checks prove local synthetic behavior, not real HTTPS MCP, external OAuth, true bilateral Joseph/mou isolation, independently retained audit witness or independent security signoff. No deployment or release authority follows from this checkpoint.
