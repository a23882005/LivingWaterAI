# Family PF — Evidence digest uniqueness hardening: CI pending

Date: 2026-10-14 Asia/Taipei
Repository: a23882005/LivingWaterAI
Branch: family-pf-ci-20261012. PR #2 remains Draft/unmerged.

## Source commits
abf25e838d8e0230e4ef0927b47a6b84db47651c — detect duplicate SHA-256 across categories and fail closed on invalid canonical paths.
c600e8a91268950ce9997de271bdbe379f278910 — add synthetic duplicate digest, NUL path and missing mapping tests.
c78a2bc09e2320ec7a970fe463fdec0bb395ba2f — preserve existing duplicate-path rejection precedence.

## QA status — do not infer PASS
First run https://github.com/a23882005/LivingWaterAI/actions/runs/38467627567 failed with 1 failed and 316 passed, 1 warning. Cause: duplicate-artifact-digest check ran before existing duplicate-artifact-path check and altered expected denial reason.
Follow-up fix commit c78a2bc09e2320ec7a970fe463fdec0bb395ba2f restored path-first ordering.
Retest run https://github.com/a23882005/LivingWaterAI/actions/runs/38467719022 reported IN_PROGRESS at last observation; verification log and Demo success have NOT yet been established.
Thus previous verified checkpoint remains 314 PASS until this retest completes successfully.

## Governance
Gate A stays HOLD; WORK13 stays 0/29.
No real Joseph/mou tenant evidence, independent OAuth proof or external audit signoff is supplied by this change. Branch remains isolated; no merge and no formal Runtime modification.
