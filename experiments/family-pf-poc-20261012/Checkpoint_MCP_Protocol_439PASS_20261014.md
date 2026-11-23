最後修改日期時間：2026/10/14 21:29（台灣時間）
# Family PF Checkpoint｜439 PASS MCP 未知工具與協定防護

## 本輪實作
- Repo：a23882005/LivingWaterAI，隔離分支 family-pf-ci-20261012，PR #2 Draft。
- 新增 test_mcp_live_loopback.py 兩項真實本機 TCP／HTTP 合成測試：
  - 未知 MCP 工具 pf_admin_read_all：JSON-RPC -32602，未發生資源讀取、未洩漏合成資料。
  - 非 2.0 JSON-RPC 版本：JSON-RPC -32600，未發生資源讀取、未洩漏合成資料。
- 原始程式 commit：a0e50a494f1e853a2f42fa8ad9a02d2720ed7c34。

## GitHub CI 真實驗證
- Actions：https://github.com/a23882005/LivingWaterAI/actions/runs/38572069664
- verify-pf-full-suite Job 115879570767：SUCCESS；439 passed, 1 warning in 13.95s。
- verify-evidence-receipt Job 115879796495：SUCCESS。
- 相較前一筆 437 PASS，本輪實際新增兩項測試。

## 安全治理與限制
- 只使用本機 127.0.0.1、合成身分與資源；未觸及外部 IdP、公網 HTTPS、實際客戶資訊或正式 Runtime。
- Gate A HOLD；外部安全驗收 EA-01～EA-09 未獲完整證據，WORK13 0/29。
- PR #2 仍維持 Draft、不合併 main；合成 CI PASS 不能替代獨立安全審查與外部正式測試。
