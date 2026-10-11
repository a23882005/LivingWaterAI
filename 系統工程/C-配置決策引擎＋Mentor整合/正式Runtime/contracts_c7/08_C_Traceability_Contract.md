# C Traceability／Lineage Contract｜v1.0.1（RECHECK修正版）

## 核心 Identity
- `run_id`：跨系統同一輪共用。
- `c_snapshot_id`：C模組不可變快照ID。
- `parent_c_snapshot_id`：C快照lineage。
- 上游Module Snapshot ID保留原名，例如`upstream_v70_snapshot_id`。

## SourceReference
每個來源至少保存：
`source_id / source_kind / owner / source_reference / source_version / source_fingerprint / source_fingerprint_algorithm / as_of / retrieved_at / data_quality / freshness / issue_codes / source_native_status`。

Output也必須帶`source_references`，讓Output內的trace／issue source IDs可自行解析，不能假設消費者一定同時保留Input。

## TraceItem
每個正式重要欄位或衍生結果至少可追到：
`field_path / owner / rule_references[] / source_reference_ids[] / as_of / data_quality / issue_codes[]`。

## Cross-object Invariants
這些不是投資Business Rule，而是資料契約完整性：
1. `source_id`在單一Canonical Object內必須唯一。
2. 所有`source_reference_ids`必須能解析到同一Object的`source_references`。
3. 已存在的V70 `run_id`必須與C `identity.run_id`一致；不得另造競爭run identity。
4. Output的B reference不得弱化Input的File ID／Fingerprint／四Sheet role/header evidence。
5. Current／Proposed／Final Target不可互換stage。

## Rule Ownership
B＝Benchmark truth；V70＝Strategic/Macro framework；V82＝股票逐檔部署；V75＝債券逐檔部署；Mentor＝訪談／Orchestration／解釋；C＝Portfolio配置試算與整合契約。

## Snapshot Safety
Checkpoint／Reference／QA／Backup不得凌駕Drive正式SOT；每個Work真正依賴上游時Fresh Read最新正式來源。
