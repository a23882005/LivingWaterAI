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

## W7 驗收狀態與 Arthur 當期問題（2026-10-25）

2026-10-24 指揮官對 Joseph 家人版 Project 的實際使用驗收，依原始紀錄維持 **Owner UAT PASS**。這是 **Joseph 的既有驗收紀錄**，不自動涵蓋 Arthur、Lilian、MOU 各自真人登入、4 小時及跨對話驗證。

實際 W7 施工 Checkpoint.json 仍列 **B07 IN_PROGRESS，B01～B06 6/23 PASS、Production HOLD、交易 NONE**。Owner UAT 歷史裁決與 B07 技術施工 Gate 應分開列示；未經正式驗證不將 B07 標為 PASS。依既有指示暫不進入 W8。

2026-10-25 Arthur Project 截圖反映「AR 帳號尚無有效登入工作階段／登入服務仍待啟用」。排查重點是正式身分驗證服務與 ChatGPT Project 工具接線、真人 AR 啟用、重開對話驗收，而非只修改 Instructions 文字。Arthur 專案要求：開場說明用途並提示輸入密碼，無須重輸固定帳號 AR；同一對話登入有效 4 小時；**新對話或執行環境重置須重新登入**；未登入可查公開總經與新聞，但個人 DB／報告必須通過實際 auth 驗證。密碼不得回顯或存入聊天紀錄、檔案。

Arthur 私人兩份正式文件僅存 Google Drive 根目錄，避免將 DB 路徑與 client_id 公開寫入 GitHub：
- [Arthur_Project_Instructions.txt（Drive）](https://drive.google.com/file/d/18h6TYSQiCFtUeWF9osnxwM0_Za2KT1-8/view)
- [Arthur_Project_Sources.txt（Drive）](https://drive.google.com/file/d/1Q43U_uI24HM0BVw_h1rGjJk9xR7Wn4Hy/view)

交付驗收：真人 AR 密碼登入 → 讀取 Arthur 本人快照 → 新對話要求重新登入 → 四小時到期重新登入 → 錯誤密碼／跨戶讀取拒絕 → 報告保存讀回，逐項留實跑證據。
