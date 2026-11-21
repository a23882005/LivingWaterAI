# FAMILY-MENTOR-SCOPE-CONSUMER：producer 介面 v1.0

依中PM `524e076` 與本輪PR59工單，交付既有producer語意、版本化欄位、最小樣本及回歸。接收端整合由中PM協調原PR60施工線，完整金融Gate及報告SOURCE_REVIEW分段各自保留。

續讀main `4163870` 的 [中PM正式交接工單](Family_金融報告交接與Mentor接收相容_中PM工單_v1.0_20261031.md)。本次 `mentor_scope` 是producer附加的版本化追溯欄位，不加嚴該工單的consumer條件。既有d250d3c的True輸出尚無此欄、舊False輸出也無此欄；兩者沿中PM正式相容規則，接收端不可將本附加欄位改列所有歷史輸出的必填條件。新金融提交仍待中PM另外鎖定版本與來源digest。

`mentor_bridge.explain_native` 先驗可信context的 `ANALYZE_ONLY`／`NONE`、本人/run/owner/currency、結果digest，並重播原Work9。`explain_holdings_recommendations` 同樣驗原context及原持倉Work9輸出。版本化scope只在這些原檢查之後附加；它不產生金融金額、不改canonical、風險或偏好、不解除來源與發布守門。

| 欄位 | 正式producer值 | 語意 |
|---|---|---|
| `mentor_scope.schema_version` | `Family.W5.MentorAdviceScope.v1` | 本次producer端版本化scope；JSON Schema為W5/mentor_advice_scope.schema.json |
| `execution_advice_allowed` | `true` | 可呈現原引擎已產出的建議動作、金額或比例；未知值原樣保留。此欄沿用既有名稱 |
| `recommendations_allowed` | `true` | 可解釋上述有來源建議，包括已知0、保護後HOLD或資料不足的限制 |
| `broker_execution_allowed` | `false` | 不可向券商提交、取消或更換指令，不授予換匯或資產執行權限 |
| `mentor_scope.financial_mutation_allowed` | `false` | 不可由Mentor或模型改原決策數值、資金、帳本或授權 |
| `mentor_scope.trade_authorization` | `NONE` | 本scope不代表本人交易授權 |
| `production`／`trade_action` | `HOLD`／`NO_TRADE` | 保留原發布與交易狀態 |

兩個producer保留舊頂層建議／券商欄位，並附相同的 `mentor_scope`。持倉部分輸出也明列 `recommendations_allowed`、`production`。嚴格型別與一致性驗證由 `mentor_scope.validate_advice_scope` 提供；`true/false` 不接受整數、字串或null，缺契約、頂層/版本化欄位矛盾或逐項券商提交權限為true均拒收。

## 最小欄位樣本

```json
{
  "execution_advice_allowed": true,
  "recommendations_allowed": true,
  "broker_execution_allowed": false,
  "production": "HOLD",
  "trade_action": "NO_TRADE",
  "mentor_scope": {
    "schema_version": "Family.W5.MentorAdviceScope.v1",
    "recommendations_allowed": true,
    "execution_advice_allowed": true,
    "broker_execution_allowed": false,
    "financial_mutation_allowed": false,
    "trade_authorization": "NONE",
    "production": "HOLD",
    "trade_action": "NO_TRADE"
  }
}
```

此樣本僅展示scope；不是可單獨使用的完整金融結果。私人成果包另附由原公開合成Work9 fixture實際產生的完整輸出、正金額/已知0/未知三類最小投影、request/context與原canonical digest，明標SYNTHETIC，不冒稱本人金融PASS。

## PR60整合現況及consumer回歸要求

PR60 `4319556` 的 `report_receiver.receive_action` 對成功Mentor硬性要求 `execution_advice_allowed is False`，與本producer正式值true衝突，現行跨分支組合仍回 `MENTOR_EXECUTION_SCOPE`。本輪保留並交付此可重現案例，沒有將producer改false來壓掉原合法建議，也沒有改報告接收端。

中PM協調consumer時，對明示本版本化scope的新輸出可使用validator核對建議權限true、券商/金融改寫權限false、NONE/HOLD/NO_TRADE；其餘歷史輸出依中PM既有True/False相容路徑。既有client/run/owner、canonical digest、data/rule lineage、來源與原Gate保留。需覆蓋正金額、已知0、未知、HOLD_PROTECTED與原risk_signal不變；新True路徑缺broker旗標、矛盾scope、非bool、跨本人/run、改值重簽或任何執行權限均拒收。失敗result仍不可攜帶canonical或Mentor，SOURCE_REVIEW不升格金融PASS。

本文件是producer介面回交；consumer分支合入、正式金融正向來源、真人Project登入與全案Gate均另待原證據驗收。
