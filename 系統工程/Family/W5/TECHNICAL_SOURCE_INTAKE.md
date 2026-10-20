> CURRENT 2026-10-21：已依指揮官核准範圍完成FamilyRunner技術接線及工程驗證，最新成果與範圍詳 ENGINEERING_ACCEPTANCE_RESULT.md；正式工程完成數與最終部署證據以Checkpoint及ZIP根目錄RELEASE_RECEIPT.json為準。以下較早進度段落僅為歷程。

> 最新接收：真實行情23/23核驗並完成既有接收器執行；詳 MARKET_INTAKE_RECEIPT.md 與 evidence/market_intake.json。原history未收到的舊描述已由本筆取代。累計16/18。

# W5-09 指定來源接線實作

依W5_09_SOURCE_MAPPING_SPEC.md（原Doc 1WfxKFSOUQegC4pt8j1YcMMoMuxTYE7JBX7rUY1uGdho）施工。整線仍16/18；09已具名來源接線部分完成，待原始history/可信時間及剩餘規則；16保持完成。18待必要來源齊備。

## 已交付

technical_source_bridge.py::read_history讀完整CSV/CSV.GZ並比對原檔SHA256；build_partial_technical驗解析後history_digest、固定commit、具名instrument/exchange/currency、DAILY/Close、已核對拆股口徑、交易session與逐bar正式Close/available_at、fetch/artifact完成receipt。metadata須由可信來源轉接器提供；本模組不推測交易日曆、ticker別名、收盤或歷史可用時間。

vendor/technical保留原analytics.py、collector.py與v82_engine.py。Git兩檔blob與規格完全相符；Legacy檔SHA與規格相符。technical_source_lock.json加入115項依賴驗證。collector只作來源與格式證據，不執行下載。Legacy經AST只載入原TD9Result、SwingPoint、calculate_td9、confirmed_swing_lows/highs，原函數body不重寫；不載入decide、TechnicalSignals預設值或舊策略。

TD9無cache至少13根，原函數逐前綴保留首次9事件；同方向持續9只記一次。High/Low/Volume缺值不影響有效Close的TD9。Swing用原嚴格比較，只消費有可信completed/available證據的前綴；確認時刻取右側第二根的available_at，保留全部confirmed pivots及尾端待確認sessions。

原analytics.technical對相鄰完整OHLCV前綴實算，保留原公式、nfloat六位小數數值及前後兩筆；比較使用這份固定producer實際輸出。固定32項名稱，已有足夠依賴時映射higher_low、dif_up、MACD正/負柱擴張、三MA鏈；原evaluate_technical聚合，ma20_ok明傳UNKNOWN。其他欄保留具名UNKNOWN、原因與依賴。MA20 above/reclaim與MACD翻正基礎facts另列，不偷換event/state。EMV14、KD原值只保存，不作未核准規則輸入。

## 呼叫與輸出界線

安裝requirements.lock。CLI：

```bash
W5_SOURCE_ROOT=/path/to/baseline python technical_source_bridge.py --history /path/history.csv.gz --history-sha256 ORIGINAL_SHA256 --metadata /path/trusted_metadata.json --evaluated-at 2026-10-21T00:00:00+00:00 --output /path/partial.json
```

metadata完整欄位與明示合成例見tests/test_technical_source_bridge.py::case。原CSV日期不補午夜；metadata帶獨立session_timezone/calendar_reference、calendar_sessions、bar_receipts、source_run與來源reference。輸出Family.W5.PartialTechnical.v1保留原history/metadata/digest、32項signals、原聚合結果與issue_codes；formal_producer_complete=false、execution_advice_allowed=false、NO_TRADE。

本模組是可獨立呼叫的來源接收器，尚未替換FamilyRunner既有stock_evidence；待正式history與metadata/剩餘規則齊備後才接正式完整producer。原FamilyRunner全合成正向維持，未將partial改標完整輸入。此次沒有收到真實行情history/snapshot原件，故新增正向是明示SYNTHETIC；實際source-backed行情結果仍待資料交付。

## 受影響驗證

17項新增測試＋17項既有stock_engine測試＝34 PASS；evidence/source09_tests.log。115來源hash PASS。新增evidence/technical_partial_synthetic.json為原函數＋原V82聚合實算的合成部分結果；三項聚合UNKNOWN保持原三值邏輯。覆蓋13根下限、相等歸零、首次9、HLV局部缺值、Swing右2時點/未完成/相等、future/無時區/缺receipt/拆股/日期連續性、版本/週期/Adj Close錯置、history SHA與日期排序、固定名稱不重複投票。

## 中PM仍需處理

1. 原history、provider/instrument metadata、交易日曆/完成bar/最早可用證據、實際fetch與artifact完成receipt、公司行動/拆股口徑。
2. KD SMA3版本相容性、EMV3,3來源；R3/R7等event/state接口；20日窗口/tie、支撐壓力level、episode、背離配對、持續/快速/明顯等原窄裁定。
3. W5接回後擴充已核定欄位、補驗並接FamilyRunner；09與18屆時結案。0.25ATR與MACD連續2根Candidate保持非執行；不要求家人重填資料。
