# BR來源口徑裁定 v0.3.1

日期：2026-10-21。裁定責任：Family中PM。這是v0.3的文件與來源核對補充，執行程式及歷史CSV不變。

## 已定案的計算口徑

|用途|採用欄位／規則|適用限制|
|---|---|---|
|既有技術指標|原程式的Close／High／Low；依供應商定義為拆股調整口徑|auto_adjust=False不表示未拆股原始價格；不得再對整段套拆股倍率|
|既有績效參考|原程式的Adj Close；沿用Yahoo調整價稅前近似報酬|已包含供應商配息調整，不再額外加一次Dividends；不是家人實際稅後入帳報酬|
|持股股數與交易現金|券商持倉、公司行動及現金帳本分別核對|調整價不能直接與不同拆股基準的歷史股數相乘；不得把配息事件日當實際入帳日|
|歷史當時可得性|沿用原快照收集完成上界與用途限制|CSV日期不是當時發布時間；不能倒填歷史版本|

核定範圍是重用既有程式的計算慣例，不新增績效模型，也不改W6六級攻防表。前版「配息報酬口徑尚未找到」已由原始程式證據補足；原始receipt未填寫的欄位保持原樣，另由本裁定說明。

## 原始工程證據

來源repo：emmanuelwithme/OpenDataStockAnalysis，固定commit cd1e1dbc9fd7e226a0c31efe80def9ffb5f947cb。

- yahoo_pipeline/yf_pipeline/collector.py：SHA256 b4cc1f5e827c98d1e6898c3534c7f81aaea98e880e5a75dfd7b6b5dd6fea3967。W5 vendor副本與來源鎖一致。fetch採1d、period=max、auto_adjust=False、actions=True、repair=False。clean移除時區並正規化為日期、同日去重、缺少事件欄位時填0。因此單憑事件0值不能證明當日絕無事件，日期也不能還原發布時點。
- yahoo_pipeline/yf_pipeline/analytics.py：SHA256 2034cc9fb49e4659e55bcb16d96169f4f7b89c1c0b5d4bb0bca998b1f728aa19。technical使用Close/High/Low；performance只對Adj Close計算CAGR及回撤，已有total_return_basis標示稅前近似。該函式未再把Dividends加進報酬。
- 上述證據固定原程式意圖與行為；未證明每個歷史值、下載時的第三方套件環境及事件調整均無誤。

## 官方說明（2026-10-21查閱；不是歷史發布憑證）

1. yfinance Price adjustment：https://ranaroussi.github.io/yfinance/advanced/price_adjustment.html 。官方說明auto_adjust=False提供Yahoo拆股調整OHLC及另含配息調整的Adj Close。此頁支持欄位慣例，不能取代逐檔品質驗證。
2. yfinance Price Repair：https://ranaroussi.github.io/yfinance/advanced/price_repair.html 。官方列出缺少拆股／配息調整及修復誤判的可能。原collector的repair=False不能當作已修復證明；也不應直接開repair=True覆寫既有來源。
3. Yahoo Adjusted close：https://help.yahoo.com/kb/SLN28256.html 。搜尋索引可讀到拆股及股息調整的定義；本輪直接開頁429，僅列輔助來源，主要裁定依前兩項及已鎖原碼。

## 正式缺口處置

|原項目|本輪裁定|剩餘完成條件|
|---|---|---|
|拆股／還原口徑|PROVIDER_CONVENTION_CONFIRMED；重複還原禁止|個別資料的split_basis_verified保持未核定。對所選正式歷史案例以發行人／交易所公司行動、價格與股數基準交叉核對|
|配息報酬口徑|EXISTING_PRETAX_PROXY_CONFIRMED；既有參考績效慣例結案|若需要家人實際現金／稅後報酬，另需入帳、稅與再投資證據；目前不聲稱具備。所選歷史案例仍需事件調整品質核對|
|歷史發布／修訂時間|NOT_RECOVERABLE_FROM_CURRENT_SNAPSHOT_ALONE|找既有按時存檔及可信receipt；沒有時不得補造。只能以確實取得時間之後的快照支援已允許用途|

23份CSV與29筆拆股／2223筆配息的存在及hash一致性已由v0.3驗證。本裁定不把這些數量當逐筆外部核實通過。

BR工程回歸PASS_WITH_DECLARED_SOURCE_GAPS沿用；BR正式Major仍OPEN_SOURCE_EVIDENCE，W7 NOT_RELEASED。Registry與市場口徑守衛均不放寬，未改任何verified欄位。此前60項測試及92項邊界驗證是v0.3證據，本次只核對來源及文件，不宣稱重新執行。

下一責任仍Family中PM：集中定位既有時間版本檔與所選案例的公司行動正式證據，再依原BR-03／07／08作裁定。不再重做已通過的重播框架，不為W6增加精算研究。Production HOLD；交易NONE。

相依：本裁定、BR_REVIEW、README、Checkpoint、Manifest與集中ZIP，以及Family施工管理、Family檔案管理、根目錄索引同輪同步。原W5/W6程式、報告、工作簿、圖表、正式DB不受影響。
