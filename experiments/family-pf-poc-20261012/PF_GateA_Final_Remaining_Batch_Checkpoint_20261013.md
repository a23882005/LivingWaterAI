# Family PF｜Gate A Remaining Work Batch Checkpoint
日期：2026-10-13（Asia/Taipei）
工作範圍：Family PF isolated experimental branch，PR #2 Draft

## 本輪施工、驗證成果
- Fresh read: 交接 ZIP 與 GitHub 分支程序、Gate A 5 項必要證據。
- `pf_audit_store.py` 新增 `export_anchor()` 和 `verify_anchor()`；在完整 HMAC 鏈檢查之外，允許比對事先由獨立可信通道保存的 seq/count 與最後 MAC，以偵測尾端遭刪除。
- `test_audit_store.py` 新增 2 項測試：尾端刪除偵測、無效錨點及增量後舊錨點失效。
- Commits：`36fa9210cd04eb60ba9737b7153e0291eddeae9f`、`16ed0743ac248c3f359996bcca77ac2947e077eb`。
- [GitHub Actions 38329216819](https://github.com/a23882005/LivingWaterAI/actions/runs/38329216819)：全 Job SUCCESS；pytest 原始日誌 **177 passed, 1 warning in 9.14s**，Demo PASS。
- 本次僅寫獨立分支；main、正式 Runtime、客戶資料未動；新增付費主機費 NT$0。

## Gate A 五項外部證據（真實狀態）
1. Remote HTTPS MCP 可由獨立外部網路連線：未取得經核准之公開測試端點與憑證實連證據。
2. External OAuth login：未提供／連接真實身分提供者、同意授權流程與測試身分；未有真實 login evidence。
3. Server-side client binding：僅合成驗證；尚待外部實際 HTTPS + OAuth JWT 對應驗證。
4. Joseph↔mou cross-client negative：合成資料雙向 DENY 測試通過，遠端真實環境 E2E 未驗證。
5. Persistent Audit denials：SQLite 合成測試通過；外部持久化、外部不可變錨點和獨立驗收待完成。

另需大PM核准獨立審核者公鑰 pin 與正式簽署；即使出現五項自報 evidence，仍必須完成獨立 review。

## 可執行的外部驗收程序（完成前全部 HOLD）
- 先由正式治理者批准隔離測試用 HTTPS endpoint（非正式 Runtime）與外部 OAuth provider、兩個合成帳號、機密管理方法和獨立 reviewer。
- 從外部網路做 HTTPS TLS 檢查、OAuth metadata/issuer 及安全挑戰檢查。
- 透過真實 OAuth 授權登入兩個合成帳號，測試 token audience/issuer/expiry、PKCE、跨客戶雙向 403/DENY、權限撤銷後仍拒絕。
- 獨立稽核者取得有時間／request-id 的脫敏 Audit Log、驗證重新啟動後留存，將 `export_anchor` 保存於獨立可信位置後實測尾端刪除可偵測。
- 獨立審核者按核准公鑰簽署證據；再由 Gate A evaluator 驗證，經大PM治理放行方可開始 WORK13。

## 決裁
- Gate A = HOLD；WORK13 = 0/29；PR #2 = Draft，不合併。
- 本輪已完成所有**現有隔離環境可直接完成**的新增稽核錨點與 GitHub CI 工作。真實外部 HTTPS/OAuth 和第三方簽核依賴已核准外部服務與獨立審查者；未獲得驗收證據不宣稱完成。
- 治理總登記需遵守 Drive 根目錄《檔案管理.md》讀檔、備份、Read-back；本輪僅保留 GitHub 分支 checkpoint。
