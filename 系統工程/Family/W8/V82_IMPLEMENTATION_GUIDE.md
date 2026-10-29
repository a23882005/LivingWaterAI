# V82 核准 v1.0 實作與驗收對照

2026/10/30，PR59，由Family中PM獨立驗收。起點27d41bd，保留中PM查核38ff92c與後續主鏈查核7fb0630，第一段原生函式f6ddf599。沿用原selector、九階比率、gap、資金MIN、共同保全、Work9及Mentor；沒有另開簡化版。

## 授權與版本

Owner本輪交辦及交接00～03為施工授權。正式實作DOCX SHA256 `816adc16dc23d982a327e0c99a8cfba992a5fb3a58cfeb5ec10bcdf61cdc9a4f`；交接ZIP `93aff27cd3530ce4555e233ff7a26cc1436f79d1e8f4163943970503b7822301`（24份manifest通過）；Fresh Read V82.md v1.21.0 `392e54808c33cce99e3567f0e8942650ad50b382d9fc87acbbe20f012b568372`。

擴充版本為 `V82_APPROVED_IMPLEMENTATION_1.0`；凍結package 0.9.0保留其封存意義。本次deployment精度修正另具名 `V82_EXECUTION_DECIMAL_1.0.1`，保留原MIN及門檻，避免高精度cap先四捨五入跨過legal lot邊界。49 canonical／13投影欄位不擴充；profile、來源、限制與帳本走sidecar。來源鎖保留上游hash、授權與修改範圍，共121份逐一校驗。

## 規則、函式、測試

原生模組位於 `股票V80/正式Runtime/v82_runtime_greenfield/src/livingwater_v82_runtime`；測試主要在 `Family/W5/tests`。

| 契約 | 實作與接線 | 主要測試 |
| --- | --- | --- |
| 自身估值qV／PIT修訂／midrank／yield反向；10→5→合法制度期 | own_history.valuation_percentile | test_v10_own_history |
| 原close／split／gross現金wealth、252日高、peak63日sigma及月末qP | own_history.own_wealth、price_percentile | test_v10_own_history、test_v10_stage4_acceptance |
| B2～B7、高階UNKNOWN、nesting、11類／6個range／明確N/A | approved_profiles.left_profile、absolute_range、resolve_approved_stage | test_v10_profiles |
| 具名Stage限制；typed DSL，無eval或不透明truth票 | constraint_expression、apply_restrictions | test_v10_profiles |
| 完整Right／事件相依T+1、Up/Down衝突、Trend8／9 | right_entry、event_recheck、select_with_entries；共同approved_decision.evaluate | test_v10_profiles、test_v10_stock_integration；W8/test_v82_approved_context |
| M八槽去重三值、模式率、信用／總經／估值乘數 | daily_slice.maturity、speed | test_v10_daily_slice |
| Trend新增時機三值、保留Mode及Target | daily_slice.trend_timing；approved_v04_technical前一prefix | test_v10_daily_slice |
| 固定G0/B0、spent/live committed、取消待確認、跨日GTC | cycle_id、open_cycle、cycle_room、update_intent、CycleLedgerStore | test_v10_daily_slice |
| slice／費用／共享cap接既有MIN、legal lot向下 | approved_decision.slice_cap → stock_engine → 原build_buy_execution_plan | test_v10_stage4_acceptance、test_v10_stock_integration |
| 同現金桶按切片比例→V70剩餘額度／FX／不重分配餘額 | slice_allocation.allocate；原funding_guard.check_aggregate | test_v10_slice_allocation、test_v10_family_cycle |
| 防守SGOV／可動用SGOV／現金／已結算分層 | slice_allocation.funding_layers及既有SGOV橋接 | test_v10_slice_allocation、test_v10_stage4_acceptance |
| 原FamilyRunner→Work9／統一Mentor、首次cycle/intent原子保存及冪等 | v82_slice_bridge.bind/ensure_cycle/finalize、family_runner、native_pipeline | test_v10_family_cycle |
| 報告與原生部署同源；每次hash／owner／時間重驗 | W8/v82_approved_context.build/validate、formal_mode_analysis、current_analysis_delivery | W8/test_v82_approved_context、test_holdings_analysis |

