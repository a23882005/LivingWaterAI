【2026-10-23施工狀態更新】B01～B05完成，5/23；現接B06統一讀寫管理。B05證據見B05_PROGRESS.md與evidence/B05/closeout.json。原契約完成條件不變；下方舊狀態保留歷史。

【2026-10-23施工狀態更新】B01～B04完成，4/23；B05進行中。B04依下列原v1.6.0最小能力實測條件裁定PASS，完成條件原文未更動；詳B04_CLOSEOUT.md。正式功能依原B06/B07/B18/B21/B23/W8分項施工驗收。下方舊狀態只作歷史，現況以Checkpoint為準。

【2026-10-23｜指揮官核定｜W7唯一B01～B23工序｜v1.6.0】
管理原則：越簡單越好，但每項務必落實。W7只用B01～B23作施工、驗收與進度；原W7-01～29停止使用，驗收目的已直接併入B項完成條件，不維護第二張進度表、不再回報0/29。A01～A14為已結案總經修復紀錄。
現況：B01～B03已完成（沿原範圍及證據）；B04進行中；B05～B23待完成。單一進度3/23，不因改編號增加任何功能PASS。B23完成後接W8→Gate D→四戶部署→試用修復→Gate E。W1既有29棒及其他已驗收工程保持原結案。
家人版採簡單帳號識別；Project整理對話，保留資料分人、固定四小時登入、跨對話接續及存檔防覆蓋。取消以取得原生Project/device ID作為強制開工前置；跨裝置行為仍須實測。具體服務接線由總PM選最小可行方案；本決定未授權購買新服務或啟用Production。
本人循序執行並維護正式契約/Checkpoint；每項完成需真實測試證據、雙端同版與治理讀回。Production HOLD、交易NONE、W4取消、RM17凍結保持。

以下為A階段歷史結案紀錄（當時進度與版本不代表現況）：
最新重跑確認：run39763653154兩個job均SUCCESS，真實feed與31契約案例全部通過。
【2026-10-22｜W7-A14正式結案／下一項B01】
Family總PM本人裁決：A01～A14總經故障階段PASS。真實來源、Task輸出與證據、發布/線上讀回、每日/月度歸檔、舊歷史保留、雙端逐檔校驗完成。交付包獨立65/65測試及22/22完整建置PASS。正式部署run39763653456 SUCCESS，真實feed瀏覽器job119773674394 SUCCESS；31契約案例已於相同程式main job119767281122 PASS。
最新結案commit33a50ff82e626a776d2eee904deae80a81c9e361；Checkpoint下一項W7-B01 READY_NOT_STARTED，接續施工者為本人。
最終完整ZIP沿原ID1L00lYv8mgEupygGPfW_qKV1pO_9mHxZS，名稱V70-3-27_完整程式與季度資料.zip，144項、11345720 bytes、SHA256 abfa719ee65a32e81ce83e3ce39402187f83d3b91f471ea4c9484dd2d490440c。工作ZIP原ID1MBqnDK7et_SCQCWzXQN4G4bU9jkSuwlr，78檔＋MANIFEST、266101 bytes、SHA256 fbaa0bda4f150c5dbe0a399fd3adf5acbc94033f71d9395ed2a181e8852c2f55。兩包均Drive實體下載逐位元、CRC及內部SHA校驗PASS。此最終憑證取代上方本輪中間包的檔數/SHA。
爬蟲ZIP原ID名稱更新總經爬蟲18項.zip；發布通知原ID名稱更新V70-3-27_本輪發布通知.md。完整包已納入全部修復程式與六項指定測試、相依檔及發布日曆，正式配對JSON與Actions deployed產物一致。
契約v1.5.10工序與範圍保持；契約追加本次驗收結果前備份1o-hNz5uMNDEz4Mly3FcfaPz-co08Fsp4。其他改前Backup承上筆A13紀錄。A14_CLOSEOUT.md、A13_PROGRESS.md及evidence/A13/均在GitHub與工作/完整ZIP。
正式Family W7驗收仍0/29。Production HOLD、交易NONE、W4取消、RM17凍結，BR結案與明列限制及原來源例外保持。本人接續B01～B23→W8→Gate D→四家人Project部署→試用修復→Gate E；正式家人/共用/帳號DB僅Drive。

# Family W7 統一施工清單 v1.6.0
更新日期：2026-10-22（台北）｜責任：Family中PM／全專案總PM本人

最新正式排序：W7-A01～A14總經bug修復與驗收 → W7-B01～B23原W7家人版工作與W7驗收 → W8整合測試 → Gate D → 家人版正式部署 → 試用修復 → Gate E。
全程由中PM本人循序執行。B01～B23為唯一現行W7施工與驗收工序，取代原W7-01～29；A01～A14保留為已結案紀錄。
此表為唯一現行施工順序，將v1.5.3～v1.5.7的缺項補正合併到各工作列，不再分別執行多份清單。A14是總經故障階段結案，B23才是W7整體驗收。

