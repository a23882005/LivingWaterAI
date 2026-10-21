# Family BR v0.3.6｜正式結案裁定

日期：2026-10-21（Asia/Taipei）。責任與覆核：Family中PM本人。

## 最新裁定與授權

指揮官於本對話明確要求BR收斂、停止擴張，並於本輪完成結案。依此最新決定，BR正式裁定CLOSED／PASS_WITH_DECLARED_LIMITS。本裁定取代前版OPEN_SOURCE_EVIDENCE及以完整真實策略正向作BR結案阻擋的條件。這是明示範圍收斂，並非新增來源證據或策略規則核定。

BR範圍為既有引擎的未來回測準備：事件與持倉快照、時點/版本模型、來源追溯、確定性重播、公司行動與未來資料守衛、固定案例和證據交付。逐日完整策略研究、績效排名、額外指標定義及全歷史資料認證不納入本次BR。

## 九項完成對照

|工序|完成範圍與證據|結案|
|---|---|---|
|BR-01|範圍固定；策略優劣研究另案|PASS|
|BR-02|原W5 request/context/result、portfolio前後狀態及事件生產器|PASS|
|BR-03|available_at/vintage模型、截止與修訂守衛；GitHub封存後可信可得上界|PASS（限定封存後）|
|BR-04|115依賴、184來源、引擎及規則版本固定|PASS|
|BR-05|32節點來源鏈、輸入/輸出hash及封存來源綁定|PASS|
|BR-06|原FamilyRunner雙次完整Golden；真實資料數值及安全案例雙次一致|PASS|
|BR-07|未來資訊/revision/split/dividend/FX守衛；官方日曆、三次股息及歷史分割核驗|PASS（保留口徑限制）|
|BR-08|固定200筆真實行情、11欄獨立參考一致；原引擎安全Golden與合成完整正向分開保存|PASS（限定固定案例）|
|BR-09|程式、證據、版本鎖、Checkpoint、Manifest及本結案裁定|PASS|

9/9為本次收斂後工程範圍接收。驗證沿用v0.3.5的83項PASS、23CSV/92邊界、原W5雙跑與官方來源核驗，見evidence/capture_full_run/、evidence/capture_proof/及evidence/official_review/。本版只更新結案治理，執行程式及既有測試未修改，不重複擴測。

## 已知限制的處置

1. 個別價格/股數調整、2013事件日映射及早於封存的逐bar發布時間，列KNOWN_LIMIT；現有拒絕/UNKNOWN保護保持。
2. W5原未核定技術規則及基本面來源，沿既有來源覆蓋限制保存；本輪不修改W5已通過規則、不新增BR施工任務、不自動移成W7工項。
3. full_historical_strategy_positive=false、historical_ready=false保留為「全歷史完整策略用途」技術能力狀態；BR工程接收為CLOSED，兩者分欄。
4. 限制責任人仍Family中PM。未來若正式產品欲使用上述不支援用途，再按實際功能需求處理。Gate D驗收採本BR限定範圍憑證，並確認實際輸出遵守用途限制；Gate D本身仍待W7/W8及既有條件完成。

## 下一工序與控制

BR施工待辦清零，停止擴充。下一步由同一Family中PM與指揮官討論W7目標、範圍、介面、子工序順序及完成條件，討論定案後再開工。W7=0/29、NOT_RELEASED；嚴格Project隔離要求保留。
Production HOLD、交易NONE、W4取消、RM17凍結。既有W1/W2/W3指定讀取器/W5/W6驗收保持。後續仍依W7→W8→Gate D→PROD→TRIAL→Gate E循序完成。

正式包：https://drive.google.com/file/d/1e6Pyuw9yy6RDNyLHTs812Vmaki4LVDnz/view
GitHub：https://github.com/a23882005/LivingWaterAI/pull/24
