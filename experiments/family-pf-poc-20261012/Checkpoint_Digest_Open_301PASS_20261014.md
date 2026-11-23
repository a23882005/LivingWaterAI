# Family PF — Opened evidence file safety checkpoint (301 PASS)

Date: 2026-10-14 Asia/Taipei
Repository: a23882005/LivingWaterAI
Branch: family-pf-ci-20261012
PR #2: Draft, unmerged

## Completed engineering
- pf_evidence_digest_verify.py: open evidence using explicit read-only flags; O_NOFOLLOW where supported; O_NONBLOCK where supported; inspect the opened descriptor using fstat for regular-file type and maximum 16 MiB size before hashing. Existing pre-open checks remain.
- test_evidence_digest_verify.py: three tests for zero-length file digest, directory rejection, and normal small file.
- Code commit: 46dd43155414ea342e9ca4bf5dfe5672bf7eac5d
- Test commit: 0699fdeb8d9fa3c6f655d1341d10488e49bf718c
- Source blob SHA: a10a70d1d7a1c370ee68fdbffe89f85f07936991
- Test blob SHA: 16504518c3f89cee1956236e6c037faaa3f40358

## Verified GitHub CI
Run: https://github.com/a23882005/LivingWaterAI/actions/runs/38461114320
Job 115516216998 completed SUCCESS.
Pytest 301 passed, 1 warning, 0 failed in 10.82s.
Demo LOCAL DEMO PASS: synthetic Project A read own=200 and read foreign=403.

## Known limits and remaining external Gate A evidence
The verifier does not perform trust attestation, authenticated live OAuth, independent evidence custody, or bilateral Joseph/mou tenant security checks. O_NOFOLLOW behavior is platform-dependent; do not claim that tests prove protection against every filesystem race. Its digest check is not Gate A acceptance.
Gate A stays HOLD. WORK13 0/29. PR #2 remains Draft and unmerged; main and formal Runtime untouched.
Independent external HTTPS MCP, OAuth, live bilateral isolation, persistent independently witnessed audit, and governance-approved reviewer signoff are outstanding.
