# Family PF digest read consistency checkpoint — 303 PASS

Date: 2026-10-14, Asia/Taipei
Repository: a23882005/LivingWaterAI
Branch: family-pf-ci-20261012; PR #2 is Draft and must remain unmerged.

## Code
- pf_evidence_digest_verify.py now compares the opened file's dev, inode, size, mtime_ns and ctime_ns before and after streaming SHA-256. Changes observed during reading produce HOLD with file_changed_during_read.
- Two added tests assert that digest comparison success and mismatch both preserve Gate A HOLD.
- Commits: 1a6d0bc7069a731d0e9d73446a55bfc45acbe5ea, d81e2a3599b05d7ced2410296d3356f78d7b827e.

## Verified GitHub Actions
Run https://github.com/a23882005/LivingWaterAI/actions/runs/38461530848
Job 115517643463 SUCCESS.
Pytest 303 passed, 1 warning, 0 failed in 9.79s.
LOCAL DEMO PASS: synthetic A own read=200; foreign read=403.

## Limitations / governance
Metadata consistency checks only detect certain in-flight changes; they cannot eliminate all filesystem races or establish independent provenance.
Gate A remains HOLD; WORK13 remains 0/29. Do not merge PR #2, modify main or formal Runtime, or claim live acceptance based on synthetic CI. Outstanding: approved live HTTPS MCP, real OAuth, independently observed bilateral Joseph-mou isolation, persistent audit verification and independent reviewer signoff.
