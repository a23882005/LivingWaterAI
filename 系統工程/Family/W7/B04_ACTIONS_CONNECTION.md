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

本輪上述三個workflow環境欄位均為空，狀態AWAITING_FAMILY_DRIVE_CONNECTION；尚未執行Google token交換或Drive請求。這是指定接線欄位結果，不推論其他名稱、環境或帳號都沒有Google憑證。如已有合適授權，直接將既有名稱接入本workflow，無須重辦；若需新增授權，透過Google正常同意流程及GitHub Secrets設定，不經對話或repo存放secret值。

GitHub工具目前提供程式、Actions結果讀取與提交，未提供Secrets管理。PM的Drive外掛連線與Actions服務連線分開，現有PM回存證據保存於drive_probe.json。

## 本人接續

1. 接入Family專用Drive服務授權，執行既有TEMP合成庫讀取探測。
2. 在同一服務入口完成合成備份、交易、同ID回存、讀回與中斷恢復，核實ChatGPT實際工具連線與跨對話接續。
3. B04通過後依B05～B23循序施工。正式家人/共用/帳號DB只放Drive；Production HOLD、交易NONE、W4取消、RM17凍結。

已實測一般HTTPS跨連線；實際四家人ChatGPT連線、正式帳號與Drive共同writer接線仍在上述未結工作中。工程環境與授權接通之後仍由總PM本人完成實作及驗收。
