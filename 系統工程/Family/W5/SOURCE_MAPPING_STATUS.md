## 2026-10-21 V70不同來源批次與Family重送綁定（仍8/18）

新增v70_source_bridge.py，保留上游原context/payload/run_id及digest；project_v70_context建立本輪分析envelope，僅映射外層與payload的run_id，原金額、issue_codes、quality、snapshot/time/lineage保持。兩支線handoff及V75 snapshot逐欄比對，接原tactical_cap。W3 ready feed仍僅供原始總經來源，戰術額度由明確V70結果提供。

operator trusted_context新增v70_source：schema_version=Family.W5.V70Source.v1、producer、version、source_reference、client_id、family_owner與context（原V70 runtime context）。request新增v70_source_digest，納入既有請求digest；來源版本變更後，原W2 staging快取重送會重新核對並拒絕舊請求。輸出保留source_run_id、analysis_run_id、original_source、projected_context與股債上限。

本線241 PASS、1 strict XFAIL，90來源hash PASS。新增13項：不同upstream run實際執行V82/V75，正常450/350，EXCEEDS_CAP時0/0；原上游資料保持；缺來源、版本/owner/批次/時間/額度/品質/副本不符及快取重驗。證據見tests/test_v70_source_bridge.py與evidence/v70_run_binding_tests.log。

本輪完成來源批次映射的本線接線；具名正式V70 producer、完整technical/報價/確認Target及C7全框架仍依既有交接定位。Family中PM裁定Work8金額/權重與V75客戶保護動作接口；W5依核定續接完整Family/Mentor。Production HOLD、交易NONE；備份backup/w5-20261021-v70-run-binding，commit/Actions/雙端讀回見累計ZIP RELEASE_RECEIPT.json。

## 2026-10-21 債券目標與Mentor來源接線（仍8/18）

bond_target_bridge逐檔核W2確認target_amount、明確target_instrument_id別名、ticker、同帳戶/同幣別，並核W1確認holding policy與C7 protected標記；UNKNOWN/未確認/缺對應停止調度。目標與當期資金分開：合成歷史目標SGOV5600、SPSB2400，當期bond budget350，原V75實際縮放運算。

Mentor新增有digest/owner/run綁定的family_policy_context及c7_client_action，原V75 source_action、canonical與client_preference_action完整保留；禁止新買但部署額非零拒絕。原Work9 V75 client_preference_action為None，跨引擎客戶動作優先序須中PM界定，現狀明標SOURCE_FACTS_ONLY_PENDING_CROSS_ENGINE_PRIORITY。

實測V75 Decimal零可能序列化成0E-28，與Frozen schema不合；W5 money_wire精確轉成一般十進位，指數零轉0，原0.00保留。另存raw_runtime_ready，策略/數值/原核心與schema未改。原Work7實際通過，完整Family仍停於既有Work8目標金額/權重接口。

本線228 PASS、1 strict XFAIL，90來源hash PASS。測試明細見evidence/bond_target_mentor_tests.log及tests/test_bond_target_mentor.py；新增18項。中PM具體責任與原檔欄位見中PM介面待界定.md。跨帳戶目標拆分/FX及具名producer仍待來源；完整Family/Mentor與最終部署續作。Production HOLD、交易NONE。備份backup/w5-20261021-bond-target-mentor；commit/Actions/雙端讀回記累計ZIP RELEASE_RECEIPT.json。

## 2026-10-21 確認目標內容接線（仍8/18）

新增 target_source_bridge.py：W2 歷史 target_lines 須非空、標的唯一且完整對應 C7；逐欄核原始 work6_final_target_weight，保護後 integrated_weight 保持原值。V82 明確 target pointer 與兩份原生 handoff 的同幣別目標金額，必須等於 W2 原 target_amount，與 planned_investments 分開。

新增14項測試，本線210 PASS、1 strict XFAIL；90來源hash PASS。即使重新產生合成確認與審核digest，空目標、重複、覆蓋差異、權重/金額差異、跨幣別缺來源與錯誤pointer仍於調度前拒絕。既有runner合成fixture補明示歷史目標內容；W2原golden及家人歷史未改。

本輪為部分語意接線：V75目標拆分/別名/資金桶、C7保護後權重推導、跨幣別FX與完整Family/Mentor仍待驗收。債券客戶行動回傳尚未於本輪修改。Family中PM續定位既有確認Target與具名producer並界定Work8金額/權重接口。Production HOLD、交易NONE。備份 backup/w5-20261021-target-source；本輪commit/Actions/讀回見累計ZIP RELEASE_RECEIPT.json。

## 2026-10-21 估值／SGOV／保護持倉增量

新增position_source_bridge.py並接FamilyRunner。operator提供valuation_source.prices（asset_id→instrument_key、value、currency、state、unit=CURRENCY_PER_SHARE、as_of、source_reference）、選用fx，以及明確portfolio_nav。請求新增valuation_digest=來源上下文的canonical JSON SHA256；重送、快取及發布前重驗沿用此綁定，來源資訊改變即拒舊請求。

W1已核對實體數量以既有value_position公式quantity×price×explicit FX估值，要求quantity時間≤quote時間≤native分析時間≤Family evaluation_at；價格與W1商品幣別、V82 valuation_price/as_of核對。UNKNOWN保留並回報DATA_UNAVAILABLE。非SGOV債券既有金額逐筆比對估值；SGOV實體價值與physical_sgov金額、owner、時間核對後交原Work7，邏輯bond/dry-powder另列。當前Family原生支線為同幣別；跨幣別路由仍待原C契約接續，既有FX公式/UNKNOWN元件測試保留。

股票保護從W1確認紀錄project_permissions取得HOLD_AS_IS或ADJUSTABLE，對照C7 target/drift/protected lock標記。現有權重以明確同幣別、同估值時間NAV核對，容差1e-12沿原Work8；不以局部持倉自行建立全戶NAV。Family pipeline交既有protect_existing→原Work8，保留risk_action及client_action。

合成Family fixture本輪補齊明確報價、NAV、ADJUSTABLE政策；校正原先零股數卻帶protected current weight .05的混合fixture，並把native/shared分析時間與Family evaluation_at對齊、重算原shared digest。直接native pipeline的原始目標單位重現仍維持strict XFAIL。真家人資料未改寫。完整HOLD_AS_IS風險分離沿既有原Work8正向元件證據；新增測試驗W1確認政策→現有估值/保護標記綁定，完整Family Work9仍待目標單位界定。

已接的來源欄位不代表完整C7全投資組合Target/Drift來源驗收完成。剩餘：C7全框架/已確認Target語意、正式報價/technical/V70 producer、不同source_run、完整Family/Mentor端到端與最終部署。

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
