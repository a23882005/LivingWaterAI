# Family PF — External evidence URL hardening checkpoint

Date: 2026-10-14 (Asia/Taipei)
Repository: a23882005/LivingWaterAI
Branch: family-pf-ci-20261012
PR #2: Draft and unmerged

## Changes
- Evidence inventory URL lint rejects backslash characters in evidence URL paths, avoiding ambiguous URL parsing.
- New synthetic test verifies malformed separator is rejected and the inventory remains HOLD.
Code commit: 89b8f1030595bcc577fad003ef1642025cbe229a
Test commit: de2b370d5315828733edf827e6e026dd9fa31c4a

## CI
Run: https://github.com/a23882005/LivingWaterAI/actions/runs/38453617886
Job: 115490550814 — completed SUCCESS.
Pytest: 287 passed, 1 warning, 0 failed in 9.96 seconds.
Demo: LOCAL DEMO PASS — synthetic authorized A->A read 200; unauthorized A->B read 403.

## Governance
Gate A remains HOLD; WORK13 remains 0/29.
PR #2 stays Draft, unmerged, main and formal Runtime unchanged.
External HTTPS MCP, actual OAuth, independently observed Joseph/mou bidirectional denial checks, independent audit log and reviewer signoff remain outstanding.
This is synthetic evidence-inventory validation, not a live security acceptance.
