> CURRENT 2026-10-21：已依指揮官核准範圍完成FamilyRunner技術接線及工程驗證，最新成果與範圍詳 ENGINEERING_ACCEPTANCE_RESULT.md；正式工程完成數與最終部署證據以Checkpoint及ZIP根目錄RELEASE_RECEIPT.json為準。以下較早進度段落僅為歷程。

# W5 累計契約驗收矩陣（2026-10-21）

結論：16/18；01～08、10～17完成，09來源協調中、18整線待收尾。僅計已滿足本棒功能與證據者；不將合成資料列為真實家人投資建議。

本輪不修改Runtime，不重跑未受影響的268項測試。沿用commit bccd1627a73dada8d4aadc03511586ac66f2312d的本機268 PASS、CI268 PASS/111來源hash PASS。CI run39469962774、job118791118667；完整log存交付包CI證據。原上游369項歷史回歸沿用原證據，未假稱本輪重跑。

| 工序/矩陣 | 證據（tests/下） | 驗收結果與範圍 |
|---|---|---|
| 09 技術輸入 | test_stock_engine.py | 完整合成輸入可實算；身份、Adj Close、缺樣本、未來swing拒絕。具名實際producer/週月K來源未收到，BLOCKED_EXTERNAL_SOURCE |
| 10 股票額度 | test_stock_engine.py; test_v70_source_bridge.py | 原引擎450上限；125額度按lot得到120；Hard Gate/EXCEEDS_CAP/零額/UNKNOWN不放行；原source_run保留。完成 |
| 11 股票投影 | test_stock_engine.py; test_target_units.py | 49/13欄原組裝，raw及金額保留；未定義減碼NEEDS_REVIEW；合法零值/目標已滿足區分。完成 |
| 12 債券額度 | test_bond_engine.py; test_family_sources.py; test_family_bridges.py | 真predicates與Step10、350預算守恆；公債/公司債原規則、信用危機、缺資料、零部署、跨戶與unsettled拒絕。完成 |
| 13 債券投影 | test_bond_engine.py; test_bond_target_mentor.py | account-level INVALID_INPUT/BLOCK即使空per-asset仍保留；長期Target和今日部署分開；raw Money保留。完成 |
| 14 SGOV | test_sgov_bridge.py; test_position_source_bridge.py | physical120、既有roles100、未分配20；未成交contribution不加持股；超分配/跨戶拒絕、UNKNOWN保留。完成 |
| 15/T01 真入口 | test_family_end_to_end.py | 真FamilyRunner→C7/V82/V75/C8C9→Mentor，股票目標/現有100，債券目標200扣既有40得到160；同源輸入不變。完成 |
| 16/T09 說明 | test_mentor_bridge.py; test_bond_target_mentor.py | 真結果可說明，數字不可被LLM改寫，Protected風險保留。中PM核准原None/null＋來源分欄；受影響34項PASS，16完成，詳PM16_APPROVAL_AND_ACCEPTANCE.md |
| 17/T10 恢復 | test_recovery_bridge.py; test_family_end_to_end.py | 真結果重送、競爭、實際逾時晚到、中斷恢復、撤權/版本更換；最多兩次計算跨重送保留。STAGING_VERIFIED |
| T02 真W3來源 | test_family_sources.py | 原read_macro讀取核定feed，m12 MOVE 101.298698進原V75 predicate；其餘完整案例明標合成 |
| T03 隔離 | test_family_input.py; test_family_boundary.py; test_funding_guard.py | 四client隔離、owner五維及digest核對；真實四庫唯讀檢查見evidence/runner_private_checks.json，私人內容僅Drive |
| T04 資金 | test_funding_guard.py; test_family_bridges.py; test_family_end_to_end.py | 多筆/股債合計/重複/未知/零額，available不推導；Family真輸出呼叫同一核對函式 |
| T05 SGOV重送 | test_sgov_bridge.py; test_family_end_to_end.py | 原physical保持，未成交contribution獨立，重送只發布一次 |
| T06 規則 | test_stock_engine.py; test_family_bridges.py; test_bond_engine.py | Hard Gate/Universe/Protected/長期目標與當期部署保留；09技術producer覆蓋缺口仍列明 |
| T07 時間版本 | test_v70_source_bridge.py; test_family_end_to_end.py | 歷史確認run/上游run與本輪run分離；未來/舊版本/晚到拒絕 |
| T08 狀態數值 | test_recovery_bridge.py; test_bond_engine.py; test_target_units.py | Decimal型別保真，UNKNOWN不填0，account狀態及raw action保留 |
| T11 回歸 | evidence/regression_runs.json、regression_0.log～regression_6.log; evidence/family_e2e_tests.log | 本線268及CI通過；原核心未改，沿用已驗上游證據 |
| T12 交付 | dependency_lock.json; requirements.lock; verify_dependencies.py | 固定commit、111hash、同一測試入口、Drive manifest與讀回；PR #22為draft，最終整合尚未完成 |

本輪完成數增加來自逐條核對既有程式及已通過測試，不新增固定回傳、不降低原schema要求、不把尚缺來源標KNOWN。缺實際資料的安全結果是覆蓋限制；需要原接口裁決的項目仍保留未完成。
