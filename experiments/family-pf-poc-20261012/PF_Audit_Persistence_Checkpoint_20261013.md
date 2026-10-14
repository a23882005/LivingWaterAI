# Family PF Audit Persistence — 中PM Checkpoint
日期：2026-10-13（Asia/Taipei）
範圍：GitHub isolated experimental branch `family-pf-ci-20261012`

## Completed
- Added `pf_audit_store.py`: opt-in standalone SQLite persistent audit component with restricted field schema and HMAC-SHA256 record chaining.
- Added `test_audit_store.py`: six synthetic tests including restart persistence, two-direction synthetic denials, mutation detection, deletion gap detection, unexpected sensitive fields rejection and wrong-key detection.
- Updated `.github/workflows/family-pf-ci.yml` to copy and exercise new extension without changing production runtime.
- Commits: `4243af363fb40f45e1fe89ad4aee72262d0102aa`, `7b21d7eda3c6c494836ef2aa129e7b8bf80694f1`, `7133e91da6bec539b80603482e6a3c05255280d8`.
- GitHub Actions Run [38291274381](https://github.com/a23882005/LivingWaterAI/actions/runs/38291274381): job `verify-pf-full-158` completed success; full test step and demo completed success. The job name retains the historical 158 label even after six test additions: expected 164 tests, confirm exact pytest count from raw test log before recording an official 164/164 figure.

## Security boundaries / remaining evidence
- The persistent audit component is standalone and **not yet wired to request-path authorization**. SQLite/HMAC detects some alterations but does not prove immutable log retention; an administrator with signing key/database control can forge or truncate a log. External append-only retention and per-request binding are required.
- No publicly reachable approved HTTPS MCP test endpoint or external OAuth identity provider credentials supplied.
- No real OAuth login, no remote Joseph↔mou synthetic-resource denial E2E or durable audit event through HTTP request has been demonstrated.
- No independently authorized reviewer pin/signature.
- **Gate A = HOLD; WORK13 = 0/29; PR #2 stays Draft; main and production Runtime untouched; additional hosting spend = NT$0.**

## Governance registration to request of ABC supervising PM
- Record this branch checkpoint in 《ABC大工程.md》 and 《檔案管理.md》 after required root-document read/backup.
- Preserve CI evidence and clarify that component tests are not remote Gate A evidence.
