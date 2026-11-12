# Family PF Gate A / HTTPS metadata regression checkpoint — 244 PASS

Date: 2026-10-14 (Asia/Taipei)
Repository: a23882005/LivingWaterAI
Isolated branch: family-pf-ci-20261012
PR #2: Draft, unmerged

## Changes
Added 11 parameterized and standalone test cases to three files:
- test_remote_preflight.py: reject query, fragment, embedded identity, nonstandard port, private IP, array metadata, non-string issuer (7).
- test_gate_a_checklist.py: null/zero/invalid evidence values and empty checklist (2).
- test_gate_a_attestation.py: signed evidence URL with query, stale signed record (2).
Commit sequence:
- 6a61afd2724bf904177f53f7dc49c85981e594cf
- 991fc72c31680d7342dfe87762e2294424ae7695
- ab83378540da369a8662e45613acd55d46c53a4d
Read-back file blob SHAs:
- test_remote_preflight.py: 5221fecd17e0ede4caab115f94ee57c3f1fa7a24
- test_gate_a_checklist.py: 8e283e9d3e545e824bf1dfc205024f5474dc7e68
- test_gate_a_attestation.py: 4e865420a2b1cffb42147206b70fd7b9c395c56f

## Full CI and Demo
Run: https://github.com/a23882005/LivingWaterAI/actions/runs/38443809226
Job ID 115456866902: completed SUCCESS.
Pytest: 244 passed, 1 warning, 0 failed in 10.22 seconds.
Demo: LOCAL DEMO PASS; A reading A=200, A reading B=403.
Non-failing dependency deprecation warning remains.

## Mandatory governance
Gate A remains HOLD, WORK13 remains 0/29.
CI assertions and synthetic tests are not a live external security acceptance.
Remaining independent real-world evidence: approved public HTTPS MCP endpoint, real OAuth execution, Joseph↔mou bilateral cross-client negative checks, independent persistent Audit Log and independent Gate A security review.
Main and Runtime unchanged; PR #2 stays Draft.
