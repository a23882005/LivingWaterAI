# BR v0.3.5｜可信封存時點與真實資料重播覆核

2026-10-21，Family中PM本人施工、另階段自覆核。

## 最新指揮官指示

本輪集中完成BR。W7於BR結束後先與指揮官討論規劃，再決定施工；原W7 v1.1僅保留討論基礎。W7保持NOT_RELEASED，這次沒有W7施工。

## 03：取得獨立封存時間證據

GitHub Actions run 39340856153（global行情收集），artifact 12228981182，GitHub記錄之archive SHA256為73be7654674f4b085c6337e8f148846e92bf5459df13ce0b22dbbfe85adbbd0a，2540288 bytes。實際從GitHub下載與原W5 global.zip逐位元相同；VOO.csv內含4052列，hash與W5一致。

Artifact建立/上傳完成2026-10-19T23:20:09Z；job 118361756593成功結束23:20:14Z。本輪採更保守的job完成時間作可得上界，固定重播cutoff為2026-10-20T12:00:00Z。這個時間證據來自GitHub平台回覆，並非Git提交者自行填寫的時間。完整receipt與ZIP存evidence/capture_proof/。

runtime/capture_receipt.py核對release pin、run關聯、job/upload成功、時間順序、後續revision、ZIP hash/size/CRC及member hash。cutoff早於上界拒絕；等於上界接受唯讀重播。每筆歷史row沿此封存上界可用；此結果未證實更早的逐bar首發時間。

## 06/08：完成兩類真實來源實算

- 正向數值重播：從已核實archive選2026年200筆原行情，實際呼叫鎖定原W5 vendor analytics.py兩次；六個均線、三個量比及兩個TD9計數，共11欄，與獨立Decimal算術/反向連續計數參考完全一致。輸入不改值，不新增策略參數，不評價策略績效。
- 原W5安全案例：原VOO.family_request/context/result，在僅遷移CSV絕對路徑並重綁對應digest之後，兩個全新FamilyRunner實算與原完整Golden逐欄相同，結果DATA_UNAVAILABLE、NO_TRADE。呼叫者/其他context為原合成fixture，市場來源真實；不標為全真實策略正向。
- 結果evidence/capture_proof/replay.json、evidence/capture_full_run/capture_replay.json；全部run_all為83測試PASS、115依賴/184來源、原合成全引擎Golden、23CSV/92邊界、官方來源核驗、真實來源數值/安全重播全部PASS。

## 整線驗收仍有的具體差距

既有CLOSEOUT_DECISION.md要求已核實公司行動/價格股數基準及原W5完整歷史正向案例。本輪證明封存後可得性與真實數值正向，尚未滿足該完整策略條件。原W5 technical_source_bridge.py明列未核定規則：KD平滑、EMV事件口徑、MACD事件/狀態、MA20站上/重返、ATR快速擴張門檻、RSI背離配對及基本面輸入等。原test_partial_known_signals_preserved_and_unknown_not_promoted要求缺項保留UNKNOWN、整體不返回OK。

價格基準個別核驗仍有原記錄缺口：供應商2013事件日與發行人收盤生效映射、完整價格/股數調整基準；官方配息資料只對上已公布精度。新增capture reader不把這些欄位升格，也沒有改原SourceRegistry的決策拒絕。

因此本輪正式狀態仍為BR OPEN_SOURCE_EVIDENCE，historical_ready=false；完整策略正向=false。PR24維持Draft。通過測試數是工程證據，沒有取代整線完成條件。

## 已備妥的驗收範圍裁定建議（尚未核准）

Master原BR定義為未來回測準備、固定歷史片段重播，非完整投資策略/績效研究。建議指揮官明確裁定：BR以版本/時點/來源/公司行動守衛及固定數值與原引擎安全重播完成工程驗收；全真實投資策略正向與未核定規則留在既有W5來源覆蓋待辦，仍由同一中PM負責，Gate D前置依正式裁定另同步。這會修訂既有BR收尾文的完整策略正向條件，現階段只作具體提案，沒有自行放行。

若維持收尾文原完整策略正向條件，下一工作是定位/核定上述規則與來源、補所選價格股數基準，再做原W5真實正向接線；由中PM本人負責，無需指揮官重交持倉。

Production HOLD、交易NONE、W4取消、RM17凍結；W5/W6原工程PASS保留。
