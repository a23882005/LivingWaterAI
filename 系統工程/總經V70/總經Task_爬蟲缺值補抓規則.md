# V70-3-27 V3｜10:00「總體經濟狀況」Task 補充資料交接規格

**最後修改：2026-10-17（台灣時間）**  
**適用版本：V70-3-27 V3**  
**用途：規範10:00總經Task查核八項補充資料，供11:00 GitHub Action建置。**

## 一、工作分工與輸出

1. 先讀取主分支 `data/18_macro_verification.json`，核對09:00核心資料的生成時間、日期、來源及狀態。核心爬蟲提供18個獨立指標及重複欄位s03。
2. 本Task查核並產出 `data/8_macro_supplement_verified.json`，items必須恰好包含八個鍵：`m06_rate`、`m06_inf`、`m06_rstar`、`m06_output_gap`、`s05`、`m03_qqq`、`m03_spy`、`m03_vt`。
3. 每個變數查核四個候選網站並逐站記錄URL、查核時間、期間／定義、數值及結果。候選網站是交叉查核清單，不可把不同口徑的數字混合或平均。
4. Task負責查核、八欄JSON、總經研究及報告；不直接改HTML，也不宣稱Action或線上發布成功。缺值或證據不足須如實標MISSING／STALE／UNVERIFIED。

## 二、八項資料與候選網站

### m06_rate｜Fed目前目標區間中點（%）
候選：Federal Reserve政策頁 https://www.federalreserve.gov/monetarypolicy/openmarket.htm；FRED DFEDTARL https://fred.stlouisfed.org/series/DFEDTARL；FRED DFEDTARU https://fred.stlouisfed.org/series/DFEDTARU；ALFRED DFEDTARU https://alfred.stlouisfed.org/series?seid=DFEDTARU。  
使用同一有效日期的官方目標區間上下限求中點，不可用有效聯邦基金利率代替。

### m06_inf｜未來12個月通膨預期（%）
候選：Cleveland Fed https://www.clevelandfed.org/indicators-and-data/inflation-expectations；NY Fed SCE https://www.newyorkfed.org/microeconomics/sce；University of Michigan https://www.sca.isr.umich.edu/；Philadelphia Fed SPF https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/inflation-forecasts。  
主來源Cleveland Fed；備援依序NY Fed SCE、Michigan。Philadelphia SPF作交叉核對，除非預測期限確實相同且有記錄，不得冒充滾動12個月預期。5年損益平衡通膨率不得代替此值。

### m06_rstar｜NY Fed HLW實質自然利率r*（%）
候選：NY Fed r-star https://www.newyorkfed.org/research/policy/rstar；HLW real-time estimates https://www.newyorkfed.org/medialibrary/media/research/economists/williams/data/Holston_Laubach_Williams_real_time_estimates.xlsx；HLW current estimates https://www.newyorkfed.org/medialibrary/media/research/economists/williams/data/Holston_Laubach_Williams_current_estimates.xlsx；NY Fed Staff Report 1063 https://www.newyorkfed.org/research/staff_reports/sr1063。  
正式值採HLW即時版本；current estimates及報告作最新值／方法交叉核對。歷史研究保留當時可得vintage，不以今天修訂值回填。

### m06_output_gap｜實際GDP相對潛在GDP產出缺口（%）
候選：CBO經濟資料 https://www.cbo.gov/data/budget-economic-data；BEA NIPA https://www.bea.gov/itable/national-gdp-and-personal-income；FRED GDPC1 https://fred.stlouisfed.org/series/GDPC1；ALFRED GDPC1 https://alfred.stlouisfed.org/series?seid=GDPC1。  
必須有一致定義的實際GDP與潛在GDP、觀測期、發布日及vintage；不可用ISM、NFP或GDP單獨水準冒充產出缺口。

### s05｜NYSE全市場站上50日均線股票百分比（$MMFI，%）
候選：Macroaxis https://www.macroaxis.com/index/MMFI.INDX/Percent-Of-Stocks；Barchart https://www.barchart.com/stocks/quotes/$MMFI/technical-analysis；EODData https://www.eoddata.com/stockquote/NYSE/MMFI.htm；TradingView https://www.tradingview.com/symbols/INDEX-MMFI/。  
確認NYSE母體、50日均線定義、0–100百分比和觀測日；不得以S&P 500或Nasdaq廣度代替。

### m03_qqq、m03_spy、m03_vt｜ETF Forward P/E或FY1（倍）
每檔四個候選來源如下：

| 指標 | 候選來源（依序） |
|---|---|
| m03_qqq | Yahoo Finance QQQ；Invesco QQQ；Portfolio Visualizer；StockAnalysis QQQ |
| m03_spy | Yahoo Finance SPY；State Street SPY；Portfolio Visualizer；StockAnalysis SPY |
| m03_vt | Yahoo Finance VT；Vanguard VT；Portfolio Visualizer；StockAnalysis VT |

只接受頁面明確標示Forward P/E、Forward或FY1的未來預估值。TTM或未標明期間的P/E不得冒充Forward；找不到可驗證值時設MISSING。

## 三、m06 V3衍生公式

Task提供四個有日期、有來源的原始值，不手填衍生m06。建置器按下式計算，單位為百分點：

`實際實質利率缺口 = m06_rate − m06_inf − m06_rstar`  
`Taylor基準缺口 = 0.5 × (同一個m06_inf − 2.0) + 0.5 × m06_output_gap`  
`m06 = 實際實質利率缺口 − Taylor基準缺口`

兩處使用同一個未來12個月通膨預期m06_inf，不再另抓Taylor通膨欄。四個原始輸入任一缺漏、未驗證或日期／來源無效，衍生m06即MISSING。分數門檻以正式HTML為準。

## 四、JSON欄位與品質檢查

頂層包含`schema`、`generated_at`、`as_of_taipei`、`items`。八筆資料各包含`label`、`value`、`unit`、`observation_date`、`source_url`、`method`、`status`、`detail`、`retrieval_time`、`publication_date`、`vintage`及`candidate_checks`。每筆`candidate_checks`恰好四筆，欄位為`site`、`url`、`metric_or_horizon`、`status`、`checked_at`、`value`、`unit`、`observation_date`、`notes`。

候選查核狀態使用FOUND、NOT_FOUND、BLOCKED或METRIC_MISMATCH；正式資料狀態依證據使用OK、USABLE、MISSING、STALE或UNVERIFIED。缺值的value設null並解釋原因；不可猜值、沿用舊值或用範本值冒充觀測值。

提交後讀回GitHub主分支，確認八個鍵與內容。11:00 Action需驗證25個獨立指標、28個傳輸指標、26個必要資料項及22/22計分欄位。全部通過才發布；未看到Action run及線上讀回證據，不得宣稱已部署。
