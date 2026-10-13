# Family PF — Offline artifact digest read-back checkpoint

Date: 2026-10-14 Asia/Taipei
Branch: family-pf-ci-20261012
PR #2: Draft, unmerged

## Delivered
- pf_evidence_digest_verify.py recomputes local artifact SHA-256 and compares expected lower-case hash, bounded to 16 MiB, rejecting missing files and symlinks.
- test_evidence_digest_verify.py includes six independent synthetic test functions: matching content, modified content, invalid hashes, missing file, symlink, oversized file.
- .github/workflows/family-pf-ci.yml explicitly copies both files into isolated CI before pytest.
- Code commits: 283bd470071bfa7f4e8c5a0cb2da38c4787c0581, 7b89b56a2280f7394ccaeaf3afd55877e5b6c232, 0ba276b7ab6f987a8ee02a2febd5a5b827d2c9f6.

## Verified
https://github.com/a23882005/LivingWaterAI/actions/runs/38460643239
Job 115514606507 — completed SUCCESS.
Full pytest 298 passed, 1 warning, 0 failed in 10.24s.
LOCAL DEMO PASS: synthetic A->A read=200, A->B read=403.

## Important limitations and governance
Digest read-back verifies only whether bytes currently on disk match an expected digest. It does not establish independent custody, provenance, reviewer identity, real OAuth, or real tenant isolation. For live verification use governance-approved retained evidence, separate trusted keys, independent audit checks and bilateral approved live test identities.
Gate A remains HOLD; WORK13 remains 0/29.
PR #2 remains Draft/unmerged; no main or formal Runtime modification.
