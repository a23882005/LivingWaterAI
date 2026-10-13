# ChatGPT 總經爬蟲8項.md

> 活水AI V70.3｜第二部分：ChatGPT 人工／工具輔助查核規格（不是 Python 網頁爬蟲）。
>
> 狀態：工作分工與查核 SOP；**不是**已完成24項實際資料驗收，也不保證排程中的 ChatGPT 能直接操作 GitHub。

## 一、兩部分正式順序（先AI八項，再Python十六項）

1. **第一步《ChatGPT 總經爬蟲8項.md》**：ChatGPT 先依本文件查證固定8項，完成真實日期、來源、單位、口徑與數值的證據核對；無法確認就標 MISSING，不編造。
2. **第二步《總經爬蟲16項.py》**：執行 Python 自動查詢 FRED／Yahoo Finance／CNN，取得16欄（包含 VIX 共用欄），並保留24欄 JSON 結構。未自動取得的8欄先標 MISSING。
3. **第三步合併與 QA**：將已核實的8項整理為 `verified_overrides.json`，用 Python `--overrides` 合併，核對24欄來源、觀測日期、單位、數值與 OK／STALE／MISSING。16項其中抓取失敗者可再由 ChatGPT 查證補值。
4. **第四步產製報告**：查核完成後再分析七群風險、V70.3、V82、債券V75及完整每日總經報告；關鍵欄位不足時 HOLD 或標示信心降低，不將示範數值當正式判斷。
5. **第五步 GitHub 交接**：只有實際寫入交接檔且讀回驗證，才稱已交給 GitHub Actions；僅修改 Task 文字不代表資料已自動送達。
## 二、第二部分固定補查的8項

| ID | 指標 | 首選來源 | 驗證要求與難點 |
|---|---|---|---|
| `m06` | Fed 未來約12個月預期升降息碼數 | [CME FedWatch](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html)、[Investing.com Fed Monitor](https://www.investing.com/central-banks/fed-rate-monitor) | 依約12個月目標會議的完整機率分布計算市場期望利率，扣除當前政策基準後÷0.25個百分點；**負數＝降息**。單一最高機率區間或Fed點陣圖都不是期望值。 |
| `m03_qqq` | QQQ 過去12個月本益比（TTM P/E） | [Invesco QQQ](https://www.invesco.com/qqq-etf/en/home.html)、[Yahoo QQQ](https://finance.yahoo.com/quote/QQQ/) | 確認TTM、持股加權口徑、資料觀測日與來源；不可用 Forward P/E 冒充。 |
| `m03_spy` | SPY TTM P/E | [State Street SPY](https://www.ssga.com/us/en/individual/etfs/spdr-sp-500-etf-trust-spy)、[Yahoo SPY](https://finance.yahoo.com/quote/SPY/) | 同上；不能直接把S&P 500另一種指數估值冒充該ETF口徑。 |
| `m03_vt` | VT TTM P/E | [Vanguard VT](https://investor.vanguard.com/investment-products/etfs/profile/vt)、[Yahoo VT](https://finance.yahoo.com/quote/VT/) | 同上；注意全球股票口徑與資料日。 |
| `m04` | ISM製造業PMI | [ISM](https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/) | 官方當月報告的 Manufacturing PMI，記錄**統計月份**及**發布日**，勿誤用S&P Global PMI。 |
| `m15` | ISM服務業PMI | [ISM](https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/) | 官方 Services PMI，同樣分開記統計月份與發布日。 |
| `m16` | 美國LEI年增率（YoY） | [The Conference Board](https://www.conference-board.org/topics/us-leading-indicators) | 僅使用**相同修訂版本**本年與上年同月指數計算 `(當期/去年同月−1)×100`；不可把六個月增速、月增或不同修訂批次硬充年增率。 |
| `s05` | MMFI市場廣度 | [TradingView INDEX-MMFI](https://www.tradingview.com/symbols/INDEX-MMFI/)、[Macroaxis](https://www.macroaxis.com/index/MMFI.INDX/Percent-Of-Stocks) | 核對指數涵蓋市場、站上50日均線比例之分母、觀測日與定義；第三方數值要標示並交叉核實，不能把其他廣度指標冒充。 |

## 三、單筆交接格式

每筆至少提供 `value`、`observation_date`（YYYY-MM-DD）、`source_url`（可查證 HTTPS 網址）、`method`、`unit`，必要時 `detail` 註明合約與數值口徑。缺值時寫明原因；無證據不得標 PASS。

```json
{
  "m06": {
    "value": null,
    "observation_date": null,
    "source_url": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
    "method": "待取得完整目標會議機率分布並計算市場期望升降息碼數",
    "unit": "碼",
    "detail": "待驗證；此為欄位範例，不是可輸入正式程式的已驗證值"
  }
}
```

**注意：上方 null 範例僅描述欄位結構，不能直接傳入 Python 的 `--overrides`；只有查證完成、非空且通過檢查的值才能放入正式 `verified_overrides.json`。**

## 四、實際合併方法

- Python 第二步產出 `24_macro_verification.json`、`24_macro_verification.csv`、`24_macro_report.md`。
- ChatGPT 先查8項，必要時再補查 Python 第二步本輪其他 `MISSING`／需重查項目。逐筆完成來源與日期驗證後，放入 `verified_overrides.json`。
- 使用同一支Python重新執行（例如 `python "總經爬蟲16項.py" --overrides verified_overrides.json --cache Python 輸出路徑/24_macro_verification.json --out 合併輸出路徑`）。歷史快取只作 STALE 備援，不能冒充新值。
- 核對 `m07` 與 `s03` 同值、`m06` 單位「碼」、`m14` 單位 USD bn、`m17` 單位 pp，並在決策前審核每個重要欄位的資料新鮮度。
- 需要將 ChatGPT 補值自動寫回 GitHub，須另行具備**可用的授權執行工具、實際寫入與讀回驗證**；只改 Task 描述並不等於 GitHub Actions 能直接呼叫 ChatGPT。

## 五、品質分級

- **OK**：真實來源＋觀測日期＋同定義／同單位，且通過新鮮度檢查。
- **STALE**：真實歷史資料、來源和日期可追溯，但未達目前新鮮度；僅作舊值參考。
- **MISSING**：無可信數值或定義不符，不填假值。
- **正式配置 Gate**：所有必要欄位 OK 才允許正式配置，否則 HOLD／資料不足，不自行使用中間值填空。

## 六、工程邊界

這是**ChatGPT八項資料查核規則文件**，不是另一支已可獨立於 GitHub Actions 執行的「ChatGPT爬蟲」。GitHub Python runner 本身不會自動喚起 ChatGPT 網頁搜尋或登入動態頁。保留原始24項資料蒐集程式、原有 V70.2／V70.3、V82、債券V75與網站，不因命名或分工變更而改動策略引擎。

## 活水書院

《活水書院》

一脈活水，流過歲月，
釀成青山，也釀成遠方。

不逐一時風起，
只守四季花開。

讓時間沉澱豐盛，
讓資產在歲月裡生長；
今日種下一方山水，
來日收成人生的富足。
