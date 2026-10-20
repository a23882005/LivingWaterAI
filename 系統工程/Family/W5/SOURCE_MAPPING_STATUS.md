# Family來源接線狀態｜2026-10-21

W5線內施工；Production HOLD、交易NONE。沿原V82/V75/C8C9，核心檔案維持核定基線。

| 來源 → 消費欄位 | 已實作核對 | 尚待完成 |
|---|---|---|
| W1股票instrument/position → V82 quantity | instrument key具名映射；ticker、exchange、currency、account/native owner；最新已知數量；同時點歧義拒絕 | 商品別名規則、來源估值與價格品質整線綁定 |
| W1債券position → V75 existing_policy quantity | 同帳戶商品數量、原生holding account/currency、證據account；UNKNOWN拒絕；具完整性證據的空部位為0 | 持倉估值逐欄綁定；SGOV實體數量與邏輯桶金額分開驗收 |
| W1 Universe/NEW_BUY → 原生股債上限 | PERSONAL、EXCLUSION與已確認policy；歧義回UNKNOWN；非新買候選加入0上限；股票走原V82 caps，債券走原V75 proportional_scale_decisions | HOLD_AS_IS到Work8、其他客戶行動保護；原風險及既有部位保留 |
| C7原輸出 → Family owner-local資金核對 | operator context獨立保留C7 payload；版本、owner映射及兩支線C7一致；兩引擎實際claims共用reconcile_funding | 正式C7產生流程與來源估值/Target的完整Family案例 |
| W3 /indicators/m12 → V75 PRED-005.move | schema、ready、digest、asOf、OK、^MOVE來源、原空unit的指數點口徑；值相等及available_at不早於feed可用時間；原列完整保留 | MOVE五日變化率與其他PRED欄，交既有具名producer；不以ready推戰術預算 |
| V70 tactical結果 → 股債部署上限 | 既有tactical_cap、EXCEEDS_CAP/Hard Gate、同run/source snapshot | 不同source_run正式binding與已確認S0/B0/Target來源 |

`trusted_context.funding_source`由operator provider提供，含`owner_binding`（family_owner、native_owner、currency、version、source_reference）及保留的`c7_funding_context`。此為施工來源上下文，W7正式身分/持久化仍由該線負責。

`native_binding.bond_instruments`以原生asset_id為key，逐筆提供instrument_key、account_key、native_owner、exchange、source_reference。商品ticker目前要求明確相同；不推測別名。

債券NEW_BUY零上限只經原V75縮放金額；原部署訊號、existing_position_action及規則碼保留，政策依據獨立保存在policy_sources/family_sources。這是原始風險訊號與允許新增金額的分離，後續Mentor/展示仍須完整整線驗收。

SGOV在W1是實體股數，在C7/V75可能是bond/dry-powder邏輯桶金額；本輪不把W1股數直接當bond bucket金額。原reconcile_sgov持續核對實體值、角色與未成交contribution。

證據：tests/test_family_sources.py（18項新增）、evidence/funding_macro_bond_tests.log、evidence/macro_move_projection.json。實際原W3 MOVE元件通過，完整PRED-005需要另一路五日變化率；正向predicate測試該變化率明標SYNTHETIC。完整Family原股債Work9案例仍有目標金額/權重strict XFAIL。
