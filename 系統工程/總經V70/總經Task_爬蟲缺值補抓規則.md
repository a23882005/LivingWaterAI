# V70-3-27｜10:00「總體經濟狀況」Task 補充資料交接規格

**最後修改：2026-10-17（台灣時間）**  
**適用版本：V70-3-27**  
**用途：規定 10:00 總經 Task 如何查核並產生 9 項補充原始資料，供 11:00 GitHub Action 合併。本文取代本檔先前所有舊版抓取規則。**

## 一、工作範圍與交接

1. 先讀取 GitHub 主分支 `data/18_macro_verification.json`，核對 09:00 核心資料的生成時間、每筆日期、來源與狀態。核心爬蟲負責 18 個獨立指標及重複欄位 `s03`；10:00 Task 負責以下 9 個補充原始輸入。
2. 產出正式檔案 `data/9_macro_supplement_verified.json`，供 `scripts/build_daily_v703_site.py` 及 `.github/workflows/v703-site-deploy-1100.yml` 使用。
3. 九個資料鍵必須恰好為：`m06_rate`、`m06_inf`、`m06_rstar`、`m06_taylor_infl`、`m06_output_gap`、`s05`、`m03_qqq`、`m03_spy`、`m03_vt`。不得自行增加、刪除或改名。
4. 每一筆都要查核四個候選來源並留下紀錄。候選來源是查核清單，不代表四個網站的數字可混平均；正式值須採同一口徑且日期可追溯的來源。資料不符、無法確認、日期過期或定義未定時，標示 `MISSING`／`STALE`／`UNVERIFIED`，不可猜值或以舊值充新。
5. 補充檔缺失、格式不合、候選查核未完成或必需資料無效時，11:00 Action 的品質閘門會阻擋發布，保留既有網站版本。

## 二、m06：五個原始輸入與推導方式

Task 提供以下五個有日期、有來源的原始輸入；**m06 衍生值由新版 builder 計算，不由 Task 手動填入或另行計分**：

- `m06_rate`：目前 Fed 目標利率區間中點（百分比）。候選來源：Federal Reserve；FRED DFEDTARL；FRED DFEDTARU；ALFRED DFEDTARU。以官方區間上下限計算中點，不可用有效聯邦基金利率替代。
- `m06_inf`：未來 12 個月通膨預期（百分比）。候選來源：Cleveland Fed 1 年期預期；NY Fed SCE 1 年期中位數；University of Michigan 1 年期預期；Philadelphia Fed SPF。必須標明實際採用的來源及期限；不同期限不可直接替代。
- `m06_rstar`：NY Fed Holston–Laubach–Williams（HLW）實質自然利率 r*（百分比）。候選來源：NY Fed r-star 方法頁；HLW real-time estimates；HLW current estimates；NY Fed Staff Report 1063。歷史回測須保留當時可得的即時版本；current estimates 僅作最新值交叉核對，不得冒充歷史即時版本。
- `m06_taylor_infl`：固定採用 **Core PCE（核心 PCE）年增率／過去 12 個月變化**，單位百分比。依季節調整月指數計算 `(本月指數 ÷ 去年同月指數 − 1) × 100`。正式數值來源為 BEA 核心 PCE 頁面及 FRED PCEPILFE；四來源查核另記錄 BLS CPI、FRED CPILFESL 作比較，但 CPI 數值不得代填此欄。Fed 的正式 2% 長期目標以整體 PCE 年增率衡量；Fed 公布的政策規則實作使用 Core PCE 四季通膨率，因核心通膨較能反映中期整體 PCE 走勢。即時值記錄觀測月、BEA 發布日及抓取時間；歷史回測保留當時可得 vintage。
- `m06_output_gap`：實際 GDP 相對潛在 GDP 的產出缺口（百分比）。候選來源：CBO 經濟資料；BEA NIPA；FRED GDPC1；ALFRED GDPC1。必須使用一致的實際 GDP／潛在 GDP 定義及可查證日期；只拿實際 GDP 水準不能冒充產出缺口。

