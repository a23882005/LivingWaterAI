# C8C9 Work6｜Funding＋Account Isolation Integration Contract

最後更新：2026/09/27 02:42（Asia/Taipei）

狀態：**✅ QA PASS／CLOSED**

## 核心責任
Work6 是 **跨層 Funding／Account Isolation 驗證器**，不是 Funding Engine。它只驗證 C7 → Work3 → Work4(V82) → Work5(V75) 在同一 run、同一 owner、同一 funding domain/account/broker 下保持一致。

## Canonical owner
`funding_domain + broker + account` 必須精確一致。

## Funding Hard Rules
- 正式三域只有：`TW_LOCAL_BROKER`、`TW_SUB_BROKERAGE`、`US_BROKER`。
- C7 必須正好三個 domain context，Funding Event total 必須等於三桶 bucket 總和。
- executable cash basis 只接受 **AVAILABLE**；不得自行推導 `available = total - unsettled - reserved`。
- Bank cash 仍為 `OUT_OF_SCOPE`。
- equity executable budget 只能送同 owner 的 V82；bond executable budget 只能送同 owner 的 V75。
- cross-account／cross-broker／cross-domain、unsettled／reserved misuse、duplicate account context、serialized scope tamper 全部 fail-closed。
- **不做 FX，不建立第二套 Funding Domain Engine。**

## Adapter binding
- Work4：`execution_account` 必須等於 canonical owner；C7 Funding Context 必須 exact pass-through；equity amount／pointer／owner／lineage 必須一致。
- Work5：Frozen V75 serialized domain＋account 必須與 canonical owner 一致；bond amount／pointer／owner／lineage 必須一致。

## Output
Work6 output 只是 validation evidence snapshot；不得重新計算配置、投資訊號、Funding 或 SGOV routing。
