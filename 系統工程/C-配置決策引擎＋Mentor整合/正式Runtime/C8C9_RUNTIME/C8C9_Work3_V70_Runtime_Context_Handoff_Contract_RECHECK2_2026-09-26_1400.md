# C8C9 Work3｜V70 Runtime Context Handoff Contract RECHECK2

- Input: `LivingWaterAI.C8C9.Work3.ContextHandoffInput / C8C9-W3-CHI-v1.0.1-RECHECK2`
- Output: `LivingWaterAI.C8C9.Work3.ContextHandoffResult / C8C9-W3-CHO-v1.0.1-RECHECK2`
- Frozen Baseline: `C8C9-BL-20260926T1014+0800-W1-5a1038869805a25e`
- Upstream Work2: `C8C9-W2-UIC-v1.0.1-RECHECK1`
- Scope: **VALIDATE + BIND + PRESERVE ONLY**
- Business logic: **unchanged upstream owners**

## RECHECK2 correction

RECHECK1 correctly locked run/owner/budget/gap/SGOV/authorization boundaries, but its Adapter trusted callers to have separately validated the full Work2 envelope. That left a Work3-owned fail-closed gap: malformed Work2 payloads such as negative executable amounts or missing `versions/lineage/reason_status` could bypass part of the Adapter guard or terminate as uncontrolled Python errors.

RECHECK2 fixes this without changing investment semantics:

1. Work2 envelope exact top-level schema boundary is enforced in the Adapter.
2. Monetary values remain exactly the Work2 rule: nonnegative JSON number or canonical Decimal string; no rounding/FX.
3. `versions`, `lineage`, `reason_status`, temporal shape, owner/currency, gap modes, settlement and SGOV boundary are structurally fail-closed.
4. Work3 Input Schema embeds the frozen Work2 top-level schema boundary.
5. Work3 Output Schema now strictly validates copied Work2 Final Target/Funding/Temporal/Version/Lineage/Reason/SGOV structures so downstream tampering is rejected.
6. V70 `snapshot_as_of` is required and `Work2.lineage.upstream_snapshot_ids.v70` must exactly match `v70_runtime_context.upstream_v70_snapshot_id`.
7. Shared Decision Context must have at least one exact `source_reference_id` join to Work2 lineage, while source-owned payload/data timestamps remain unmodified.
8. Non-JSON provenance payloads (for example NaN) fail closed rather than producing a nonportable digest.

## Invariants retained

- Same `run_id` across Work2, Client State, V70, shared decision context and both engine bindings.
- Shared `as_of` equals Work2 `temporal.as_of`.
- V82 and V75 reference one shared decision context id + SHA-256 digest.
- Owner key remains `funding_domain + broker + account`; no cross-owner funding.
- V82 points only to equity executable budget; V75 points only to bond executable budget.
- `remaining_target_gap.v82` and `.v75` remain independent engine namespaces.
- V82 `authorization_reference` remains the confirmed C7 Final Target `allocation_id`.
- `V70_ORIGINAL_DRY_POWDER` is context only, not V82 executable funding.
- `V82_UNDEPLOYED_TO_SGOV` remains absent/null; raw V82 equity budget cannot auto-route to SGOV.
- `data_as_of` source-owned nested/object/scalar content is deep-copied unchanged.

## Still forbidden

No FX, no rounding, no target/gap recomputation, no investment Threshold/Fallback, no second Funding Domain Engine, no V82/V75 patch, no Family F2, no Production Cutover, no Shared Governance write.

Work4 alone adapts this handoff to V82 Ready Runtime. Work5 alone adapts it to V75 Ready Runtime.
