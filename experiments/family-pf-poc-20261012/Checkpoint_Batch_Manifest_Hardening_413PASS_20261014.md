最後修改日期時間：2026/10/14 14:34（台灣時間）
# Family PF｜外部授權 Manifest 一批次安全加固 Checkpoint（413 PASS）

## 正式工程成果
- pf_external_start_guard.py：新增嚴格 JSON 載入，拒絕重複鍵與超過 64 KiB 文件；所有欄位類型、字串長度、控制字元、反斜線、首尾空白均受檢查；租戶 ID 使用 casefold 對比避免大小寫分身；外部 HTTPS origin 的 DNS labels 禁止萬用字元、前後連字號、空白 label 與末尾點。
- test_pf_external_start_guard.py：新增約十五項負向／相容性檢查，包括錯誤型別、超長文字、控制字元、異常 DNS、同租戶大小寫、重複 JSON 欄位、超大 Manifest 與有效文件正向檢查。
- 沒有實際執行外部 HTTP、OAuth 或獨立安全審查；正向結果僅 READY_FOR_AUTHORIZED_OPERATOR_REVIEW，不能解除 Gate A。
- 程式 commit：09e710a299669edae73f94266d8a8f9b15248502。
- 測試 commit：e1794933a73d1e1ec98b1d845cb2097b6e00c819。
- 依首次 CI 精確定位失敗回歸測試的反斜線輸入問題，修正 commit：66326aaa79c081ef8f55ccfff5c10d1555aa81da。

## GitHub Actions 驗證與追溯
- 最後完整 CI Run：https://github.com/a23882005/LivingWaterAI/actions/runs/38522914973
- 完整測試 Job 115716507990：SUCCESS；合成套件 407 passed, 1 warning in 11.98s。
- 同 Job 安全契約測試 6 passed in 0.03s。
- 兩批合計 413 PASS，並非單一 pytest 套件。
- CI Evidence Job 115716675417：SUCCESS；SHA256 與 Commit 對應回讀。
- 第一輪中途 Run 38522797260：因字面反斜線測試失敗，406 pass / 1 failed；已修正後由上述成功 Run 取代，保留原日誌可稽核。

## 安全治理與剩餘外部依賴
- PR #2 Draft、未合併；main/正式 Runtime 未修改。
- 外部 EA-01～EA-09 仍 BLOCKED；Gate A HOLD；WORK13 0／29。
- 真正解除 Gate A 需要經核准獨立環境、外部 HTTPS MCP、OAuth 合成身分／兩個真正分離的測試租戶、持久化獨立 Audit 與獨立安全審查批准。
