# LivingWaterAI V70.3｜每日五階段正式工作程序
文件日期：2026/10/17｜時區：Asia/Taipei
正式目錄：GitHub 與 Google Drive 的「系統工程/總經V70」

## 正式版本與資料契約
唯一正式 HTML 母版為 `V70-3-27.html`，配對 JSON 為同目錄的 `V70_macro_latest.json`。舊 HTML/JSON 只作歷史查閱，不可當作新版計算輸入。

V70-3-27 驗證契約：26 個獨立指標、29 個傳輸指標、27 個必要資料值、22 個必要計分指標。10:00 補充檔包含九個原始欄位：`m06_rate`、`m06_inf`、`m06_rstar`、`m06_taylor_infl`、`m06_output_gap`、`s05`、`m03_qqq`、`m03_spy`、`m03_vt`。m06 本身由 HTML/建置器依五項子資料計算，不再採用舊的 Fed 升降幾碼定義。

`m06 = (Fed目前利率中點 - 未來12個月通膨預期 - HLW即時r*) - [0.5 × (Taylor通膨 - 2%) + 0.5 × 實際GDP相對潛在GDP缺口]`。各輸入必須附數值、單位、觀測日、來源、方法、狀態及適用時的發布日／資料 vintage。Fed利率中點取官方目標區間中點；未來12M通膨以 Cleveland Fed 1Y 為主，NY Fed SCE 1Y及密西根1Y依序備援並標明實際來源；r*取NY Fed HLW即時版本；產出缺口不得拿ISM或NFP代替。

三檔估值只收明確標示 Forward/FY1/forwardPE 的未來12個月預估值；TTM、未標明口徑或無法驗證的數值一律 MISSING。s05 固定為 NYSE MMFI 全市場站上50日均線比例，不以 S&P 500 或 Nasdaq 廣度代替。

目前 3-27 內嵌資料為 `ready=false`、計分欄位19/22，三檔 Forward P/E 均 MISSING。資料未補齊前，總經體質分與正式配置維持 NA/暫停，不可把舊 23/24 JSON 標成新版。11:00 Action 只在來源快照、日期、29傳輸欄和22/22計分項全通過時才部署。

## 每日五階段
| 台灣時間 | 執行者 | 工作 |
|---|---|---|
| 07:00 | GitHub Actions | 更新國外股票、債券、ETF歷史資料 |
| 09:00 | GitHub Actions | 執行 `總經爬蟲18項.py`，輸出 `data/18_macro_verification.json`（18個指標及 s03=m07 的VIX重複欄） |
| 10:00 | ChatGPT「總體經濟狀況」Task | 驗證09:00資料並查九個補充原始欄位，輸出 `data/9_macro_supplement_verified.json`，讀回核對；缺資料照實標MISSING/STALE |
| 11:00 | GitHub Actions | 以 `V70-3-27.html` 建置29傳輸欄 JSON/網站；需22/22計分通過才更新GitHub配對JSON並部署Hostinger |
| 14:30 | GitHub Actions | 更新台灣股票、債券、ETF歷史資料 |

## 10:00 輸出格式
九個 key 必須完整且不可多欄；每筆包含 `value`、`unit`、`observation_date`、`source_url`、`method`、`status`、`detail`。m06五項子欄另存來源、發布日/vintage及抓取時間。前向本益比只接受明確Forward/FY1，保存各站查核紀錄；抓不到時保留 MISSING，不准以TTM補值。Task 不可只寫 HTML 而漏掉 JSON 輸入檔。

## 11:00 部署驗收
建置器 `scripts/build_daily_v703_site.py` 讀取18項主檔與9項補充檔，產生 `V70.3/family-macro-feed-v2`。只有同時滿足 `independentIndicators=26`、`transportIndicators=29`、`valid=27/27`、`requiredScoringIndicatorsValidated=22/22`、三檔PE明確Forward/FY1、m06五項來源快照齊全時才發布。任何缺值或舊schema均停止部署並保留網站最後一次有效版本。GitHub Action成功不等於實站通過，須讀回首頁與JSON核對版本、asOf及指標。

## 一般可靠性
所有資料保留來源、觀測日、抓取時間與品質狀態。過期值標STALE，缺值標MISSING；不以預設值或歷史值冒充最新值。07:00/14:30市場資料維持原排程與品質驗證流程。

