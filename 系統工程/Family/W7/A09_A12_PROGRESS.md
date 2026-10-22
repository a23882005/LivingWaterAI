# W7-A09～A12 工程與驗證（2026-10-22）
責任及施工者：Family總PM本人，sequential。

A09完成：共用15組政策正向/負向/期限案例，Python、Node、Chromium使用相同資料與明訂期望。補歸檔示範/來源不符/日期未核實/無效分數拒絕及衝突保留歷史bytes。契約所列既有monthly/state/alert/capture測試及新增policy_rate/cache測試均列入工作包。Action接線實跑通過。
A10完成：沿原v703-frontend-regression.yml內嵌瀏覽器測試，新增隔離w7-contract-browser。完整HTML經Chromium載入受控合成feed，真實DOM與既有計算函式執行；31案例含正式有效、15政策共用案例、三種手動修改、開頁後政策/快照到期、研究模式、四子項過期/候選查核缺漏、實際瀏覽器分數→歸檔冪等。原main現行資料瀏覽器測試保留。測試資料僅fixture及測試artifact，沒有寫入正式歷史CSV。
A11工程完成：11h工作流保持原ready/25/28/26/22、完整圖表及部署回執門檻；新增Task補充契約驗證、政策/歸檔測試、發布前26小時及四子項重驗。線上HTML/JSON完整比對建置原件；main分支護欄、依ref concurrency。資料檢查失敗發生於發布步驟前，部署回執仍僅在既有線上讀回成功後產生。真實發布及回執由A13驗收。
A12工程及相容性驗證完成：每日歸檔重用validate_v703_publication.py政策/四子項/衍生值/26小時規則，拒絕布林分數、台北批次日期不符；保留既有來源一致、正式模式、分數範圍、冪等與append-only。月度公式及既有正式歷史檔未改，11項月度及3項銀行相依測試通過。真實正式來源的線上歸檔於A13整鏈讀回。

證據：工程commit547e8493318ac0ca41306742cf8e489c924d71cd（A09/A10），adeb3c4c083998dfba9e5f6cc6eaecdbd18d84e0（A11/A12）。最終09h隔離run39760153970共65測試PASS；browser run39760153987共31案例PASS；發布run39760154112依分支護欄skipped。逐案日誌及job/step結果見evidence/A09、A10、A11_A12。第一輪browser run39759553965亦30案例PASS，新增歸檔鏈後31案例。

狀態：A09/A10已完成；A11/A12隔離工程完成，正式切換、真實來源、Task產出、線上讀回與歸檔共同納入A13。A04與A08既列A13後段條件保持。正式W7 0/29，Production HOLD、交易NONE、W4取消、RM17凍結。
下一項由本人A13：核對main最新差異，協調已驗證消費端與Task提示詞切換；真實來源重跑與完整測試；依契約部署讀回與歸檔；重建正式兩ZIP及同ID程式鏡像，逐檔校驗；再A14故障階段結案，接B01。
