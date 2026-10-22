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


## 五、W7-A02共同政策證據契約（2026-10-22，隔離修復版）

由Family總PM依v1.5.10 A02定案，供A03前端與A04 Task生產者共同實作；A13整套驗證後切換正式消費端。現行Task提示詞由A04更新。本段優先於舊版將政策日期當行情日期的作法。

- `policy_schema`固定字串`fed-target-evidence-v1`。`value`為有限數值中點，`unit`為`%`。
- `effective_date`、`publication_date`、`observation_date`為YYYY-MM-DD；保留來源所載政策生效／發布日期，observation_date等於effective_date。發布不晚於生效，兩者不晚於判定當日（Asia/Taipei）；不將生效日改成取得日。
- `retrieval_time`、`last_verified_at`為含時區RFC3339時間戳，計算轉UTC；取得≤成功核實≤判定時點。日級政策不據此推定未提供的生效時分。
- **有限期限：取得及成功核實各須小於26小時**；恰滿26小時即失效。這是A02工程期限決定，與既有每日更新／26小時快照保護一致，並非官方政策有效期。政策可能長期不變，但須重新取得現行官方證據；週末也不自動展延。有效期限為兩個時點各加26小時的較早者。快取讀取、重建、recover及失敗重試不更新此兩時點。
- `lower_bound`、`upper_bound`各為物件，必含數值`value`與`effective_date`；日期均等於本筆effective_date，0≤下限≤上限≤100，中點誤差≤1e-9。不得以EFFR代替目標區間。
- `source_evidence`必含`url`、`checked_at`、`result`、`excerpt`、`response_sha256`、`effective_date`、`publication_date`、`lower_bound`、`upper_bound`、`value`。URL等於本筆source_url，HTTPS且host為www.federalreserve.gov、fred.stlouisfed.org或alfred.stlouisfed.org；checked_at等於last_verified_at；result為CURRENT_CONFIRMED。excerpt為實際來源的必要簡短證據摘要，response_sha256為取得內容的64字元小寫SHA256。資料欄位逐一與本筆值及日期相同；上下限證據結構與本筆一致。
- 生產者須真正查核當期官方政策頁／最新官方序列，確認沒有已生效的更新，保留取得內容以供hash稽核。舊公告本身只證明歷史決定；CURRENT_CONFIRMED須由本次現行查核產生，不能單靠舊公告或自填旗標。單一URL或hash格式正確不代表來源真實性已獲獨立證明；A04負責實際生產與證據留存，A13做真實整鏈驗證。
- 四站candidate_checks既有格式保留；四個m06子項各先通過status、有限數值、來源、method、日期／既有期限及候選查核結構。m06_rate另通過本節政策證據。任一子項失格，衍生m06=MISSING/value=null，原因加入QA，22項計分合格數依實際結果產生。
- 衍生m06保留原V3公式；其observation_date採rstar與output_gap兩個已驗證季度期末中較早者，四個原始日期另保留在子項與detail，避免將政策生效日或月資料誤標成衍生季度日期。
- 正式feed命名：policy_schema→policySchema、effective_date→effectiveDate、lower_bound→lowerBound、upper_bound→upperBound、last_verified_at→lastVerifiedAt、source_evidence→sourceEvidence；既有retrievalTime/publicationDate/dataDate保留。sourceEvidence內部保留原snake_case。normalize原樣傳遞，禁止自行產生新查核時間。
- A03須按同一欄位與期限驗證，修改值／日期／來源即重驗，正式配置動作當下重驗；A04須生產上述證據；A05更新每日程序；A13驗證GitHub／Drive／Task／前端整套相容後發布。本契約不變更其他18項快取資格或投資計分公式。


## 六、A04生產者提交前檢查（A13協調切換）

schema維持`V70.3/10h-eight-supplement-v3`，以policy_schema識別新增政策契約；generated_at與as_of_taipei皆為含時區RFC3339，表示同一實際生成時點，as_of_taipei固定+08:00（取代無時區顯示字串）。新輸出由scripts/validate_macro_supplement.py檢查八鍵、時間、單項資格、四站紀錄、政策證據、Forward/FY1證據與MMFI百分比。檢查不會修改輸入或發布。

新Task提示詞位於系統工程/Family/W7/A04_Task提示詞_待A13切換.txt，原真實提示詞與排程已存evidence/A04/task_before.json供差異核對。原提示詞逐字保留於新版前段；A13完成配套相容測試後，同一Task原ID更新prompt，保持排程／啟用／通知；隨後以真實取得資料產出及提交讀回。A04目前的預備測試不替代此真實生產驗收，交由A13收斂。
