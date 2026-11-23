最後修改日期時間：2026/10/14 18:34（台灣時間）
# Family PF｜TCP 身分交替隔離＋外部驗收操作手冊 Checkpoint（440 PASS）

## 本次一次整批交付
- 新增三項 Uvicorn TCP 127.0.0.1 合成身分端到端測試：未攜帶授權 token 時兩個租戶資源均不洩漏；active tenant 正確但 resource ID 錯配必須拒絕；交替兩個身分的 ALLOW/ALLOW/DENY/DENY 順序隔離。
- 施工 commit：34db83242a02c36100d04ea45b958937b7f7c2de。
- 新增 Gate_A_External_Test_Operator_Runbook_v1.md，將外部授權、Endpoint、IdP OAuth、雙向隔離、外部 Audit 保管與獨立審查／Gate 核准工作排序，標明仍待實際資源與權限。
- 操作手冊 commit：4999da50c6a3f652da545416aebd213b81b3b71b。

## 真實 CI 結果
- GitHub Actions：https://github.com/a23882005/LivingWaterAI/actions/runs/38548572361
- 第一 Job 115800645534 SUCCESS：434 passed, 1 warning in 12.29s（合成套件），另 6 passed in 0.02s（工作流程安全契約）；兩批合計 440 PASS。
- 第二 Job 115800905479 SUCCESS，回讀 receipt SHA、GitHub Commit 綁定、Gate A 九項證據仍未驗證狀態。
- 本次功能測試屬真實 loopback TCP，但不等於公網 HTTPS OAuth 外部驗收。

## 不得誤宣告
- PR #2 Draft 未合併；main/Production Runtime 保持不變。
- 外部 EA-01～EA-09 尚未獨立查核；Gate A HOLD；WORK13 0／29。
- GitHub Runner 沒有被當成正式對外長期服務，沒有產生可被誤當真實 OAuth、持久化 Audit 或獨立 Reviewer 的外部證據。
