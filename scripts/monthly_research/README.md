# Macro Safety 月度研究乾跑

> 最後修改日期時間：2026/10/19 18:15（台灣時間）

此目錄是隔離研究工具，不會在瀏覽器重算研究結果。每日歷史檔由 11:00 正式部署流程在上線 HTML、JSON 與部署收據全部驗證成功後追加；同一流程按每月 5 日台北時間截止規則重建真實月度分數與斜率 CSV。若 5 日當天流程漏跑，補跑會保留實際觀察日期。S&P 500 序列有第三方授權限制，確認可供公開研究與圖表使用的資料來源前，月度分數照常累積，報酬欄標為 `SOURCE_PENDING`，不發布原始行情或衍生報酬。若尚無當月有效 V70 分數，該月不造點。建置器會把五張機構比較圖、總經候選季度斜率圖及七線總覽，共七張 PNG 打包至網站靜態目錄並供 V70-3-27 頁面讀取。總經圖目前是候選季度方向斜率（分數點／季），不是正式月度微分；正式月度 Macro Safety 圖需等待真實月資料累積後再產生與替換。

## 輸入契約

`macro_safety_daily.csv` 由 `scripts/capture_v703_daily_snapshot.py` 從正式建置 feed 與線上 V70 頁面讀取最終 `mSafe_final` 產生。必須先通過完整 25/28/26/22 feed 閘門、線上頁面來源驗證、22/22 計分資料與日期驗證，以及部署收據讀回。記錄版本規則、feed SHA、來源快照與來源指標逐欄證據。輸出至少包含：

`observation_date,run_timestamp_utc,v70_version,source_commit,health_score,score_status,neutral_imputed_items`

原始指標值與來源證據以 JSON 欄位保留；缺值使用字面 `NA`，不補寫原始觀測。正式流程要求 22/22 齊全，因此本擷取器的 `neutral_imputed_items` 留空。若另有核准的上游 composite 流程需對缺項採中性值，只能在 composite 計算內代入 5/10，原始值仍保留 NA，並須記錄代入項目。擷取器不重算 `mSafe_final`；只有 `VALID` 或 `FORMAL_VALID` 的分數會納入月度快照。

S&P 500 價格序列需來自已授權可供公開網站使用的供應者，且須保存來源、口徑、日期與擷取時間。待完成授權查核前，月度 CSV 只保存經核驗分數、真實月斜率與來源 lineage；S&P 欄位留空並標 `SOURCE_PENDING`。取得核准來源後，起點採觀察日當日或之前最近一個交易日收盤；終點採觀察日加三個日曆月當日或之後第一個交易日收盤。只有終點已可得且 `--as-of` 到達終點日期，報酬才標為 `REALIZED`，否則報酬欄留空並標 `PENDING`。

### 公開基準來源授權查核（2026-10-19）

