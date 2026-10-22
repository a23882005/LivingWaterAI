# W7-B03 依賴盤點與版本鎖核對

2026-10-22；本人循序施工；狀態 IN_PROGRESS。核對 GitHub main a4ea9c0b1a3e92f217e0131fccddbfa91bad0ed9，完整 tree 695 項、未截斷。

## 已驗證結果

- 已取回 161 個 GitHub 檔案，逐檔 Git blob 一致；115 支 Python 完成 AST 依賴初盤，逐檔語意處置尚未全部完成。
- 實際載入 runtime_loader 明列的 C8C9 Work3～Work9 七個模組，26 個 schema 常數均找到實體檔，Draft202012Validator.check_schema 全數通過。
- 六份 lock 共 115 列：現行 main 的 114 列一致，唯一差異為每日更新的 `系統工程/總經V70/V70_macro_latest.json`。
- 在隔離暫存樹只換回 W5 已驗收 ZIP 內該資料快照，原 verify_dependencies 原碼通過 115/115；刻意改動一支固定程式後，原驗證器正確拒絕。
- 原件與現行資料未改；本輪未修改 lock、runtime、DB 或部署。探測環境補裝 jsonschema 4.26.0，未修改專案依賴版本宣告。

## 每日資料與固定程式的處置

直接呼叫鏈為 c7_engine.run_c7_engine → verify_dependencies.verify → dependency_lock；因此 C7 尚未開始計算便受到舊每日快照 hash 阻擋。這是已重現的版本鎖耦合，並非投資計算結果錯誤。

後續實作須保留原 W5 固定驗收模式；正式每輪存取另外綁定受信任來源的 commit、檔案路徑、bytes SHA、觀測/取得時點與 run，不接受呼叫者自己聲稱的 hash 作信任根。固定程式/schema 仍逐檔鎖定；即時資料由既有 W3 reader、macro_source_bridge 及 A 段有效期/來源政策驗證。此設計尚未實作或驗收，不能以略過總經檔校驗、更新成今天 hash 或重算全部 lock 代替。

## 已定位但未在 GitHub 的既有程式

完整 tree 中無 W2 target_draft.py、target_confirmation.py，以及 W6 src_v16 六支報表程式。已從原驗收包抽取並記錄逐檔 SHA256（見 missing_github_sources.json）；另含兩支 W2 原測試。W5 w2_dependency_lock 只封裝 recovery.py 與 reason_catalog，不能據此宣稱目標產生端已納管。

後續先展開上述檔案的 imports、設定、模板及資產依賴，僅補入核實過的原碼到 GitHub，增加來源/目的地鎖與 Drive 鏡像，再由 B14/B16 接線。原驗收包及測試歷史保留，不重做 W2/W6 已結案驗收。

## 接續工序

本人完成 115 支 Python 逐檔輸入輸出/讀寫處置，補齊 W2/W6 及 WORK12 直接依賴，完成每日資料驗證介面與受影響 lock 對應方案，再簽 B03、進入 B04。尚未達到 B03 完成條件。正式 W7 仍 0/29；Production HOLD、交易 NONE、W4 取消、RM17 凍結。
