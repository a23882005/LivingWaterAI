# Family PF 中PM｜MCP Audit Request Wiring Checkpoint
日期：2026-10-13（台灣）｜範圍：獨立實驗分支 family-pf-ci-20261012

## 完成本輪實際施工
- 修改 `pf_mcp_protocol.py`：`attach_mcp(..., persistent_audit=None)` 接入可選的 AuditStore；在工具資源讀取成功（ALLOW）及授權拒絕（DENY）時寫入 HMAC 鏈式 SQLite 稽核元件；失敗時依例外傳播中止回傳受保護內容。
- 新增 `test_mcp_audit_wiring.py` 兩項合成 E2E 測試：Joseph→mou 和 mou→Joseph 拒絕、自有資源讀取成功、SQLite 重啟重新開啟後四筆事件的鏈式驗證、模擬 Audit Log 寫入失敗時中止輸出。
- GitHub Actions `.github/workflows/family-pf-ci.yml` 已載入測試。
- Commits：`b94044ed2be686dd29fb3b386e869735dbb7d872`、`82bc44c46f0d1a26be29caa58eb32720d3ecf736`、`bbdae0ffb54d2d36fe2a137657f4031cf3375149`。
- QA：GitHub [Run 38316091015](https://github.com/a23882005/LivingWaterAI/actions/runs/38316091015) full test suite step success，Demo step success。本次測試總數應從原始 pytest log 核實，僅以 CI step PASS 做正式主張。

## 注意／未完成
- 目前只針對 MCP tools/call 資源讀取 ALLOW/DENY 透過合成路徑持久化；Origin／Bearer 認證早期失敗仍保留原 in-memory scope.audit，尚未落盤整合。
- actor_ref 暫時是 synthetic_subject 定值，正式環境須伺服器端生成穩定不可逆 subject pseudonym 並驗證一對一映射及不得洩露真實客戶個資。
- 現有 SQLite + HMAC 是元件層驗證，尚非獨立不可竄改外部審計證據，也未有獨立存取控制／保留治理。
- 真實外部 HTTPS MCP、外部 OAuth、遠端 Joseph↔mou 雙向 E2E、持久化伺服器 audit、第三方獨立審核簽章仍未完成。
- Gate A=HOLD；WORK13=0/29；PR #2 Draft；main 與正式 Runtime 未變更；未購買 Render，額外主機費 NT$0。

## 治理登記事項
由正式治理管理者依根目錄檔案管理規則，將本 checkpoint/commit/run 登入 ABC大工程.md 及檔案管理.md；此階段只改 GitHub 實驗分支，未覆寫 Google Drive 正式治理檔。
