# Family 金融→報告交接契約及接收相容修補工單 v1.0
日期：2026/10/31（台灣）。責任：家人版中PM／全專案總PM。

## 1. 本次基準與交付
- 金融producer：PR59 d250d3c506da3f7bec1dd7f3b5c89639a69765f7。
- 報告consumer：PR60 4319556a67f83f1cf3fc754446a2c401335db3e1。
- 已完成驗收：PR59 W1與四戶32檔封存重播分段PASS；PR60四戶77頁SOURCE_REVIEW資料／靜態排版／保存查閱分段PASS，正式留言：https://github.com/a23882005/LivingWaterAI/pull/60#issuecomment-6535506724。
- 本輪只鎖定上述producer/consumer介面及修補範圍；完整真人同輪金融來源尚待補齊。日後金融producer有新commit，中PM另鎖版本與來源digest，禁止把新commit寫成已驗收舊版。
- SOURCE_REVIEW、1fe71862排版PASS及來源超界CLOSED保持；不重做四戶報告、不修改正式本人DB、不改核准配置或任何投資門檻。
- 執行架構維持GitHub存程式、Drive存DB/帳本/報告、ChatGPT按需執行。

## 2. 已查證問題與現行權責
FAMILY-MENTOR-SCOPE-CONSUMER 已重現：
PR59 W5/mentor_bridge.py:explain_native 輸出 execution_advice_allowed=True、recommendations_allowed=True、broker_execution_allowed=False，production=HOLD、trade_action=NO_TRADE。
其既有 tests/test_recommendation_output.py::test_native_work9_to_mentor_keeps_advice_amounts_without_trade_permission 明確驗這組語意；起源提交56ec864為建議金額與券商執行權限分離。
PR60 W6/runtime/report_receiver.py:receive_action 卻固定要求mentor.execution_advice_allowed is False。把真實PR59原Work9/原Mentor輸出接入PR60既有test_actual_original_work9_and_mentor_output_shapes_are_consumed，出現MENTOR_EXECUTION_SCOPE。
中PM裁定：沿原「建議可呈現，券商交易未授權」語意，修報告consumer相容性；不將金融producer flags改回False消除例外。

## 3. 第一階段：立即交原報表Codex沿PR60修補
輸入：上述固定金融producer程式與原生Work9合成golden fixture；原PR60 consumer與已核准母版。工程合成正向可立即重現，不必等待四戶金融原件齊全；此階段不產生新的真人完整金融報告。

准改範圍：
1. 系統工程/Family/W6/runtime/report_receiver.py（本輪新增明確准改檔，限receive_action權限接收/追溯）。
2. 系統工程/Family/W8/report_canonical_adapter.py（僅必要欄位承接、驗證；不重算策略）。
3. 系統工程/Family/W8/tests/test_report_canonical_adapter.py、test_report_rendered_html.py、tests/fixtures/report_html/synthetic.py。
4. 原W6 report_receiver對應測試；如原檔不存在，可新增W6/tests/test_mentor_scope_compatibility.py。
5. 本線Report_HTML_Contract_20261030.md、Report_HTML_Checkpoint.json與report_html_evidence/證據。
保留w6_member_render.py母版/配色/字級/來源換行全檔；不修改W5金融producer、共用README/Checkpoint、W1/帳本/登入/真實DB。若來源鎖需反映新增consumer，列出必要diff交中PM核對，不更新不相關金融規則鎖。

接收行為：
- 舊版明確execution_advice_allowed=False：保留原合法路徑；不要求舊版缺少的新欄位。
- 新版True：僅接受明確Family.W5.mentor.v1、recommendations_allowed is True、broker_execution_allowed is False、production=HOLD、trade_action=NO_TRADE，且既有result/request/client/run/owner/currency/來源/Work9/canonical/hash驗證全部通過。
- 任何明示broker_execution_allowed=True、非法型別、未知權限值、錯本人/錯run/錯canonical等必須拒收。新True路徑缺少明確新flags亦拒收；不以bool('False')或truthy字串判讀。
- 所有既有來源／scope／C7／NAV／保護／Work9／Mentor／章節守門保留，失敗result仍無canonical/mentor建議。
- 原始engine.result.mentor與其權限原值須完整保留在lineage。報告顯示建議不授予交易權；receiver既有回傳欄位如需新增映射，須在本線契約列清楚，禁止偽改上游原值或偷偷重定義既有欄位。
- scope=SOURCE_REVIEW、缺canonical C／market未知時，繼續沿現行UNKNOWN規則；CANONICAL_CALCULATION仍需原正式C與成功Work9等全部資格。

