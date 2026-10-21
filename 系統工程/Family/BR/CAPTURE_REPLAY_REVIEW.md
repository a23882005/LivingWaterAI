# BR v0.3.5｜可信封存時點與真實資料重播覆核

2026-10-21，Family中PM本人施工、另階段自覆核。

## 最新指揮官指示

本輪集中完成BR。W7於BR結束後先與指揮官討論規劃，再決定施工；原W7 v1.1僅保留討論基礎。W7保持NOT_RELEASED，這次沒有W7施工。

## 03：取得獨立封存時間證據

GitHub Actions run 39340856153（global行情收集），artifact 12228981182，GitHub記錄之archive SHA256為73be7654674f4b085c6337e8f148846e92bf5459df13ce0b22dbbfe85adbbd0a，2540288 bytes。實際從GitHub下載與原W5 global.zip逐位元相同；VOO.csv內含4052列，hash與W5一致。

Artifact建立/上傳完成2026-10-19T23:20:09Z；job 118361756593成功結束23:20:14Z。本輪採更保守的job完成時間作可得上界，固定重播cutoff為2026-10-20T12:00:00Z。這個時間證據來自GitHub平台回覆，並非Git提交者自行填寫的時間。完整receipt與ZIP存evidence/capture_proof/。

runtime/capture_receipt.py核對release pin、run關聯、job/upload成功、時間順序、後續revision、ZIP hash/size/CRC及member hash。cutoff早於上界拒絕；等於上界接受唯讀重播。每筆歷史row沿此封存上界可用；此結果未證實更早的逐bar首發時間。

## 06/08：完成兩類真實來源實算

- 正向數值重播：從已核實archive選2026年200筆原行情，實際呼叫鎖定原W5 vendor analytics.py兩次；六個均線、三個量比及兩個TD9計數，共11欄，與獨立Decimal算術/反向連續計數參考完全一致。輸入不改值，不新增策略參數，不評價策略績效。
- 原W5安全案例：原VOO.family_request/context/result，在僅遷移CSV絕對路徑並重綁對應digest之後，兩個全新FamilyRunner實算與原完整Golden逐欄相同，結果DATA_UNAVAILABLE、NO_TRADE。呼叫者/其他context為原合成fixture，市場來源真實；不標為全真實策略正向。
- 結果evidence/capture_proof/replay.json、evidence/capture_full_run/capture_replay.json；全部run_all為83測試PASS、115依賴/184來源、原合成全引擎Golden、23CSV/92邊界、官方來源核驗、真實來源數值/安全重播全部PASS。

## 最終處置（v0.3.6）

依指揮官2026-10-21最新收斂結案指示，BR工程已接收並CLOSED。完整策略正向、早於封存逐bar可得性及個別調整基準列已知用途限制；W5未核定規則保持原狀。上述工程證據及限制仍有效，前版將其作BR持續開工阻擋的條件已由CLOSEOUT_DECISION.md取代。下一步W7規劃討論。Production HOLD、交易NONE。
