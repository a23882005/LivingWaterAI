# LivingWaterAI V70.3｜每日五階段自動化正式工序（2026-10-14）
> 唯一現行總經分工：**09:00 Python 18項 + 10:00 ChatGPT 5項 = 23個獨立總經指標**。另外 s03=m07 VIX 重複傳輸，共24欄。舊版「爬蟲22項」「8+16」不是現行分工。
> 所有時間均為 Asia/Taipei。排程設定與實際成功執行是兩回事；要看 Actions run／log／資料回讀方能標示PASS。

| 時間 | 執行者 | 執行內容與交付 |
|---|---|---|
| **07:00** | GitHub Actions 任務1 | IBKR上可交易國外股票、債券與ETF歷史價格／股息／還原價格增量下載，附資料日期與品質驗證 |
| **09:00** | GitHub Actions 任務2 | 跑 **`系統工程/總經V70/總經爬蟲18項.py`**，輸出並提交 **`data/18_macro_verification.json`** |
| **10:00** | 既有 ChatGPT「總體經濟狀況」Task | 先讀09:00 JSON；固定自行抓 **m06、m03_qqq、m03_spy、m03_vt、s05**；Python其餘18項若 MISSING/STALE/UNVERIFIED，也自行查原始網站補抓；完成23項分析與完整總經報告，**實際回寫** GitHub 合併JSON並read-back |
| **11:00** | GitHub Actions 任務3 | 只讀10:00驗證整合資料，重建 `V70-3-10.html` 對應的 `index.html`，部署 Hostinger 並回讀正式網站驗收；缺資料則 fail closed 不覆蓋 |
| **14:30** | GitHub Actions 任務4 | IBKR上可交易台灣股票、債券與ETF歷史資料增量下載；未收盤確認的日K標未完成 |

## 09:00 正式檔案與來源
- Actions：`.github/workflows/macro18-preflight.yml`，原 macro22-preflight.yml 已退役。
- 主程式：`系統工程/總經V70/總經爬蟲18項.py`，原「總經爬蟲22項.py」已退役。
- 原始資料：`data/18_macro_verification.json`（18個獨立指標＋s03複用VIX，實際19筆）。
- 每筆皆保存 `value`、`unit`、`observation_date`、`source_url`、`method`、`status`、`error`；資料過期不得冒充今日。

## 10:00 固定五項由 ChatGPT 處理
1. **m06｜未來約12個月 Fed 政策利率期望變動**：Investing.com `https://www.investing.com/central-banks/fed-rate-monitor` 讀最接近一年後FOMC的全部機率與利率區間，交叉查CME及FRED現行Fed目標區間。計算 `expected_rate = Σ[各區間中點×機率]/Σ機率`；`raw_change_pp = expected_rate - current_policy_midpoint`，**原始value採百分點**（例如 +0.80475），`change_quarters = raw_change_pp / 0.25` 為碼數（+3.219）。前端不可重複換算，兩欄口徑須明定。保留會議日期、時間、機率表及CME交叉核對結果。
2. **m03_qqq／m03_spy／m03_vt**：優先 Portfolio Visualizer `https://www.portfoliovisualizer.com/fund-performance?s=y&symbol=QQQ`（另將 symbol 改SPY、VT），確認ETF本身標的，直接讀 `Fund Information → Price/Earnings (TTM)`，不自行算TTM PE。估值日期不明須標UNVERIFIED並查備援。
3. **s05｜NYSE MMFI**：Barchart `https://www.barchart.com/stocks/quotes/%24MMFI/comparison` → StockCharts `https://stockcharts.com/h-sc/ui?s=%24MMFI` → Market-In-Out → TradingView；需確認NYSE股票站上50日均線比例及觀測日期，禁止無日期的搜尋摘要冒充當日值。
4. **其餘18項任何缺值**：Task按原指標定義逐一補查，官方網站如FRED/BLS/Treasury/ISM/Conference Board為優先，不把舊快取當新值。
5. **合併寫回**：23個獨立指標（18+5），再加入 s03=m07 的重複傳輸欄，總計24欄；可追溯原始來源、日期與品質狀態。10:00 Task 必須實際寫GitHub並read-back；寫不進去應報錯，不能宣稱11:00已拿到資料。

詳見 [總經Task_爬蟲缺值補抓規則.md](./總經Task_爬蟲缺值補抓規則.md)。

## 11:00 部署驗收與已知限制
- 現有 `.github/workflows/update-v70.yml` 目前仍有舊16項爬蟲與未完成 Hostinger 自動部署路徑，**需另行改寫與實際驗收**；這份程序文件不等於已部署。
- 10:00的整合JSON必須來源可靠、口徑一致、日期確認；若缺值可提供標註版報告，但不可把缺失充作OK。
- 只有確實建立index.html、上傳Hostinger、網址讀回顯示新版時，才標示網站部署成功。

## 通用六項可靠性
分批抓取、節流、有限退避重試、增量快取、可靠備援、資料日期/交易時區/完整性/異常/配息口徑品質驗證；失敗保留前次有效資料、標示STALE和失敗原因。
