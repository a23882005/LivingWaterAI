V70 正式頁及教育候選頁的瀏覽統計共用一個 Apps Script 網頁應用程式，兩頁直接使用部署網址。計次服務只儲存總計、當期計數與日期鍵。台灣時間每日零點、週一及每月一日切換期間。

部署版本 1：https://script.google.com/macros/s/AKfycbwSd5yYr-bUzMgSq9c8T6Q3cJW02g7nLJq_UxwpxdU9qMlwobzvxndxDGiEivsSMYd9/exec

每次成功送達的瀏覽事件計一次，包含重新整理、自動化瀏覽和驗收。部署前的歷史訪問未匯入。修改服務請更新原部署版本以保留網址。PR 分支的瀏覽器驗收使用兩個獨立 Chromium 程序讀取兩個候選頁，並檢查總計增量。
