# BR v0.3.4｜所選VOO案例官方來源核驗

2026-10-21；責任：Family中PM本人。範圍限原BR-03/07/08來源處置，既有W5/W6與家人資料不改。

## 已完成

1. Vanguard 2026-09-30 factsheet：VOO、CUSIP 922908363、NYSE Arca身分已核實。原PDF存evidence/official_review/VOO_factsheet.pdf。
2. NYSE官方2026日曆：2026-01-01至10-19應有200個交易日，與既有VOO CSV逐日完全相符；缺漏0、額外日期0。保存當年度假期、提早收盤與America/New_York夏令時間換算。此處是排定交易日/收盤時間，逐bar正式價格發布憑證另列。
3. Vanguard 2026-09-30 investment profile第3頁：3/27、6/26、9/28三次配息，官方兩位小數1.87、1.96、1.82；CSV為1.872、1.962、1.823，按兩位小數核對一致。第三位小數精度尚未由此文件認證。
4. SEC N-CSR 000093247115005659，Vanguard 500 Index Fund ETF Shares財務摘要第24頁：2013-10-24收盤時1-for-2反向分割。CSV同日Stock Splits=0.5，事件存在與比例吻合。發行人收盤生效與Yahoo事件日的精確映射、各價格及股數還原基準仍待證實。
5. 新增review_official_sources.py，核對原CSV與四份官方原件SHA、200交易日、三次配息及分割比例。整合進run_all；來源比對程式不修改原行情、原Registry或投資授權。
6. 新增11項測試：正常、夏令時間、假期/提早收盤、年度範圍、缺交易日/週末/重複、配息差異/額外事件、分割比例、review/CSV/官方原件篡改。測試用合成故障資料；實際官方來源核驗另由runner執行。

## 驗證

本輪run_all：75測試PASS；原W5雙次重算與原Golden一致；115依賴/184來源；23歷史CSV、92用途/時間邊界全部PASS；官方來源核驗PASS_BOUNDED_SOURCE_REVIEW。完整log及結果在evidence/official_review_run/。

原件在evidence/official_review/；review.json固定觀測、URL、原件SHA與適用範圍。PDF擷取文字及SEC解析文字為查閱輔助；原件雜湊才是核驗輸入。取得日期是2026-10-21，文件as-of日期與下載日期分列，沒有回填成歷史發布時刻。

## 尚待完成與下一責任

Family中PM本人接續：固定歷史案例的可靠available_at/vintage；分割精確時點與調整價格/股數證據；完整原引擎所需規則/來源及受信審核讀取分支；正向歷史實算後作BR整線裁定。2026交易日核驗不擴張為2010–2025全期間核驗，分割比例一致不擴張為全歷史調整基準通過。

BR工程驗收沿用，正式整線OPEN_SOURCE_EVIDENCE、historical_ready=false。W7需求已確認嚴格Project隔離、契約v1.1；平台能力待實證，0/29 NOT_RELEASED。Production HOLD、交易NONE；W4取消、RM17凍結。

## 官方來源

- https://workplace.vanguard.com/assets/corp/fund_communications/pdf_publish/us-products/fact-sheet/F0968.pdf
- https://workplace.vanguard.com/assets/corp/fund_communications/pdf_publish/us-products/investment-profiles/0968.pdf
- https://www.nyse.com/markets/hours-calendars
- https://www.sec.gov/Archives/edgar/data/36405/000093247115005659/index_final.htm

下載紀錄：曾有附帶聯絡電郵的User-Agent請求被自動審核攔下；後續使用不附個資的公開GET成功取得四份原件。沒有要求指揮官提供新的持倉或資金資料。
