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