實體位置前綴：
- G＝GitHub a23882005/LivingWaterAI/；預設main，automation-state另列。
- D＝Google Drive根目錄/系統工程/總經V70。
- Z＝D/V70-3-27_完整程式與季度資料_部署160_20261020.zip內的V70-3-27交付/（原ID1L00lYv8mgEupygGPfW_qKV1pO_9mHxZS）。
- F＝Google Drive根目錄/🫅活水AI系統最高規劃企劃書及法規管理者。
- C＝G/系統工程/C-配置決策引擎＋Mentor整合/正式Runtime/。
- B區新增/修改程式的Drive交付：F/W7/＋完整repo相對路徑（待建鏡像）；已驗收W5既有包為F/W5/W5_累計施工成果_20261020.zip。
所有執行依賴使用W7-A/B編號。尚待定位、擬新增保留真實狀態，由B01～B04完成對應核實。

|編號|工作內容／修改內容與狀態|涉及檔案|實體位置與子目錄路徑|
|---|---|---|---|
|W7-A01| 核對最新施工版本、m02／m14原抓取錯誤，保存重現證據；依真實來源結果修復，維持既有投資公式。 【完成條件】最新施工基準、原抓取錯誤及真實來源重跑結果可追溯。| 總經爬蟲18項.py、macro_source_config.json、18_macro_verification.json | GitHub：G/系統工程/總經V70/總經爬蟲18項.py、G/系統工程/總經V70/macro_source_config.json、G/data/18_macro_verification.json。Drive：D/總經爬蟲18項.py（1P9WWNdrkRtSBZsMU805TDGoFGdcSgXBV）、D/macro_source_config.json（18V0hdvQL0EABamsotpelmcNmiLJCP4ld）；資料副本位於Z/data/18_macro_verification.json。 |
|W7-A02| 明訂政策生效日、發布日、取得時間、成功核實時間、證據與有限期限；上下限同日、中點一致。四子項完整驗證後才產生合格m06；輸出保留核實欄位。 本項先定案共同欄位、型別、時區、證據結構及有限核實期限，再改builder；同一契約供A03前端及A04生產者使用。【完成條件】共同契約已定案，合格/缺證據/逾期/未來生效/上下限不一致案例結果正確。| build_daily_v703_site.py ；總經Task_爬蟲缺值補抓規則.md（共同契約）| GitHub：G/scripts/build_daily_v703_site.py。Drive：Z/scripts/build_daily_v703_site.py。 共同契約：G/系統工程/總經V70/總經Task_爬蟲缺值補抓規則.md，Drive交付Z/系統工程/總經V70/同名檔（補入）。|
|W7-A03| 前端沿同一契約驗證；數值／日期／來源改動後重驗。補正式配置當下26小時檢查，含開頁後才過期情境。 【完成條件】與後端判斷一致，手動修改及開頁後過期驗證通過。| V70-3-27.html | GitHub：G/系統工程/總經V70/V70-3-27.html。Drive：D/V70-3-27.html（1kWdpjQgfrYZYcHyMrN1BpNxcKvXqnUz7）；Z/系統工程/總經V70/V70-3-27.html。 |
|W7-A04| 修正補充資料產生契約、實際Task提示詞及輸出，明訂新欄位／格式／時區／證據。保留Task原報告與3／6／12個月預測工作。 先準備與測試新Task提示詞/輸出；正式Task切換與A13已驗證消費端版本協調，切換後真實產出並讀回。【完成條件】實際Task按新契約產出，提交與讀回一致，原報告職責保留。| 總經Task_爬蟲缺值補抓規則.md、8_macro_supplement_verified.json；「總體經濟狀況」Task | GitHub：G/系統工程/總經V70/總經Task_爬蟲缺值補抓規則.md、G/data/8_macro_supplement_verified.json。Drive：Z/data/8_macro_supplement_verified.json；上述契約MD需補入Z/系統工程/總經V70/（現包缺此檔）。ChatGPT Tasks：總體經濟狀況，ID 6a9401fbb0648191ad87e528dd375daf，每日10:00 Asia/Taipei。 |
|W7-A05| 修正雙端每日程序文件不一致：Drive仍寫九補充／五子項／舊schema；同步現行八補充／四子項與25獨立、28傳輸、26必要、22計分，加上新核實契約。 【完成條件】GitHub、Drive獨立文件及包內副本同版同口徑。| 每天總經及html更新程序.md | GitHub：G/系統工程/總經V70/每天總經及html更新程序.md。Drive：D/每天總經及html更新程序.md（14l0q_5G6ffIGJ9qXhG-YE_LN15dkCwPx）；Z/系統工程/總經V70/每天總經及html更新程序.md。 |
|W7-A06| fallback保留原錯誤、嘗試結果、快取來源及原日期；一致CSV欄位與序列化，JSON／CSV／報告一起產生驗證；m14維持共同週三與13週口徑。 【完成條件】JSON/CSV/報告輸出成功，原錯誤及快取來源保留，m14期次完整。| 總經爬蟲18項.py；18_macro_verification.json、18_macro_verification.csv、18_macro_report.md | 程式同W7-A01。Action執行器：build/macro18/18_macro_verification.json、build/macro18/18_macro_verification.csv、build/macro18/18_macro_report.md；09h產物包macro18-09h-<run_id>。正式JSON：G/data/18_macro_verification.json。 |
|W7-A07| 保存同值但新核實證據，分開最新診斷與歷史觀測；復原保留歷史性質，告警讀取新診斷；期限規則與既有例外逐一列明。 【完成條件】同值新證據可追溯，歷史復原不刷新核實，告警與狀態相容。| macro18_state.py、macro18_alert.py、macro_source_config.json；macro_alert_state.json、macro18_*.json；擬新增macro18_latest_diagnostics.json | GitHub程式：G/scripts/macro18_state.py、G/scripts/macro18_alert.py、G/系統工程/總經V70/macro_source_config.json；Drive程式：Z/scripts/同名檔、D/macro_source_config.json。GitHub automation-state分支根目錄/macro_alert_state.json、backups/macro18_*.json；擬新增根目錄/macro18_latest_diagnostics.json，實作後才建立。 |
|W7-A08| 修改09:00 Action：接入新診斷保存路徑、CSV／報告驗證與新增測試，確保git add會提交新診斷；保留備份復原及告警流程。 【完成條件】新測試/診斷檔實際被工作流執行及保存，產物與分支讀回一致。| macro18-preflight.yml；alerts.json、d009_actions_proof.json | GitHub：G/.github/workflows/macro18-preflight.yml；G/data/d009_actions_proof.json。Drive：Z/.github/workflows/macro18-preflight.yml。Action產物：build/macro18/alerts.json；狀態分支位置同W7-A07。 |
|W7-A09| 補後端政策、快取、狀態、告警、正式歸檔測試；前後端共用相同邊界案例。新測試實際接入Action執行。 【完成條件】必要正向/負向/邊界案例實跑通過，逐案結果保存。| test_v703_monthly_release.py、test_d009_state.py、test_d009_alert.py、test_macro_safety_daily_capture.py；新增test_v703_policy_rate.py、test_macro18_cache_diagnostics.py | GitHub：G/tests/上述六個完整檔名。Drive：Z/tests/上述六檔，現交付包未含這六檔，本次補齊。前四為GitHub既有測試，後二為擬新增。 |
|W7-A10| 修改前端回歸Action，執行政策日期、子項失效、手動改值、開頁後過期、正式／研究模式案例。 【完成條件】瀏覽器實測通過，與後端契約一致。| v703-frontend-regression.yml；內嵌瀏覽器測試 | GitHub：G/.github/workflows/v703-frontend-regression.yml。Drive：Z/.github/workflows/v703-frontend-regression.yml。瀏覽器測試目前寫在此YAML內，沿用此位置。 |
|W7-A11| 修改11:00發布流程所需檢查與測試接線，保留ready及完整計分門檻、線上HTML／JSON／部署回執驗證、後續歸檔。 【完成條件】發布門檻、失敗保留舊版及部署回執驗證通過。| v703-site-deploy-1100.yml；index.html、V70_macro_latest.json、QA.json、v703_deployment_receipt.json | GitHub：G/.github/workflows/v703-site-deploy-1100.yml；G/系統工程/總經V70/V70_macro_latest.json。Drive：Z/.github/workflows/v703-site-deploy-1100.yml；D/V70_macro_latest.json（1qDFMlWojDU4OEaDY53jcN0k0V0S03sFt）。Action執行器：build/site/上述四個產物；QA產物包v70-3-27-qa-<run_id>。線上：www.happihelp.com/、/V70_macro_latest.json、/v703_deployment_receipt.json；實際部署目錄由既有HOSTINGER_SITE_DIRECTORY設定取得。 |
|W7-A12| 驗證每日分數歸檔接受同一資格規則；必要時修正捕捉檢查，保留月度計算公式與歷史有效列。 【完成條件】正式每日資料歸檔、月度相依流程通過，舊有效歷史保留。| capture_v703_daily_snapshot.py；macro_safety_daily.csv、macro_safety_monthly.csv、bank_macro_monthly_snapshot.csv；相依macro_safety_monthly.py、build_bank_macro_monthly.py | GitHub：G/scripts/capture_v703_daily_snapshot.py；G/data/macro_safety_daily.csv；G/data/macro_safety_monthly.csv；G/experiments/macro-safety-monthly-research/bank_macro_monthly_snapshot.csv；G/scripts/monthly_research/macro_safety_monthly.py及build_bank_macro_monthly.py。Drive程式：Z/scripts/同相對路徑。月度程式為相容性驗證對象，依實測必要差異修正。 |
|W7-A13| 真實來源重跑、發布與線上讀回；重建完整交付包，逐檔GitHub／Drive版本校驗，補齊包內缺少的契約與測試。 【完成條件】真實來源、完整測試、發布/線上讀回、歸檔、雙端逐檔校驗及Task切換驗證完成。| V70-3-27_完整程式與季度資料_部署160_20261020.zip；總經爬蟲18項_2026-10-19.zip；V70-3-27_本輪發布通知_部署160_20261020.md；跨專案正式通知_V70-3-27.md | Drive：D/前述兩ZIP（ID 1L00lYv8mgEupygGPfW_qKV1pO_9mHxZS、1G_JnJLWDBgbZIdN_2HytEp6tpao6rgNf）、D/發布通知（1pBscTeIPbCV2b-sfqb4AfewRcOOyhRIL）。GitHub：G/系統工程/總經V70/跨專案正式通知_V70-3-27.md；Drive：Z/系統工程/總經V70/跨專案正式通知_V70-3-27.md。完成時按實際版本更新名稱及通知，沿原ID；包內deployed/index.html、deployed/V70_macro_latest.json、deployed/QA.json一併重建。 |
|W7-A14| 更新修復清單、逐檔異動／備份／讀回紀錄及結案證據；確認修復驗收完成後，由中PM本人回到原W7清單。 【完成條件】故障階段驗收及治理完成，證據清單完整後接B01。| Family_W7_施工規劃與契約.md、Family家人版_施工管理.md、家人版_檔案管理.md、Family家人版_全生命週期MasterWBS_v6.1.0、檔案管理.md | Drive：根目錄/🫅活水AI系統最高規劃企劃書及法規管理者/前四檔；根目錄/檔案管理.md。契約ID 17WVU8De4cAuXxwAJUlJ21bLqpSDac-xL；施工管理1GdoI3Xo4kD1GS_pG_UwbKHMIHSicEycTG75mEY44NBg；Family檔案管理1a6EmKnsBc-hmJjfyh0e9XonGZqR6dMjh2Ejo3Lw_dII；Master1coxJ34aDseT09Oxo6OdiMlR6GmYm8RQckvnpr9KlRdo。 |
|W7-B01|開工前核對四家人正式DB：登記唯一ID、版本、本人身分及目錄。已知交接來源，日常獨立檔待定位；若未建立則從驗收版本建立。【完成條件】四戶唯一正式DB身分/ID/版本/位置/schema登記且讀回驗證。|mou.db、Arthur.db、Lilian.db、Joseph.db|已有Drive：根目錄/TEMP/W5_交中PM_完整交接_20261021.zip，包內private/w1/。日常獨立檔擬根目錄，待同名/權限檢查。|
|W7-B02|開工前核對共用績效SOT、schema與實際計算函式。已確認現行讀取器使用XLSX；WORK12成果、共用DB及計算器路徑待查實。【完成條件】共用正式來源、schema、計算器與口徑已核實並可實際讀取。|標的績效基準資料.xlsx；重要標的物之績效及曝險資料.db；benchmark_reader.py、xlsx_minimal_reader.py|已有Drive：根目錄/系統工程/B-基準資料工程/標的績效基準資料.xlsx。已有GitHub：C/work2/。共用DB及績效計算器尚待定位，禁止以讀取器冒充計算器。|
|W7-B03|開工前完成全線資料存取與呼叫清冊，逐檔記直接/間接讀寫、輸入輸出、修改或沿用理由，含規則JSON/CSV、schema、動態載入依賴。現已重取30支檔案；尚須沿依賴展開收尾。<br>補列W5實際動態載入的C8C9執行鏈，不只列Work5/Work6公開入口。已從最新runtime_loader.py核對7個明列路徑；各檔內容及其schema於完整依賴盤點逐一核對，介面受影響者才改碼。<br>補列依賴校驗：若改到被鎖定檔案，須評估影響並按原契約更新對應清單與測試，維持已驗收基線；禁止停用驗證或任意重算全部lock。【完成條件】直接/間接讀寫與動態載入依賴逐檔有處置，受影響lock及測試有對應。|W7-B08～B22全部相關程式、依賴/schema/母規則<br>runtime_loader.py；C8C9_Work3_Context_Handoff_Adapter.py；C8C9_Work4_V82_Integration_Adapter.py；C8C9_Work5_V75_Integration_Adapter.py；C8C9_Work6_Funding_Account_Isolation_Guard.py；C8C9_Work7_SGOV_Runtime_Role_Integration.py；C8C9_Work8_Protected_Holding_Client_Action_Protection.py；C8C9_Work9_Unified_Deployment_Mentor_Return.py<br>verify_dependencies.py；source_lock.json、dependency_lock.json、w2_dependency_lock.json、frozen_schema_lock.json、c7_fixture_lock.json、technical_source_lock.json；schemas/|G/系統工程/Family/W5/、G/系統工程/Family/W6/runtime/、C；其餘由實際import/runtime loader定位。清冊待建於G/系統工程/Family/W7/並鏡像F/W7/。<br>loader已有GitHub a23882005/LivingWaterAI/系統工程/Family/W5/runtime_loader.py。7個模組載入目錄為同repo/系統工程/C-配置決策引擎＋Mentor整合/正式Runtime/C8C9_RUNTIME/。<br>已有GitHub a23882005/LivingWaterAI/系統工程/Family/W5/。六個lock檔名稱由本輪verify_dependencies.py實際讀取清單確認；逐檔內容依W7-B03核對。|
|W7-B04|開工前驗證可信Project/session傳遞、Chat修改檔回存、Action觸發與Drive授權、全寫入者共同排隊；以最小合成資料測試。結果決定接線，非另設網站。此為合成資料與最小原型能力探測；正式共同寫入管理於B06完成，正式Action於B18/B21接通，分別驗收。【完成條件】合成資料實證入口/授權/回存能力，正式接線設計有明確可行依據。 【本版正式完成條件補正，優先於舊敘述】核實最小執行入口、執行中斷/恢復及錯誤回覆；以已驗證家人帳號判斷身分，Project整理對話，不以取得原生Project/裝置ID作前置阻擋。服務授權與共同寫入仍須合成實測。|既有TEMP能力測試DB；待建W7接線設定與測試|Drive根目錄/TEMP/；G/系統工程/Family/W7/待建。GitHub連線與Drive授權設定屬服務設定，不當作已存在的程式檔。|
|W7-B05|建每資源管理表頭：Close=無活動存取、Read=讀取、Update=更新；讀寫名單外置，含檔案ID與更新持有者。待建。【完成條件】每個盤點資源有讀寫權限與表頭，程式可正確解析。 【本版正式完成條件補正，優先於舊敘述】資源權限名單以家人帳號綁定，使用者文字不能自行提升權限。|mou管理表頭.md、Arthur管理表頭.md、Lilian管理表頭.md、Joseph管理表頭.md、帳號管理管理表頭.md、重要標的物之績效及曝險資料管理表頭.md|Drive與各DB同目錄；私人/帳號庫擬根目錄，共用庫依W7-B02正式位置。其餘共用規則表頭依W7-B03盤點。|
|W7-B06|統一讀寫：核驗→排隊取得更新權→下載最新版→保存原版備份→SQLite交易→驗證→同ID回存→讀回→解鎖；讀者取得最後完整版本；過期工作不得覆寫。待施工。帳號庫啟動由受信任帳號管理入口存取；登入成功後，業務資料入口核驗session，避免登入循環依賴。【完成條件】競爭更新、完整讀者快照、備份/回存/讀回、失敗與過期工作處理通過。 【本版正式完成條件補正，優先於舊敘述】驗證最後完整快照讀取、備份政策、實際還原、交易互斥與故障恢復，涵蓋同時請求、過期更新與提交讀回。|資料存取管理.py；各DB、表頭及備份|G/系統工程/Family/W7/資料存取管理.py待建；DB在W7-B01/W7-B02/W7-B07對應Drive位置。備份沿根目錄檔案管理規則，位置寫入資源設定；MD Flag為狀態呈現，互斥由共同寫入機制實現。|
|W7-B07|新增登入/改密碼/管理功能，固定成功登入起算4小時；同人同Project跨對話有效，保存無二次密碼。待施工。同Project跨對話須依B04已驗證的session機制；不同裝置/登入工作保持獨立。本人改密碼與管理者帳號管理權依既定需求落地。【完成條件】登入、固定四小時、跨對話、換人、本人改密碼及管理權測試通過。 【本版正式完成條件補正，優先於舊敘述】家人帳號登入、本人改密碼及管理權；成功登入起算固定四小時。換對話接續，裝置切換驗證本人狀態及期限，採最小可行session機制。|帳號管理.py；帳號管理.db（account、login_session）|G/系統工程/Family/W7/帳號管理.py待建；Drive根目錄/帳號管理.db擬建。程式Drive鏡像F/W7/系統工程/Family/W7/帳號管理.py待建。|
|W7-B08|建立每工作身分JSON，接入分析入口、本人核對及runner，避免全域共用目前使用者。待施工。【完成條件】不同人同時工作仍正確綁定本人Project/session/request與資源。 【本版正式完成條件補正，優先於舊敘述】每request帶受驗證家人身分；跨戶拒絕，Project指令及工具路由指向登入者。姓名或Project文字不授予他人資料權。|工作身分.py、家人工作流程.py〔新〕；run_analysis.py、family_boundary.py、family_runner.py、family_input.py〔已存在，納入接線修改評估〕|新檔G/系統工程/Family/W7/；現有G/系統工程/Family/W5/。修改/新增同版鏡像F/W7/＋完整repo路徑。JSON為工作內物件；session保存在帳號DB。|
|W7-B09|四庫增量遷移，核對既有schema後保存進度、分析、快照與報表索引；保留已驗收資料與歷史。同步修正清倉寫入及讀取投影：family_boundary.position_view須按最新有效狀態/快照讀取，避免已清倉標的由舊列重新出現；部分截圖未顯示持倉保持原狀。驗收完整清倉、部分截圖、重試及資料完整性。【完成條件】四庫完整性/歷史保留、清倉投影、部分截圖及重試測試通過。 【本版正式完成條件補正，優先於舊敘述】資料增量遷移/版本、來源/事件/變更歷史與清倉投影；既有歷史保留。|mou.db、Arthur.db、Lilian.db、Joseph.db；workflow_state、analysis_run、result_snapshot、report_artifact；遷移腳本；family_boundary.py、family_input.py、家人工作流程.py|DB正式ID與位置由B01核實。GitHub既有：G/系統工程/Family/W5/family_boundary.py、G/系統工程/Family/W5/family_input.py；擬新增：G/系統工程/Family/W7/家人工作流程.py、G/系統工程/Family/W7/migrations/下遷移腳本（DDL及檔名由schema核對後定案）。Drive程式：F/W7/＋相同repo相對路徑，待建鏡像。|
|W7-B10|逐一接通股債、總經、資金、持倉、目標與技術資料的身分/run/版本關聯，完成逐檔修改或沿用核對。【完成條件】九個橋接模組逐檔驗證同戶同run及來源版本傳遞。|stock_source_bridge.py、bond_source_bridge.py、macro_source_bridge.py、funding_bridge.py、position_source_bridge.py、target_source_bridge.py、bond_target_bridge.py、c7_engine.py、family_technical_bridge.py|全部已有：G/系統工程/Family/W5/。本次已重新取得9檔；受影響依賴由W7-B03展開。|
|W7-B11|核對主運算與解說各段的同戶同輪資料傳遞；需要的介面修改，投資算法沿原契約。【完成條件】主流程完整結果持久化，重開DB可讀回同一輪。|native_pipeline.py、stock_engine.py、bond_engine.py、mentor_bridge.py、v70_source_bridge.py、recovery_bridge.py|全部已有：G/系統工程/Family/W5/；recovery_bridge目前為StagingAnalysisStore，正式保存需W7接通。|
|W7-B12|核對配置/Mentor內部鏈與共用資料入口，逐檔接線並確認保存結果完整。【完成條件】配置/Mentor鏈與共用入口相容，既有算法回歸通過。|配置決策引擎.py、mentor_adjustment_loop.py、work5/core_engine.py、work6/adjustment_loop.py、work2/benchmark_reader.py、work2/xlsx_minimal_reader.py|全部已有：C下所列相對路徑。相關work3/work4與schema依賴由W7-B03繼續展開；不將本表列舉冒稱全部傳遞依賴已掃完。|
|W7-B13|訪談與持倉更新：讀本人背景/資產/限制，按清楚的本人資料更新；部分截圖不清空未顯示持倉。待接保存。【完成條件】訪談/持倉資料寫入本人庫、來源可追溯並能跨對話接續。 【本版正式完成條件補正，優先於舊敘述】查持倉/訪談與正式更新均由統一入口；清楚本人資料直接保存，模糊才詢問；取消的操作不落正式資料，重送不重複。|家人工作流程.py、資料存取管理.py；個人profile/持倉/現金/事件表|新程式G/系統工程/Family/W7/；四家人DB沿W7-B01。訪談及資產寫入函式由此統一實作，既有入口依W7-B03映射。|
|W7-B14|Loop1：讀個人資料與共用基準，保存長期目標、版本與確認依據。待接保存。<br>補列W2目標草案/確認產生端。W5 validate_target實際要求完整CONFIRMED payload、draft_hash、target_hash、confirmation_evidence及其hash、source_reference_ids、版本/時間，不能只保存final_target_allocation比例。W7須持久保存完整既有canonical record，再重建等價W5 confirmed_target envelope；優先復用既有表/既定JSON欄位，schema確認前不任意加表。<br>目標保存後關閉並重新開啟DB，還原完整confirmed_target，通過原W5 validate_target、target hash/confirmation evidence驗證；本人變更與舊版本歷史皆可追溯。取消存檔二次密碼不等於取消Loop1既有目標決定證據；對話已明確確認即沿用，無需重問。【完成條件】完整CONFIRMED目標保存後重開庫，通過原W5目標與證據驗證。 【本版正式完成條件補正，優先於舊敘述】Loop1完整目標與本人確認證據保存；不另加存檔二次密碼。|家人工作流程.py；final_target_version、final_target_allocation、workflow_state；配置引擎鏈<br>target_draft.py；target_confirmation.py；family_boundary.py validate_target；target_source_bridge.py；家人工作流程.py與migration<br>本人DB；W7整合測試；既有W2確認輸出與W5驗證器|新程式G/系統工程/Family/W7/；既有引擎C；資料在本人Drive DB（W7-B01）。<br>W2已驗收本機來源：/workspace/scratch/6be1e4a82c48/w2_review/runtime/c_configuration_core/work17/target_draft.py、work18/target_confirmation.py（同runtime/c_configuration_core前綴）。兩檔正式GitHub/Drive交付位置仍須沿W2索引定位，本輪GitHub檔名搜尋無結果，不能將本機路徑填成正式遠端路徑。W5消費端已有GitHub a23882005/LivingWaterAI/系統工程/Family/W5/family_boundary.py與target_source_bridge.py；W7新流程在同repo/系統工程/Family/W7/。<br>本人DB沿W7-B01正式Drive位置；測試待建GitHub a23882005/LivingWaterAI/系統工程/Family/W7/tests/，同版Drive交付。|
|W7-B15|Loop2：讀本人持倉/資金/長期目標，串總經→V82→V75→Mentor整合，保存當日正式配置/理由/快照/歷史。成交事實另更新持倉現金。待接保存。【完成條件】當日完整配置/理由/快照保存成功，長期目標與成交事實保持分開。 【本版正式完成條件補正，優先於舊敘述】Loop2完整結果、理由與來源run保存，與成交事實分離。|family_runner.py、W7-B10/W7-B11/W7-B12全部涉及模組；analysis_run、result_snapshot；家人工作流程.py|已有G/系統工程/Family/W5/及C；新增G/系統工程/Family/W7/。結果在本人Drive DB。|
|W7-B16|報表與跨對話接續：讀同一已保存run，保存報表索引/連結，HTML自由選看；純查舊結果不重算。待接線。<br>報表交付需列資料準備、既有renderer、HTML/圖檔產出、Drive上傳、來源檔案ID/連結讀回；report_artifact僅在遠端驗證成功後READY。report_receiver/current_report_bridge是接收與綁定，不能當作已完成全部渲染與交付。新生成報表沿W6既有模板，不重開RM17。【完成條件】既有renderer產物成功上傳讀回，報表/來源/DB同run並標READY。 【本版正式完成條件補正，優先於舊敘述】啟動查詢、舊結果/報表讀取、同帳號跨對話接續及中斷後恢復，維持輕量對話操作。|report_receiver.py、current_report_bridge.py、source_views.py、target_receipt.py；report_artifact；HTML/圖檔<br>report_receiver.py；current_report_bridge.py；既有render.mjs、report.mjs、reader.mjs、workbook.mjs、validate.mjs、package.py；report_artifact|已有G/系統工程/Family/W6/runtime/。索引在本人Drive DB；新報表輸出路徑須依既有W6規則於施工前登記，尚無本輪新報表實體。<br>已驗收W6本機來源：/workspace/scratch/6be1e4a82c48/w6_review/sources/rebuild/src_v16/，manifest.json列有這6個檔。正式GitHub位置/Drive包內位置與本次運行選用版本仍依W6索引核對，本輪查無搜尋結果，不猜路徑。W6 Python接口已有GitHub a23882005/LivingWaterAI/系統工程/Family/W6/runtime/。輸出Drive目錄在前置盤點核定。|
|W7-B17|臨時標的研究：先查共用庫，缺少時IB優先、IB無法使用再yfinance；標明初步未含息/來源/期間。IB與Yahoo兩檔日線已實測，選路待整合。【完成條件】缺標的初步查詢、IB/Yahoo選路、期間口徑標示及補庫交接通過。|家人工作流程.py；補齊標的資料.py〔新〕；IB工具；ib_market_history_update.py〔現有〕|新G/系統工程/Family/W7/；現有G/scripts/ib_market_history_update.py。IB為Chat連接工具，程式呼叫方式由W7-B04驗證，不假定Action繼承IB連線。|
|W7-B18|一批symbols＋request_id觸發一個Action，同標的已執行任務去重，提供工作狀態查詢。待接線。【完成條件】一批一Action、任務去重及狀態查詢成功。 【本版正式完成條件補正，優先於舊敘述】批次任務持久狀態、去重、失敗可查及中斷恢復；服務憑證不進程式、提示詞或日誌。|family-symbol-backfill.yml；家人工作流程.py；任務紀錄|G/.github/workflows/family-symbol-backfill.yml待建；G/系統工程/Family/W7/家人工作流程.py待建。任務紀錄Drive路徑待W7-B04定案；用GitHub run ID連結，不存憑證。|
|W7-B19|Action取得程式、安裝依賴、批次抓價格/股息/拆股；節流、有限重試、增量快取、備援、品質核對。增加指定symbols介面，保留既有區域排程。待修改。【完成條件】批次下載及六項可靠性措施實測，逐標來源/品質/失敗明確。|scripts/ib_market_history_update.py；workflow；套件設定；CSV/JSON原始資料與快取|收集器已有G/scripts/ib_market_history_update.py；workflow在W7-B18。工作暫存於Actions runner；需永久保留的來源/快取Drive目錄待W7-B02/W7-B04定案，正式DB不提交GitHub或打包artifact。|
|W7-B20|依既有口徑算含息績效/回撤，記期間/幣別/再投資/資料截至與品質；計算期間不佔DB更新權。待施工。【完成條件】含息績效與回撤可重現，期間/幣別/再投資口徑一致。|補齊標的資料.py；既有正式計算器；批次結果|G/系統工程/Family/W7/補齊標的資料.py待建；計算器實際路徑依W7-B02查明；批次結果在runner暫存，正式成果走W7-B21。|
|W7-B21|Action統一排隊寫回：讀表頭/取得更新權/下載最新版/備份/合併本批/同ID回存/讀回/解除Update；保存逐檔成功失敗。所有共用庫更新者走同入口。待施工。同request重試不重複合併；跨Chat與Actions全部共用同一寫入入口，排隊保留每筆請求。【完成條件】多批排隊、重試冪等、失敗復原與Drive提交讀回通過。 【本版正式完成條件補正，優先於舊敘述】同request重試冪等、多批保存及唯一提交入口，失敗可恢復，避免舊工作覆寫新版本。|資料存取管理.py；共用DB與管理表頭；備份、任務結果|程式G/系統工程/Family/W7/；共用庫Drive位置依W7-B02，任務結果位置依W7-B04。Drive API憑證放GitHub Actions secrets，值不寫repo/MD/日誌。|
|W7-B22|補齊mou截圖缺項＋VOO、2454.TW、2330.TW，核對自行重算結果與引擎讀取同版資料。截圖待提供，到此提醒指揮官；有效WORK12成果保留。【完成條件】mou提供清單與三指定標的逐檔對帳，缺項處置及引擎讀取同版通過。|共用績效DB；來源證據；W7-B19/W7-B20程式|Drive共用庫位置依W7-B02；程式依W7-B19/W7-B20。MU與AVGO現為已實測標的，完整入庫另由補庫工作紀錄追蹤。|
|W7-B23|分項/整合驗證：登入4小時、跨對話、錯戶拒絕、多人read/update、重試不重複、過期工作拒絕、復原、Loop1/2保存、報表同run。待執行。補驗依賴鎖、帳號庫啟動、清倉投影、四戶實際保存與重新讀取；W7驗收證據完成後再交W8。本項驗W7新增與修改功能及其接口；W8再做全系統端到端驗收，沿用本項有效證據並聚焦跨線剩餘風險。【完成條件】W7功能/接口測試、四戶實際保存再讀、依賴校驗及雙端治理交付通過。 【本版正式完成條件補正，優先於舊敘述】沿用既有build/依賴/manifest與版本證據；驗四戶讀寫、四小時、跨對話及裝置切換、跨戶拒絕、重試、還原、完整引擎與報表。必要工具防護含SQL參數、路徑/資源白名單及不洩漏憑證。驗收以B01～B23單一清單結案，不另開29項。|測試、遷移測試、Checkpoint、manifest|G/系統工程/Family/W7/tests/及G/系統工程/Family/W7/〔待建〕；Drive F/W7/＋repo相對路徑同版交付。|

