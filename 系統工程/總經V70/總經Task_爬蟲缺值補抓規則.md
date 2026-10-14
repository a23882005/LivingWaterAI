# 10:00「總體經濟狀況」Task｜爬蟲缺值自動補抓（2026-10-14）

**新增強制規則：凡09:00 GitHub Actions《總經爬蟲18項.py》結果狀態為 MISSING、STALE、UNVERIFIED 的指標，10:00 ChatGPT Task 一律自行開網頁搜尋、讀取、計算、查核。不限四項。s05 MMFI 固定自行查。保留原Task全部分析內容與章節，不新增Task。**

1. 讀 `a23882005/LivingWaterAI/data/18_macro_verification.json`，核對 generated_at、18項每筆 value / observation_date / source_url / status。若當日09:00未成功產檔，逐項補查，舊數據不得充新。
2. **m06**：先讀 https://www.investing.com/central-banks/fed-rate-monitor 完整約12個月後FOMC利率機率表（Target Rate / Current Probability）；參照 https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html 及FRED https://fred.stlouisfed.org/series/DFEDTARL 、 https://fred.stlouisfed.org/series/DFEDTARU 查目前政策區間。令 expected_rate = Σ[(lower+upper)/2 × p] / Σp；current_mid=(current_lower+current_upper)/2；**m06=(expected_rate-current_mid)/0.25**，傳給V70 value 為純數字碼數，例如利率差+0.75個百分點→value=3。保留會議日、機率表更新時間/時區，拒絕只用期貨價格或舊分布猜值。
3. **m03_qqq** 第一優先 Portfolio Visualizer https://www.portfoliovisualizer.com/fund-performance?s=y&symbol=QQQ ，確認主基金為QQQ，讀 Fund Information → Price/Earnings (TTM)。依序備援/比對 Yahoo https://finance.yahoo.com/quote/QQQ/ 、Invesco https://www.invesco.com/qqq-etf/en/about.html 、Stock Analysis https://stockanalysis.com/etf/qqq/ 。
4. **m03_spy** 第一優先 Portfolio Visualizer https://www.portfoliovisualizer.com/fund-performance?s=y&symbol=SPY ，確認主基金為SPY，讀 Price/Earnings (TTM)。備援/比對 Yahoo https://finance.yahoo.com/quote/SPY/ 、State Street https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy 、Stock Analysis https://stockanalysis.com/etf/spy/ 。已知24.20倍（2026-10-08）僅可作歷史參考，需當次核對。
5. **m03_vt** 第一優先 Portfolio Visualizer https://www.portfoliovisualizer.com/fund-performance?s=y&symbol=VT ，確認主基金為VT，讀 Price/Earnings (TTM)。備援/比對 Yahoo https://finance.yahoo.com/quote/VT/ 、Vanguard https://investor.vanguard.com/investment-products/etfs/profile/vt 、Stock Analysis https://stockanalysis.com/etf/vt/ 。Vanguard歷史20.8倍（2026-07-31）不可冒充當日PV TTM。
6. **s05 MMFI** 依序：https://www.barchart.com/stocks/quotes/%24MMFI/comparison → https://stockcharts.com/h-sc/ui?s=%24MMFI → https://www.marketinout.com/stock-screener/above-50-day-moving-average → https://www.tradingview.com/symbols/INDEX-MMFI/ 。需驗證NYSE市場股票站上MA50比例、原始日線觀測日、0～100；Barchart Last 無可核對日期時僅記候選，不當今日值。
7. **其他任何缺項**：優先查原始來源與正式指標字典；官方入口 FRED https://fred.stlouisfed.org/ 、BLS https://www.bls.gov/ 、BEA https://www.bea.gov/ 、Treasury https://home.treasury.gov/ 、Fed https://www.federalreserve.gov/ 、ISM https://www.ismworld.org/ 、Conference Board https://www.conference-board.org/ 。按原指標公式重算，禁止為填數而變更定義。
8. 每項保留 id/value/unit/observation_date/retrieved_at/source_url/method/status/error；只有同口徑且有日期來源證據才OK，否則MISSING/STALE/UNVERIFIED。合併22+s05=23獨立項，另s03=m07形成24欄。向使用者交付**原完整總經報告**，並實際用已連接GitHub工具回寫整合JSON再讀回確認，交給11:00 Actions；未能回寫要明示阻礙，不得假稱交接/部署完成。


## 2026-10-14｜QQQ／SPY／VT 三檔PE一致採用 Portfolio Visualizer
三檔均以 Portfolio Visualizer 的 **Fund Information → Price/Earnings (TTM)** 為第一來源，先確認頁面主標的是正確ETF（不可把 Benchmark 的資料讀錯），**直接讀數值，不自行算PE**。m03_qqq URL `https://www.portfoliovisualizer.com/fund-performance?s=y&symbol=QQQ`；m03_spy URL `https://www.portfoliovisualizer.com/fund-performance?s=y&symbol=SPY`；m03_vt URL `https://www.portfoliovisualizer.com/fund-performance?s=y&symbol=VT`。已知歷史參考 QQQ 28.32、SPY 24.20；不硬編碼為每日最新值。VT PV 最新值未核對，不以發行商不同日期值冒充。失敗時由10:00總經Task依相同方法讀網頁並紀錄 value、TTM口徑、來源、觀測日期與抓取時間；其餘備援依原規則。


## 2026-10-14 最新優先正式規則（覆蓋上方22項與m06舊說明）
09:00 來源改為 `總經爬蟲18項.py` → `data/18_macro_verification.json`。10:00 Task固定負責 **5項**：m06、m03_qqq、m03_spy、m03_vt、s05；另外補抓任何18項缺失。m06 **先保存 raw_rate_change_pp = 一年後最接近12個月FOMC完整機率分布加權中點 − 現行Fed目標利率中點**，例如 +0.80475 個百分點；**rate_change_quarters = raw_rate_change_pp / 0.25**，例如 +3.219碼。兩者不得混成同欄；V70原欄位m06的口徑須與HTML計分公式一致，禁止重複除以0.25。保留完整各檔機率、會議日期、資料觀測時間、來源、CME交叉核對及品質狀態。QQQ/SPY/VT一律Portfolio Visualizer的Fund Information Price/Earnings (TTM) 優先。最後23項需確實回寫GitHub並讀回驗收。
