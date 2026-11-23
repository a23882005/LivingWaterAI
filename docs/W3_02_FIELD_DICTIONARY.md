# W3-02 唯讀 Reader｜欄位與執行說明

版本：W3 v1.6；完成範圍：W3-02。來源commit固定00fc36bc20736c4083b890ed3503324e88afee16。

依W3-01已完成盤點，補讀正式W3 v1.6包、W2-22包、V70完整程式包，以及原研究交接包的程式索引。現存builder/行情更新器/研究生成器均有上游建置、網路下載或研究計算責任，沒有可重用的通用唯讀市場reader。新增唯一正式程式`scripts/pv70_5_reader.py`；`config/p70_5_source_lock.json`是來源鎖定設定；tests是驗收工具，沒有新增第二個Runtime、API、爬蟲或排程。

執行：
`python staging/scripts/pv70_5_reader.py --repo frozen --commit 00fc36bc20736c4083b890ed3503324e88afee16 --out staging/build/pv70_5 --generated-at-taipei 2026-10-20T15:00:00+08:00`

輸出：`reader_result.json`，schema=`LivingWaterAI/p70-5-reader-v1`。這是W3-02解析結果，不是尚未施工的W3-04正式market_context/envelope。

| 欄位 | 定義 |
|---|---|
| source_commit | 此次來源凍結commit；與外部lock不同即BLOCKED |
| value_state／issue_codes | 解析整體結果及明確錯誤；必要檔案/狀態失敗即BLOCKED |
| source_files[] | path、source_commit、git_blob_sha1、blob_sha256、size、producer、use_class、schema、data_date；兩種雜湊分欄 |
| macro18／macro8 | 保留來源完整原始object。18個獨立指標有19個傳輸item，s03與m07重複VIX；不刪除原欄 |
| formal_feed | 唯一canonical原始v3全文；不加研究欄、不改原schema、不重算分數 |
| wallstreet5[] | 原forecast列放raw，外層標DISPLAY_ONLY；不進正式計分 |
| daily_macro_history[] | 原始每日CSV逐欄字串；保留歷史source_commit，不要求歷史事件commit等於本次檔案commit |
| quotes[].value | 原CSV最後有效原始Close；Adj Close獨立adjusted_value，絕不替代 |
| quotes[].source_csv_line | 含表頭的CSV行號；能逆查原始列與來源SHA |
| quotes[].currency／exchange／instrument_id | 只讀已存在的來源證據；目前manifest未提供時保持null，issue為INSTRUMENT_IDENTITY_EVIDENCE_MISSING；不按代號猜幣別/交易所 |
| quotes[].status／raw_status | 保留manifest原狀態；value_state另外表示該報價解析可用程度 |
| quotes[].date_validity_state | NOT_EVALUATED_REQUIRES_REQUEST_POLICY；交易日曆與新鮮度是後續W3-04按可信請求政策驗證 |
| generated_at_taipei | 固定輸入時間或原feed asOf換成Asia/Taipei；實際執行時間另記log，支援同輸入bytes重現 |
| research_assets | W3-02保持空列表；完整索引由W3-03產出，不把候選數據送入formal_feed |

負向處理：缺檔、SHA/大小不符、錯schema、壞JSON/CSV、重複JSON key、非有限數字、manifest筆數/日期不符、來源commit混用，均保留明確issue並BLOCKED。路徑跨出repo遭拒，輸出若位於repo內僅准寫build/，避免覆寫來源。

實際凍結來源結果：成功讀取31份來源，組裝29筆manifest標的（23個有CSV、6個來源標為MISSING）。六個缺檔使整體BLOCKED、CLI exit=2，這是預期的資料狀態，不把來源缺口改成0。23筆原始價格及原始Macro資料仍逐列保留。受控合成fixture提供完整證據時，P01讀出OK；12項單元測試及P/N/B通過。

測試：`python -m unittest discover -s staging/tests -p test_pv70_5_reader.py -v`。socket/create_connection已在唯讀重現測試中攔截；請求數0，115份原始來源前後SHA一致。同固定時間、commit、設定重跑輸出SHA一致。
