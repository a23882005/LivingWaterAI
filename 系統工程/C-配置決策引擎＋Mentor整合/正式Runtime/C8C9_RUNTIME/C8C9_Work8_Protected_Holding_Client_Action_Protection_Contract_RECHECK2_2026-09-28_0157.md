# C8C9 Work8｜Protected Holding＋Client-action Protection Contract｜RECHECK2

最後更新：2026/09/28 01:57（Asia/Taipei）

## 狀態

Work8-owned contract hardening。**不修改 V75／V82／C Work1～7／Frozen Baseline／Funding 經濟語意。**

## 核心語意

1. Protected holding 仍由既有 C Work6／Work7 Contract 管理：`Final Target = Current`、`Drift = 0`、`client_facing_action = HOLD_PROTECTED`。
2. V82 原始 fundamental／valuation／technical／macro／Hard-Gate-related evidence 與 `execution_action` 必須完整保留，不得因 protected 狀態改寫成 HOLD。
3. Risk disclosure 與 client preference mutation 是兩條平行來源事實；Work8 不把 V82 risk action 重分類成 allocation action。

## RECHECK2 新增 fail-closed binding

- C Work7 serialized payload 必須通過 frozen `C-W7-v1.2.0` exact schema。
- `parent_work6_snapshot_id == snapshot_lineage.work6_snapshot_id`。
- `identity.request_id == snapshot_lineage.canonical_request_id`。
- `work6_final_target_reference.allocation_id / confirmed_at / confirmed_by` 必須存在且非空。
- Work4 `authorization_reference == C7 work6_final_target_reference.allocation_id`。
- V82 canonical `project_target_position == C7 integrated_asset_framework.instrument_targets[asset].integrated_weight`。
- 任一同 run serialized substitution／lineage drift 一律 fail-closed。

## 禁止

不 Patch V82／V75；不重算 Final Target／Drift／V82 signal；不建立第二套 Funding Engine；不提前 Work9／Work10／Family F2／Production Cutover；不修改 shared governance。

真正 cross-line Contract／Schema Hard Fail：**STOP，回 ABC 小PM。**
