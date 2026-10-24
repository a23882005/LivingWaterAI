# Family 專案參考索引

此目錄收錄供 Family 各工作與相依專案共用的安全參考入口。完整 Joseph 專案文件以 Google Drive 正式檔為準，連結需有檔案權限。

## Joseph 專案文件

- 專案指示：[Joseph_Project_Instructions.txt（Google Drive）](https://drive.google.com/file/d/1qjVWts4u-IuIM9I5vTgXc6sfcZ_2LAVw/view)
- 資料來源：[Joseph_Project_Sources.txt（Google Drive）](https://drive.google.com/file/d/194zJSkEKRxbfkxUcGKiTCT5a4GEe2nVG/view)
- 版本：專案指示 v1.13.1；資料來源 v1.13.2 修正版，2026-10-24。

## Joseph 專用存取規則

- 只登入 Joseph 帳號；拒絕其他使用者帳號。
- 個人資料 DB 只可讀寫 Joseph.db；不得讀寫 mou.db、Arthur.db 或 Lilian.db。公用資料庫不受此限。
- 配置報告只可讀寫 Joseph 本人的報告；不得讀寫其他家人的報告。公用配置報告模板不受此限。
- 正式報告存於 Google Drive 的 W6／Joseph_正式配置報告；每次成功產報使用台灣時間戳命名並永久保留。

## 跨專案引用與實作狀態

引用時請連回上方具權限控管的 Drive 文件，沿用其版本。個人 DB 連結、client ID、私有 Drive 資料夾 ID 等細節只留在 Drive，不複製到公開程式碼。

報告命名修正已在 GitHub commit `d18681f951c68a01618138290cb1ace6288020e3`。正式 renderer、私有資料夾／writer lock 注入及 Project 端到端仍待完成；詳細狀態以 Drive 正式紀錄為準。

Drive 正式資料來源檔 ID：`194zJSkEKRxbfkxUcGKiTCT5a4GEe2nVG`。


## MOU 專案文件

- 專案指示：[MOU_Project_Instructions.txt（Google Drive）](https://drive.google.com/file/d/1rzj5FP6re6dfhme2Mos9DRthygqM3zMM/view)
- 資料來源：[MOU_Project_Sources.txt（Google Drive）](https://drive.google.com/file/d/1LoB6o4hWgj94Sy4yTV3bdiiybzRqGesF/view)
- 版本：專案指示 v1.0.0；資料來源 v1.0.0，2026-10-24。
- 本專案只登入 MOU 本人帳號，只讀寫 mou.db 與 MOU 本人配置報告；其他家人個人資料與報告隔離，公用 DB／公用報告模板依功能使用。
- MOU 正式報告資料夾位於 Google Drive W6／mou_正式配置報告。個人 DB ID、client ID 與私有資料夾 ID 留在有權限控管的 Drive Sources 檔。

## W7 驗收狀態

指揮官已完成 Joseph 家人版 Project 實際使用測試並確認通過。W7 整體目標標記為 **PASS／CLOSED（Owner UAT）**；目前停在 W7，依指揮官指示不進入 W8。正式細節以 W7 契約與私人驗收紀錄為準。
