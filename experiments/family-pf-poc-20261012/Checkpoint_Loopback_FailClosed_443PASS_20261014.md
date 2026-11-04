最後修改日期時間：2026/10/14 22:09（台灣時間）
# Family PF｜Loopback RPC Fail-Closed 安全補強 Checkpoint（443 PASS）

## 範圍
- 倉庫：a23882005/LivingWaterAI。
- 唯一施工分支：family-pf-ci-20261012。
- PR #2：Draft，未合併、未部署，main 不變。
- 本次只變更隔離工程目錄的合成測試與 Checkpoint。

## 實作
- 修改：test_mcp_live_loopback.py。
- 新增 4 個真 TCP 127.0.0.1 合成安全回歸測試：
  1. JSON-RPC 缺少 request id 時 fail-closed，不讀取資源。
  2. JSON-RPC 版本 2.1 時 fail-closed，不讀取資源。
  3. resource_id 類型錯誤（陣列）時 fail-closed，不讀取資源。
  4. active_client_id 空白時 fail-closed，不讀取資源。
- 每項驗證拒絕回應、不暴露 synthetic-j，以及沒有觸發資源稽核讀取事件。
- 程式提交：6ced95bf1eebd82cfd8c9db3b507380ae774a9df。

## GitHub Actions 真實證據
- Workflow run：https://github.com/a23882005/LivingWaterAI/actions/runs/38577911995
- verify-pf-full-suite Job 115899789658：SUCCESS。
- 完整合成套件：443 passed，1 warning，0 failed，15.09 秒。
- CI security contract：獨立 8 passed，0 failed（不重複計入 443）。
- verify-evidence-receipt Job 115900071358：SUCCESS。
- 上一版 439 passed；本版新增 4 passed。
- 本 Checkpoint 只記錄經上述 SHA 驗證的實測結果；Checkpoint 本身後續 commit 仍應另行驗證該 commit CI。

## 邊界與後續
- Gate A = HOLD；WORK13 = 0/29；EA-01～EA-09 = NOT_VERIFIED。
- 本次為合成 loopback 驗證；真 HTTPS、真 OAuth/IdP、外部雙向租戶驗證、獨立稽核保留、第三方審查仍待正式外部驗收。
- 禁止合併 PR、正式部署、真實客戶資料或真實 OAuth token。
