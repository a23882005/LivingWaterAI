最後修改日期時間：2026/10/14 21:38（台灣時間）
# Family PF｜CI 最小權限與禁止部署 Checkpoint（439 PASS）

## 實作與原始碼
- GitHub：a23882005/LivingWaterAI；隔離分支：family-pf-ci-20261012；PR #2 為 Draft，未合併 main。
- 修改檔：experiments/family-pf-poc-20261012/test_workflow_security_contract.py。
- 新增兩項離線安全契約測試：禁止 contents:write / id-token:write / pull-requests:write；禁止一系列部署 actions 與 production environment 指定。
- 程式 Commit：ca8cc750312befeaa51fd30d3bf696dc82fc39bb。
- 這些是針對當前 workflow 文字契約的回歸測試，不代表平台權限不可被其他流程修改，也非外部正式安全測試。

## CI 真實證據
- Actions：https://github.com/a23882005/LivingWaterAI/actions/runs/38573284886
- verify-pf-full-suite Job 115883747221：SUCCESS；完整合成套件 439 passed、1 warning、13.95 秒。
- 相同 Job 中的獨立 workflow security contract：8 passed、0 failed（先前為 6 tests）。
- verify-evidence-receipt Job 115884005078：SUCCESS。
- 不將契約測試 8 項重複計入完整合成套件 439 項；新增 2 項契約測試。

## 安全治理
- Gate A HOLD；EA-01 至 EA-09 的外部真實驗收未完成；WORK13 0/29。
- 不部署正式環境、不使用客戶個資或真實憑證、不合併 PR。
- 原定 JWT 篡改合成測試提交受到工具安全檢查攔阻，未寫入、未聲稱完成；改為本次純離線 CI 防護測試。
