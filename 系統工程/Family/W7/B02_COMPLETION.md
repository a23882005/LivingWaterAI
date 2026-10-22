# W7-B02 來源與計算元件核實完成

責任：Family總PM本人；契約v1.5.10；狀態PASS_SOURCE_INVENTORY。

## 正式來源分工
- 現行C Work2讀取標的績效基準資料.xlsx，既有XLSX遷移SQLite為同內容基線；依原架構共用SQLite為持久來源，Excel保留歷史交付。
- 已取得WORK12已驗收v1.1.0整線包，原始SHA256 b6e25e56137e068f365549dd5c0ebb8c117c14c06a93fb50b780569d6654524a，102326191 bytes。完整原件與DB只保存在Drive W7，精確ID與導航見私有元件登錄。
- 外包IMMUTABLE/W1_WORK12_REAUDITED_TO_W1_SMALL_PM_v0.2.0_2026-10-11.zip → IMMUTABLE/WORK12-28_TO_W1_WHOLE_LINE_HANDOFF_v1.0.0_2026-10-11.zip → release/canonical_benchmark_work12_25.db：schema canonical_benchmark 1.0.1，11 instruments、330 metric_values、55 release_status；quick_check ok。
- 同包canonical_benchmark_with_provenance_v1.1.1.db為先前provenance基線，metric_values=0；不與330筆成果混淆。
- WORK12 canonical schema與較早XLSX四表schema不同。B12讀取介面須分別映射benchmark規則與canonical metrics，保持data_class/value_state/release_status/期間/幣別/來源；B20重用計算、B21統一寫回。尚未切換現行C runtime。

## 原始計算元件
沿W28 upstream→W27→W26→W25→W24鏈定位既有Frozen Capability Bundle及原始凍結包：
- WORK12-9包20_WORK12-7_ENGINE/pretax_performance_engine.py：calculate_cagr、wealth/total-return處理；ACT/365.2425，滿一年才CAGR、股息再投資與拆股guard。
- WORK12-21包內WORK12-15/01_UPSTREAM_FROZEN/CONTRACT/risk_engine.py：max_drawdown_daily_wealth、recovery_metrics、Sharpe/Sortino/Calmar；同口徑日含息wealth，MDD為負decimal；缺口回UNKNOWN。
- WORK12-24-08包SOURCE/04_FROZEN_UPSTREAM/FROZEN_CAPABILITY_BUNDLE/IMMUTABLE_MODULES包含上述以及稅、配息、公司行動等10個既有能力。B03逐檔展開相依；B20再部署所需原碼到GitHub及Drive程式鏡像。
- 實際載入兩個原碼模組成功；合成100→121兩年CAGR約10%、100/120/90/130 MDD=-25%、blocking_gap→UNKNOWN通過。此為重用介面探測，未重開WORK12全線驗收。

## 原資料狀態承接
WORK12 release_status保留：PERFORMANCE及RISK各10 READY/1 NOT_COMPUTED；AFTER_TAX 11 BLOCKED_PENDING_REAL_INPUTS；BENCHMARK 11 MISSING；TAX 11 NOT_COMPUTED。這些是原驗收明列資料狀態，工程CLOSED維持。後續只使用各欄位實際可用狀態，必要補項歸B19～B22。
BNDW現有家人假設持倉可保存；舊WORK12 active pool排除規則與持倉保存分開處理，B22依最新版契約定範圍。

下一步本人B03全線依賴盤點；正式W7仍0/29，Production HOLD、交易NONE、W4取消、RM17凍結。
