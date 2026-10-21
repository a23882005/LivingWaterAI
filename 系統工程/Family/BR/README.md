# 最新進度｜BR v0.3.5

可信GitHub Actions封存時點已核實，新增受信唯讀capture reader。200筆真實行情11欄獨立數值正向重播及原W5安全Golden雙跑通過；run_all共83測試PASS。完整策略正向與個別調整基準仍未滿足原收尾條件，BR OPEN_SOURCE_EVIDENCE。原條件對照與待裁定提案見CAPTURE_REPLAY_REVIEW.md。指揮官最新指示：先完成BR，W7需再次討論規劃才開工；W7 NOT_RELEASED。

# 最新進度｜BR v0.3.4

2026-10-21：官方VOO商品、NYSE日曆、配息與SEC歷史反向分割證據已保存；200個交易日與3次配息核驗通過。run_all新增離線官方來源核驗步驟，75項測試及原W5重播、23CSV/92邊界全部PASS。見OFFICIAL_SOURCE_REVIEW.md。BR整線OPEN_SOURCE_EVIDENCE；W7契約v1.1嚴格Project隔離已確認，平台實證待辦；W7 NOT_RELEASED。完整來源原件與實測證據在Drive同ID v0.3.4包，GitHub保留通用程式/測試/文件。

# 最新進度｜BR v0.3.3

2026-10-21：本輪原run_all重跑PASS；新增VOO遠端封存綁定核驗與4項測試，合計64項PASS。實際成果、仍待條件及程式接線限制見 TAKEOVER_FINDINGS.md。BR OPEN_SOURCE_EVIDENCE、historical_ready=false、W7 NOT_RELEASED保持。W7方向已由指揮官確認，29項契約已形成，可信Project綁定方案待裁定。以下為歷史紀錄。

# 最新收尾｜BR v0.3.2

2026-10-21：收尾裁定與工程成果接收完成；完整run_all重新執行PASS。見CLOSEOUT_DECISION.md及evidence/handoff_review/。BR正式整線OPEN_SOURCE_EVIDENCE與W7 NOT_RELEASED保持，剩餘03/07/08證據具名交接。下一對話由Family中PM重新規劃W7並接續推進；現有W7草稿僅供參考。

---

# 最新補充裁定｜BR v0.3.1

2026-10-21：原collector及analytics來源SHA核對一致；拆股欄位慣例與既有Adj Close稅前近似績效口徑已確認，禁止重複還原／重複加息。詳細證據及正式剩餘條件見SOURCE_ADJUDICATION.md。

工程PASS維持；逐案例公司行動品質與歷史發布版本證據尚待補齊，BR正式Major OPEN_SOURCE_EVIDENCE、W7 NOT_RELEASED。原Registry未升格，執行程式未改。既有60項測試、92項邊界驗證沿v0.3，本次未重跑。以下舊紀錄由本補充更正口徑狀態。

---

# 最新裁定｜BR v0.3

本輪工程回歸PASS_WITH_DECLARED_SOURCE_GAPS；正式BR Major為OPEN_SOURCE_EVIDENCE。詳細九項對照與三類來源待辦見BR_REVIEW.md。

乾淨目錄一次跑通：60項測試、原W5雙次實算、完整事件來源圖、23份歷史CSV稽核與92項來源時間／用途邊界驗證。

```sh
python run_all.py /path/to/w5_handoff /path/to/evidence_output
```

source_registry的發布版digest由交付manifest固定，應與請求資料分開提供。已登記快照支援ARCHIVE_READ_ONLY；DECISION_INPUT及HISTORICAL_REPLAY會明確要求相應口徑／發布證據，不因檔案雜湊正確就升格用途。

本輪工程段已完成。下一責任仍Family中PM：定位既有歷史發布、拆股還原、配息報酬口徑證據，依原九項完成正式Major裁定，再接W7。W6 PASS維持，Production HOLD、交易NONE。

以下為前版工程紀錄，進度與裁定以本段及BR_REVIEW.md為準。

---

# 最新進度｜BR v0.2 事件與來源追溯接線
日期：2026-10-21。此段取代下方v0.1同事項；本輪仍由Family中PM負責。

- 49項測試PASS；W5原引擎兩次重新計算、完整Golden比對PASS。
- 事件生產器已實接W5；32個來源圖節點通過校驗，原案例1帳戶／3持倉逐值保留。另測兩帳戶隔離、未知現金、零持倉、篡改重算hash與錯誤回覆保留。
- event_capture保存所有request/context頂層欄位、版本、完整portfolio tables、輸出及其hash。分析模式前後實際持倉相同；建議不記成已成交交易。
- 拆股／配息／FX口徑守衛已做：未來資料、重複還原、總報酬又加股息、反向匯率、過期與非有限匯率均拒絕；未實施價格調整或交易。
- 既有23份歷史CSV共104,788筆，檔案SHA與原context一致；解析資料hash與原intake、逐列內容一致。日期順序／重複／收集時間／數值檢查PASS；盤點29筆拆股、2,223筆配息。
- CSV byte SHA與canonical rows SHA是不同欄位，程式分別核對，不混用。

執行：`python -m pytest -q tests`；`python run_w5_replay.py /path/to/w5_handoff evidence/w5_replay.json`；`python audit_existing_history.py /path/to/w5_handoff/market_intake evidence/history_audit.json`。

