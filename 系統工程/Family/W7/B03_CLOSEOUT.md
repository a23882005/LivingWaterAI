# W7-B03 全線存取盤點完成

2026-10-22，Family總PM本人循序完成。基準main：5d220c522ba350da81d354b7349327bf076a557a。

## 清冊與處置

`B03_ACCESS_INVENTORY.json`列169個GitHub既有檔案的SHA、直接/間接存取處置、API輸入簽章/輸出說明、函式內imports、IO/動態呼叫、規則/schema結構及$ref。169檔與基準Git blob逐一相符。清冊是Family實際呼叫閉包，不宣稱掃描整個repo全部歷史程式；程式AST資訊配合本次逐模組語意讀取與下列專門處置。

- W5頂層30支：`B03_W5_DISPOSITION.md`，保留既有兩項持倉重現與技術時點/總經期限問題。
- C work2～7、兩公開入口、C8C9七支：清冊逐檔列明XLSX/binding/schema讀取、記憶體結果及保存責任。26個動態schema既有實載/驗證證據沿用。caller提供的binding/schema路徑不是程式內已存在的固定正式檔，B12必須以已核實來源配置供入。
- V82/V75：原生規則/模型/驗證沿用。V82 `persistence.py`本機JSONL writer不得作Family正式保存；B06/B11以共同Drive SQLite writer實作既有port。V75 work4讀取凍結deployment契約JSON，保持版本鎖。
- W5 technical vendor：實際只抽取legacy v82_engine五個定義，另載analytics；不執行整份legacy策略或collector。未使用collector的config/symbols.json不假裝是正式接線依賴。正式B19使用已存在scripts收集器及其兩份區域清單。
- W6 runtime六支與評等JSON：來源綁定/接收不是完整報表交付。既有renderer六支、模板與資產輸入逐檔處置沿用`B03_SOURCE_INTEGRATION.md`，私人原件保留Drive，B16參數化後才鏡像程式。
- W2六個已納管檔案：沿用獨立來源lock、原9項與W5相容性4項證據；B14保存完整confirmed payload。
- 既有IB命名市場收集器實際呼叫yfinance。讀區域清單/CSV/manifest，寫市場CSV及manifest；兩既有Action將市場快取提交GitHub，沒有Family DB或Drive授權。B17/19新增按需介面與來源選路，保留既有排程；B21獨立處理正式共用DB。

## WORK12原碼納管與輸入限制

從已驗收WORK12完整ZIP逐層定位兩個原模組，原bytes不變放`vendor/work12/`；`work12_source_lock.json`保存完整nested member chain與SHA。兩模組只有Python標準庫imports，`version_lock`是pretax模組函式，不是遺漏的另一支程式。

`pretax_performance_engine.py`：price/NAV observations、distribution schedule/status、五期間boundary matrix、corporate-action status/plan、index rows → 含息wealth/cumulative return/CAGR及版本口徑。`build_engine_from_root`讀WORK12-4/-5/-6 manifests與原freeze目錄；CLI可寫`--json-out`。B20重用計算類及原方法，但以已驗證批次輸入適配，不把凍結11標的CLI當成任意標的服務。保留幣別、期間、股息零值證明、拆股不得二次調整等原契約。

原碼明確排除BNDW；Lilian的BNDW假設配置可保存，但不能據此宣稱已有WORK12含息結果或移除原排除條件。B20/B22維持明確不可計算狀態，擴大計算範圍須有獨立核定依據。原`version_lock()`中的NOT_STARTED是歷史模組當時敘述，不覆蓋WORK12整線40/40結案。

`risk_engine.py`：日期/日wealth/月報酬及同幣RF → MDD、recovery、Sharpe、Sortino、Calmar與KNOWN/UNKNOWN；無網路/檔案/DB寫入。B20由可信資料準備端提供對齊期間與缺口狀態，保留原觀測數與幣別限制。

## 動態資料與版本鎖

原六lock仍驗115列；只有已完成的每日總經fixture分離修復，沒有重算全鎖或停用驗證。B10每日正式消費來源另綁定可信commit/hash/取得時點/當輪及A段有效期；fixture通過不等於當日feed合格。WORK12新來源使用獨立lock，不修改W5歷史lock。

## 驗收界線

B03的逐檔存取/處置清冊與受影響lock方案完成。既有W5/W6/WORK12驗收沿用；後續B06/B09/B10/B12/B14/B16/B19/B20/B21仍須實作及驗收，不能把盤點當作整線接通。正式W7仍0/29。本人接B04能力探測；Production HOLD、交易NONE、W4取消、RM17凍結。
