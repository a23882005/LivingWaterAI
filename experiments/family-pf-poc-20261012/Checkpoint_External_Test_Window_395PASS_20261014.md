最後修改日期時間：2026/10/14 14:14（台灣時間）
# Family PF｜外部測試 UTC 時窗有效性 Checkpoint（395 PASS）

## 本棒已完成的工程
- 修改 pf_external_start_guard.py：外部測試 manifest 的 test_window_utc 必須是 UTC 的明確起迄，起始時間尚未過期，且長度不超過 24 小時。無效格式、非 UTC、倒序及過期均拒絕進入操作人員審查。
- 更新 test_pf_external_start_guard.py：正向合成窗口改用執行當下之相對時間，並加測過期／不正確時區／超長／倒序窗口。
- 此守門器僅執行靜態 manifest 前置審查，不進行任何外部 API、MCP 或 OAuth 呼叫；READY_FOR_AUTHORIZED_OPERATOR_REVIEW 不等於 Gate A 放行。
- 程式 commit：12e2459050bfdd11060cdecb504a9ba249a71e51
- 測試 commit：104eb4528c4fda3f1e1d89a3129961bf0f941e07

## 真實 GitHub QA 證據
- Actions run：https://github.com/a23882005/LivingWaterAI/actions/runs/38520974172
- 完整測試 Job 115710399303：SUCCESS，合成功能測試 389 passed, 1 warning in 12.40s。
- 額外安全契約測試 6 passed in 0.03s；合計兩批 395 PASS，不是單一 pytest 執行。
- 證據 SHA 與 commit 比對 Job 115710546282：SUCCESS。
- 本棒開始之前 latest checkpoint 已為 394 PASS（GitHub commit a78895d96bfd4c39eca6e6ffb4a712e160a53360）。

## Gate 與權限
- 主分支 main 與正式 Runtime 未修改；PR #2 持續 Draft、未合併。
- EA-01～EA-09 外部驗收仍待真實公網 HTTPS、外部 OAuth、雙向隔離、可信持久化 Audit 及獨立審查，故 Gate A HOLD；WORK13 0/29。
- 必須由獲授權操作人員依批准範圍操作外部測試，且獨立審查者另行簽核，不得以 395 PASS 的合成測試代替。
