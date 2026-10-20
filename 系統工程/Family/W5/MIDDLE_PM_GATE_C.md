Family中PM｜W5 Major／Gate C 工程驗收裁決
日期：2026-10-21（台灣）
裁決：PASS_WITH_SOURCE_COVERAGE_GAPS；W5-01～18核准工程範圍正式驗收通過。
PR22已合併main；merge commit：612a96daeb13f6c3cebd4ae0e8a4fa38d661cd31。
驗收版本：f2702f90d459e7ce96bb244c37020ff549a2083b；契約v2.2.1＋ENGINEERING_ACCEPTANCE_APPROVAL.md七項核准條件。

一、驗收證據
中PM實際下載TEMP完整包，ZIP SHA256=7935c16ba39a988c1c5bede86b2d52d35cab112afc3d6a744e3d3e6308baecc1；CRC及481/481 manifest通過。實跑115來源依賴hash全部通過。
獨立重點測試28/28 PASS（43.44秒）：test_family_technical.py、test_family_end_to_end.py、test_sgov_bridge.py、test_pm16_approval.py。涵蓋producer→正式股債引擎→C8C9→Mentor、UNKNOWN與快照邊界、四客戶隔離、來源變更重驗、撤權/版本、競爭/重送/逾時晚到、SGOV實體與角色及未成交貢獻分離、核准null與來源分欄。
GitHub最終Actions run39492512833/job118869077830讀回success；隨包CI憑證與log載302 PASS／115hash。PR158個新增檔案限W5與專用workflow。FamilyRunner、technical bridge、recovery bridge三支遠端Git blob與本地驗收程式一致。
沿用原23真實行情安全結果及4家人歷史安全結果；本輪不重跑全部歷史工程。完整正向為明示SYNTHETIC工程輸入，真實資料缺口保留。

二、Gate範圍與後續使用
W5 Major及Gate C依最新核准工程範圍通過，承接W2 PASS_WITH_12_OPEN_P2及W3指定讀取器已接收PASS；W2原12項P2保持OPEN。此裁決允許W6/W7接線續作，Production HOLD、交易授權NONE。
歷史PIT、真實資料完整覆蓋、正式跨程序身分/持久化、W8全系統E2E及最終上線仍由既定後續工序驗收。
原W5 runtime及核心策略本輪修改0；RM17凍結，W4取消。原工程交付ZIP與TEMP交接包保留為f2702f90不可變交付證據；現行Gate以本裁決及原位更新Checkpoint為準。

三、來源缺口責任與完成條件（OPEN）
1. W5-TECHNICAL-SOURCE／W5-SNAPSHOT-METADATA-AND-RULE-COVERAGE：
主責Family中PM親自定位既有資料與正式規則，先重用現有行情與producer；六檔台灣債券ETF、NATO精確商品對應、交易所/幣別/日曆/正式收盤/拆股證據逐項補來源。未核定KD/EMV、窗口、事件/持續狀態、背離與閾值由中PM查正式母規則，必要重大取捨交指揮官。完成條件為具名來源/版本/口徑及受影響測試；現階段UNKNOWN/MISSING保留，不阻擋本輪核准工程Gate。
2. W5-CONFIRMED-TARGET-SOURCE：
主責Family中PM定位四家人既有確認Target與C7來源，沿用現有私人資料；不要求家人重新填資料。完成條件為確認證據、版本、owner、目標欄位與金額/權重對應具備可追溯來源，再由W5接回驗證受影響案例。
3. W7正式身分/持久化：
由中PM將W7_RECOVERY_HANDOFF.md納入W7原工序契約，施工責任W7；跨程序保存/恢復、CAS、發布去重與身份驗權於W7驗收。本輪記憶體staging通過結果沿用。
本輪責任登記不代表已向其他工作線送出新發包通知；目前來源定位由中PM自己續辦。W5如有具名本線缺陷，負責修復。

四、正式位置與備份
PR：https://github.com/a23882005/LivingWaterAI/pull/22
程式：main／系統工程/Family/W5/；專用workflow：.github/workflows/family-w5.yml。
工程成果：https://drive.google.com/file/d/1lm3ss_YSN7VVaQDSRqDrJ_Zk40XhsCX0/view
TEMP回交：https://drive.google.com/file/d/1BC4jcvbH27U1j73fokikuTCECXeUQ8Hc/view
現行Checkpoint：https://drive.google.com/file/d/1jcy2YuhGmM3rs2yM5JFTt5wC5u2EXshB/view
索引：https://drive.google.com/file/d/1j7qoMxIX7wl4scZ_mafZ5eOUalHTp-8_/view
合併前main備份：backup/main-before-w5-gatec-20261021 → bc8d581d74c7f17204a0b3e251c0f659279aedc8。
Drive修改前備份均在根目錄Backup；施工台帳1cQcwARVQjcg3RavWDmjZNWm0-BWhOnEOjHUjPn74E0s；檔案台帳1fNiwlRXDz-E3BRIxwsnB3fnza-rE4N6TBm-fgP6ML1U；Checkpoint 1-3-KTvxBwjYK0qx6JfGGHDMNtM7LW6ou；索引1lnST36kjsYntXwtFK1EyF5c-z9BogQMA；Root 1lVdBOQLL6t8Nh_zVUp4P4aRGy88a8f_r。

五、下一步
Family中PM親自接續W6 v11：回寫既有績效資料庫加權年化報酬決定、來源覆蓋與資料計算，再製圖/HTML；持續定位上述來源缺口，管理W7及後續全線工序。
