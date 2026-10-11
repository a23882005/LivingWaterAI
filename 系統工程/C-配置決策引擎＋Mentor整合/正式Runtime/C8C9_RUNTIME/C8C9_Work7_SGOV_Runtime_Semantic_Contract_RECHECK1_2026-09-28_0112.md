# C8C9 Work7｜SGOV Runtime Semantic Contract｜RECHECK1

最後更新：2026/09/28 01:12（Asia/Taipei）

版本：`C8C9-W7-SGOV-CONTRACT-v1.0.1-RECHECK1`  
狀態：**QA PASS／CLOSED**

## 1. 三個 SGOV 語意
- `SGOV_BOND_BUCKET`：V75 正式債券配置中的 SGOV。
- `SGOV_DRY_POWDER_BUCKET`：等待後續部署的 SGOV 邏輯角色；Work7只讀取目前角色，不建立最終聚合。
- `V75_UNDEPLOYED_TO_SGOV`：Frozen V75 本輪合法未部署 bond executable budget 的 output contribution；不是第三個可重複持有的資產桶。

## 2. 合法路由
`V75_UNDEPLOYED_TO_SGOV` 只能回到**同一 US_BROKER、同一 broker、同一 account、USD** 的 `SGOV_DRY_POWDER_BUCKET` 語意。

## 3. RECHECK1 新增 upstream binding fail-closed
Work4 V82 adapter 必須同時符合：
- serialized Runtime `run_id`＝本 run。
- serialized `execution_account`＝canonical owner。
- `work3_context_handoff_id`＝本次 Work3 handoff。
- serialized C7 Funding Context digest＝Work6 authoritative C7 digest。
- equity executable leg 的 owner／currency／`AVAILABLE` basis／source pointer 均須維持 canonical。

上述任一漂移一律 fail-closed；這只強化 Work7 integration validation，**不修改 V82／V75 或 Funding 經濟語意**。

## 4. 明確禁止
- V82 equity executable budget → SGOV：禁止。
- 一般 idle AVAILABLE USD → SGOV：禁止自動導入。
- reserved／unsettled → SGOV：禁止。
- Fabricated `V82_UNDEPLOYED_TO_SGOV`：禁止。
- Work7 自行計算 Dry Powder final aggregate：禁止。
- Work7 建立 Family physical SGOV sub-ledger：禁止。
- FX／第二套 Funding Engine／Patch V75／V82：禁止。

## 5. No-double-count
Work7只輸出「既有 BOND role」「既有 DRY role」「本輪 V75 contribution」三者及其 lineage；**不做 `existing dry + contribution` 聚合**，也不宣告實體 SGOV 持倉已 reconciliation。最終 physical ↔ logical role reconciliation 留給 Family downstream。
