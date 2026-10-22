# B03 每日資料與驗收快照鎖分離

2026-10-22。Family 總 PM 本人施工，B03 IN_PROGRESS。

已從 GitHub d0a2e946cabebcdb1fed9cfb92ce6428a30818ba 恢復並逐檔核對 120 個相關原件。工作區維護清理後，93 檔工作包從 Drive 恢復並通過原 Manifest。

## 修正

W5 dependency_lock.json 原將每日 `系統工程/總經V70/V70_macro_latest.json` 鎖為舊驗收資料，造成 c7_engine 啟動時拒絕正常更新的資料。

只調整這一列的 path，改指 `系統工程/Family/W5/tests/fixtures/macro/V70_macro_W5_accepted.json`，新增 source_path 與用途說明。新 fixture 直接取 GitHub 原 blob ca92c88643750ea73389d05c10421793b01669de，SHA256 仍為 71c8cfad106927fdde6c16ca1b24c40fc57d625e59732b662fb079f4c598b83f。既有 sha/sha256 不重算；其餘 lock 列、其他五份 lock、驗證器及投資算法全部沿用。

固定依賴驗證仍為原 verify_dependencies 的 115 項。每日資料仍由 P70-5.read_macro 及 macro_source_bridge 使用原路徑、原介面讀取與驗證。兩者用途分開：固定驗收 fixture 不提供當輪行情；依賴校驗通過也不代替當輪資料驗證。可信來源、每輪版本與來源 digest 的正式接線仍依 B10/B18 完成；本修正不新增信任來源或調整正式資料有效期政策。

## 實測

- 現行來源加固定 fixture：原驗證器 115/115 PASS。
- 新增 test_macro_dependency_separation.py：5/5 PASS。
- 正向：現行來源驗證通過；每日資料更新保持原驗收基線並由原 reader 讀取新內容。
- 負向：固定 fixture 竄改與程式竄改均遭原驗證器拒絕；每日 verification.ready=false 遭原 reader 拒絕。

測試僅使用暫存目錄及總經資料，不存取家人 DB。W5 原驗收交付包保留歷史，W7 工作包納入修正版依賴清單、原快照及測試；未重開 W5 驗收。

## 下一步

B03 的版本鎖耦合已修復，仍須完成其餘 W5/C/WORK12 逐檔讀寫與輸入輸出處置清冊，再驗收 B03 並進 B04。由本人循序完成。正式 W7 0/29；Production HOLD、交易 NONE、W4 取消、RM17 凍結。
