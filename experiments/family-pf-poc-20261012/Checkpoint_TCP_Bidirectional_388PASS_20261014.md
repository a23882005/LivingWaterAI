最後修改日期時間：2026/10/14 12:31（台灣時間）
# Family PF｜真實 TCP 合成雙向租戶隔離 Checkpoint（388 PASS）

分支：family-pf-ci-20261012；PR #2 Draft；不更動 main／正式 Runtime。

## 本棒完成
- 在 test_mcp_live_loopback.py 增加三項 Uvicorn＋TCP 127.0.0.1 端到端回歸測試。
- 第二組合成測試身分讀取自身授權資源成功，最後 Audit decision ALLOW。
- 第二組身分跨入第一組資源被拒絕，回傳 JSON-RPC isError true，敏感的合成資源文字未洩漏，Audit decision DENY。
- 第一組身分連續執行授權→跨租戶拒絕→授權，逐次驗證 ALLOW/DENY/ALLOW，避免切換 active_client_id 後保留錯誤權限。
- 使用既有 GitHub Actions 雙 Job；沒有購買、部署或觸及任何外部服務。

## GitHub 真實證據
- 程式提交 commit：48a7ef96a7e2caf60a0b654bd8052d4d4a00b65f。
- Actions run：https://github.com/a23882005/LivingWaterAI/actions/runs/38511691768
- 完整測試 Job 115681420515：SUCCESS；pytest 388 passed, 1 warning in 9.82s。
- 證據 SHA 與 GitHub commit 比對 Job 115681580824：SUCCESS。
- 新增三項 TCP 測試，與先前 385 PASS 相比為 388 PASS。

## 重要限制／Gate
- 這是本機 loopback TCP 真請求、合成身分和合成資源，不是外部真實 OAuth 身分供應者、不是真正公網 TLS／HTTPS、也不是獨立 Audit 儲存。
- Gate A HOLD；EA-01 至 EA-09 外部安全驗收未完成；WORK13 0/29。PR #2 保持 Draft、未合併。
- 下一步仍需經明確核准的外部非正式服務環境與獨立安全審查資源，才能正式驗證 Gate A。
