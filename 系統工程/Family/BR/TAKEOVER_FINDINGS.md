# BR v0.3.3 接任實測與來源定位

2026-10-21；責任：Family中PM本人。指揮官已同意前輪W7方向，維持BR先完成再正式放行W7。

## 本輪完成

- 隔離依賴依 requirements.lock 重建，原 run_all 實測PASS：60項測試、原W5雙次實算、23CSV與92項來源用途邊界；證據 evidence/takeover_review/。
- 從GitHub固定commit fd0f33a28d86073e67f1b26885d9857e91ff70e6 實讀 VOO.csv 及manifest，Git blob與下載內容一致；VOO原始492148 bytes與W5 intake逐位元一致，4052筆，2010-09-09至2026-10-19。
- 新增 verify_archive_binding.py；實際來源核驗PASS，4項正向/篡改測試PASS。證據 evidence/archive_verification/。
- 此段關閉「所選VOO封存版本是否與W5一致」的定位工作。Git提交時間與原收集完成時間皆記2026-10-19T23:20:09Z；這些是封存與收集紀錄，未取得獨立的逐根歷史發布證明。

## 實際剩餘工作定位

1. BR SourceRegistry.v1 的 read_snapshot 對 HISTORICAL_REPLAY 固定回 PER_BAR_PUBLICATION_UNPROVEN，對 DECISION_INPUT 固定回 DECISION_BASIS_REVIEW_REQUIRED。後續取得可靠證據後，還需要增加經可信審核的選取分支與負向測試；只補文件無法使原引擎接收。
2. W5 VOO真實案例的 technical_source 尚缺正式商品/交易所/幣別參考、交易日曆、逐bar收盤憑證與拆股基準驗證。已有SOURCE_BACKED資料完整性，未形成完整策略正向輸入。
3. W5 test_partial_known_signals_preserved_and_unknown_not_promoted 明確驗證：拿掉synthetic_complete_predicates後，部分訊號保持UNKNOWN，結果不為OK。故完整真實歷史策略正向不只依賴CSV，還依賴原已列出的規則/來源覆蓋；不得把合成predicate換標籤當真實證據。

## 裁定與下一步

BR工程原通過狀態維持；新增封存綁定核驗PASS。BR整線 OPEN_SOURCE_EVIDENCE、historical_ready=false，W7 NOT_RELEASED。W5/W6既有PASS沿用；Production HOLD、交易NONE。

下一責任仍中PM：以同一固定案例完成公司行動/日曆/收盤證據及必要原規則輸入，加入受信審核分支後實算。若要將BR驗收限於工程快照重播、把完整歷史投資正向移交後續驗證，這是明確範圍變更，需指揮官另行裁定；本輪的「好」僅確認原W7方向，沒有自動豁免BR條件。