| 來源 | 查核結果 | 本研究處理 |
| --- | --- | --- |
| [FRED SP500](https://fred.stlouisfed.org/series/SP500) | 系列註明 S&P DJI 版權，重製須取得事先書面許可；FRED 條款也要求第三方資料另獲資料權利人許可。 | 許可未取得前不發布該序列或其衍生三個月報酬。 |
| [Yahoo Finance](https://au.help.yahoo.com/kb/finance-for-web/exchanges-cover-sln2310.html) | 官方說明明確禁止再散布 Yahoo Finance 顯示或提供的資訊。 | 不作公開圖表的資料來源。 |
| [Alpha Vantage 市場資料政策](https://www.alphavantage.co/realtime_data_policy/) | 政策區分個人非商業用途與商業用途；商業使用需聯繫供應商安排資料授權。尚未核實其歷史 S&P 500 指數資料是否包含本網站及衍生報酬用途。 | 未取得涵蓋該用途的書面授權前，不作公開圖表來源。 |
| [Nasdaq Data Link 條款](https://data.nasdaq.com/terms) | 條款限制再散布，具體權限取決於相關資料集的適用授權。尚未找到同時涵蓋 S&P 500 指數歷史值與公開衍生報酬的資料集授權。 | 暫不採用；先確認產品級授權範圍。 |
| [S&P DJI 官方授權](https://www.spglobal.com/spdji/en/about-us/data-index-licensing/) | 官方提供指數歷史資料與網站／媒體展示授權服務。 | 目前是需直接確認授權範圍的候選來源；尚未取得許可或報價。 |

### 追加供應商授權查核（2026-10-19）

| 供應商 | 公開條款 | 本研究判定 |
| --- | --- | --- |
| [Financial Modeling Prep（FMP）](https://site.financialmodelingprep.com/developer/docs/pricing?planType=commercial) | Enterprise 方案列有展示與再散布，但官方要求另簽 Data Display and Licensing Agreement。 | 可列為商用授權洽詢候選；需確認授權明確涵蓋 S&P 500 指數歷史值、以該值計算的三個月報酬，以及本網站靜態圖表展示。普通 API 訂閱不構成授權。 |
| [Polygon 市場資料條款](https://polygon.io/terms/market_data_terms.pdf) | 除非取得書面同意或第三方供應商協議明確允許，條款限制公開展示市場資料及其衍生圖表、分析或研究。 | 一般帳戶／API 使用權不足；只有取得涵蓋本用途的書面許可才可採用。 |
| [EODHD 商用授權說明](https://eodhd.com/financial-apis/commercial-vs-personal-license-use) | 價目頁方案供個人使用；商業或團體用途需另行評估與報價。其條款亦指出部分指數資料是 CFD／做市商來源、可能為指示性價格。 | 個人方案不可用於網站公開展示；即使取得商用報價，也須先核實該端點是正式 S&P 500 指數價格序列，而非 CFD／替代品，並確認展示與衍生報酬權利。 |

目前查到的供應商都沒有以一般訂閱直接授予本研究所需的完整權利。後續若評估 FMP、Polygon 或 EODHD，先取得書面授權範圍，逐項確認「指數歷史資料來源與口徑、衍生三個月報酬、網站靜態 PNG 展示、GitHub／網站託管、保留期限與下架義務」；再把授權文件和期限記錄後，才接入現有 `--sp500` 輸入流程。

因此目前仍沒有已核准的公開 S&P 500 基準來源。SPY 是 ETF，不等同 S&P 500 指數報酬，不能替代本研究指定的指數基準。以上結論只針對公開網站與衍生報酬用途；資料來源未來若提供涵蓋該用途的授權，應保存授權證據、來源口徑與使用期限，再接入資料流程。

每個月份從該月 1 日至明確指定 `--cutoff-day`（月底不足該日則月底）間，選最後一筆有效的實際日觀察；無資料的月份不補值。若原定日的日流程失敗，補跑時可指定 `--retry-month YYYY-MM`，程式只為該月放寬至實際 `--as-of` 日期，並記錄真實觀察日，不偽造原定日快照。 若已封存的是截止日後的啟動首點，後續執行會固定其實際觀察日期，只採同一日較晚的正式快照更新修正版分數，不會把首點移到隔日。斜率以相鄰快照的健康分差除以日曆月差；同一日號的相鄰月快照恰為 1 個月，缺月按跨越的月數計，延後幾天則按該段日曆月比例計。單位為分數點／月。季度檔因缺少每日契約欄位而直接拒收，不會插值。

## 月度序列長度與歷史回補

正式月度序列以 **60 個真實月度點（5 年）**為研究目標，先在 **36 點（3 年）**做第一個完整性與穩定性檢視。每月只選一個通過正式 V70 驗證的分數點，按月追加保存；每日來源快照保留作為稽核證據。預測後三個月的 S&P 500 報酬需要等待三個月成熟，因此 36 點檢視時，末端約 3 點仍會是 `PENDING`。

本輪正式日分數收集自 2026-10-19 起；因啟動日在當月 5 日之後，第一筆月度點會保留實際 2026-10-19 觀察日作為起點，後續月份使用當月 1 至 5 日間的最後一筆有效分數。

現有 `V70_3_27_2020至2026_29季_22指標歷史補值底稿.csv` 是季度日期的探索底稿，不是已計分的 Macro Safety 序列：多數季度僅有 3/22 個指標，最近兩列分別只有 1/22 與 0/22，正式總分欄空白。因此不以這些季度列製造月點。若要回補正式月資料，必須另取得每個歷史月份當時可得的 22 項資料、正式計分規則版本與來源發布時間，逐月重建並標示歷史回算狀態；在完成之前，正式月度序列從首筆通過驗證的每日 V70 快照開始累積。

正式 Actions 每日流程在當月 5 日或之後選取當月 1 至 5 日內最新一筆正式有效的 V70 分數，並輸出 `data/macro_safety_monthly.csv`；若沒有截止前觀察而後續補跑，才使用實際補跑日且記錄該日期。輸出按月份冪等合併：保留輸入暫缺的歷史月，未改變列保留原執行時間，既有已成熟報酬不會被較不完整的新輸入降回待成熟，最後以原子替換寫檔。手動研究乾跑仍須明確提供 `--cutoff-day`、`--as-of` 和實際 UTC `--run-timestamp-utc`。

## 本地乾跑範例

```sh
python scripts/monthly_research/macro_safety_monthly.py \
  --daily /path/to/macro_safety_daily.csv \
  --sp500 /path/to/sp500_daily.csv \
  --output /tmp/macro_safety_monthly_backtest.csv \
  --cutoff-day 5 --as-of 2026-10-18 \
  --run-timestamp-utc 2026-10-18T23:00:00Z
```

正式每日 Macro Safety 快照封存在 `data/macro_safety_daily.csv`，月度序列輸出至 `data/macro_safety_monthly.csv`；兩者由每日 Actions 流程更新。交接 ZIP 的季度研究資料不得冒充正式月度輸入。測試中的合成資料僅驗證程式行為，不是研究結果。

## 五大機構研究圖表乾跑

`bank_forecast_research.py` 讀取交接工作簿的「五大機構來源」與「季度回測資料」工作表，輸出來源登錄表、觀察日比較 CSV、五張機構圖與一張總覽圖。每個季度基準日只選擇證據日期不晚於實際觀察日、且目標日仍在未來的最新目標；隱含報酬以當日 S&P 500 收盤計算。年底目標隱含報酬與後三個月實報期限不同，圖表明確註明研究用途及 PIT 待核，不代表命中率。

來源表「公開資料最遲可得日期」保留為 `evidence_date`；原始發布日沒有逐筆驗證時，`publication_date` 留空、`verification_status=RESEARCH_PIT_PENDING`。輸出記錄來源網址、工作簿 SHA-256、工作表與列號。預測登錄表以 `forecast_id` 追加新版本，重跑不重複舊筆，修訂版新增列、舊列保留。研究圖的 S&P 500 實報直接沿用工作簿逐列資料，不改寫原值。

```sh
python scripts/monthly_research/bank_forecast_research.py \
  --workbook /path/to/V70_季度回測_新增MacroSafety中性5分試算.xlsx \
  --output-dir experiments/macro-safety-monthly-research
```

## 五大機構與 Macro 月表

`build_bank_macro_monthly.py` 將每個正式 Macro 月快照配對至觀察日當時已發布、且目標日尚未到期的五大機構最新預測，輸出五列／月。若 Macro 月表含有已授權的 `sp500_start_close`，程式計算 `forecast_implied_return_pct = (forecast_value / sp500_start_close - 1) × 100`，並一併輸出基準收盤日與收盤值；基準收盤缺漏或尚未取得公開使用授權時，價格與隱含報酬欄以字面 `NA` 保存。Macro 三個月實際報酬狀態沿用月表，不把年底目標期限誤標成三個月預測。

```sh
python scripts/monthly_research/build_bank_macro_monthly.py \\
  --bank-register experiments/macro-safety-monthly-research/bank_forecast_register_research.csv \\
  --macro-monthly data/macro_safety_monthly.csv \\
  --output experiments/macro-safety-monthly-research/bank_macro_monthly_snapshot.csv
```

本次工作簿乾跑轉錄 52 筆來源紀錄（高盛12、摩根大通7、摩根士丹利11、美國銀行14、瑞銀8），形成 117 筆可比對的季度×機構資料及六張 PNG。29 個觀察點中 27 個有已實現報酬，待成熟為 2026-10-01 與 2026-10-16。交接工作簿「閱讀說明」有一處把 2026-07-01 列為未成熟，但同工作簿逐列資料已有該日三個月報酬；乾跑按逐列資料處理並保留這項查核註記。
