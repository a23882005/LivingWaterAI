【2026-10-23現況補正】B04依原v1.6.0最小能力實測契約已驗收PASS，W7 4/23，當前B05。下文先前將正式MCP/常駐服務/真實跨對話列為B04阻擋的敘述停止適用；後續責任依B04_CLOSEOUT.md及Checkpoint。既有測試證據保持。

# B04 Actions實際部署與Drive接線｜2026-10-23

總PM本人循序施工。W7唯一B01～B23；目前3/23，B04進行中。

## 已完成

沿既有Hostinger SSH/SFTP設定由Actions讀取執行能力，實際取得PHP8.2、PDO SQLite、curl、OpenSSL、Python3.9及SQLite3.34.1。原部署及總經排程保持原用途。

`family-w7-capability-probe.yml`新增既有服務能力與合成HTTPS部署兩個job，無新增排程。短暫部署於唯一run/attempt子目錄，合成狀態庫置於public_html之外；測試後清除唯一入口及合成狀態庫。原網站首頁與正式資料未異動。

GitHub run39842417666三個job SUCCESS：原20項合成測試通過；實際網站18項HTTPS檢查通過；cleanup PASS。測試項含認證、固定14400秒、重複登入不延長、獨立HTTP連線接續、兩合成帳號隔離、Chat/Action共用排隊、衝突拒絕、重試不重複、並行更新、登出撤銷及舊工作取消。證據evidence/B04/hosted_action_run.json；工程commit84207b73b8a342ebcf9a959fc4e393dcdf5e7bd4。

`probes/hosted_entry_probe.php`為既有PHP主機的合成能力探測；`hosted_entry_client.py`建立隨機測試憑證並由Actions執行HTTPS驗證。憑證、已填憑證的生成PHP檔及合成DB皆不納GitHub/Drive工程包；只保存程式模板與去識別證據。端點已清除，本次不建立常駐正式服務。

## Drive指定接線

`probes/actions_drive_read_probe.py`只讀取原TEMP合成DB ID `1SDnOCLoHpX-XfJ9v838o84VJmzdmoPzI`，檢查SQLite完整性/外鍵並輸出去識別SHA/bytes。OAuth token與錯誤回應內容不輸出。

此回合明確建立Family專用Actions欄位契約：

|GitHub Actions Secret|用途|
|---|---|
|FAMILY_DRIVE_CLIENT_ID|既有Google OAuth應用程式識別|
|FAMILY_DRIVE_CLIENT_SECRET|該應用程式密鑰|
|FAMILY_DRIVE_REFRESH_TOKEN|經Drive授權帳號同意的離線更新token|

2026-10-23接線已完成：三個Secrets已存入指定GitHub repository，readiness job120125682760實際OAuth更新及TEMP讀取PASS（8192 bytes，完整性/外鍵PASS）。原run39842417666其餘HTTPS與cleanup job亦SUCCESS。下方待接文字由本段取代。

新增獨立workflow `family-b04-drive-roundtrip.yml`，commit4614b04d2fa50562ff25d2bfe5d6cb07159b89d5，run39866437563/job120129684482 SUCCESS。10/10本機與Actions故障邊界測試通過。固定TEMP ID備份→建立獨立合成表交易→同ID回存→精確讀回→worker立即exit73（不執行finally）→新OAuth client依Drive持久journal恢復；原8192 bytes SHA 7c75b192ff45bb0d71f88f0b6f16bfb59fc1a73d53a7aa29ad9e9471238872a8完全恢復。二次recover為CLEAN。備份ID1wnzAhB5cltURq4mGEHDl_-v6mB21HpEo保留在Backup。證據evidence/B04/oauth_drive_roundtrip.json。

限制：workflow concurrency只序列化本probe；hash重驗可偵測外部更動，但不是跨服務原子鎖。本次不等於常駐共同writer或真實ChatGPT跨對話驗收。整台runner失聯時由下次執行先recover，尚未驗證無人值守災難復原。Google OAuth仍Testing；官方規則此Drive refresh token七天到期，不能宣稱永久接通。長期授權需品牌/發布條件核對，正式Family Production仍HOLD。
官方來源：https://developers.google.com/identity/protocols/oauth2

GitHub工具目前提供程式、Actions結果讀取與提交，未提供Secrets管理。PM的Drive外掛連線與Actions服務連線分開，現有PM回存證據保存於drive_probe.json。

## 本人接續

1. 已完成Family專用Drive服務授權及TEMP讀寫/備份/復原；接續處理OAuth Testing七天限制。
2. 將已測復原能力接至常駐共同writer，核實ChatGPT實際工具連線與跨對話接續。
3. B04通過後依B05～B23循序施工。正式家人/共用/帳號DB只放Drive；Production HOLD、交易NONE、W4取消、RM17凍結。

已實測一般HTTPS跨連線；實際四家人ChatGPT連線、正式帳號與Drive共同writer接線仍在上述未結工作中。工程環境與授權接通之後仍由總PM本人完成實作及驗收。

## 2026-10-23共同writer接線更新

已完成合成HTTPS共同queue到Drive writer的實際接線；單主機flock、Drive持久journal與資料/receipt原子image配合，修復上傳成功但回覆中斷的重試重複問題。程式、部署、驗收及私人設定清理見B04_SHARED_WRITER.md與evidence/B04/shared_writer_action_run.json。接續由本人完成MCP transport、服務端認證與真實跨對話接線，OAuth Testing期限仍在待辦。

登出交界補強：Drive已提交但queue尚未確認時，登出/失效session重新登入先以receipt對帳；已提交工作標為DONE，未提交工作才取消。線上新增登出再登入去重驗收，結果以shared_writer_action_run.json為準。
