# LivingWaterAI V70.3｜每日更新程序

文件日期：2026-10-17｜時區：Asia/Taipei  
唯一正式HTML母版：`系統工程/總經V70/V70-3-27.html`  
配對資料：`V70_macro_latest.json`

## 正式資料契約：V70-3-27 V3

- 09:00核心爬蟲提供18個獨立指標及重複欄位s03。
- 10:00總經Task查核八項補充原始值，寫入`data/8_macro_supplement_verified.json`：m06_rate、m06_inf、m06_rstar、m06_output_gap、s05、m03_qqq、m03_spy、m03_vt。
- 11:00建置器計算m06 V3、驗證資料並產生網站HTML及JSON；Action和線上讀回均通過才算發布成功。

m06 V3公式（百分點）：

`實際實質利率缺口 = m06_rate − m06_inf − m06_rstar`  
`Taylor基準缺口 = 0.5 × (同一個m06_inf − 2.0) + 0.5 × m06_output_gap`  
`m06 = 實際實質利率缺口 − Taylor基準缺口`

m06只需四個原始輸入。不得再要求獨立的Taylor通膨欄；同一筆未來12個月通膨預期m06_inf用於公式兩處。

驗證契約：25個獨立指標、28個傳輸指標、26個必要資料項、22個必要計分指標。Forward估值只接受明確Forward/FY1；TTM不得代用。缺值或過期時保持`ready=false`及正式配置NA。

## 每日順序

| 時間 | 負責方 | 工作 |
|---|---|---|
| 09:00 | 核心爬蟲 | 產生並驗證`data/18_macro_verification.json` |
| 10:00 | ChatGPT「總體經濟狀況」Task | 核對核心資料；查八項補充資料，每項記錄四個候選來源；提交JSON並讀回核對 |
| 11:00 | GitHub Actions | 依V3契約建置28個傳輸欄；只有22/22計分資料及所有來源檢查通過才部署 |
| 14:30 | GitHub Actions | 更新台灣股票、債券及ETF歷史資料 |

## 10:00交付檢查

補充JSON必須恰好有上述八個鍵。每筆資料要有值、單位、觀測日、來源、計算方法、狀態及四筆候選來源查核。資料缺漏標MISSING／STALE／UNVERIFIED，不沿用舊值。Task需讀回GitHub檔案，Action需讀回部署JSON及HTML；未取得成功證據時不得宣稱更新完成。
