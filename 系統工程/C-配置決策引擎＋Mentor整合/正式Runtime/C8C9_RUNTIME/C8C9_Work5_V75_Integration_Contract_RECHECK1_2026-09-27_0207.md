# C8C9 Work5｜V75 Integration Adapter Contract｜RECHECK1

最後更新：2026/09/27 02:07（Asia/Taipei）

狀態：**RECHECK1 QA PASS／CLOSED**  
Frozen Baseline：`C8C9-BL-20260926T1014+0800-W1-5a1038869805a25e`

## Contract versions
- Input：`C8C9-W5-V75AI-v1.0.1-RECHECK1`
- Source Context：`C8C9-W5-V75SC-v1.0.1-RECHECK1`
- Output：`C8C9-W5-V75AO-v1.0.1-RECHECK1`

## 核心契約
- 只消費 owner account 的 `/funding_context/executable_budget/bond`；`cash_basis=AVAILABLE`。
- **正 bond executable budget 只有 `SETTLED` 可進入 V75**；`UNSETTLED／PARTIAL／UNKNOWN` 全部 fail-closed。
- 不做 FX；不碰 equity／bank cash／reserved／unsettled。
- Work3 run／owner／V70 snapshot／shared context id＋digest 必須完全一致。
- V75 `market_snapshot` 必須來自同一 Work3 shared decision context：payload fragment、as-of 與 source lineage 必須可證明同源。
- V75 source-owned 欄位必須顯式提供；Adapter 不猜值。
- Work3/shared/source provenance tokens 必須穿過 Frozen V75，並在 canonical V75 output＋Work6 Ready snapshot 回收時重新驗證。
- 四層 Schema 在 Adapter 內部自行 fail-closed 驗證；Decimal 依 Frozen schema 用精確 decimal string 保護。

## SGOV
`SGOV_BOND_BUCKET` 保留；`SGOV_DRY_POWDER_BUCKET` 只讀；`V75_UNDEPLOYED_TO_SGOV` 只能消費 Frozen V75 自己的合法輸出。Work5 不創造金額／路由。

## 禁止
不得 Patch V75／V82、不得重開 C Work1～7、不得建立第二套 Funding Engine、不得做 FX、不得提前 Work6 實作／Family F2／Production Cutover。
