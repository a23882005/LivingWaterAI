# Family W5 接線施工中

契約：v2.2.1；基線：32c9322c8bb3150480f6c86becf28e04592f5e8e。
Production HOLD；交易授權 NONE。

本次已實作唯讀四庫讀取、原 W3 feed 封裝、精確資金合計守恆、C8C9 同名 schema 載入路徑解析。
既有 V82/V75 原生回歸已實跑；完整 Family 調度及 Mentor 回傳仍待接通。

安裝：Python 3.11 以上，`python -m pip install -r 系統工程/Family/W5/requirements.lock`。
本線測試：`python -m pytest 系統工程/Family/W5/tests`。
目前尚未交付最終 `run_analysis.py`；不要將原生回歸通過視為整線分析入口已完成。

`family_input.read_snapshot` 只讀指定四庫隔離副本，保留歷史資料與未知值，不推導 AVAILABLE。
`market_bridge.read_macro_snapshot` 直接呼叫已接收 P70-5，原 payload 不變。
`funding_guard.check_aggregate` 是合計額度檢查，不產生新的配置或分配優先序。
`runtime_loader` 不修改核心檔，也不替換 Frozen schema；缺件維持 DEPENDENCY_MISSING。

詳見 Checkpoint.json 與 evidence/；私人四庫與讀取結果僅放私有 Drive。
