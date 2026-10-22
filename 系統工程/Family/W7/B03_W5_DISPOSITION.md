# W7-B03：W5 三十支入口與橋接程式逐檔處置

2026-10-22；責任與施工：Family總PM本人。基準commit `2d569cc9d61bc70538f5dd6e3087d4af5d014e08`。30/30原碼與GitHub內容及Git blob核對一致。本表完成W5頂層30支程式語意盤點；C內部、vendor及WORK12剩餘逐檔處置仍待完成，B03保持IN_PROGRESS。表內「接線」是後續指定工項責任，尚未宣稱正式運行完成。

## 逐檔讀寫與處置

路徑前綴：`系統工程/Family/W5/`。純記憶體指該檔本身無持久寫入；動態模組與間接檔案讀取另外列出。

|檔案|輸入、直接／間接讀寫與輸出|處置及所屬工項|
|---|---|---|
|run_analysis.py|讀request及獨立trusted-context JSON；呼叫FamilyRunner；寫指定output JSON|B08從可信session供應context，B11/B15把完整結果交統一保存；CLI輸出限暫存，非正式DB提交。|
|family_input.py|直接讀SQLite、29表與identity；mode=ro/query_only及前後SHA；輸出完整歷史snapshot|B06下載不可變完整版本後交此唯讀器；B09核對新表投影，保持原身分／跨戶檢查。|
|family_boundary.py|記憶體request/context/snapshot/confirmed target；版本、hash、時點、owner核對；產生PreparedInput及position_view|B08可信上下文；B09清倉與同時點歧義；B14保存完整確認記錄，沿用validate_target。|
|family_runner.py|讀六鎖並動態載入W2 recovery；呼叫各source bridge、pipeline及Mentor；記憶體StagingAnalysisStore|B11/B15接正式analysis_run/result_snapshot；每輪重新核驗context；現有重播只限單一實例。|
|recovery_bridge.py|深複製request、型別化digest、W2測試journal；RLock及_entries只在程序記憶體|B06/B11以持久版本／request冪等接線；保留Decimal編碼、超時不發布及有限重試；不可將此RLock當跨Chat/Actions共同鎖。|
|runtime_loader.py|讀C8C9 Work3～9 Python、frozen_schema_lock及schema；動態載入、有限同名schema重定位|沿用七模組與原schema驗證；C內部另逐檔處置；被鎖定內容變更才更新對應lock。|
|verify_dependencies.py|讀source/dependency/w2/frozen_schema/c7_fixture/technical六鎖及各檔bytes；回傳校驗數|沿用原驗證器；本輪前已完成每日快照分離修正；B10～B12變更被鎖定程式須局部更新與回歸。|
|stock_source_bridge.py|讀W1 instrument/position及permissions投影，核對原生股數；產生stock source與新增買入cap|B09/B10承接最新有效持倉；完整快照才能以缺列代表零；幣別／市場／account映射照原契約。|
|bond_source_bridge.py|讀W1持倉／政策、bond instruments及V75 evidence；產生實體股數與買入限制|B09/B10與股票共用清倉語意；保留SGOV實體與邏輯金額分離；不自行推算券商或匯率。|
|macro_source_bridge.py|讀記憶體macro feed與bond evidence；驗ready/schema/MOVE來源、日期、值；回傳MOVE投影|B10由market_bridge取得已驗證每輪資料；本檔無26小時過期驗證，入口須保留既有P70-5期限驗證。|
|market_bridge.py|直接讀P70-5.py與latest JSON、動態呼叫read_macro；前後bytes不變；輸出commit/hash/reader hash|B10使用固定下載快照及已核實commit；source_commit參數本身不構成遠端核實，可信入口供應。|
|funding_bridge.py|讀可信funding source/version及native owner；間接C8C9 Work6/schema；輸出資金核對結果|B10沿用原來源與雙分支相等檢查；B15持久保存結果，不改資金公式。|
|funding_guard.py|純記憶體精確Decimal、owner/run/claim；輸出股債使用及餘額|沿用保守精度、重複claim及總額限制；B10/B15保存來源與結果。|
|position_source_bridge.py|讀可信prices/FX/NAV、W1股數、native估值；輸出估值及保護政策投影|B09/B10同輪持倉投影；假設總價值須保留來源種類，禁止擅推股數來湊原生介面；沿用缺價/匯率狀態。|
|valuation.py|純記憶體quantity×price×明確FX；輸出KNOWN/ESTIMATED/UNKNOWN與來源|沿用精確換算及估計標記；B10由上游提供同口徑資料。|
|permission_bridge.py|讀歷史position、universe、permission與holding confirmations；間接Work8；輸出existing_holding/retain及保護結果|B09必須連動清倉修正：目前held集合使用任一歷史列，零股最新列仍顯示持有；與position_view共用最新有效狀態。|
|target_source_bridge.py|讀完整W2 confirmed target與C7/native targets；輸出原權重與同幣別金額核對|B14沿用完整record；跨幣別與未決拆分維持原明列限制。|
|bond_target_bridge.py|讀W2每標的目標、bond mapping/policy及C7 drift；輸出逐標原始事實|B10/B14沿用顯式映射、保護旗標與原客戶動作；跨引擎優先序保留既有待定狀態。|
|target_units.py|讀原C7 work6目標／分母與V82 gap；輸出金額、權重、單位及來源|沿用Money與portfolio_weight雙表示；B12/B15保持來源與單位，不新增算法。|
|v70_source_bridge.py|讀獨立V70 tactical context；深複製後綁analysis run，保存original digest|B10/B11保存原run與分析run；宏觀feed不能替代V70金額來源。|
|tactical_budget.py|讀V70 context及settlement；輸出股票／債券cap與原額|沿用原明確金額、風險零上限與SETTLED/AVAILABLE條件。|
|c7_engine.py|讀六鎖；動態import work7.asset_framework及work2～7；讀contracts_c7四schema；輸出完整原碼結果|B12核對C內部讀取器與共用DB接口；保留模組來源衝突檢查、原公式及原始source。|
|family_technical_bridge.py|可信metadata/CSV路徑/hash；間接read_history/build_partial_technical；輸出技術summary並深複製套入bundle|B10保持SYNTHETIC與真實資料分流，無資料時沿用UNKNOWN；B19來源收據要接通。|
|technical_source_bridge.py|直接讀CSV/GZ、metadata、technical lock及vendor；AST只取5個指定原定義；載analytics/pandas/V82；CLI寫output|B10/B19處理真實來源snapshot_available_at目前固定2026-10-19/20的限制，接可信每批收據後測試；既有指標待定規則不重訂。|
|stock_engine.py|動態載V82及C8C9 Work4，讀runtime_output.schema；純計算輸出原生core/deployment/canonical|B11沿用原規則與49/13投影；結果含Decimal/dataclass，正式保存需明確編碼而非直接str。|
|bond_engine.py|動態載V75及C8C9 Work5/schema；輸出predicate、step10、runtime-ready、canonical|B11沿用原評估及money_wire精確定點字串；保存原raw與wire對照。|
|native_pipeline.py|間接股債引擎、Work6/7/8/9、funding/SGOV/protection；輸出完整native_result與trace|B11/B15保存完整同戶同輪結果、原生風險與客戶動作；無正式DB寫入。|
|sgov_bridge.py|讀實體SGOV快照與Work7角色；輸出既有分配、未分配及建議新貢獻|沿用角色守恆；B15建議未成交部分不回填實體持倉。|
|output_bridge.py|間接Work9標準化；讀原stock/bond輸出，回傳動作及完整原件|沿用原映射，B15/B16讀已保存結果而不再計算。|
|mentor_bridge.py|間接Work9重建核對，直接讀固定SHA reason_catalog；輸出繁中說明與原證據|B11/B16沿用原事實／未知代碼狀態，完整保存來源；模型不得變更金融結果。|

## 本輪具體發現與驗收責任

1. B09清倉不能只改family_boundary.position_view：permission_bridge.project_permissions亦需共同投影。合成歷史10股→最新0股的實測記於evidence/B03/w5_semantic_probe.json；現行existing_holding與retain皆為true。這是已重現、尚待B09修正的接口問題。
2. 同時點同標的兩列，position_view會採輸入先後；下游股債bridge有歧義拒絕，B09應在共同投影入口明確處置，不以排序選一筆。
3. technical_source_bridge的真實snapshot模式使用固定地區收件時間；B10/B19接線須使用可信當批收據，避免新資料仍帶舊可用時點。原W5凍結驗收意義保持。
4. 正式持久化集中B06/B09/B11/B14/B15；原StagingAnalysisStore記憶體重播及CLI JSON均非正式DB持久層。B04先證實平台可信session與共同寫入能力。

本輪為B03必要語意處置及缺口定位；未改投資公式、既有runtime、DB或正式報表。原W5 PASS維持。下一步由本人完成C／vendor／WORK12其餘清冊，再簽B03進B04。
