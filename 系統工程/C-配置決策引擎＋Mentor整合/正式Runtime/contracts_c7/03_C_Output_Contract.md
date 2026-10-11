# C Canonical Output Contract｜v1.0.1（RECHECK修正版）

## 1. 定位
Canonical Output 是 C 對 Mentor／Report／後續 V70/V82/V75 Integration 的單一結果外殼；Work1只定義形狀，不產生真正投資結果。

## 2. Identity
- `run_id`：跨系統同一輪共用。
- `c_snapshot_id`：C Immutable Module Snapshot ID。
- `parent_c_snapshot_id`：C快照lineage。
- `result_status`允許`NOT_RUN`，讓Contract fixture不必假裝成BLOCKED／FAILED的正式運算。

## 3. 必要輸出物件
- Current／Proposed／Final Target Allocation Slots（Stage與確認狀態受Schema約束）。
- `v70_asset_framework_reference`：run／snapshot／as-of／DQ／freshness／source refs。
- `benchmark_reference`：與Input相同的完整B Canonical Reference。
- `source_references`：Output自身必須能解析traceability中的source IDs，不能只靠外部Input物件。
- `performance_risk_result`：Work3才真正計算；Work1=`NOT_RUN`。
- `lookthrough_exposure_result`：Work4才真正計算；Work1=`NOT_RUN`。
- `deployment_integration_reference`：Work8才真正整合；Work1=`NOT_RUN`。
- `formal_output_eligibility / issues / traceability`。

## 4. Formal Output Eligibility一致性
- `eligible=FALSE` → `scope=NONE`。
- `eligible=TRUE` → `scope=FULL`或`PARTIAL`。
- `scope=FULL`不得仍列blocking reason。
Formal Output Gate只是資料／結果能否正式對外輸出，不等於市場Hard Gate。

## 5. NOT_RUN一致性
Module `status=NOT_RUN` 時 `payload`必須null，且其formal output必須FALSE／NONE；不得在「尚未執行」外殼偷塞假計算結果。

## 6. Work1 Fixture
Work1範例Output之根`result_status=NOT_RUN`；Performance／Exposure／Deployment均`NOT_RUN`，Formal Output＝FALSE/NONE。這是Schema fixture，不是客戶結果。
