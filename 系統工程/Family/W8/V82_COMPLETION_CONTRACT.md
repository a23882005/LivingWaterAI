V82補齊工程，2026/10/30，Family中PM驗收線

本文件下方保留第一段施工快照。後續已完成同源Entry/Stage、M/日切片、持久cycle及Family04接線，現行契約與規則→函式→測試對照見 [V82_IMPLEMENTATION_GUIDE.md](V82_IMPLEMENTATION_GUIDE.md)；實跑及驗收狀態以最新Checkpoint為準。第一段「尚未接線」不再代表現況，兩戶必要來源及C7未通過仍不得宣稱全功能驗收。

本批沿 PR59，基準27d41bd，保留main查核報告38ff92c。授權為Owner本輪交辦及正式三層量化規格v1.0；規格DOCX SHA-256：816adc16dc23d982a327e0c99a8cfba992a5fb3a58cfeb5ec10bcdf61cdc9a4f。交接ZIP SHA-256：93aff27cd3530ce4555e233ff7a26cc1436f79d1e8f4163943970503b7822301。Fresh Read V82 v1.21.0 SHA-256：392e54808c33cce99e3567f0e8942650ad50b382d9fc87acbbe20f012b568372。

原生Owner位於股票V80/正式Runtime/v82_runtime_greenfield；新增已核准的v1.0方法，保留既有selector、九階比例、gap及資金MIN。49／13欄不擴充，profile、來源、限制與帳本進sidecar。舊來源鎖保留，新增原生模組逐份登錄核准範圍與hash；不是以改hash跳過驗證。

第一段：own_history.py 實作PV2同標的、listing、幣別與方法的qV、未調整價格／除息日gross現金再投資wealth、252日高點及高點63個log return sample sigma的qP。月／季已完成期、發布與修訂時間、90% coverage、連缺不超過2期、至少2年、10→5→可比制度期、current排除均為具名資料契約。合法主估值歷史不足不換主指標；不支持的事件與日曆保留UNKNOWN。

approved_profiles.py 實作PV3 B2～B7、range適用性／明確N/A、最高TRUE以上未知及nesting conflict、具名限制、完整Right Entry與事件相依T+1、Trend8／9。R_ok保留技術子條件；Hard Gate不加進Right分析Entry，Up/Down衝突先處理。缺Stage必要事實不發Base1／Right8保底。

第一段測試：Family/W5/tests/test_v10_profiles.py及test_v10_own_history.py，44項通過。涵蓋十一類合法選階介面、嚴格邊界、高階未知、range N/A／未知／override、具名限制、完整Right與T+1、相同標的PIT／修訂／歷史可靠度、split／cash不重算及斷鏈。

此段只完成原生函式與單元驗證，Family第04項、M／切片／daily cycle、共同資金整合及真實資料接入續作；不宣稱完整V82或兩戶驗收。V75衝突施工保持暫停。Production HOLD，NO_TRADE；不下單、不購買、不新增排程、不展開Arthur／Lilian。圖文修訂由中PM協調。
