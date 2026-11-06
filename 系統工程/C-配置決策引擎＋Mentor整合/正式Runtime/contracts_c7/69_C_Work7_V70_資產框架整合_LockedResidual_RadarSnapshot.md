# C Work7｜V70_2／資產框架整合＋Locked Weight／Residual Allocation＋Radar Snapshot

最後修改日期：2026/09/24（台灣時間）  
文件狀態：Work7 RECHECK6 增量修正版 Staging Contract／待 ABC 小PM Gate #1 重新驗收  
程式版本：`C-W7-v1.2.0`

## 1. Work7 唯一責任

Work7 只負責把 Work6 已確認的 Final Target／Preference Lock／Drift／Radar、同一輪 V70 資產框架，以及上游已提供的 Funding Context 做**整合、隔離與 Contract Validation**。

正式邊界：

- **V70**：Strategic Risk Budget／S0-B0／Macro 計算 Rule Owner。
- **C Work7**：V70 Output Consumer／Adapter；Funding Context 也只做 validation／routing，不建立第二套 Funding Domain Engine。
- **Work6**：客戶確認後 Final Target、Protected Existing Holding、Drift、Radar 的正式上游 Contract。
- **Mentor／Client State／Database 上游**：提供 Funding Context、broker／account／domain 與各帳戶 executable budget。
- **Report Engine**：只顯示正式 Snapshot，不得自行重算 Final Target、Drift、Radar 或跨帳戶資金。
- **Work8**：本 Work 不執行；`work8_released=false`。

## 2. RECHECK5 全部保留

RECHECK6 不推翻 RECHECK5。以下既有修正全部保留：

1. 非 protected Drift 逐標的 Current／Final／Drift 數學反查。
2. protected lock current 反查真正 Current Allocation。
3. protected Final Target＝真正 Current、Drift＝0。
4. S0／B0／T 必須 KNOWN finite；S0+B0＝100%。
5. V70 `snapshot_as_of` 必須 ISO-8601 可解析。
6. NaN／Infinity fail-closed。
7. Same-run lineage、V70 stale／insufficient 路由、Portfolio 100% 數學。
8. Radar 四圖同六軸／同順序／完整中文標籤。

## 3. V70 → C Input Adapter

Work7 只消費 Canonical Input `v70_asset_framework` 已存在欄位，不重算 V70。S0／B0／T 與 tactical Stock／Bond／`V70_ORIGINAL_DRY_POWDER` 必須完整、finite、內部一致；V70 stale 固定 `RETURN_TO_V70`，data quality insufficient／unknown 固定 fail-closed。

## 4. Locked Weight → Residual Allocation

正式順序固定：

> **先鎖全部 protected existing holdings → 再計算各 V70 bucket residual → 只在同一 bucket 內依 Work6 已確認 Final Target 相對權重重建 residual。**

Work7 不得暗改客戶已確認 Final Target。若 same-run V70 bucket 與 Work6 Final Target bucket 不一致，固定 `RETURN_TO_V70`。

## 5. Portfolio Drift Snapshot

Work7 deep-copy Work6 `drift_snapshot`，但 Gate 必須逐標的獨立驗證：

- Drift universe＝Current ∪ Final。
- 每列 Current＝真正 Current Allocation。
- 每列 Final＝真正 Work6 Confirmed Final Target。
- `Drift = Final - Current`。
- protected flag 與 active Preference Lock 一致。
- protected=true → `HOLD_PROTECTED`、Drift=0。
- Report Engine 不得自行重算。

## 6. Radar Snapshot

四張 Radar 固定：`CURRENT_ATTACK`、`TARGET_ATTACK`、`CURRENT_DEFENSE`、`TARGET_DEFENSE`。

六軸固定同 ID、同 order、同繁中 label：

1. 牛市初期
2. 牛市中期
3. 牛市末期
4. 非衰退熊市／估值壓縮
5. 景氣衰退熊市
6. 金融／流動性危機

缺軸、換序、改 label 或四圖不一致＝fail-closed。

## 7. RECHECK6 新增｜Funding Context Contract

### 7.1 三個正式 Funding Domain

Funding Context 必須且只能各有一個：

- `TW_LOCAL_BROKER`
- `TW_SUB_BROKERAGE`
- `US_BROKER`

Global Portfolio 可以合併做分析；**Executable Budget 不得跨 broker／account/domain 互通**。

### 7.2 資金總額一致性

上游必須先把三個券商桶金額正規化為同一 `base_currency`。Work7 **不做 FX conversion**，只驗證：

`total_new_investment_amount = Σ 3 broker bucket_new_investment_amount`

不相等＝Funding Context Validation FAIL。

### 7.3 Bank Cash Out of Scope

`bank_cash_scope` 固定為 `OUT_OF_SCOPE`。銀行現金不得被 Work7 拿來補任何 executable budget。

### 7.4 Brokerage Cash State

每一 broker/account 至少保存：

- `total`
- `available`
- `unsettled`
- `reserved`

四者必須 finite、非負；只有 `available` 可作 executable budget 基礎。`unsettled`／`reserved`／bank cash 不得被當成可部署資金。

### 7.5 Account Isolation

每一 context 必須有明確且 KNOWN 的：

- `domain`
- `broker`
- `account`

同一 broker/account context 不得跨 funding domain 重複。缺 broker／account／domain、unknown context、duplicate context 一律 fail-closed。

### 7.6 Executable Budget Isolation

每一 account 自己保存：

- equity executable budget
- bond executable budget

每一 executable leg 必須：

- `cash_basis = AVAILABLE`
- `source_domain = 本 context domain`
- `source_broker = 本 context broker`
- `source_account = 本 context account`
- amount finite、非負
- equity+bond 不得超過本 account `available`
- equity+bond 不得超過本 account new-investment bucket

