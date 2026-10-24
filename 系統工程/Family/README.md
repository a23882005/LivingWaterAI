# Family 專案參考索引

此目錄收錄供 Family 各工作與相依專案共用的安全參考入口。需要完整 Joseph 專案規格時，請以 Google Drive 的正式來源檔為準。

## Joseph 專案資料來源

- 正式檔：[`Joseph_Project_Sources.txt`（Google Drive；需有檔案權限）](https://drive.google.com/file/d/194zJSkEKRxbfkxUcGKiTCT5a4GEe2nVG/view)
- 版本：v1.13.2 修正版，2026-10-24；搭配同版 `Joseph_Project_Instructions.txt`。
- 個人資料庫邊界：Joseph 專案的個人資料 DB 僅限 Joseph.db；公用 DB 不受此限。
- 配置報告命名：`Joseph_配置報告_YYYYMMDD_HHMMSS_TW.<副檔名>`，使用 Asia/Taipei 時間；每次成功報告保留，同秒重名加序號。
- 正式報告目錄：W6 的 `Joseph_正式配置報告` 私有資料夾；資料夾識別資訊及個人 DB 來源細節保留在具權限控管的 Drive 正式來源檔。
- 實作狀態：檔名修正已在 GitHub commit `d18681f951c68a01618138290cb1ace6288020e3`；fake-transport 命名／目錄測試及 Python 編譯通過。正式 renderer、私有目錄與 writer lock 注入、Project 端到端驗收仍待完成。

## 跨專案引用方式

引用 Joseph 規格時，連回上方 Drive 正式來源檔並沿用其版本；本索引只保留非敏感摘要。個人 DB 連結、client ID、私有 Drive 資料夾 ID 等資訊只在具權限控管的 Drive 文件中查看，不複製到公開程式碼或其他專案。

Drive 正式來源檔 ID：`194zJSkEKRxbfkxUcGKiTCT5a4GEe2nVG`。
