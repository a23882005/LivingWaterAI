# Family PF｜中 PM 合成測試環境啟動守門程式 Checkpoint
日期：2026-10-14（台灣時間）；僅限隔離工作分支 family-pf-ci-20261012
## 完成
- 新增 pf_external_start_guard.py：離線、fail-closed 的外部實測前置授權檢查器，不進行網路連線。
- 每份 manifest 必須有範圍/環境/測試時窗/預算/執行者/IdP/合成 A-B 身分/Audit 保管/獨立審查/治理者等實際已核准識別；拒絕正式環境、真實客戶資料、未明確核准的 live test、自審與同身分租戶。
- 完整輸入的輸出僅能是 READY_FOR_AUTHORIZED_OPERATOR_REVIEW，不具啟動真實連線或 Gate A 放行權限。預設 BLOCKED、Gate A HOLD、WORK13 false。
- 新增 test_pf_external_start_guard.py 共 9 項案例；本地離線 pytest 實測 9 passed (0.06 seconds)。
- 修改 .github/workflows/family-pf-ci.yml 將新程式與測試接入既有合成 suite，沒有更動 main/Runtime。
## 提交與證據
- 程式 commit 1c8868aa095f857d6904262d0484a8998d8e723e
- 測試 commit 426f959d3483601e0ea4d783aac0789a1af53fb3
- CI 接線 commit 0766de239cebfa822d77bd700c3b0742d532d41b
- 程式 GitHub blob SHA 9b5498bf8ca50f57680e89dcaf05d6c7acc583c1
- 新 CI run 38499508313，建立 Checkpoint 時正在執行，最終結果須以 GitHub job 和日志重新核對；上游 356 PASS 為舊版已確認基準。
## 安全界線與依賴
- 專案負責人已授權「隔離非正式環境、合成帳號的準備」，授權記錄見 Issue #3。
- 真正 HTTPS MCP 外部端點、OAuth/IdP、可用身分、預算、獨立保管與審查者尚缺可核驗配置；EA-01～EA-09 外部實測維持 BLOCKED。
- Gate A HOLD；WORK13 0/29；PR #2 Draft 未合併；main/正式 Runtime 未更動。
- 本 Checkpoint 記錄完成本地 QA、GitHub 程式提交與 CI 接線；不宣稱外部測試或獨立安全審查已完成。