**禁止跨 broker、跨 account、跨 domain 借用資金。**

### 7.7 No Second Funding Domain Engine

Work7 的 boundary 固定：

`UPSTREAM_FUNDING_CONTEXT_VALIDATE_AND_ROUTE_ONLY_NO_SECOND_FUNDING_DOMAIN_ENGINE`

Work7 只驗證及往後傳上游已提供的 funding facts／budget；不得自行最佳化、搬移、補洞、找錢或建立第二套 Funding Domain Engine。

## 8. RECHECK6 Funding numeric hardening

Funding Context 的 total／bucket／cash state／executable budget 也全部適用 finite-number fail-closed：NaN／Infinity 不得通過 schema／semantic validation。

## 9. Work7 六項 ABC 小PM Gate #1 Hard Check

RECHECK6 正常 formal fixture 必須同時：

1. **Protected Existing Holding Contract＝PASS**
2. **Portfolio Drift Snapshot Contract＝PASS**
3. **Radar Axis Label／Order Contract＝PASS**
4. **Funding Context Schema／Validation＝PASS**
5. **Account Isolation＝PASS**
6. **No Cross-Account Funding／Executable Budget Isolation＝PASS**

任一 FAIL，不放行 A78／A79+。

## 10. STOP／治理

即使 Work7 輸出 `READY_FOR_PM_GATE`：

- `pm_gate.required=true`
- `pm_gate.a78_a79_released=false`
- `pm_gate.status=PENDING_ABC_PM_CONTRACT_SCHEMA_GATE`
- `pm_gate.work8_released=false`

RECHECK6 完成後必須 **STOP 回 ABC 小PM Gate #1**。六項 Gate 全 PASS 後才可能放行 A78／A79+；C Work8 仍須等待後續 ABC Runtime Readiness Gate 正式 RELEASE。
# Family 新 scope 附錄｜2026-10-30 中PM方案B

本附錄只適用 `FAMILY_LONG_TERM_TARGET_WITH_V70_CEILING_V1`。正式裁定為
`系統工程/Family/W8/契約/V82_C7_長期目標與當輪額度分離_中PM裁定_v1.0_20261030.md`，
SHA-256 `112b4ffad8d900971879f5502702bbf1252214edd709d22398a604ec070ed2e0`。
以下原當輪 scope、§4、bucket equality、`CONFIRMED_TARGET_WOULD_CHANGE` 及原 schema 均繼續有效。

新 scope 使用 input 83、Work6 result 84、Work7 result 85 與 `Family_LongTerm_V70Ceiling_v1.manifest.json`。
Family source 明訂 `Family.W5.Work6Source.v2`／`Family.W5.C7Source.v2`；沒有正式新 scope 及完整來源，不自動切換。
`work6.family_long_term_read.run_existing_long_term` 只接受 `REVIEW_ONLY/KEEP_PENDING`，
呼叫原 C Work5、protected／Drift／Radar 函式，讀取原核准者與時間，不呼叫確認函式，不新增歷史簽名事件。

原核准 `approved_long_term_target`、權重、投資池本金及 `Project Target` 金額原樣保留。
Work6 的 derived effective view 使用 Current NAV 供持倉權重、Preference Lock 與 Drift；其金額不能當作新的 Project Target。
兩種 base 的來源與角色放在 nested `family_scope_evidence`，`target_units` 從原核准投資池取得 V82 Gap 金額。
protected effective Final 等於真正 Current、Drift 為0；若因此無法維持100%或有治理衝突，阻擋而不做 residual 重配。

`work7.family_long_term.capacity` 沿工程63-B消費原V70總金額及同base總池cap：
`occupied = confirmed + effective remaining BUY + other commitments - confirmed releases`，
`room=max(ceiling-occupied,0)`，`capacity=min(room,settled authorized available funding)`。
來源含 owner／account／run／cutoff／原件hash與事件識別。未確認取消不釋放；同事件不重算；
net available cash不再扣reserved。未知Required cap/cash保留UNKNOWN，已知總額度耗盡可以證明新增0，未知原件仍保留。
新 scope 不要求長期 bucket 等於 V70 bucket，不縮放長期目標；單純 overage 只限制新增，不產生強制賣出。

Family `family_ceiling_bridge` 把 capacity 交給既有 MIN 與 CMR-ALLOC-01，保留原 gross V70 payload、G0/B0、
日切片、fees及lot。多account以各自原owner/bucket及唯一owner/asset unit進入同一原allocator，
不複製全戶capacity、不共用別帳戶cash。缺FX正規化原件時具名拒收，不以匯率預設值繼續。
serialized Work8 consumer 明確辨別新版本並重播 scope／capacity／snapshot digest；舊 frozen schema 不更動。

所有原 C7 hard checks 保留。成功最多 `READY_FOR_PM_GATE`；`pm_gate`、a78/a79、Work8 release仍為pending/false。
下游可產出僅供驗收的read-only分析，但 `formal_deployment_ready=false`，不下單、不買資料、不視為Production放行。
49個canonical分析欄與13個展示欄不增加；新證據只在版本化 sidecar。

驗收測試：`Family/W5/tests/test_c7_family_ceiling.py`、`test_family_ceiling_bridge.py`、
原 `test_c7_engine.py` 黃金檔、`test_target_units.py` 及既有 cycle／pending commitment 回歸。
合成QA與本人金融實跑分開。缺核准本金、Current NAV、帳戶來源、FX、訂單對帳或適用cap時，
列實際欄位與來源缺口，不以空ledger、0現金或模擬數字冒充本人資料。
