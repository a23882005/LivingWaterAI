# V75 Work5 LivingWaterAI Integration Output Contract v1.0.0

1. Work5 is a final-classification and serialization/integration layer, not a new investment engine.
2. Work3 target/gap/eligibility and Work4 predicate/deployment results are authoritative inputs.
3. Per-asset decisions must exactly cover Work3 `per_asset_inputs` for formal output.
4. All decisions must remain in the same broker account and currency.
5. Total deployed amount cannot exceed same-account `bond_executable_budget`.
6. When `v75_undeployed_to_sgov` is present, deployed + undeployed must exactly reconcile to executable budget.
7. `SGOV_BOND_BUCKET` is preserved; `SGOV_DRY_POWDER_BUCKET` remains read-only upstream context and must not be emitted as a final V75 aggregate.
8. Formal output requires COMPLETE upstream state and no missing required fields.
9. Work5 must not change Root rules, PRED thresholds, P0-02, funding/settlement/account-isolation semantics, or Work1–Work4 canonical calculations.
10. Work6 cutover/runtime-ready is out of scope.
