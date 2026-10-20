# Family 中PM裁定接收與 W5-16 驗收

本版正式裁定：沿用原 Work9 的 None／null＋來源分欄。保留 V75 原生動作與金額、W1 持倉政策、C7 客戶動作，各欄互不覆寫；沿用既有核心，不新增債券優先序。None 不代表 HOLD 或買賣許可。不支援的債券保護情況仍明確阻擋。

W5-16：COMPLETED。受影響補驗34 PASS（33項 Mentor／債券分欄回歸，加1項原C7債券保護契約拒絕）。新增3項測試，既有268項證據保留，未重跑無關案例；本輪runtime與核心修改0。

核驗：原生source_action、canonical、deployment_amount完全相等；W1 policy與C7 action保持原來源；Python None序列化為JSON null；trade_action=NO_TRADE、execution_advice_allowed=false。Family對不符保護框架回BOND_PROTECTED_FLAG_MISMATCH且無Mentor發布；原C7回protected SGOV is not an existing individual company stock。禁止新買卻帶非零部署亦拒絕。

相容性說明：既有client_action_resolution字串SOURCE_FACTS_ONLY_PENDING_CROSS_ENGINE_PRIORITY及摘要「待接口確認」保留為舊版wire文字，本裁定已解除W5-16接口待決；本版正式語意為核准的來源分欄，仍無新增跨引擎債券優先序。依中PM限縮範圍，本輪僅更新說明、狀態與測試。

W5-09：BLOCKED_EXTERNAL_SOURCE。中PM已定位行情歷史程式與舊TD9／Swing函數，尚未核定完整供應現行V82欄位的producer。來源定位由Family中PM續辦，W5不自造算法、不重跑相同測試。
W5-18：IN_PROGRESS。必要來源齊備後由W5補受影響接線、整線與最終部署。沿既有家人歷史資料，不要求重填。累計16/18，Production HOLD、交易NONE；最終Major Gate由Family中PM驗收。

證據：tests/test_pm16_approval.py、tests/test_bond_target_mentor.py、tests/test_mentor_bridge.py、evidence/pm16_tests.log、evidence/pm16_protection.log。
