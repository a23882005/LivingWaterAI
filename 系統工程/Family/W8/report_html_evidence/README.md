# PR60 來源文字換行補修證據（2026-10-31）

中 PM 對 81e741da 的資料承接、靜態產物及正式保存／工程查閱已分段 PASS；本輪修正 REPORT_SOURCE_REFERENCE_HORIZONTAL_OVERFLOW，排版待中 PM 複驗。共用 W8 README／Checkpoint 仍由中 PM 維護，本線沒有修改。

- 准改範圍：原 19 個檔案內，本次修改 12 檔，完整路徑見 changed_files.json 的 layout_repair_changed_files。
- 程式只改 w6_member_render.py：章節及雷達來源共用完整換行樣式，保留 18px 字級；QA 同時檢查來源文字 Range、卡片內緣及 scrollWidth/clientWidth。來源、lineage、日期、scope 與數字不截斷、不刪除。
- 257 項＋65 子案例通過，10 項真實 Chromium 測試，0 failures/errors/skips。新增合成長 URL／路徑／64 位 SHA／中文標點案例，驗 12 張來源卡、PDF 字框及全部頁面 PNG／HTML 同源；JUnit 與命令見 validation.json。
- 本機合成證據在 /workspace/report-layout-20261031/final-synthetic/：report.html、report.pdf、index.html、report.zip、mobile.png；long_reference/ 保存新增長字串案例的完整四種產物。artifact_hashes.json 可核對 bytes／SHA。所有公開 QA 只含合成資料。
- 四戶按中 PM 指定凍結來源重出 17／19／15／15 頁，共 66 頁；60 張來源卡（含 32 張估值來源）全文相等、文字範圍及 PDF 字框在卡片內，全部保存頁與 ZIP PNG 像素相等。current digest、核准比例、run、資料日期不變。四戶 SOURCE_REVIEW、缺值 UNKNOWN 保留。
- 新 20 份正式原件／manifest 已依本人 Sources 資料夾與新台灣時間檔名保存，舊報告保留；全新下載、私人父目錄、bytes／SHA、run／DB 綁定及工程 Menu12 查閱通過。現行正式 DB 的後續版本另列私人 SHA 比對，沒有混入凍結資料，沒有 DB 寫入或金融重算。
- 完整私人證據：Google Drive 根目錄／TEMP／Family_Report_HTML_PR60_排版補修複驗入口_20261031.txt；完整包同目錄 Family_Report_HTML_PR60_排版補修完整成果_待中PM複驗_20261031.zip。私人報告、圖片及完整來源不放公開 GitHub。

核准 v16 母包 SHA、六支產生程式 SHA、凍結上游版本與最新 metadata 查核見 source_versions.json。本機 Chromium 需已授權的執行權限；file:// 仍實測 ERR_BLOCKED_BY_ADMINISTRATOR，沒有繞過。四戶離線窄畫面 reader 通過；真人 Project 密碼登入 UAT 未執行，Android/iOS 實機依 Owner 暫緩。完整金融整線與全案 Gate 不由本輪宣告 PASS。

歷史：原輪 241＋51／7 個 browser；前輪 255＋65／8 個 browser／69 頁，相關舊發布受阻診斷均為封存歷史。當前狀態以本 PR 最新提交及本輪私人複驗入口為準。
