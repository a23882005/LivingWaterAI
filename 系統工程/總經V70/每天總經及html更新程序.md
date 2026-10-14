# LivingWaterAI V70.3｜每日五階段正式工作程序

文件日期：2026-10-14  
時區：Asia/Taipei（UTC+08:00）  
正式目錄：Google Drive `系統工程／總經V70／`  
GitHub：`a23882005/LivingWaterAI/系統工程/總經V70/`  
唯一正式網站HTML：`V70-3-10.html`  
正式施工順序：**任務2 → 任務3 → 任務1 → 任務4**（施工順序）；每天自動執行仍按07:00 → 09:00 → 10:00 → 11:00 → 14:30時間順序。

## 每日五階段總表

| 台灣時間 | 執行者 | 工作與正式產出 |
|---|---|---|
| **🍎07:00** | GitHub Actions **任務1** | 下載／增量更新 IB 可交易之國外股票、債券、ETF 歷史資料，輸出帶日期與品質狀態的 CSV／JSON |
| **🍎09:00** | GitHub Actions **任務2** | 執行 `系統工程/總經V70/總經爬蟲22項.py`，輸出並提交 `data/22_macro_verification.json`，附日期、來源、OK／STALE／MISSING |
| **🖼️10:00** | ChatGPT「總體經濟狀況」Task | **先讀 GitHub 09:00 結果**，查證與補充 NYSE MMFI（s05），完成最新總經分析報告，將合格資料回寫 GitHub 並讀回驗收 |
| **🍎11:00** | GitHub Actions **任務3** | 讀取09:00＋10:00正式已驗證資料，以 **`V70-3-10.html`** 為唯一HTML母版產生 `index.html`，QA通過後部署Hostinger並驗證 |
| **🍎14:30** | GitHub Actions **任務4** | 下載／增量更新 IB 可交易之台灣股票、債券、ETF 歷史資料，輸出帶日期與品質狀態的 CSV／JSON |

## 07:00｜任務1：國外股票／債券／ETF歷史資料

- Actions：`.github/workflows/ib-global-history-0700.yml`；Python：`scripts/ib_market_history_update.py`；標的清單：`config/ib_global_symbols.txt`。
- 對已核實為IB可交易的國外股票、債券、ETF進行分批增量更新；保存開高低收、成交量與可得的還原價、配息／拆股資料。初期清單只是試跑清單，**尚未代表IB所有可交易商品全集**。
- 每次產出真實觀測日期、時區、來源與品質狀態；遇失敗沿用前次已驗證資料並標STALE。

## 09:00｜任務2：22項總經爬蟲

- Actions：`.github/workflows/macro22-preflight.yml`；主程式：`系統工程/總經V70/總經爬蟲22項.py`。
- 執行主程式、自我測試及欄位契約QA；保留歷史有效快取，產出 `data/22_macro_verification.json`、CSV、查核報告與 Actions artifact。
- **22項為22個獨立來源／計算指標**；`s03` 與 `m07` 是重複傳輸的VIX欄，非第23個獨立指標。`s05`（NYSE MMFI）留給10:00補入。合併後 **23個獨立指標、24個傳輸欄**。
- 日期、單位、來源、值均需查核；m06、QQQ/SPY/VT本益比等缺值不可造數或以舊值冒充當日。

## 10:00｜ChatGPT總經Task（非GitHub Actions第五個任務）

1. **先讀GitHub `data/22_macro_verification.json`**；查核執行時間、每個 `value`、`observation_date`、`source_url`、`method`、`status`、`detail`，判定22項實際成功數。GitHub Action延後／失敗要明示。
2. **補s05／NYSE MMFI**：依序參考Barchart `$MMFI`、StockCharts `$MMFI`、Market-In-Out（確認NYSE股票池與定義）、TradingView `INDEX:MMFI`，取得真正的NYSE站上50日均線百分比、觀測日期與來源；需品質驗證。Gmail提供的有日期數值可作備援交叉核對。
3. 對09:00缺值逐項查核可靠官方／發行商／正式市場來源，不能混用ETF TTM與FY1本益比，也不把未驗證候選數字標成OK。
4. 依既有完整「總體經濟狀況」Task正式章節產生總經報告；完整監控通膨、信用、利率、流動性、就業消費、估值、市場廣度、AI盈利、重大新聞及6個月／1年／3年情境，最新V82／債券V75規則仍獨立有效。
5. 寫入**當輪經過驗證且來源可追溯**的s05與總經整合JSON到GitHub，寫入後讀回對照版本、SHA／時間、資料狀態及數量；如寫入失敗，保留報告並明示「10:00 GitHub交接未完成」。
6. 交接給11:00的完整輸出須附 `schema`、`generated_at`、每項資料觀測日期及 `status`，明確區分當日新下載、先前已核證但仍有效及STALE/MISSING；**不把未驗證值當成市場最新資料**。

## 11:00｜任務3：HTML生成與Hostinger部署

- 正式Actions：`.github/workflows/v703-site-deploy-1100.yml`；建置器：`scripts/build_daily_v703_site.py`；母版：`系統工程/總經V70/V70-3-10.html`。
- 讀09:00＋10:00結果，檢查同批次schema、來源日期、VIX重複欄一致性、s05、缺值及必要欄位；合格才輸出 `index.html` 與JSON。
- 正式上線前保留上一版可用網站，部署到Hostinger的 `public_html/index.html` 與相應資料文件，查驗實際網址 `https://www.happihelp.com`，含快取／回應與檔案版本檢驗。
- **狀態界線：** Actions程式存在不代表每日網站已成功部署；需實際完成憑證、FTP／網站驗證、必要時復原演練，才算正式PASS。資料缺漏時fail-closed保留原網站。
- GitHub Actions cron採UTC，實際啟動可能延遲，需記錄實際開始／完成時間。

## 14:30｜任務4：台灣股票／債券／ETF歷史資料

- Actions：`.github/workflows/ib-taiwan-history-1430.yml`；Python：`scripts/ib_market_history_update.py`；標的清單：`config/ib_taiwan_symbols.txt`。
- 分批更新已查驗之IB可交易台灣標的，必要時對照台灣證交所／櫃買中心資料；先查是否已收盤與資料日期，避免將未完成日K當正式日K。
- 使用台灣紅漲綠跌判讀；數值與回測欄位以時間戳和實際報酬口徑為準。現有清單只是初始清單，後續須確認IB實際可交易性。

## 六項資料可靠性與正式驗收

1. **批次下載**：合理批量、控制並發，避免單一失敗拖垮整批。
2. **請求節流**：限制頻率，加入適量隨機延遲。
3. **有限重試**：429／暫時錯誤指數退避；持續限流即停止。
4. **資料快取**：增量更新、避免重抓。
5. **備援來源**：依資料種類選來源；總經優先FRED／BLS／BEA等官方資料。
6. **品質驗證**：日期、時區、完整性、缺漏、異常值與原價／還原價／配息／含息報酬定義一致。

每個任務都要記錄最新成功時間、失敗原因、STALE／MISSING欄位、Artifact與Read-back結果。正式報告保留所有已核定監控指標和既有章節。不得擅自更改Family家人版Runtime、DB與其他工程Gate。

## 《活水書院》

一脈活水，流過歲月，  
釀成青山，也釀成遠方。

不逐一時風起，  
只守四季花開。

讓時間沉澱豐盛，  
讓資產在歲月裡生長；  
今日種下一方山水，  
來日收成人生的富足。
