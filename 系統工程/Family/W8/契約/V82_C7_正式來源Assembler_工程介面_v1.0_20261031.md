# C7 正式同輪來源 assembler：工程介面 v1.0

依據：[中PM方案B裁定](V82_C7_長期目標與當輪額度分離_中PM裁定_v1.0_20261030.md) §2–7，以及 PR59 中PM 2026/10/31 續工裁定。此為來源轉接介面，不修改投資門檻、原49/13欄、舊scope、PM Gate或既有配置。

入口為 `family_c7_source_assembly.assemble_original_producers`，由原 `AssetSourceProducer` 呼叫。它讀原W1／已核准文件及 `native_target_source`、原 `v70_tactical_input.calculate`、原產品分類與V75標的分類。核准本金保留在原幣別原件，報表幣別沿原FX投影；Current NAV另列。試算現金、零cycle或缺少訂單列均不是實際資金／空訂單簿證明。

## 原件與內部正規化介面

可直接使用的本人核准與V70來源由程式組裝，不要求本人補寫。其餘原始券商／W1／Owner已確認資料經來源工程資格驗證後，才可正規化為 `Family.W8.PortfolioReconciliationFacts.v1`。這個JSON是工程內部介面，不能要求本人製作，也不能把欄位的 `VERIFIED` 字樣當作原件的替代品。

透過本人producer設定的 `portfolio_reconciliation_source.local_path/sha256` 讀取。內容不得含 `family_scope`、`canonical_input`、Work6／C7／native結果；來源必須綁本人client、原DB SHA、target version、原件reference、as_of及available_at。所有實際投資帳戶逐一列出owner/account/broker/currency/funding_domain及原身份證明；缺的帳戶不補造。

| 來源原件／原producer | 正規化資料 | assembler／consumer |
|---|---|---|
| 原W1／文件既有核准，原本金原件 | 原確認者、時間、版本、權重與native FX投影 | 原核准快照、approval receipt；原Work6讀取，不新增CONFIRM |
| 原V70計算與原HTML/feed SHA | 原allocation base、原總股票額、來源snapshot/as_of | schema83 total_stock_ceiling/accounting_base；不從現金或NAV反推 |
| 全帳戶身份與持倉／現金對帳 | `accounts`，每戶實際positions與net_asset_value | 分帳重算NAV、原C Current；不將未結算／可用現金混為NAV |
| 原持倉與價格原件 | position_id、economic_effect_ids、asset_id/ticker、quantity、price/currency、price_as_of/basis/reference | 數量×已證實market price；逐筆保留經濟事件，Current與confirmed exposure對帳 |
| 原現金／結算與W1 cash available資格 | total/settled/unsettled/reserved/available_cash、原source及settlement證明、cash_basis | 總額與已結算／reserved逐項核對；NET_AVAILABLE不再扣一次reserved |
| 本人已核准增額資金／資金域限制 | authorized_incremental_amount與原授權reference／時間／證據狀態 | 與可用現金分列；broker balance不是本人授權額，新增資金不是總股票cap |
| 原完整訂單簿／成交對帳 | `orders`、`fills`及coverage，原intent/event/effect IDs、總數量／已成交／未成交、state與commitment price basis | 只算未成交BUY承諾；partial/cancel-pending/replace-pending保留占額；原成交已反映持倉則不另加一次 |
| 原取消／到期／拒絕／部位減少確認 | `confirmed_releases`、確認狀態、所釋放event、economic effect ID | 只減確認釋放，沿原C7去重；未成交SELL不構成釋放 |
| 原其他承諾／涵蓋範圍 | `other_commitments`及positions/orders/fills coverage | 名列完整／不完整；缺整份list不能當空list |
| 原Owner／W1保護確認 | `protection_confirmation`、`holding_directives`及完整coverage | HOLD_AS_IS／UNLOCKED轉原Preference Lock；空表不表示無保護，沿原Work6治理 |
| 原client/global cap適用證明 | `portfolio_caps`與明確適用性；已知cap綁同currency/accounting_base_id | 原MIN，UNKNOWN保留；NOT_APPLICABLE須原件及原因，空list不作豁免 |
| 原Work64／明確FX原件 | `reporting_fx`，實際owner與幣別方向 | 只正規化報表預算；不下換匯指令、不創造現金 |

