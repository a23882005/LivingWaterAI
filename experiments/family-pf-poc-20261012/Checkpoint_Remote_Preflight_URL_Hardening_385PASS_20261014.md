最後修改日期時間：2026/10/14 11:42（台灣時間）
# Family PF｜遠端 HTTPS MCP Metadata URL 負向安全測試 Checkpoint（385 PASS）

Repository：a23882005/LivingWaterAI；Branch：family-pf-ci-20261012；PR #2：Draft、未合併。

## 本棒真正完成
1. 修改 pf_remote_preflight.py：外部 HTTPS endpoint 預檢拒絕空白與反斜線 URL；保留網域檢查統一使用大小寫不敏感比較。
2. 同一支程式的 OAuth issuer metadata URL 增加空白與反斜線拒絕處理，維持 read-only、無授權 token／客戶資料、禁止自動放行。
3. 更新 test_remote_preflight.py 增加兩組參數化負向測試，涵蓋保留網域大小寫、反斜線、含空白以及錯誤埠號等八個測試情境。
4. GitHub Actions 雙 Job 完成：完整 pytest 與下載合成 CI Receipt、SHA／Commit 關聯檢查皆 SUCCESS。

## 真實提交及 CI
- 程式 commit：fa1b75a60947fcf5e861b81623f01ff0ddf87370
- 測試 commit：1e4e9256ecec8793e7ca5ed516bb297d2903e217
- CI Run：https://github.com/a23882005/LivingWaterAI/actions/runs/38507578550
- 完整 QA Job 115668496662 SUCCESS；pytest 日誌：385 passed, 1 warning in 7.17s。
- Receipt 驗證 Job 115668593468 SUCCESS。
- 先前 377 PASS 技術基準保留；最新 385 PASS 為本棒 CI 驗證結果。

## 保護範圍與驗收 Gate
- CI 屬合成測試，未執行真實外部測試主機配置、OAuth 交換、正式客戶隔離或獨立持久化 Audit。
- 依 Issue #3，隔離非正式環境／合成身分的準備已獲原則性批准；具體資源與獨立審查者待落實。
- Gate A HOLD、EA-01～EA-09 BLOCKED、WORK13 0/29，PR #2 保持 Draft；main／Production Runtime 不修改。