## 工序狀態
BR-01／04／06本段完成；BR-02完整portfolio事件與BR-05輸入到結果來源圖已接線測試。BR-03／07／08已接既有真實歷史快照及缺口驗證，原始發布vintage、拆股還原與配息報酬口徑的正式證據仍OPEN。BR-09階段交付更新；整線仍IN_PROGRESS，W7 NOT_RELEASED。

歷史CSV存在拆股／股息欄位，不等於原價格口徑已核准。快照收集完成時間可作此份快照最早可用界線；不能回填成歷史每根K棒當時可用時間。market_basis的evidence_ref需由可信來源登記實證支援；測試中的正向口徑為明示合成案例。
來源圖目前從收到的原request/context開始，外部CSV／網站來源以歷史稽核及原W5來源鎖銜接；不是對外部來源真偽的認證。W5需先執行自身驗證，event_capture不替代原授權驗證。

下一責任仍Family中PM：把歷史稽核接成可信來源登記與可用時間選擇，沿既有來源處理口徑缺項，完成BR整線裁定。W6 PASS維持，Production HOLD、交易NONE。

---
以下v0.1為前段實作背景；進度以本段為準。

# Family BR｜重播核心與W5接線 v0.1

日期：2026-10-21。負責人：Family中PM（本對話）。
本次依已核定接續契約，完成隔離測試環境中的重播核心與W5原引擎接線。Production HOLD、交易NONE。W6工程PASS及既有六級評等保持。

## 已完成與驗證
- runtime/replay.py：事件欄位、客戶／帳戶／資金桶、輸入hash、來源口徑與品質驗證。
- 歷史發布時間截止檢查、同時刻修訂衝突拒絕；單次select_vintage只處理各series的一個觀測期，多觀測期先分組。
- 檔案版本鎖、路徑邊界、來源鏈hash／循環／斷鏈／孤立節點檢查。
- 兩次獨立計算、逐欄Golden與重跑差異；26項測試通過。
- W5既有115項來源校驗通過；額外固定184份施工與測試來源。
- 直接呼叫原FamilyRunner，兩次均為新實例並重新執行C／V82／V75／Mentor。完整結果一致；股用額0、債用額160.00，均為既有SYNTHETIC案例。
- 原W5完整Golden每一原欄位逐值比對一致。後增technical_intake依原W5無technical_source分支明訂為null，僅此欄位補入相容Golden。原始差異檔保留，未覆寫W5 Golden。

## 執行
使用Python 3.12與requirements.lock；在獨立環境安裝依賴。

```sh
python -m pytest -q tests/test_replay.py
python run_w5_replay.py /path/to/w5_handoff evidence/w5_replay.json
```

W5_HANDOFF須含repo/系統工程/Family/W5、baseline/sources及synthetic_evidence/family_e2e_full_result.json；source_lock.json會先校驗來源，再匯入原引擎。本包依賴已交付的W5完整包，並非獨立重包所有引擎。

## 原工序進度與下一段
|工序|狀態|已完成／剩餘|
|BR-01|本段完成|範圍固定為重播準備；策略優劣另案|
|BR-02|部分完成|事件驗證器已做；跨帳戶完整portfolio事件生產器仍待接線|
|BR-03|核心完成、歷史證據待補|截止／修訂檢查已測；真實歷史發布證據仍待來源接入|
|BR-04|本段完成|184來源及本次環境依賴固定|
|BR-05|部分完成|來源圖驗證器已測；全鏈lineage事件生產器待接線|
|BR-06|本段完成|原W5雙次完整重新計算及Golden比對|
|BR-07|部分完成|未知口徑、未來資料拒絕；拆股／配息／FX實際歷史案例待接入|
|BR-08|部分完成|沿用原W5合成Golden；真實歷史片段待驗|
|BR-09|階段交付|本段程式／測試／證據保存；整線驗收待前述接線完成|

下一責任人仍為本對話Family中PM：完成BR-02／05生產器與BR-07／08既有歷史來源接入，依證據裁定整線，再放行W7。整線BR尚在施工，W7尚未Release。

## 契約界線
- 只改Family/BR新增檔案。W5／W6／母引擎及四顆真人DB保持原版。
- replay接收的engine callback必須為隔離、純計算adapter；此Python函式不提供作業系統層沙箱。
- source_lock由可信呼叫端固定；hash驗證不代表歷史發布證明或金融規則正確。
- sources／portfolio／版本宣告須來自可信producer。現在的通用驗證器驗結構與一致性；完整原生輸入的權限與來源綁定交原W5驗證。
- verify_lineage為可單獨呼叫的守衛，尚待全鏈producer整合；未整合時不可宣告所有決策的lineage均完整。
- 歷史模式需可核對的publication_evidence；欄位存在本身不能代替證據核實。
- 本輪不下載新行情、不重算攻防評等、不比較策略績效、不操作正式DB及交易。

## 正式來源
接續契約：https://drive.google.com/file/d/1zoc-K2d8-Xbg5omIWaaOs1BcWFKwOE3W/view
Master：https://docs.google.com/document/d/1coxJ34aDseT09Oxo6OdiMlR6GmYm8RQckvnpr9KlRdo/edit
W5原交接：https://drive.google.com/file/d/1lm3ss_YSN7VVaQDSRqDrJ_Zk40XhsCX0/view
W6合併基線：f95434555dcf479a9ff9b4c46d1b806995f7da8d。
