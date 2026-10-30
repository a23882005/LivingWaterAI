# 新Codex｜Family報告與HTML獨立施工交辦

新Codex，請接手Family報告／HTML三項獨立修正。

施工包：https://drive.google.com/file/d/1695xJKZ2CTJeoedKAAjxlJI05jVc0j70/view?usp=drivesdk
位置：Google Drive根目錄／TEMP／Family_Report_HTML_Codex_Handoff_20261030.zip
SHA-256：d37e3ade355c66f4542be6567f5aff8e194d16ce1e35cefefe57f673a4f06386

請依包內00～04與version_snapshot開工，先核對最新main及PR59。只做：
• 接用C正式配置／漂移結果。
• 接好既有核准目標、四雷達與章節來源。
• 保存report.html完整分頁正文，核對PDF／翻頁HTML一致。

V82、每日切片／cycle及共同資金已由原Codex沿PR59施工，保持原分工。請從最新main開獨立分支、獨立Draft PR，只改契約准改的報告轉接／渲染／測試及本線文件；共用介面變更交中PM協調。
保留核准v16母版、配色、14章與既有缺資料呈現及工程驗收。先做獨立HTML與合成契約測試，再串正式上游。
包內50項既有報告測試已通過，屬施工前基線；新修正另補測試與視覺QA。交回PR、commit、改檔、測試／視覺證據與依賴，由Family中PM獨立驗收。


準備時 main：946a2a4e057b212865b693c18ffac54e30bff401；原 PR59 head：48e896128a94eaa2132f9d210fbbcb94d9ec8ed1。開工重新核對最新版本。



新Codex獨立任務｜Family報告資料承接與HTML修正
日期：2026/10/30（台灣時間）；委託／驗收：Family中PM；Owner：指揮官。

只做三項：正式配置／漂移承接、報告來源轉接、完整內文HTML保存。
V82、日切片／cycle、共同資金已由原Codex沿PR59施工。本包沒有將這些重新交辦。

依序讀00、01、02、03、04、version_snapshot.json；然後Fresh Read最新main、PR59及兩線Checkpoint。
Repository：a23882005/LivingWaterAI。
基準與snapshot SHA見version_snapshot.json。開工從最新main另建獨立分支，例如family/report-canonical-html-20261030；保留原PR59分支。
包內source_snapshot是讀取時參考，逐檔Git blob已核對；實作以開工時最新程式與正式契約為準，不整包覆蓋工作樹。

工程交付：獨立Draft PR、改檔清單、介面映射、測試與視覺證據、剩餘依賴，回Family中PM獨立驗收。此包是施工交辦，不是程式完成憑證。
優先把不依賴V82新輸出的HTML修正及合成契約測試做完；正式整線在中PM協調的上游版本就緒後進行。
不得改投資規則、比例、私人DB或原線持續施工的共用程式；需要共用修改時，列具體檔案／欄位／原因交中PM統一處理。

正式架構：GitHub程式＋ChatGPT按需執行＋Google Drive本人DB／報告。不新增常駐服務、排程或券商下單。
本包不含私人DB、真實持倉或帳號憑證。以合成資料先施工及回歸，真人驗收由中PM在本人授權環境執行。


Family報告／HTML獨立施工契約

【目標】
讓既有W6報告接到正確的正式配置／漂移與核准來源，並使獨立report.html保存完整分頁正文。保留Owner核准v16外觀、封面、配色、14章、四雷達、餅圖、雙條漂移圖與翻頁母版。

【三項工作】
報告正式結果承接：W8/w6_current_data.py目前按本輪投資池×DB權重重算target/drift；補接C正式目標／漂移／保護持倉與來源，不建立另一套金融決策。
報告來源轉接：W8/formal_report_source.py目前只從DB的final_target表產目標；補可信外部既有核准目標，以及四雷達／八組章節來源的無損轉接與同輪驗證。
HTML保存：W8/w6_member_render.py目前寫檔後才在瀏覽器分頁，最後回讀原始檔；保存完成分頁DOM，使report.html獨立開啟有完整正文。