新版 builder 使用下式推導 m06，輸出單位為百分點：

`實際實質利率缺口 = m06_rate − m06_inf − m06_rstar`  
`Taylor 缺口 = 0.5 × (m06_taylor_infl − 2.0) + 0.5 × m06_output_gap`  
`m06 = 實際實質利率缺口 − Taylor 缺口`

五項原始輸入任一缺漏、未驗證或無有效日期／來源，衍生 m06 即為 MISSING；不得用範本預設值補算。

## 三、s05：NYSE 市場廣度

指標定義固定為 **NYSE 全市場站上 50 日移動平均線股票百分比（$MMFI）**，單位百分比、範圍 0–100。不得以 S&P 500 或 Nasdaq 廣度代替。

四個候選來源：Macroaxis MMFI；Barchart $MMFI；EODData MMFI；TradingView INDEX:MMFI。查明標的範圍、50 日均線口徑及原始觀測日；只有報價而無可核日期時不得當作當日值。四個來源只作查核紀錄，不作數值平均。

## 四、m03：三檔 ETF Forward P/E／FY1

`m03_qqq`、`m03_spy`、`m03_vt` 一律查 **未來 12 個月 Forward P/E 或明確標示的 FY1 預估本益比**，單位「倍」。四個候選來源依序為：

| 指標 | 候選來源（依查核順序） |
|---|---|
| m03_qqq | Yahoo Finance QQQ；Invesco QQQ；Portfolio Visualizer；StockAnalysis QQQ |
| m03_spy | Yahoo Finance SPY；State Street SPY；Portfolio Visualizer；StockAnalysis SPY |
| m03_vt | Yahoo Finance VT；Vanguard VT；Portfolio Visualizer；StockAnalysis VT |

只接受頁面明確標示 Forward P/E、Forward、FY1 或相同意思的 12 個月預估欄位。**TTM 是落後 12 個月，不得作為 Forward/FY1，也不得填入正式值。** 找不到符合口徑的資料時，該 ETF 設為 MISSING，不可拿 TTM 或其他 ETF 代填。每一站都記錄實際查核結果及時間。

## 五、正式 JSON 格式

頂層至少包含 `schema`、`generated_at`、`as_of_taipei`、`items`。正式 `items` 僅含上述九個鍵。每個項目包含：

- `label`、`value`、`unit`
- `observation_date`、`source_url`、`method`、`status`、`detail`
- `retrieval_time`、`publication_date`、`vintage`
- `candidate_checks`：恰好四筆，每筆包含 `site`、`url`、`metric_or_horizon`、`status`、`checked_at`、`value`、`unit`、`observation_date`、`notes`

`candidate_checks.status` 使用 `FOUND`、`NOT_FOUND`、`BLOCKED` 或 `METRIC_MISMATCH`，每筆都填實際查核時間。正式資料 `status` 依證據填 `OK`、`USABLE`、`MISSING`、`STALE` 或 `UNVERIFIED`；只有 `OK`／`USABLE` 才代表有可供 builder 驗證的數值。不得把候選查核狀態誤填為正式資料狀態。

## 六、完成檢查

1. 九個資料鍵完整且無多餘鍵；每筆四個候選來源查核都有結果與時間。
2. 數值、單位、觀測日、發布日、抓取時間、來源及計算方法彼此一致；不得使用未標示期間的估值或跨口徑拼接。
3. 生成並提交 `data/9_macro_supplement_verified.json` 後，回讀 GitHub 主分支檔案確認內容。
4. 11:00 Action 會執行新版 builder，檢查核心與補充資料、m06 衍生值、22 個計分指標、估值 Forward/FY1 口徑及來源紀錄；全部通過後才發布 HTML／JSON。Task 不得宣稱 Action 已成功或網站已更新，除非已看到該次 Action 與線上驗證結果。
