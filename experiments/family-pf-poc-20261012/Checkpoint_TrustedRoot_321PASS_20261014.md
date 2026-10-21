# Family PF — Trusted Evidence Root Checkpoint (321 PASS)

Date: 2026-10-14 (Asia/Taipei)
Repository: a23882005/LivingWaterAI
Branch: family-pf-ci-20261012
PR #2: Draft/unmerged

## Closed prior CI
Previous retest https://github.com/a23882005/LivingWaterAI/actions/runs/38467719022 succeeded.
317 passed, 1 warning, 0 failed and LOCAL DEMO PASS, synthetic A-own 200 and A-cross-client 403.

## Delivered this iteration
pf_evidence_package_verify.py now accepts an optional trusted_root. When supplied it must resolve to a real existing directory, and every evidence artifact canonical path must be within that approved root. Invalid root, outside path, and symlink escapes stay HOLD; API without trusted_root remains backwards compatible.
Added four tests: allowed in-root package, outside-root denial, nonexistent root denial, symlink escape denial.
Code commit 88fe74207824bdef92a177355dceef746a67b741
Tests commit 375d78c49543fc9e0f2d6d94c2ee718f3fa6f995

## GitHub CI validation
Run: https://github.com/a23882005/LivingWaterAI/actions/runs/38468280374
Job 115540506328: SUCCESS.
Full suite 321 passed, 1 warning, 0 failed in 10.61 seconds.
LOCAL DEMO PASS: synthetic Project A authorized own READ=200, cross-client attempt=403.

## Governance and limitations
Gate A remains HOLD, WORK13 remains 0/29, PR #2 Draft/unmerged.
Main and formal Runtime unchanged. No real Joseph/mou data used.
Path containment is an offline preflight property. It is not independently witnessed provenance or secure custody by itself; trusted_root is optional for existing callers and should be required by a controlled production evidence review pipeline.
Outstanding external Gate A: real approved public HTTPS MCP, real OAuth, independent bilateral Joseph-mou isolation tests, persistent independent audit verification, and security reviewer signoff.
