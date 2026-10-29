# V82 Runtime — approved v1.0 additions and archived W12 baseline

2026/10/30: adopted component `V82_APPROVED_IMPLEMENTATION_1.0` adds own-history qP/qV, full Entry/stage selection, M/speed/Trend timing and persistent daily planning cycles. Family W5/W8 use the same native contract; canonical 49/13 fields remain unchanged. See [the current implementation guide](../../../Family/W8/V82_IMPLEMENTATION_GUIDE.md) for authority, input contracts, tests and limits.

`deployment.py` uses `V82_EXECUTION_DECIMAL_1.0.1` to keep high-precision caps below legal lot boundaries; existing MIN and investment thresholds remain unchanged. Component versions are separate from frozen package metadata 0.9.0. The W12 evidence below describes its archived baseline, not acceptance of these additions or Joseph/MOU readiness. Current additions await Family middle-PM independent acceptance: Production HOLD, NO_TRADE.

## Archived W12 E07 RECHECK4 baseline

Current engineering status of this package:

- W5 scaffold / canonical models: implemented.
- W6 Funding + Account Isolation validation: implemented.
- W7 core rule engine: implemented.
- W8 deployment / execution planning: implemented.
- W9 canonical output / persistence / ports: implemented.
- W10 Unit + State-transition + Invariant tests: implemented and passing.
- W11 Negative + Contract + Regression + Integration tests: implemented and passing.
- W12 Full E2E / Cutover rehearsal / Runtime Readiness evidence: **8/8 PASS**.
- Formal Test Matrix: **78/78 PASS**.
- Unresolved P0/P1: **0 / 0**.

## E07 authorized Legacy Shadow / Dual-run

ABC小PM supplied and authorized the exact Legacy Runtime baseline. E07 verifies those exact bytes and Legacy 34/34 health tests, then actually executes Legacy and the current Greenfield Runtime against the same frozen semantic facts through a schema-only compatibility adapter. All W4 shadow invariants are evidenced/classified, with no unresolved P0/P1.

The Legacy files remain isolated under `Latest_Working/E07_Evidence/legacy_baseline_readonly/`; they are evidence only and are **not** copied into the Greenfield Runtime source tree or used as implementation skeleton.

E08 rollback compatibility remains independently checked with a frozen W9 JSONL persistence-contract reader rather than the current repository class reading its own files.

## Current state

`READY_FOR_ABC_V82_RUNTIME_READY_GATE`

This is an A-line candidate handoff state only. Cutover activation remains `false`; this package does **not** self-declare the ABC Runtime Ready Gate, and C Work8 remains **not released** until ABC小PM performs the formal gate.

> Note: `pyproject.toml` description/version are frozen W0–W11 package metadata and are **not** the current readiness status indicator. Runtime readiness is governed by the W12 QA artifacts and handoff documents.