【准改清單｜路徑以系統工程/Family/起算】
W8/w6_current_data.py
W8/formal_report_source.py
W8/on_demand_w6.py
W8/w6_member_render.py
W8/report_canonical_adapter.py（如需要新增，專責轉接，不計算投資結論）
W8/tests/test_w6_current_data.py
W8/tests/test_formal_report_source_current.py
W8/tests/test_on_demand_w6.py
W8/tests/test_w6_member_render.py
W8/tests/test_report_canonical_adapter.py（如需新增）
W8/tests/test_report_rendered_html.py（如需新增）
W8/Report_HTML_Contract_20261030.md（本線契約）
W8/Report_HTML_Checkpoint.json（本線獨立checkpoint）
W8/report_html_evidence/（只放合成資料、無私人數值的證據）
完成這些範圍所需的測試fixture可新增於W8/tests/fixtures/report_html/，必須全合成。

【准讀、保持原件的介面】
Family/W8/on_demand_project.py、official_family_entry.py、on_demand_report_delivery.py、正式架構裁決_ChatGPT按需執行.md。
Family/W6/runtime/report_receiver.py、source_views.py、report_archive.py、REPORT_SPEC.md、ENGINEERING_ACCEPTANCE.md。
Family/W5/family_runner.py、mentor_bridge.py：只核對上游輸出形狀及來源驗證，不改。
C-配置決策引擎＋Mentor整合/正式Runtime/work6/adjustment_loop.py：只讀Final Target／drift／radar契約與輸出函式。
同目錄work7/asset_framework.py：只讀report_contract、drift／radar轉交與資格。
同目錄C8C9_RUNTIME/C8C9_Work9_Unified_Deployment_Mentor_Return.py：只讀canonical_deployment_result與mentor_return輸出。
Mentor.md只讀最新Report／Downstream handoff與C整合契約相關段落；根檔案管理.md為重要Drive操作必要治理來源。
Family/W8/Checkpoint.json、PR59本輪契約／Checkpoint只讀進度與衝突範圍；shared Checkpoint與Family README由中PM統一更新。

【原線負責、保持界線】
V82/V75 runtime、V70程式／feed、Family W5及W8分析／資金／配置來源producer均留原Codex。不要為報告改49／13欄、金融演算法、目標權重、來源資格或上游狀態。
四戶私人DB、帳號庫、Project Instructions／Sources、正式客戶報告原件與網站部署都不在本線寫入範圍。
如需要新上游欄位，本線先完成可注入adapter、合成fixture與具體缺口清單；由中PM與原Codex協調。不可把已交辦V82工作再接過來重做。

【既有驗收與缺資料語意】
根治理已裁定W6_ENGINEERING_GATE=PASS_WITH_DECLARED_SOURCE_GAPS；保留原報表工程驗收及既有資料缺口呈現方式。
來源轉接修正依原正式規則驗證：當報告宣稱展示某項canonical計算結果時，必須有可追溯的該項正式結果；部分分析／歷史來源報告則沿其原報告scope及UNKNOWN標示，不新增所有報告都要完整部署或正現金的門檻。
不把全章節資料齊全綁成重新開啟W6整線已結案工程的理由；本次驗收聚焦上述三項增量行為。

【提交與協作】
獨立分支／PR，依准改清單檢查git diff。先完成本線隔離施工；真實上游共同整線依中PM指定版本串行驗收。
以最新main為base；原PR59未合併部分只作介面對照，不把整個PR59合入自己的報告PR，不複製其金融實作。
若原線同時修改准改檔，保留兩邊差異、暫停該檔覆寫，回報中PM具體衝突；其他不衝突工作繼續。
交付Draft PR，不自行合併、正式部署或修改客戶資料。


輸入輸出契約與驗收案例

【現行呼叫鏈】
Menu13 → on_demand_project.stage_latest_report → formal_report_source.build_report_source(snapshot) → OnDemandW6Renderer(formal_source, options) → trusted_current_input_producer → {market, engine} → build_w6_current_data → 核准v16 renderer → prepare_report_delivery。
此鏈只展示位置；本線准改範圍見01，選單及Drive交付介面保持。

【上游正式來源】
本人DB snapshot：client_id、identity、source_sha256、payload_digest與來源表。snapshot本身不等於即時估值。
C配置：正式Final Target、目標版本／確認證據、Current、共同分母、drift_snapshot.items、protected及client_facing_action、radar_snapshot、來源與資格。
Work9／Mentor：同輪canonical_deployment_result、來源bindings及摘要、原有可呈現範圍。
市場資料：經核實的持倉估值／FX、來源日期／資格、同client／DB SHA／run。
外部核准目標：既有W2／正式來源核准物件與原確認證據；保留原版本／reference，不新造簽署時間或改成另一套核准。
八組章節與四雷達：可信上游具名來源；缺值依原報告scope處理。文本來源可有不同as-of，需符合原規則並明列，不強迫所有原始資料時間完全相同。

