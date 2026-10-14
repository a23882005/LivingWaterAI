# Family PF｜雙 GitHub Actions Job 與合成 QA 證據回讀 Checkpoint（375 PASS）
最後修改日期時間：2026/10/14 11:17（台灣時間）
Repository：a23882005/LivingWaterAI
Branch：family-pf-ci-20261012
PR #2：Draft / 未合併
狀態：合成工程驗收完成；Gate A HOLD；WORK13 0/29

## 本棒實際成果
1. 新增 pf_ci_evidence_receipt.py：將 pytest JUnit 摘要轉為最小化 JSON 證據，保存執行 HEAD SHA、原始 JUnit 雜湊與四個測試統計欄位；輸出固定標明 SYNTHETIC_CI_ONLY、外部 Gate A HOLD、WORK13 false。
2. 新增 test_pf_ci_evidence_receipt.py：八項證據安全負向測試，包括錯誤/失敗結果、竄改 SHA、偽造 Gate 權限、非 JUnit 格式、帶敏感測試名稱不輸出、無效 SHA、異常型態等。
3. 修改 .github/workflows/family-pf-ci.yml：原完整套件產生 JUnit XML 於 Runner 暫存；僅將摘要 receipt.json 與 receipt.sha256 上傳為 Actions Artifact（retention 7 天）。
4. 增設第二個 GitHub-hosted Runner Job：download-artifact → SHA256 計算/內容約束回讀。第二個 Job 僅證明同 CI 證據完整性，不等於外部獨立稽核保管或安全審查。
5. 針對首次 CI 的測試斷言與一次換行字元錯誤，依原始 GitHub Job 日誌修正，最後完整 CI 成功。

## 版本與真實 QA
程式 commit：5e36e83d2d84b33b9e07df68b866cdedf0f69467
測試 commit：ac8a0dd057368418306167c61a7c048a373c60a0
雙 Job CI 接線 commit：7624fe79c60a50fbb982e7ff13b44d291308f54a
測試修正提交：f1eec7cead40b2c6913570b88fb15e4e81d6325c、78749c78985ddfe40ad8c47497ed11f6ff4abe67
成功 GitHub CI：https://github.com/a23882005/LivingWaterAI/actions/runs/38505274111
QA Job ID：115661238668；原始 pytest 日誌：375 passed, 1 warning in 8.83s。
Receipt Job ID：115661384174；status completed / SUCCESS。
之前失敗的中途 CI Runs 38505157112 與 38505225560 保留在 Actions 記錄供追蹤，已透過最終成功 CI 修正。

## 尚待正式外部驗收
- EA-01～EA-09 真實外部 HTTPS MCP、OAuth、雙向隔離、持久化 Audit 與獨立審查：BLOCKED。
- 使用者已核准隔離非正式環境與合成測試帳號的準備，具體端點、身分、成本與獨立審查權限仍須依 Issue #3 辦理。
- main/正式 Runtime 不變；PR #2 維持 Draft，不合併；Gate A HOLD；WORK13 0/29。
