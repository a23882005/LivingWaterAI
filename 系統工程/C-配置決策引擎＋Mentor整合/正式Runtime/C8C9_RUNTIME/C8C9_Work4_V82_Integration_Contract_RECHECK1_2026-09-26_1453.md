# C8C9 Work4｜V82 Integration Adapter Contract｜RECHECK1

- Status: **QA PASS / CLOSED**
- Rechecked: `2026-09-26T14:53:00+08:00`
- Frozen Baseline: `C8C9-BL-20260926T1014+0800-W1-5a1038869805a25e`
- Input: `C8C9-W4-V82AI-v1.0.0`
- Output: `C8C9-W4-V82AO-v1.0.0`
- Frozen V82 Input/Output: `V82-INPUT-v1.0.1-W2-RECHECK2` / `V82-OUTPUT-v1.0.1-W2-RECHECK2`
- V82 Rule: `V82-v1.21.0`

## Contract boundary

Work4 is a C8C9-owned adapter. It **does not patch or reinterpret V82 business logic**. It binds the exact Work3 owner/account context to Frozen V82 Runtime and returns V82 canonical semantics without a second business rule.

### Fail-closed runtime boundary

- The Adapter itself validates the packaged Work4 Input Schema. It does **not** trust the caller to have validated JSON Schema first.
- The integrated result is validated against the packaged Work4 Output Schema, which embeds the frozen V82 Runtime Output contract.
- Decimal transport is never silently rounded. A Decimal is converted to a JSON number only when value equality is preserved exactly; otherwise `C8C9.W4.PRECISION_LOSS` fails closed.

### Funding

- Only Work3 `/funding_context/executable_budget/equity` is executable for V82.
- `cash_basis` remains `AVAILABLE`; Work4 never derives AVAILABLE from total/unsettled/reserved.
- No FX, no cross-domain/broker/account subsidy, no bond-budget consumption, no bank cash, no reserved/unsettled cash, no SGOV access.
- Frozen V82 input requires the **complete original C7 FundingContext**. Work4 passes it unchanged and proves that the selected C7 owner cash/equity/bond facts exactly match Work3. Other C7 account contexts are neither synthesized nor made executable.

### Context / lineage

- Work4/V82/Work3/C7/V70 use the same `run_id`.
- execution domain/broker/account exactly equals Work3 owner.
- `authorization_reference` is the confirmed C7 `allocation_id`.
- V70 snapshot id is exact Work3 lineage; `V70_ORIGINAL_DRY_POWDER` remains context only.
- Shared Macro/Market/News uses the same Work3 `context_id` and exact SHA-256 digest. Source-owned nested/object/scalar `data_as_of` is preserved.

### Output

- Canonical V82 values are preserved.
- Frozen V82 in-memory 13-field Mapping may be serialized only into the frozen 13-entry wire-array representation; every row is checked against Canonical 49 projection equality.
- Diagnostics/reasons/no-action remain V82 semantics.
- `V82_UNDEPLOYED_TO_SGOV` may not be fabricated; unused equity budget is never auto-routed to SGOV.

## Out of scope

No V82/V75 patch, no C Work1-7 reopen, no Work5/Work6 execution, no Family F2, no Production Cutover, no ABC Shared Governance write.
