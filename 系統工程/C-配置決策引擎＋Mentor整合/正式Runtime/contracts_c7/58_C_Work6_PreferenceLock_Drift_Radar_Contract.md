# C Work6｜Mentor Adjustment Loop＋Preference Lock＋Final Target＋Drift／Radar Contract

版本：C-W6-v1.0.0  
狀態：Work6 Staging Contract／不修改正式 Mentor SOT  
日期：2026-09-24（台灣時間）

## 1. Work6 唯一責任

Work6 只負責「客戶調整 → C 內重算或回 V70 → 顯示 → 再調整 → 客戶明確確認 Final Target」的迴圈，並產生 Mentor／Report Engine 可直接消費、不得自行重算的正式結果 Contract。

本 Work 不實作 V70 規則、不做 V82／V75 Deployment、不做 Report Engine 繪圖、不修改正式 Mentor／B／V70／V82／V75 SOT。

## 2. Adjustment Loop

正式輸入：`56_C_Work6_Adjustment_Request.schema.json`  
正式輸出：`57_C_Work6_Mentor_Adjustment_Result.schema.json`

每輪保留：
- Draft Allocation
- Previous Proposal
- Current Proposal
- Adjustment History
- 客戶確認狀態
- Final Target
- Work6 Snapshot lineage
- C_ONLY／RETURN_TO_V70／BLOCKED 路由

下列大類變更不得在 C Work6 自建第二套規則，必須 `RETURN_TO_V70`：
- `ASSET_CLASS_FRAMEWORK_CHANGE`
- `FUNDING_HORIZON_CHANGE`
- `WITHDRAWAL_REQUIREMENT_CHANGE`
- `LIFE_STAGE_OR_RISK_CAPACITY_CHANGE`

## 3. 既有個股 Preference Lock

只適用於「Current Allocation 中已存在的個別公司股票」，不適用 ETF／基金。

硬規則：

`protected=true → Final Target = Current → Drift = 0`

- 即使 reference allocation 對該個股是 0%，也不得把 protected target 改成 0。
- optimization／drift correction 不得把 protected holding 轉成 sell／reduce-to-zero。
- 估值、基本面、集中度、波動、重大風險仍可揭露。
- 「風險警示／不建議再加碼」與「要求賣出」必須分離。
- 只有客戶明確、可追溯的 `UNLOCK` 才解除保護。
- LOCK／UNLOCK 均要求：`client_explicit_decision=TRUE`、合法 `confirmed_at`、可解析 `source_reference_ids`。
- 多檔 protected holdings 先鎖住 Current 權重，再以 residual allocation 分配同一 V70 bucket 內剩餘比例。
- 若 protected Current 權重已超過 V70 已凍結的大類資產 bucket，Work6 不偷改 V70 框架，改回 `RETURN_TO_V70`。

## 4. Final Target

Final Target 只能從「已套用 Preference Lock＋residual math 後」的 Current Proposal 建立。

只有客戶明確確認且證據完整時才可：
- `stage=FINAL_TARGET`
- `confirmation_status=CONFIRMED`
- 產生正式 Final Target ID

未確認時：
- Final Target=`NONE`
- Drift Snapshot=`NONE`
- 不得用 Proposed 冒充 Final Target。

## 5. Drift Snapshot Contract

Final Target 確認後，每個正式標的逐檔輸出：
- Current
- Final Target
- Drift = Final Target - Current
- protected flag
- client-facing action

硬規則：
- Universe = Current ∪ Final Target；不得合併成「其他」。
- Protected 個股必須 `Current = Final Target` 且 `Drift = 0`。
- 三者使用相同 Final Target denominator object。
- Report Engine 只能渲染此 Snapshot：`renderer_must_not_recompute_final_target=true`。
- UNKNOWN 不得轉為 0／False／Neutral。

## 6. Radar Display Contract

四張 Radar 固定：
1. `CURRENT_ATTACK`
2. `TARGET_ATTACK`
3. `CURRENT_DEFENSE`
4. `TARGET_DEFENSE`

六軸固定 id／中文標籤／順序：
1. `BULL_EARLY`｜牛市初期
2. `BULL_MID`｜牛市中期
3. `BULL_LATE`｜牛市末期
4. `BEAR_NON_RECESSION_VALUATION`｜非衰退熊市／估值壓縮
5. `BEAR_RECESSION`｜景氣衰退熊市
6. `FINANCIAL_LIQUIDITY_CRISIS`｜金融／流動性危機

四圖必須同軸、同順序；六個中文標籤必須直接顯示且可讀。缺失／遮蔽／不可讀／順序不一致，Report QA 必須 FAIL。

Radar 缺值與 UNKNOWN 保留為 `UNKNOWN + null`，不得補 0。相同 view 或相同 axis 的重複輸入視為 ambiguity，Work6 fail-closed，不採最後一筆覆蓋。

## 7. Source／UNKNOWN 防呆

- Work6 request 裡所有 `source_reference_ids`（包含 weight override、Preference Lock、Confirmation、Radar）都必須解析到 Canonical Input 或本輪新增 SourceReference。
- UNKNOWN／NONE／NOT_APPLICABLE 不得在權重調整中偷轉成 0。
- 同一 request 對同一 instrument 的重複 weight override／Preference decision 視為歧義，BLOCKED。
- Work6 不以 ETF benchmark 代理未受 B SOT 支援的個別股票；Work5 若因個股缺 benchmark 而 BLOCKED／PARTIAL，須原樣透明保留，且不因此取消客戶 Preference Lock。

## 8. Work7 必須承接

Work7 必須直接承接：
- locked weights
- Final Target／Drift Snapshot
- Radar Snapshot
- Snapshot lineage
- RETURN_TO_V70 路由語意

且 Work7 QA 必須新增三項 Hard Check：
1. Protected Holding Hard Check
2. Drift Contract Hard Check
3. Radar Axis／Label／Order Hard Check

Work7 QA PASS 後強制 STOP，交回 ABC 小PM；Work8 不得提前施工。
