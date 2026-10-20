# W5 工程驗收裁定｜2026-10-21

核准人：指揮官。依本對話建議核定文與隨後明確回覆「准」，正式採用第2、6項新增驗收範圍，並沿用以下七項條件。此檔為W5線內核准紀錄；原核心策略與中PM最終Gate權責維持。

1. 沿已接收23份行情、原TD9/Swing及正式V82/V75引擎施工。
2. 本輪採快照取得後評估。全球快照可用時間2026-10-19T23:20:09Z；台灣2026-10-20T07:14:26Z。評估不得早於相應時間。本輪不驗歷史當時可用性，historical_pit_verified=false。
3. 商品識別、交易日曆、正式收盤、拆股缺證維持UNKNOWN。NATO.CN不替代NATO LSEETF/USD；六檔缺少台灣債券ETF行情保持MISSING。
4. 未核定KD/EMV、事件/持續狀態、窗口、背離、模糊閾值保持UNKNOWN，候選規則不啟用。
5. 真實行情接收器接FamilyRunner，驗證已知訊號、UNKNOWN傳遞、安全拒絕。
6. 工程正向使用明示SYNTHETIC完整輸入，實際producer→adapter→正式Runtime，無mock與繞線。合成完整predicate是明示工程輸入，補足UNKNOWN僅限SYNTHETIC且原已知值不覆寫；它不是候選規則算法。原partial訊號及來源另欄完整保留。真實行情安全測試與覆蓋分開列。
7. 完成股債計算、四客戶隔離、受影響回歸、Actions與雙端讀回後回交09/18工程驗收。來源缺口獨立保留；Production HOLD、交易NONE；W5 Major/Gate C由Family中PM最終裁決。

## 接線介面

可信context_provider新增technical_source：client_id、family_owner、metadata，以及csv_path/sha256（真實行情）或history（明示合成）。請求technical_source_digest鎖完整source。metadata.history_digest再鎖解析後全history；symbol須等於本次asset_id。每次計算及重送重新驗來源及owner。
metadata.evaluation_mode=SNAPSHOT_AFTER_ACQUISITION；market_region=global/taiwan。UNKNOWN metadata保留；可信bar_receipts仍須提供completed/formal_close_available及完整session對照，僅歷史close_at/available_at不屬本輪驗收。原metadata不修改，衍生TD9/Swing確認時間使用取得後上界並明示模式。
SYNTHETIC完整正向另附synthetic_complete_predicates，欄位順序依technical_source_bridge.NAMES；只作明示輸入值，實際原V82核心作聚合及決策。合成來源及可用時間須明示；真實來源禁止使用該補充。
Family結果technical_intake保留原TD9/Swing、partial signals、數值、來源digest、已知/UNKNOWN及原V82聚合。canonical技術摘要未知者維持UNKNOWN，TD9計數/事件與確認Swing沿原值投影。

## 重現

W5_SOURCE_ROOT指向核定GitHub基線根目錄；依requirements.lock安裝後執行verify_dependencies.py與python -m pytest tests -q。真實CSV/四家人資料與輸出只放私有Drive累計ZIP；CI用合成資料。最新執行證據以ENGINEERING_ACCEPTANCE_RESULT.md與交付ZIP根目錄RELEASE_RECEIPT.json、CI_RECEIPT.json為準。
