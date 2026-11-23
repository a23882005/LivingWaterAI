# Family PF — Evidence URL control-character safety checkpoint

Date: 2026-10-14 (Asia/Taipei)
Repository: a23882005/LivingWaterAI
Branch: family-pf-ci-20261012
PR #2: Draft / unmerged

## Changes verified
- pf_external_evidence_inventory.py: reject control characters (U+0000 to U+001F and U+007F) in external evidence reference URLs to avoid ambiguous URL parsing.
- test_external_evidence_inventory.py: cover newline, carriage return, tab and DEL in URL input; evidence remains HOLD.
Commits:
- eab9937a5169d2a74f40d1c4fe4603967ccd3bbc
- d6b094a0f5221ee332061d28e46287bedc2c0aab
Read-back source SHA 327dab1d79654b629dfc1d0f6db9106cb94fc059.
Read-back test SHA ed56d78acbcc5ea248cf0d5f5df5150721256fd2.

## Full GitHub verification
Run https://github.com/a23882005/LivingWaterAI/actions/runs/38455773003
Job ID 115497977000 concluded SUCCESS.
Pytest: 288 passed, 1 warning, 0 failed in 10.05 seconds.
Demo: LOCAL DEMO PASS; own-resource READ 200, cross-client READ 403 in synthetic fixture.

## Governance
Gate A remains HOLD, WORK13 0/29.
PR #2 remains Draft/unmerged; no main or formal Runtime changes.
Real external HTTPS MCP, OAuth login, independent Joseph-mou bidirectional tenant tests, independently retained audit trail, and approved security reviewer remain outstanding. Synthetic tests are not formal production security evidence.