【轉接原則】
優先重用原有canonical來源驗證與receiver能力；讀完整呼叫鏈後決定最小adapter。
如果需新增report binding，先用本線契約明列實際path、型別、單位、分母、來源digest／snapshot、版本與UNKNOWN／N/A語意；外部可信注入合法，但須有具體producer映射及驗證案例。
既有OnDemandW6Renderer輸入外框為{market, engine}，不擅自增加對外必填參數；必要report sidecar可由可信producer提供，寫清楚兼容／報告scope行為。
重用C正式目標與drift，純顯示單位／符號轉換須具名、可逆並保留canonical原值。C drift=Target−Current；現行雙條圖差額=Current−Target，圖例保留。符號相反本身不是算錯。
protected現有股票的canonical target=current、drift=0及保護動作完整保留；風險說明與賣出指示分離。
同run是分析綁定；歷史核准版本沿其原時間與授權，不為了同輪捏造新確認。transport retry與economic identity依既有正式契約處理，不改上游cycle。
W6輸出CurrentData仍含actual/target/drift/approved_radar/verified_sections、client、來源digest與render QA狀態；保留既有單位與格式，必要增量追溯欄只作sidecar。

【必測案例】
• 同一組完整合成C／Work9／市場輸入，報告目標、逐檔漂移及保護動作與canonical逐欄一致；涵蓋Current∪Target及僅存在其中一邊的標的。
• 原canonical drift為正／負／零時，顯示反號與圖例一致；保留原值與具名display欄位，不把反號回寫canonical。
• 完整本人外部核准目標在DB目標表空白時能合法承接；不同client、錯版本、缺確認證據、來源digest衝突被原規則拒絕或回原限定scope。
• DB目標與外部核准來源並存且衝突時明確回報，禁止默默挑第一份；既有多target_key與最新確認版本選擇測試保持。
• 假設／歷史來源不進當期actual；成交後持倉投影仍由原上游提供，不在報表另造。
• 同client不同DB SHA、錯run、錯owner／account、變更canonical摘要、錯單位／分母等可識別；測試依原契約精確驗證，不把無關缺值變新買進門檻。
• 四雷達六軸／六級順序與上游一致；八組章節有來源與原scope，未知內容依既有格式呈現，不偷帶舊Joseph數字。
• 報告類型：完整正式計算、合法WAIT／零新增、部分來源回顧、必要身分或來源錯誤，各維持原狀態語意，既有W6缺資料呈現回歸通過。
• report.html離線單獨開啟，有14章完整正文、目錄及分頁；無需再手動執行Playwright注入的PAGINATION_SCRIPT。一般讀取不顯示空白main。
• PDF、內文HTML、index翻頁版的client／run／資料日期／目標與漂移數字一致；封面、目錄、頁碼、圖片與中文長名不出框；主題樣式維持Owner核准母版。
• index與ZIP的PNG／data URI、手機翻頁／目錄與PDF頁數一致；圖片broken與overflow原QA保持。
• 舊API與on_demand_report_delivery既有測試回歸。prepare_report_delivery維持staging；真實上傳／讀回／manifest由中PM或當次正式執行者依原流程驗收。

【合成整線順序】
可信資料→canonical轉接→CurrentData→核准母版渲染→HTML/PDF/reader→staging計畫→mock receipts/readbacks驗證；真人Drive發布另由中PM依本人資料與授權驗收。


三項查核證據與正式母版

基準檔案SHA見version_snapshot.json；開工重新確認latest main內容，已修部分先驗證再跳過。