## 實際來源與帳本介面

原AssetSourceProducer可信 `context_seed.v82_approved_sources[symbol]` 指向 `{local_path,sha256}`。原件schema為 `Family.W8.V82ApprovedSource.v1`，必含client_id、完整owner、asset_id、實際source_db_sha256、available_at及source_reference；來源不由選單payload任意注入。股票Thesis與ETF結構分開，股票不套ETF安全判定。

可填price_history／valuation_history，各自仍須通過原生listing／share class／幣別／provider／method／時間／日曆及公司行動契約。absolute_range_proof須帶profile、已驗產品類型、版本與生效區間；N/A有明確來源。stage_restrictions使用具名AND/OR/NOT/TRUTH及已知值比較DSL；額外stage_constraint_facts必帶KNOWN、snapshot、source及rule_version，不能覆蓋qV與A等原生事實。未知限制不猜成不適用。

完整Right使用原生技術R、off_low、基本面、信用、非Down、適用估值與right_event_dependencies；事件範圍明確驗證後，空陣列才表示無相依事件。缺自身歷史、Thesis或事件來源時輸出具名UNKNOWN，不退回無切片Maximum。現行SOURCE_BACKED輸入不能省略核准新契約走舊路。

planning_ledger_source帶owner/local_path/source_reference/planning_write_authorized。操作端可明確初始化新的本地planning SQLite容器，但不能因此宣稱全部券商訂單／成交已知；讀取不存在帳本不會建立空帳。真實session必帶交易所、calendar/version、起迄與是否開放planning，交易事件須來源receipt。

分析只提出首個cycle，不提前寫入。原Family保全及Work9／Mentor通過後，在SQLite同一transaction重新檢查原共同資金保全，再將固定G0/B0與PLANNED intent一起CAS保存，最後才發布。這是建議占額，沒有券商送單或現金reservation；相同request/intent重跑新增占額0。後續request重讀最新cycle；跨日舊GTC留原cycle並納入實際Active曝險。正式Drive掛載、跨機同步、session與券商事件receipt屬操作端實際來源，不能以本地驗證冒稱已部署。

## 同輸入正向與邊界

明示合成歷史、價格100、lot1、已知費用；ProjectTarget1,000,000，Stage4／45%，Confirmed250,000＋ActiveBuy50,000，Projected300,000，Gap150,000。M成熟、乘數1：slice37,500；M未成熟22,500。現金100,000／200,000未給slice時，原元件分別輸出100,000／150,000；接上slice均37,500。只有現金20,000則取20,000。

已授權現金20,000＋可動用SGOV80,000，規劃池100,000、結算額20,000分欄，原MIN仍只給20,000，不自動售出SGOV。高精度cap19,999.999…／價格100僅199股、19,900，避免四捨五入成200股。Gate關時合法Right仍保留Stage8／Target／Gap，新增0；Left依安全條件FALSE，必要原始UNKNOWN仍保留。

另有真正FamilyRunner合成正向例穿過原C7／Work9／Mentor與持久帳本；同worker及新worker重跑不重複占款，同池既有本地計畫超額時發布0次、無新intent。完整原始fixture、輸出、call trace、digest與JUnit保存在私人回交包；這些不是實際行情、投資績效或真人下單驗收。

## 回交邊界

本輪改檔／測試／實跑結果見最新Checkpoint與查核紀錄。新增CI只跑合成W5/W8回歸，不讀私人DB、不碰券商。V75衝突施工暫停待DOT；既有SGOV／SPSB查核不重做。MOU核准SGOV20%與Joseph正式目標保留，不展開Arthur/Lilian。圖文Gate／UNKNOWN、range與SGOV分層修訂由中PM協調。

程式接線與真實來源完整度分開驗收；兩戶C7或必要來源未過即明列欄位及契約，不宣稱全功能完成。Production HOLD、NO_TRADE，中PM獨立驗收尚待執行。
