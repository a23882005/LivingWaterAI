# W5 同次調度：目標單位待界定

狀態：OPEN；Production HOLD；交易 NONE。這是施工問題回交，並非整線驗收。

## 實測與範圍

`tests/test_native_pipeline.py::pipeline_case` 將原 Work4／5／8 合成案例接成同次呼叫。實際執行 V82、V75、Work6、股債合計及 Work7 後，Work8 回 `C8C9.W8.FINAL_TARGET_BINDING`。V82 原生部署以目標金額 1000 計算，W5 目前將此金額投影至 canonical `project_target_position`；Work8 直接與 C7 `integrated_weight=0.05` 比較。

這個組合案例仍有原 Work8 的持倉保護與配置 fixture 語意，尚不是已完成一致性核對的整線正向案例。單憑此失敗不能認定原核心策略有錯。可確定的是目前 W5 的金額投影與 Work8 的權重比較無法直接相接；既有 canonical schema 只標 `Money/Rate Target`，不足以授權 W5 任意換單位。

## 精確位置與責任

- V82：`系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src/livingwater_v82_runtime/deployment.py`，`calculate_position_gap(project_target_position_amount, ...)`；confirmed amount = quantity × price，target amount = project target amount × deployment rate。
- W5：`系統工程/Family/W5/stock_engine.py`，`assemble_stock_output` 的 `project_target_position` 投影。
- C8C9：`系統工程/C-配置決策引擎＋Mentor整合/正式Runtime/C8C9_RUNTIME/C8C9_Work8_Protected_Holding_Client_Action_Protection.py`，`protect_client_action` 比較 `integrated_weight` 與 canonical `project_target_position`。
- 影響：W5-15 的完整 Work9 正向結果、W5-16 真結果 Mentor 及 W5-18 整線驗收。
- Family 中PM：指定此跨線欄位的正式單位，以及既有來源中的目標金額／權重／估值 NAV 綁定規格；界定最小修正應在 W5 投影或 C8C9 接口。若涉及核心，具名核定最小修改範圍。
- W5 小PM：依指定語意補明確來源與單位轉換，保留原金額及原權重，建立語意一致的正向 fixture，再跑完整 Work9／Mentor。不得用調整數值、關閉 schema 或跳過原檢查取得 PASS。

## 可重現證據

`evidence/pipeline_unit_reproduction.json` 記原檔 SHA256、實際數值及錯誤；`evidence/pipeline_recovery_tests.log` 保存執行紀錄。正向測試暫標 strict XFAIL，僅允許此精確錯誤；不計為 PASS，未來意外通過亦使測試失敗，要求正式移除缺項並驗收。

```sh
W5_SOURCE_ROOT="$PWD/w5_start/sources" python -m pytest repo/系統工程/Family/W5/tests/test_native_pipeline.py -q -rx
```

## 獨立完成的恢復接線

`recovery_bridge.py` 重用 W2 Work21 `new_test_state`／`apply_event`，只在同一 staging store 補 client_id＋request_id、完整輸入 digest、目前版本／許可重驗、實際逾時至多重試一次及晚到結果拒收。Decimal 精度、陣列順序與型別均納入版本化 digest；測試包含並行重送、快取撤權、計算中版本失效及真正延遲。

此段測試使用受控無副作用計算 provider；完整 Family runner 接入及跨程序持久化未完成，後者由 W7 負責。沒有宣稱 W5-17 全棒或正式恢復 PASS。核心策略／Frozen schema 修改數仍為 0。

## 2026-10-21 債券客戶動作接口

原 `C8C9_Work9_Unified_Deployment_Mentor_Return.py` 的 V75逐檔與帳戶輸出，`client_preference_action` 固定為 `None`；原 Work8 接收 V82，未提供 V75 保護輸出。W5 已將 W1 確認 holding policy、C7 drift 原 client_facing_action、V75 raw source_action 和部署金額分欄接入 Mentor，附來源digest/owner/run並於Family重送前重驗。NEW_BUY拒絕時原V75縮放至零，Mentor另核實際部署為零。

Family 中PM需具名界定：V75 的 HOLD_AS_IS 客戶動作是否沿 C7 drift，或由 C8C9 擴充統一保護介面；若改核心，列最小原檔/欄位/優先序與回歸。W5負責依核定來源接線，現階段保留 `SOURCE_FACTS_ONLY_PENDING_CROSS_ENGINE_PRIORITY`，未自行覆寫原 Work9 client_preference_action。

同輪完成 W2→V75 明確商品別名及同帳戶/同幣別逐檔 target_amount 核對。以明確確認逐檔金額接原V75；跨帳戶目標拆分、整體目標拆資金桶及FX仍須具名來源，W5不重新配置。合成案例歷史NAV 20000、SGOV目標5600/SPSB2400，當期預算350，保留與長期目標不同的語意。

V75原Decimal零有 `0E-28` 表示，Frozen Money schema要求一般十進位字串；W5 `money_wire`僅做Money字串等值序列化，指數零轉`0`，原`0.00`保持，原始snapshot另存raw_runtime_ready。原策略/Frozen schema修改0；實際Work7通過後仍到既有Work8目標單位待界定處。

## 2026-10-21 原始 C7 重新驗證與一次交回事項

已補回准讀原始 work7/asset_framework.py 並實跑 Work21 QA_RUN3，結果完全符合原 golden。這項證據只證明原 C7 可正確載入與重現，不能解決目前拼接 runner fixture 的來源一致性。

原 validate_drift_contract 要求 drift.denominator 與 confirmed final_target.denominator 完全相等，逐檔 drift=target-current，且非零漂移的 client_facing_action 應為 INCREASE_TARGET_WEIGHT/DECREASE_TARGET_WEIGHT；原 validate_protected_holding_contract 的保護對象為既有個股，非 ETF/債券。這些規則由原程式保留，W5 不擴充其策略。先前合成 runner 多處手動調整，不視為 C7 原生運算結果；SOURCE_BACKED 路徑現已要求原輸入重算及全結果核對。

Family 中PM待提供／界定：
1. W1 四庫 final_target_version 皆0筆：請定位四位家人已有確認記錄（fileId/path、client_id、allocation_id、版本、確認證據及target_lines），交 W2/資料責任人，不要求家人重填。
2. C Work6→C7 原始 canonical_input、work6_result、funding_context 及 producer/version/source_reference：由C線提供與確認目標相符的既有原件，W5用原引擎運算。
3. 正式 technical、報價/FX/NAV、V70戰術額度來源：各責任線指定檔案與欄位；W3原始feed就緒不等於戰術額度已具名。
4. Work8 project_target_position 金額/權重，以及 V75 HOLD_AS_IS 客戶動作優先序：由中PM具名核定接口；若涉及原核心，明列最小修正範圍。

影響W5-09～18最終驗收。W5現有來源綁定、實際引擎與恢復程式保留；收到既有來源與接口後續接同一Checkpoint，不另建替代規格。
