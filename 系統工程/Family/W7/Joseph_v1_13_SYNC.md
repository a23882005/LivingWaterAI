# Joseph v1.13 程式與規則同步

2026-10-24（台灣）。總PM本人。基準8fb00213c24e7162f1a836dbd70da6552f5cca82。

本輪交付：
- `joseph_menu.py`固定十四項操作鍵、舊規則路徑對照、問候請登入、登入後接續待辦、完成結果後完整選單、07網站直連、14登出。
- W6 `report_archive.py`使用既有Drive transport，台灣日期時間命名、同秒新檔序號、歷次保留、同run同內容重送去重、檔案讀回與最後完成manifest；12取得上次或指定日期成功報告。
- `report_handlers(auth,store,renderer)`實際銜接12/13。renderer只接受受信任正式W6/QA入口；QA未通過即停止保存。正式設定提供本人owner-only report folder與既有single-host writer lock；程式不內建私人位置或憑證。
- 五份既有menu規則、四份新增規則、menu README、完整程式鏈、W6 README及Checkpoint同步。舊規則檔名前綴保留穩定，畫面05→舊04、06→舊05、13→舊11。

驗證：新增28項（menu14、archive14）加既有Joseph簡易登入15項，43/43 PASS。涵蓋十四項新編號、開場登入、保留原需求、網站直連、完整選單、時區跨日、同秒重名、重送衝突、保留舊檔、傳輸失敗／manifest未完成、雜湊竄改與跨folder拒讀。使用本機合成Drive協定，無正式客戶報告／DB寫入。

後續由本人完成：正式renderer參數化、私有報告資料夾與writer鎖設定、既有報告索引核實、專案安裝與真人登入／產製／跨對話驗收。W7 B07仍IN_PROGRESS、6/23；B16未新增PASS。Production HOLD、交易NONE、W4取消、RM17凍結。

Joseph兩份安裝文件最新v1.13保存在Drive原ID，Sources的GitHub基準須更新至本次實際提交並同版交付。舊Sources固定6771867無法取得新增模組，故須一併更新，保留登入程式本體與私人資料位置在私有文件。
