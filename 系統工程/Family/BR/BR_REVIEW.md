# 最新收尾｜BR v0.3.2

2026-10-21：收尾裁定與工程成果接收完成；完整run_all重新執行PASS。見CLOSEOUT_DECISION.md及evidence/handoff_review/。BR正式整線OPEN_SOURCE_EVIDENCE與W7 NOT_RELEASED保持，剩餘03/07/08證據具名交接。下一對話由Family中PM重新規劃W7並接續推進；現有W7草稿僅供參考。

---

# 最新補充裁定｜BR v0.3.1

2026-10-21：原collector及analytics來源SHA核對一致；拆股欄位慣例與既有Adj Close稅前近似績效口徑已確認，禁止重複還原／重複加息。詳細證據及正式剩餘條件見SOURCE_ADJUDICATION.md。

工程PASS維持；逐案例公司行動品質與歷史發布版本證據尚待補齊，BR正式Major OPEN_SOURCE_EVIDENCE、W7 NOT_RELEASED。原Registry未升格，執行程式未改。既有60項測試、92項邊界驗證沿v0.3，本次未重跑。以下舊紀錄由本補充更正口徑狀態。

---

# Family中PM｜BR v0.3 整線工程檢查

日期：2026-10-21。責任人：Family中PM（本對話）。

裁定：本輪既有資料範圍的工程回歸 PASS_WITH_DECLARED_SOURCE_GAPS。
BR正式Major Gate：OPEN_SOURCE_EVIDENCE；W7 NOT_RELEASED。
本裁定保留原Master的歷史可重播要求，完成工程回歸與正式歷史READY分開記錄。

## 已完成
在獨立乾淨目錄，透過run_all.py一次執行全部流程：
- 60項測試通過。
- 原W5兩個全新FamilyRunner重新計算，完整結果與既有Golden相符；只依原W5契約新增technical_intake=null。
- 115項原W5依賴驗證；184份引擎與測試來源固定。
- 原W5輸入／context／結果形成32節點來源圖；1帳戶3持倉逐值保留。多帳戶、未知及零值另外有測試。
- 23份既有真實歷史CSV、104,788筆資料，檔案及canonical rows雜湊核對通過。
- 23來源登記完成；92項實際來源時間／用途邊界檢查通過。
- Registry SHA256：86e2814a73a2e5799b7f5ff4405dbf3de73451dba271da456bccc70912b1ee5c。

## 原九項工序對照
|工序|本輪證據|工程狀態及保留事項|
|---|---|---|
|BR-01 範圍固定|README、run_all、Checkpoint|已完成；策略優劣比較另案|
|BR-02 決策／持倉事件|event_capture、test_capture_basis、clean_run/w5_captured_event.json|已接原W5；分析前後實際持倉相同，完整輸入與版本保存|
|BR-03 可得時間／版本|select_vintage、source_registry、registry_checks|快照收集時間選擇已完成；歷史每根K棒發布證據OPEN|
|BR-04 版本固定|source_lock、requirements.lock、W5依賴驗證|已完成本次可重播版本固定|
|BR-05 來源追溯|verify_capture、verify_lineage、registry檔案與receipt校驗|輸入到結果圖與外部快照登記已完成；來源權威由原證據支援|
|BR-06 決定性重播|run_w5_replay、clean_run/w5_replay.json|已完成兩次實算與完整Golden比較|
|BR-07 未來資料／公司行動|market_basis、test_capture_basis、history_audit|口徑守衛及真實事件盤點已完成；還原與配息正式口徑OPEN|
|BR-08 固定歷史案例|原W5合成正向Golden＋23真實歷史快照邊界案例|已有可重現工程基準；完整歷史策略正向案例待來源證據|
|BR-09 證據整包|run_all、RUN_STATUS、MANIFEST、PR24、Drive|本輪整線檢查與交付完成；正式Major保留來源待辦|

## 三類來源待辦與責任
|項目|現有證據|尚需證據|責任／完成條件|
|---|---|---|---|
|歷史發布時間|快照收集完成時間與不可回填的時間選擇已實測|所選歷史觀測值當時的發布時間及修訂版本|Family中PM沿既有資料線來源定位；固定可核對來源後才標HISTORICAL_READY|
|拆股／還原口徑|原CSV保留Close、Adj Close及29筆Stock Splits；split_basis_verified為未核定|價格與股數調整基準的正式來源說明／證據|Family中PM協調原資料契約；確認後輸入既有market_basis守衛，避免重複還原|
|配息報酬口徑|原CSV保留2,223筆Dividends|總報酬或現金配息計算口徑、含稅／未稅設定|Family中PM定位正式口徑；確認後以已建立的重複計入負測驗收|

FX正向與負向守衛已完成工程測試。本輪沒有以合成匯率代替家人真實歷史匯率；需換匯的歷史案例仍依既有來源契約取得當時匯率。

## 接續方式
下一步由Family中PM本人處理上述來源契約與證據定位，維持原BR九項，不再增加相同功能的程式或反覆重做已通過工程。證據補齊後，沿run_all既有入口重跑受影響案例，作BR正式Major裁定，再交W7。

Production HOLD；交易NONE；W1／W2／W5／W6原驗收維持。