必要驗收案例：
A 真正PR59原Work9→explain_native→PR60 receiver/adapter正向通過，amount/ratio/action/owner/run/canonical/digest逐值不變。
B 舊版False合法fixture仍通過。
C 新True但broker=True、broker缺失、recommendations缺失/False、flags字串各拒收。
D 對client/run/owner/currency/canonical/hash/來源時點的既有攻擊仍拒收；失敗狀態無建議。
E 新舊SOURCE_REVIEW／DB-only／canonical要求及來源換行回歸仍通過；本輪不拿合成正向當四戶金融PASS。
F 檢查來源/章節輸入不被修改、無DB寫入、無券商動作。
測試隔離：PR60的原W5可保留，測試明確載入固定PR59 producer；不得為混用sys.path把整個W5散拷到報告分支。固定上游snapshot/hash作合成測試依賴可用；私人真人資料不放公開repo。

回交：同一最終commit、准改差異、來源blob/hash、原始JUnit/CI、正負案例與回歸結果、精確私人成果位置。PR60維持Draft，中PM獨立複驗。接收相容修補本身無須重產四戶20份報告。

## 4. 金融線：原PR59持續；中PM集中原件
原V82 Codex沿既有工單完成既有合法原件資格／正規化／原金融主鏈；本包36組需求映射179原列，不是36份已取得文件，也不是新增36個Gate。
中PM負責每戶一次性整合業務原件，不要求Owner填JSON；Codex負責技術正規化。
原已驗收6帳戶/25歷史持倉/3現金快照只作觀測；實際完整帳戶資格0保留。404個ORIGINAL_FACT_NOT_PROVIDED欄位仍沿1105原清單逐檔追蹤，未被179列去重取代。
MOU核准池NT$837000與SGOV20%保持；Joseph撤回本金不恢復；Arthur/Lilian自述現金不代入核准總投資池。

## 5. 第二階段：完整金融章節，另由中PM鎖真人交接版本後放行
目前狀態：WAITING_FOR_QUALIFIED_FINANCIAL_SOURCE_AND_PM_VERSION_LOCK；不是這一階段修補的前置阻擋。
原金融線交付：4戶同輪原件／request／context／result／C7／Work9／Mentor／call_trace、來源schema83/84/85版本與hash及本人DB/ledger/run/cutoff/owner/currency。
中PM核對後，才鎖定新的consumer交接清單與全戶來源digest，交原報表Codex逐章接入。
現行介面沿Family.W8.ReportSources.v1：source、request、result、c7、target_context與sections同本人/同run/同DB與snapshot digest；上游C/Work9/Mentor原值不由顯示層補算。
sections精確八鍵：bond、market、radar、valuation、actions、risks、education、institutions。每個envelope沿canonical_section的client_id/run_id/section/value_state/source_id/rules_sha/as_of/payload_sha256/payload；未知章節保留具名UNKNOWN，不能把八鍵與歷史七組envelopes稱為同一套分類。
四雷達使用原C驗證器及canonical_snapshot，UNKNOWN/N/A原意保持；無合格雷達不產生分數。
完整章節驗收後才重新產製四戶PDF/完整內文HTML/reader/ZIP/manifest，依本人Sources原folder保存、新台灣時間檔名、20件新下載/查閱驗證；保留本輪已驗收報告。
真人Project UAT、56項、Gate D/發布/試用/Gate E由中PM依既定WBS接續；Android/iOS實機Owner暫緩，Production HOLD／交易NONE。

## 6. 溝通與狀態
本文件是中PM已完成、可交原Codex的具體工單。第一階段READY_FOR_REPORT_CODEX；原會話ACK尚待回覆，不宣稱背景施工已啟動。第二階段尚待真人金融來源及中PM新版本鎖定。
