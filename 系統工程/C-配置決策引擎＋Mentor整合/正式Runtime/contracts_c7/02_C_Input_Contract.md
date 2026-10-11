# C Canonical Input Contract｜v1.0.1（RECHECK修正版）

## 1. 定位
本 Contract 只固定 C 的輸入資料形狀、狀態、來源與可追溯性，不重算 V70／V82／V75，也不重建 B 資料。

## 2. Top-level Required Objects
1. `identity`：`run_id / client_id / portfolio_id / request_id`。
2. `decision_phase`：配置探索、提案審閱、Final Target 審閱／確認或部署準備。
3. `capital_context`：客戶總投資金額、Base Currency、必要 FX metadata。
4. `allocations`：Current／Proposed／Final Target 三個獨立 Slot。
5. `v70_asset_framework`：只承接 V70 已產生／已核准的大類資產框架與戰術額度。
6. `benchmark_reference`：B 正式 Excel＋四Sheet role/header fingerprint。
7. `source_references`：來源版本、Fingerprint＋Algorithm、As-of、DQ、Freshness。
8. `issues`＋`traceability`：所有問題與欄位 lineage。

## 3. Allocation 三層與Stage不可錯接
- `current_allocation` 若為KNOWN，Snapshot `stage` 必須=`CURRENT`。
- `proposed_allocation` 若為KNOWN，Snapshot `stage` 必須=`PROPOSED`。
- `final_target` 若為KNOWN，Snapshot `stage` 必須=`FINAL_TARGET`，且 `confirmation_status=CONFIRMED`、`confirmed_at/by`不可為null。
- Final Target未確認時保留 `NONE / UNKNOWN`，不得把 Proposed 自動升格。

Slot `value_state=KNOWN` 必須有Snapshot；`NONE / UNKNOWN / NOT_APPLICABLE` 時Snapshot必須為null。若只是Snapshot內部分欄位未知，Slot仍可KNOWN、未知狀態放在內部欄位，不用把整個Snapshot丟掉。

## 4. Value State完整性
- `MoneyValue=KNOWN` → `amount`必須是number且currency必須有效。
- `MoneyValue=NONE/UNKNOWN/NOT_APPLICABLE` → `amount=null`。
- `MetricValue=KNOWN` → `value`不可為null。
- `MetricValue=NONE/UNKNOWN/NOT_APPLICABLE` → `value=null`。
- Weight、V70權重／T、FX Rate使用 `NumericMetricValue`，KNOWN時必須為number。
- `UNKNOWN`不得帶一個看似可正式使用的數值，也不得轉成0／False／Neutral。

## 5. Money／Currency
所有 Money Value 帶 `amount + currency + value_state + as_of + data_quality + freshness`。Allocation Line 的組合金額固定叫 `portfolio_amount`；不同幣別不得裸數相加。FX實際換算與資料Gate留後續合法Work。

## 6. V70 Input Boundary
C只接收 V70 已形成的 Strategic／Tactical Framework，包括S0/B0、T、股票／債券／V70 Original Dry Powder權重與可得Amount，以及 `run_id / upstream_v70_snapshot_id / life_stage / snapshot_as_of / DQ / freshness / source`。Rule Owner仍是V70。

## 7. B Sheet1～4 Reference
固定引用：Sheet1 Performance/Risk Baseline、Sheet2 Source/Calculation/Proxy Rules、Sheet3 Exposure Taxonomy、Sheet4 Exposure Primitives。Input與Output使用同一個Canonical `BenchmarkReference`，不得在Output退化成只有sheet name。

## 8. Source Version／Fingerprint
每個`SourceReference`必須明示 `source_version` 與 `source_fingerprint_algorithm`。有fingerprint時algorithm不得UNKNOWN；沒有fingerprint時algorithm只能NOT_APPLICABLE／UNKNOWN。避免同一字串不知道究竟是SHA、revision還是其他fingerprint。

## 9. UNKNOWN與B Native Status
Canonical Field Value State只允許：`KNOWN / NONE / UNKNOWN / NOT_APPLICABLE`。B 的 `PENDING_DERIVATION / NOT_RECOVERED` 等native sentinel原樣保存於`source_native_status`，Work2才依B正式規則映射。
