# B03：W2 目標來源納管與 W6 逐檔處置

2026-10-22。由 Family 總 PM 本人循序施工。B03 IN_PROGRESS；原 W2/W6 驗收沿用。

## W2 已完成

從 H2 已核實的 W5_FULL.zip 取出兩支目標產生端、兩支原測試及兩份 SYNTHETIC_TEST_ONLY fixture，原 bytes 不變，放在本目錄 vendor/w2/。w2_target_source_lock.json 記錄原包成員、目的地與 SHA256。兩個產生端均僅依賴 Python 標準函式庫，在記憶體處理輸入並回傳草案／確認紀錄；不自行寫 DB。

原測試 9/9 PASS：草案資金限制、跨幣別分桶、重複資料、身分、雜湊穩定性、明確確認、過期、重試與版本競爭。新增 tests/test_w2_target_compatibility.py 4/4 PASS：完整 CONFIRMED 記錄 JSON 往返後通過原 W5 validate_target；跨戶、確認證據竄改、目標比例竄改皆拒絕。

本次新增獨立來源 lock；W5 六份歷史 lock 及原碼不動。後續 B14 保存的是完整 canonical record 與確認依據，並經受信任身分入口寫入本人 DB。此次相容性驗證為記憶體/JSON seam；正式 DB 關閉重開及同 Project 接續仍由 B14 驗收。

## W6 六支程式處置

原件位置：W6_FINAL.zip / sources/rebuild/src_v16/；逐檔 SHA 見 evidence/B03/missing_github_sources.json 的原始盤點。檔案中既有家人專屬文字與舊輸入相依，原件保持 Drive 保存，後續 B16 以參數化程式鏡像 GitHub；私人輸入仍由 Drive 取得。

| 檔案 | 直接輸入 → 輸出 | 接線處置 |
| --- | --- | --- |
| report.mjs | report_data.json → blocks.json、assets SVG、report.html | 沿用章節與圖表；核對姓名與敘述改由當輪輸入提供。money/pct 對 null/空值的處理須補明確缺值判斷，避免 Number(null)=0。 |
| render.mjs | report.html、字型、Chromium → pagination.json、頁圖、PDF、更新 HTML | 沿用分頁/溢出檢查；瀏覽器路徑、頁尾身分、輸出檔名參數化，等待圖片錯誤須有明確失敗結果。 |
| reader.mjs | 最新母模 mother.html、pagination.json、頁圖 → index.html | 最新 Drive 正式母模讀回後使用；姓名、標題、路徑改由工作身分與產物目錄決定。 |
| workbook.mjs | 舊 v14 XLSX、當輪 report_data.json、pagination.json → XLSX、公式檢查、預覽 | 舊工作簿含歷史家人資料，先清楚切分模板/輸入；固定 18 列範圍與專屬文字改由當輪列數/來源決定，公式與章節映射保留。 |
| validate.mjs | 報表資料、分頁、閱讀器 → qa.json | 原瀏覽器功能檢查沿用；輸出路徑/瀏覽器參數化，頁數與章節契約採正式母模而非散落常數。 |
| package.py | XLSX、v15 sources/Checkpoint、runtime/src/QA → CSV、Checkpoint、manifest、ZIP | 沿用 SHA/CRC；改成明列輸入及當輪正式治理狀態，避免把 v15 舊驗收敘述和固定家人資料重新包入新報告。 |

外部程式相依：Node 標準 fs/path、playwright/Chromium、@oai/artifact-tool；Python openpyxl 與標準庫。資料/模板相依：report_data.json、mother.html、舊 v14 工作簿、v15 sources/Checkpoint、字型與頁圖。由 B16 依本清冊接線並做實際視覺驗收；本輪不重產客戶報表、不改 RM17。

## 接續

B03 尚餘其餘 W5/C/WORK12 逐檔語意處置與每日資料版本鎖實作/對應測試。本人完成後才進 B04。正式 W7 0/29；Production HOLD、交易 NONE、W4 取消、RM17 凍結。
