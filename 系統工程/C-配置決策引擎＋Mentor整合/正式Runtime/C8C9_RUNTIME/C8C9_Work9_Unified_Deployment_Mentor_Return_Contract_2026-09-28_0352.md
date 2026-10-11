# C8C9 Work9｜Unified Deployment Output＋Mentor Return Contract

最後更新：2026/09/28 03:52（Asia/Taipei）

## 目的

Work9 只做 **integration normalization**：把已經由 Work4／5／6／7／8 鎖定的 V82、V75、Funding、SGOV、Protected Holding 來源事實，合併成一份 Canonical Deployment Result，再交給 Mentor 解釋。

**Work9 不重新計算任何投資邏輯。**

## Canonical Action

固定只使用：

`BUY / WAIT / HOLD / PAUSE / NO_ACTION / BLOCK / UNKNOWN / NEEDS_REVIEW`

每一筆仍保留 `source_action`／`source_decision`，所以正規化狀態永遠不能取代或遮蔽原始 V82／V75 決策。

## Owner／Run 邊界

一份 Work9 Result 對應 **同一 run、同一 canonical owner envelope**：

`funding_domain + broker + account + currency`

Work9 不做跨 account／broker／domain 的 portfolio funding aggregate，也不挪資金。

## Work9-owned fail-closed seam

除了 frozen schemas，Work9 重新綁定：

- Work4／5／6／7／8：同 baseline、同 run。
- Work4／5／6／7：同 owner、同 currency。
- Work4／5／6／7／8：同 Work3 handoff lineage。
- Work4 ↔ Work5：同 V70 snapshot、同 Shared Context ID、同 Shared Context SHA-256。
- Work8 Final Target allocation ID ↔ Work4 authorization reference。
- Work8 ↔ Work4 exact serialized digest＋canonical V82 digest。
- Work7 ↔ Work5／Work6 exact serialized digest。
- Work4 equity budget ↔ Work6 equity budget。
- Work5 bond budget ↔ Work6 bond budget。
- Work5 Ready snapshot.output ↔ canonical V75 output。
- Work5／Work7／V75 的 `V75_UNDEPLOYED_TO_SGOV` 一致。
- Work7 funding evidence ↔ Work6 cash evidence。

## V82 normalization

- 原始 `execution_action` 永久保留。
- `BUY → BUY`。
- `NO_NEW_BUY → NO_ACTION`。
- `BLOCKED_UNKNOWN → BLOCK`。
- 已是 Canonical Action vocabulary 者原樣通過。
- 未知／sell／reduce 等未在 Work9 明確擁有的字彙，**不猜意思**，回 `NEEDS_REVIEW`，raw action 仍保留。
- Protected holding 的 client-facing action 由 C Work6／7 → Work8 來源控制；Work9 只呈現 `HOLD` 的 canonical client-action 狀態，**不把 V82 risk action 改成 HOLD**。

## V75 normalization

- 每個 `per_asset_decision` 保留完整 raw source decision。
- BUY 家族只正規化成 `BUY`；PAUSE／WAIT／HOLD依原 source state正規化。
- `INVALID_INPUT → BLOCK`、`INSUFFICIENT_DATA → UNKNOWN`、review/reduction state → `NEEDS_REVIEW`。
- 若 V75 account-level Runtime 本身 BLOCK／UNKNOWN／REVIEW，或沒有 per-asset decision，額外輸出 `V75:__ACCOUNT_SCOPE__`，避免上游狀態被空陣列吞掉。

## Funding／SGOV

- 只承接 Work6 已隔離的 `AVAILABLE` equity/bond executable budgets。
- 不推導 `available = total - unsettled - reserved`。
- 不碰 unsettled／reserved。
- 不建第二套 Funding Engine，不 FX。
- `V75_UNDEPLOYED_TO_SGOV` 只做 disposition；Work9 不計算最終 SGOV dry-powder aggregate，也不建立 Family physical subledger。

## Mentor Return

Mentor 可以：

- 解釋 Canonical Result。
- 顯示 reason codes、data/rule lineage、資金來源與 undeployed disposition。

Mentor 不可以：

- 重算／改寫 V70、V82、V75、C、Funding、Protected Holding。
- 將 UNKNOWN 當 False／0／Neutral。
- 跨 account／broker／domain 挪錢。
- 把 risk warning 偷改成 client preference action。

## 禁止提前

不提前 Work10、Family F2、Production Cutover；不修改 shared governance。

真正 cross-line Contract／Schema Hard Fail：**STOP，回 ABC 小PM。**
