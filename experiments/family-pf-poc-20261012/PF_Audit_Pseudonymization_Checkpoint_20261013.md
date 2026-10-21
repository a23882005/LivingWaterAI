# Family PF — Audit Pseudonymization Checkpoint
Date: 2026-10-13 (Asia/Taipei)
Scope: isolated experimental Family PF branch.

## Work completed
- `pf_audit_store.py`: new `pseudonymize(verified_subject)` deriving a deterministic keyed HMAC-SHA256 subject pseudonym with domain separation; invalid or absent subject rejected.
- `test_audit_store.py`: two new tests verify same identity maps consistently, different identities/keys separate, original raw identifier does not appear, and invalid subjects are rejected.
- Commits: `cb0687501037c438a12ac5f8e8ebe5863d92066f`, `91909a17f6a1d04ec9cad1bf0214a92c4def886d`.
- CI: [Run 38322028922](https://github.com/a23882005/LivingWaterAI/actions/runs/38322028922); test and demo steps passed during checkpoint creation. Verify final job conclusion separately.

## Current boundary and next steps
- New pseudonym method is a tested AuditStore primitive, **not yet connected** to MCP resource-read event actor_ref; resource-read still records a constant synthetic_subject. Attempted MCP wiring write was blocked by tool safety check.
- Need separately review use of dedicated HMAC key (production should separate pseudonym key from chain integrity key), request correlation, rotation and unlinkability.
- Gate A HOLD and WORK13 0/29 until actual public HTTPS/OAuth, external two-client cross-denial, durable external audit and signed independent review evidence.
- PR #2 Draft, no production runtime or customer data touched, additional hosting cost NT$0.
- Governance registration: supervising PM to fresh-read Google Drive root 《檔案管理.md》 before its required backup and formal registration; no Drive mutation in this branch.
