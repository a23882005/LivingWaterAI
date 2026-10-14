# 活水AI總經24項｜每天工作程序

版本：2026/10/14 正式流程
時區：Asia/Taipei（台灣時間）
正式目錄：`系統工程／總經V70／`
GitHub 對應目錄：`a23882005/LivingWaterAI/系統工程/總經V70/`

## 每日 10:00｜ChatGPT「總體經濟狀況」Task｜步驟1～6

1. **ChatGPT 查證8項**：先讀《ChatGPT 總經爬蟲8項.md》最新正式版本，查核 m06、m03_qqq、m03_spy、m03_vt、m04、m15、m16、s05；保留 value、observation_date、source_url、unit、method、必要 detail，區分 OK／STALE／MISSING。
2. **Python 擷取16項**：執行《總經爬蟲程式16項.py》，依正式資料來源取得其餘16項，記錄真實執行狀態；若Task執行環境無法執行Python，明確標示阻塞並依正式可用Runtime處理。
3. **合併24項與品質查核**：彙整8＋16欄位；m07與s03共用VIX，不重複算作獨立來源。核對數值、來源、日期、單位、計算口徑、更新時效及完整性；不以假數值、HTML預設或展示數據充當正式結果；缺值保留 MISSING 並進行合理補查。
4. **總經報告第1～11項**：依最新正式報告規則，完整分析七群風險、PPI／CPI／PCE等通膨指標、信用與雙燈／三燈、Fed／利率／殖利率、流動性、市場廣度、AI企業盈利、重要新聞與情境權重；每項保留資料時間、判定與必要門檻。
5. **V82、債券V75與情境圖**：依最新正式股票ETF V82、債券ETF V75分析標的，產出具體操作建議、情境機率及既定三張情境圖；保留完整原報告內容。
6. **總經報告第12項及交接**：產生 `verified_overrides.json`（8項已核實資料）和完整24項JSON（含日期、來源、狀態及版本），以及11:00流程所需報告資料；寫入 GitHub `a23882005/LivingWaterAI` 指定資料路徑，完成讀回驗證。若寫入或驗證失敗，明列「GitHub交接未完成」，保留當輪結果與錯誤紀錄。

## 每日 11:00｜GitHub Actions｜步驟7（資料自動化已實作；Hostinger 部署尚未實作）

7. **最終目標：接力部署正式網站（尚未實作／未驗收）**：透過 `.github/workflows/update-v70.yml` 的每日11:00排程（UTC 03:00）接收同批、最新、已驗證的JSON；確認日期、schema、品質狀態與完整性；生成最新版總經 `index.html`；對HTML做完整性及版本檢查；備份Hostinger現有 `public_html/index.html`；上傳並覆蓋該檔；驗證 `https://www.happihelp.com` 實際呈現本次新版本（必要時處理快取）；保存Actions日誌、部署版本、成功/失敗結果。部署或網站驗證失敗時，保留／回復上一正常版本並發出異常通知。GitHub排程可能較11:00延遲，必須紀錄實際執行時間。

## 正式驗收標準

- 10:00 Task：步驟1～6確實完成、資料可追溯，8＋16合併及正式報告完整；GitHub交接有讀回證據。
- 11:00 Actions：現有 `update-v70.yml` 只負責抓取、稽核、建立 V70.3 JSON feed 並提交 GitHub，**不會自動上傳 Hostinger、也尚未產出部署版 index.html**。只有未來新增實際部署流程且完成備份、上傳、網站驗證後，才可標記「每日部署PASS」。
- 不新增重複Task；不變動無關Family家人版Runtime、DB、其他網站或施工Gate。正式規則更新與部署時遵守Google Drive根目錄《檔案管理.md》及版本、備份、Checkpoint規範。
- 本檔為**工作程序規格**；GitHub Actions至Hostinger的自動上傳、備份及實站驗收須以實際執行紀錄確認，不能把規格文件當成部署完成證據。

## 《活水書院》

一脈活水，流過歲月，
釀成青山，也釀成遠方。

不逐一時風起，
只守四季花開。

讓時間沉澱豐盛，
讓資產在歲月裡生長；
今日種下一方山水，
來日收成人生的富足。


## 2026/10/14｜s05 MMFI 改由每日10:00總經 Task 自行讀網頁（使用者最新指示）

- **執行時機：** 先完成原定 Python 爬蟲工作與 Gmail 讀信，再由現有「總體經濟狀況」Task 自行使用網頁搜尋／開啟工具取得 s05；**不交由另一個工程對話繼續施工，也不新增 Task**。
- **四站依序：** ① Barchart $MMFI：https://www.barchart.com/stocks/quotes/%24MMFI ② StockCharts $MMFI：https://stockcharts.com/h-sc/ui?s=%24MMFI ③ Market-In-Out：https://www.marketinout.com/stock-screener/above-50-day-moving-average （必須確認切換 NYSE 後口徑與 MMFI 相同）④ TradingView INDEX:MMFI：https://www.tradingview.com/symbols/INDEX-MMFI/ 。
- **品質規則：** 必須實際讀頁面最新數值與觀測日期；驗證 NYSE 股票站上 MA50 比例、0–100、資料時間與來源。搜尋索引中的歷史數字、無日期的「29.17」或其他市場股票池的百分比，不能當作當日最新值；不能取得則標示 MISSING／STALE，不捏造。
- **Gmail 角色：** Gemini 寄來的 s05 可作備援交叉核對；優先採 Task 當次自行查得且通過品質驗證的 s05。其餘原有 Task 章節、10:00 時間與 11:00 GitHub Actions 交接均維持。

## 2026/10/14｜先爬蟲、後總經 Task（修正前後順序）

1. **09:00 台灣時間：** GitHub Actions `.github/workflows/macro22-preflight.yml` 執行 `系統工程/總經V70/總經爬蟲22項.py`，產出並提交 `data/22_macro_verification.json`（22個獨立指標，另有s03重複VIX欄）。
2. **10:00 台灣時間：** 現有「總體經濟狀況」Task 應**先讀取** `https://raw.githubusercontent.com/a23882005/LivingWaterAI/main/data/22_macro_verification.json`，核對 `generated_at`、每項 `status`、`observation_date`、`source_url`，確認09:00爬蟲是否成功產生當日檔。若GitHub Actions延後/失敗，保留上次資料，標STALE或MISSING；不得宣稱今日22項已更新。
3. **10:00 Task 自行處理：** 按 Barchart→StockCharts→Market-In-Out→TradingView 順序直接查 s05/MMFI，核對NYSE MA50定義、最新數值與日期，合併23個獨立指標（24傳輸欄，s03=m07）。
4. **11:00 台灣時間：** 原 `.github/workflows/update-v70.yml` 仍跑16項舊版，**尚未整合上述10:00 Task 的最新輸出**；正式部署前必須另行對接驗證，不能宣稱全自動網站更新已完成。

**重要：** 本頁為既有 Task 的工程交接規範，不代表已直接修改該 Task 的儲存提示文字。執行時如遇原Task舊提示與本頁先後順序衝突，以最新經核定工序為準；不刪原Task其他分析要求。