帳戶原始reported/gross cash未完成payable、netting、nonoverlap或結算查核時，不能填成合格available cash。原broker settled觀測也不自動等於可用現金。數量與金額以原十進位字串保留；日期與原始SHA不改成此次執行時間。

既有W1原件由 `w1_portfolio_observations.normalize` 產生內部 `Family.W8.W1PortfolioObservationReview.v1`，保留在 `original_observations.w1_portfolio_review`。逐帳戶列正式身份缺欄，具備完整明確候選時重用原W5 `bind_owner` 驗證，不用帳戶名稱推定券商／幣別／資金域，不傳分析用的臨時category scope充當金融身份證明。這是部分來源查核，不能直接當完整 `PortfolioReconciliationFacts.v1`。

現金每account/currency只選cutoff前同一最新as_of/version的完整原row；同版異值拒收，不逐欄回填較早非空值。W1 INTEGER分幣按原 `official_mutations.minor_units` 的100倍尺度精確轉成原幣十進位字串，附原minor欄位和值、幣別、row digest及原時間。不同幣別分列，未明確選定時不產生單一account現金值；`pending_payable_minor`只列應付款，不列為unsettled cash。reported／settled／receivable／payable／reserved原觀測各自保留，available與本人增額授權未知仍null，未自動推導或升格為可執行資金。持倉歷史逐account/instrument選最新觀測，不加總不同日期數量；缺完整涵蓋證據仍UNKNOWN。

相同instrument在兩個帳戶、同一報價單位的持倉，Current按instrument彙總一次，confirmed exposures仍逐帳戶分列；不同單位不能偷偷合併。position_id不能重複。CANCEL_PENDING／REPLACE_PENDING須附券商最後已確認的`last_acknowledged_commitment`（原總數量、承諾價、來源與時間），目前占額必須與之相符；尚未確認的縮量、降價不能降低占額。原觀測時間缺失時，inventory明列null／NOT_PROVIDED，另列本輪binding_checked_at，不能以本輪時間冒充原件時間。

## 輸出與依賴

每個schema83必填欄及具名子欄輸出來源定位、時間、hash、producer、consumer及下一責任，分三類：`EXISTING_BOUND_SOURCE`、`EXISTING_SOURCE_NEEDS_QUALIFICATION`、`ORIGINAL_FACT_NOT_PROVIDED`。未組齊時仍保留已可綁的核准／V70與原始觀測，輸出 `PARTIAL_ORIGINAL_SOURCES`，不再僅回「缺整個family_c7_scope_source」。

原始positions/cash足夠時可算Current NAV，不因訂單coverage未齊把NAV改為UNKNOWN；該缺項仍限制exposure book。明確授權0可與未知settlement/available並存，未知值不補0，由原C7判定是否足以證明新增0。此為來源／依賴判定，不代表四戶金融整線通過。

全來源結構可組裝時寫 `Family.W8.C7FamilyScopeSource.v1`：schema83、原件references/hash、完整Current snapshot；狀態為 `SOURCE_ASSEMBLED__ORIGINAL_C7_VALIDATION_PENDING`。原reader再次讀回並驗原件SHA，交原Work6／C7、原Gap／切片／MIN／帳本／Work9。來源組裝本身不核准金融決策。新scope最高仍READY_FOR_PM_GATE，a78/a79及Work8 release沿原Gate。

原V70數值函式的執行時鐘綁定request.evaluation_at，使其calculatedAt與同cutoff的原件hash可精確重播；HTML、feed、allocation base與原算式不變。這是計算時鐘，不能取代任何原始觀測的as_of／available_at；執行的實際牆鐘時間另存在run_receipt。

真實cycle只在合格Gap、permission、session及book成立後初始化。原SQLite交易、G0/B0、pending不提前釋放、Drive單序列writer／寫前重查／備份／原ID／重新下載讀回均沿用；沒有Drive分散式CAS，也沒有下單、取消、換匯或購買資料。