## W7之後的正式工序（保留接續，不併成W7已完成）
1. W8：整套家人版端到端整合測試與修復。
2. Gate D：依正式契約驗收，形成具體放行證據。
3. 家人版正式部署：四家人ChatGPT Project指令、程式來源與Drive DB資源綁定。
4. 試用與修復：沿既有資料實測，追蹤問題至修復驗收。
5. Gate E：結案、版本與檔案治理、完整交接。
各段持續更新F/Family家人版_施工管理.md、F/家人版_檔案管理.md、F/Family家人版_全生命週期MasterWBS_v6.1.0及根目錄/檔案管理.md。

## 共通契約與完成條件
程式執行來源為GitHub，修改程式GitHub/Drive雙端同版；正式家人/共用/帳號DB只在Drive。登入固定4小時、同Project跨對話、不追蹤閒置、保存無二次密碼；每工作獨立身分，每DB附管理表頭，統一寫回/備份/讀回。家人版保持輕量，沿用已驗收W1～W6及投資公式。
Loop1保存完整目標與確認證據；Loop2保存當日正式配置、理由、快照與歷史；實際成交另記。報表沿既有W6模板與renderer，成功上傳讀回後READY。按需標的採一批一Action，計算後短時間取得共用DB更新權。
A區完成真實來源、政策資格、回歸、發布/線上讀回、歸檔及雙端同步後才進B區。新增快取放行資格另依核定規則；Family Production HOLD、交易NONE、W4取消、RM17凍結保持至正式Gate裁決。
原W7-B前置尚待定位內容：四戶日常DB獨立ID、共用庫/正式計算器、W2目標產生端與W6 renderer正式遠端位置、可信session/回存/Action授權及共同排隊機制。責任由中PM本人完成。

## v1.6.0 複核與執行界線
本次37項逐列複核：統一依賴編號、先定共同資料契約再改前後端/Task、明訂原版備份在交易修改前、區分前置原型與正式接線、逐列補完成條件。現行W7只計B01～B23；A段已結案另列歷史。
A01～A12按序在隔離修復分支/工作區完成；涉及會自動觸發Actions的程式、測試及工作流須完整相容後，在A13協調正式切換與部署。現行main自動排程不因半完成的契約更新而提前採用不相容資料。不得於清單中先宣稱Task/Action已改。
本次只修既有總經發布鏈，不擴張Hostinger主機/網域管理；Family正式Project部署仍在Gate D之後。總經既有JSON/CSV與automation-state保留原管線；Family正式DB僅Drive。本次不搬移總經資料管線或重寫投資公式。
尚待確認事項分別歸責：A01來源失敗根因；A02共同欄位及有限期限具體值；B01四戶日常DB ID；B02共用庫/正式計算器；B03完整依賴及W2/W6遠端位置；B04可信session/回存/Actions授權能力。每一項完成後更新實體位置與證據，進入其相依施工。



