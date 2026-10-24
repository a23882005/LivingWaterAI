# W6 加權歷史參考

`performance_reference.py`僅計算既有歷史數值的權重參考。逐項校驗唯一標的、非負有限權重、權重合計、完整期間及報酬口徑。缺值不重配，跨期間不發布完整A_ref。攻防分數始終未核定。

測試：`python -m unittest discover -s runtime -v`（在W6目錄）。六項去識別案例涵蓋完整輸入、缺值、期間不同、口徑缺漏、重複標的與權重不完整。

HTML／工作簿製作腳本含私人交付映射，與其輸入一起保存在Drive完整包。正式產品驗收仍未通過；不能將計算測試PASS作為W6整線PASS。


## 日期時間報告保存（Joseph v1.13）

`report_archive.py`使用既有GoogleDriveTransport，新增報告檔案，保留歷次成果。`publish_report`接收已完成QA的renderer bytes及真實run／資料日期；`previous_report`讀取已完成manifest與驗證產物。W7 `report_handlers`接畫面12／13。正式端注入owner-only folder及同一single-host writer lock；不改私人DB或投資引擎。
新增測試：`python -m pytest 系統工程/Family/W6/runtime/test_report_archive.py -q`。
