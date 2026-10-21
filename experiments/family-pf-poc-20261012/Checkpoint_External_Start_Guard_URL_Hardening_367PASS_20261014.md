# Family PF｜External Start Guard URL hardening Checkpoint（367 PASS）
日期：2026-10-14（台灣時間）
Repository: a23882005/LivingWaterAI
Branch: family-pf-ci-20261012
PR #2: Draft，禁止合併

## 本棒目標與成果
沿用已驗收的 365 PASS，不重做上游工作。對先前 pf_external_start_guard.py 使用 startswith("https://") 所造成的寬鬆 URL 判斷增加嚴格解析及安全負向測試。
1. pf_external_start_guard.py 加入 urllib.parse.urlsplit 與 ipaddress：拒絕沒有合法 host、不合 HTTPS、私有/迴圈 IP、localhost/保留域名、非 443 連接埠、額外路徑、credential/query/fragment、反斜線與空白。
2. test_pf_external_start_guard.py 新增兩項參數化式案例（迴圈涵蓋多種非預期來源）：非法/非公開 URL 阻擋，有效 HTTPS Origin 仍維持僅能進入人工審查。
3. 守門器仍以 BLOCKED 為預設；即使欄位完整，輸出只允許 READY_FOR_AUTHORIZED_OPERATOR_REVIEW；Gate A 一律 HOLD，WORK13 false，不能自動進行網路操作。

## 真實提交與 QA
- Code commit: 5afeaa55078f7c8609c24409e46083f8f1101a17
- Regression test commit: 5aa7d391bc5e92d7fef4ea6cc1cbebcfede27f3c
- GitHub Actions run: https://github.com/a23882005/LivingWaterAI/actions/runs/38501499749
- Job: 115649266750, conclusion SUCCESS；原始執行日誌：367 passed, 1 warning in 7.16s
- 最終以 GitHub 同分支內容 SHA 回讀為準。本文件為獨立本棒 Checkpoint。

## 閘門與剩餘依賴
- 主持者已授權獨立非正式環境與合成身分「準備」，記錄在 Issue #3。
- AUTH 欄位真實資源/範圍、IdP、兩組測試身分、獨立 Audit 保管者、獨立審查者仍須核可與提供。
- EA-01～EA-09 外部真實驗收全數 BLOCKED；Gate A HOLD；WORK13 0/29；PR #2 Draft。
- 本棒僅是 URL 靜態/合成安全前置檢查，不宣稱已測過真實外部端點、OAuth、持久化 Audit 或客戶隔離。