報告承接：w6_current_data.py在same檢查只核對engine部分外框，後段按DB目標及投資池自行建立target_rows／drift。C正式契約在原work7.asset_framework的report_contract明列renderer_must_use_work6_drift_snapshot／radar_snapshot。需補正式來源與資格，並區分完整計算與既有缺資料報告scope。
來源轉接：formal_report_source.py._confirmed_target_details只讀snapshot.tables的final_target_version/allocation；W5另有正式外部核准來源。本人外部核准目標與W6 DB-only來源需轉接；這不是要求改DB schema或重新核准。
雷達與章節：w6_current_data.py消費engine.approved_report_radar及approved_w6_section_content，renderer要求四視圖與八組章節；需對照實際producer與正式契約，不以參數名稱存在代替完整接線。
HTML：render_current_w6先write_text(_source_html)，再page.evaluate(PAGINATION_SCRIPT)，最後讀回原report.html；檔案沒有保存動態DOM。_source_html的main#pages為空且只有JSON資料script。PDF與index使用渲染DOM／PNG路徑，修正只補HTML保存與一致性驗收。

evidence/probe_report_chain.py與results為前輪隔離合成元件probe：可驗證上述原始HTML行為及CurrentData外框。該probe不執行完整Chromium，不當正式整線通過證據；新增測試須核對最新實作並擴充有意義案例。
此包不附私人DB診斷收據，避免讓承包者接觸非本線資料。

【核准母版與來源】
W6正式包：Google Drive ID 1oHZvKsKYa6VKFeV1C7D2KIUvGXzZxvyk。
https://drive.google.com/file/d/1oHZvKsKYa6VKFeV1C7D2KIUvGXzZxvyk/view
原包SHA256 b9b8d6eb1718b510f82e41e925f7a9145880caa8d3fe0a2dec4320ada515796e，與w6_member_render.W6_ZIP_SHA256一致；本輪本地CRC通過。
需讀的包內位置：sources/rebuild/src_v16/report.mjs（CSS來源）、sources/rebuild/mother.html、assets/cover_reference.jpg、assets/header_reference.jpg；必要時讀同src_v16的render.mjs／reader.mjs／validate.mjs等既有渲染程式。
包內visual_reference僅含上述CSS、reader母版及兩張圖的核對副本，供檢查外觀，不能拿來冒充原完整ZIP或繞過原ZIP SHA驗證。
正式包另含歷史客戶資料，本線只讀指定程式與母版，不取歷史持倉／報告數字回填新報告，也不把整包私人內容放Git。
如執行環境無法取得正式ZIP，先完成純資料／HTML函式與合成測試，回報具體資產取得介面，完整渲染由中PM以同版母包接續驗收；不另畫新母版替代。

根治理W6工程裁決保留PASS_WITH_DECLARED_SOURCE_GAPS；報表版號沿v16，工程裁定v16.4。後續具體Owner新裁定優先，從最新正式索引讀取。


施工工序與回交

開工：讀根檔管、最新main／PR59／本線範圍；查AGENTS及最新正式報表契約；列版本、diff與准改檔案。新分支從最新main建立，原V82保持原線。
接著：列實際producer→consumer欄位映射，指出哪些main已有、哪些仍依賴未合併上游；確認既有W6驗收與母版保持。
先做：獨立HTML保存修正與測試；再做canonical／外部核准目標／雷達章節轉接，依賴以可信注入與合成fixture先驗證。
驗證：跑受影響資料、renderer、來源與交付回歸，產合成HTML／PDF／PNG並逐頁檢查。完整渲染需要Playwright／Chromium與核准母包，依原runtime依賴使用；缺依賴明列實際錯誤與已完成的其他工作。
交付：獨立Draft PR，標題清楚寫Family報告來源承接與完整HTML。PR描述列問題、修正行為、真實測試、視覺證據、上游依賴；不把未跑測試標為通過。

回交必附：
• base/head commit、branch與PR URL、完整實際改檔清單。
• producer／consumer精確path、單位、分母、來源及資格映射。
• 測試命令、數量、輸出與失敗／跳過原因；全部使用合成資料的說明。
• HTML/PDF/index一致性及逐頁QA證據；母版SHA、圖片、中文長名、手機互動、頁碼檢查結果。
• 已完成／未完成、跨PR依賴與唯一下一責任；本線Checkpoint與恢復步驟。
• 中PM獨立驗收所需最短重現程序與指定fixture。

治理：本線只寫自己的Contract／Checkpoint／合成evidence；中PM負責共享工程、檔管、MasterWBS與W8 Checkpoint同步。新增重要Drive檔先讀根檔管；既有檔修改先備份、同ID、讀回。私人資料不進Git。
完成後交中PM驗收，再由中PM安排與原Codex正式版本整線、真人報告、本人Drive保存讀回。原PR59的V82與共同資金責任保持原分工。
