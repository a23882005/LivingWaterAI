最後修改日期時間：2026/10/27（台灣時間）
# W8｜四戶共用 ChatGPT 按需 SQLite 原位寫回

正式位置：`系統工程/Family/W8/on_demand_drive_io.py`。
本補丁只修復 ChatGPT 本地 SQLite → Google Drive Plugin 的傳遞及驗證，不改投資引擎、不改正式資料模型、不增加常駐服務。

## 必須接入的既有入口

四份私人 `*_Project_Sources.txt` 的「本人資料讀取」及「第一次建倉／資料保存」旁加入下列共同流程引用。`Instructions` 的一般工作方式可維持，不能聲稱更新 Drive Sources 已自動更新使用者手動貼入的 Project 設定。

當選單 01／03／06／10／11 需要保存已確認資料時，先沿用 Sources 的 FamilyLogin 及固定帳號／client_id／本人 Drive File ID，從 GitHub 取得本模組，在本次 ChatGPT Python 環境執行。登入有效性仍由既有 `auth.require_login()` 驗證；此模組不建立或延長登入、不索取密碼、不繞過本人隔離。

`for_project(auth, login_account=固定帳號, client_id=固定client_id, file_id=固定本人FileID, family_alias=本人DB既有別名)` 回傳 writer。私人固定映射取本人 Sources，不把四戶 DB ID、client_id 或持倉寫進公開 GitHub。不得從使用者隨意指定的檔名或輸入覆蓋這個映射。

## 實際操作順序

1. Drive metadata 核實本人正式檔案；`fetch(download_raw_file=True, include_base64=False)` 取得原檔，使用回傳 workspace_path。保存原始 SHA-256，保留原影像不修改。
2. 按既有業務程式修改獨立工作副本。COMMIT 並關閉所有寫入連線；若使用 WAL，呼叫 `seal_working_copy(工作檔, 全新封存檔)` 透過 SQLite backup API 包含已提交 WAL。不得僅複製主檔而丟掉 WAL。
3. `plan = writer.prepare(原影像路徑, 封存候選路徑)`。結果只為 STAGED_NOT_PERSISTED，不是正式保存。
4. Drive `copy_file` 備份原 File ID 到已核定私人備份位置。重新下載備份與原檔到兩個新路徑。
5. `preflight = writer.authorize_update(plan, 新下載原檔, 新下載備份, 備份FileID)` 先檢查來源與備份 SHA。未提供候選檔參照時回 `CONNECTOR_FILE_REFERENCE_REQUIRED`，不會產生更新參數。
6. 先核實本次執行環境的工具 schema。2026/10/27 Work 的 Google Drive `upload_file.file_uri` 及 `update_file.file_uri` 支援由執行環境上傳**本機絕對路徑**：已以合成 SQLite 完成新檔、備份、原ID更新與獨立下載 SHA/SQL 驗證。這個能力由當次工具提供，不能推定所有 ChatGPT 環境相同。當次能力已確認時，使用 `writer.authorize_update(..., candidate_file_uri=plan['candidate']['path'], local_upload_supported=True)`；它會再次檢查候選內容、原件、備份、身分，並要求路徑精確等於封存候選。舊環境仍支援工具真正回傳的 `sediment://file_...` 參照；不要自行拼裝。`READY_NOT_PERSISTED` 後執行 `update_file(**ready['update_file_args'])`，保留本人原 File ID，接著完成第7、8步。當次工具無此上傳能力時，保留待寫回狀態。不得用新 DB ID 替換正式原ID。
7. `update_file` 明確成功後，再 `fetch` 同一原 ID，物化到另一個全新路徑。`writer.verify_readback(plan, 新下載遠端路徑, 原FileID, checks)` 比對 SHA-256、SQLite integrity_check、foreign_key_check、本人身分與此次修改逐欄值。`checks` 是可信業務程式產生的 SELECT／參數／精確預期列；不得接受使用者提供任意 SQL。
8. 僅 PERSISTED_REMOTE_VERIFIED 才回報完成。記錄原／後 SHA、備份 ID、原 File ID、欄位驗證、時間及 request 來源，私人資料證據留在核定 Drive 位置。

## 錯誤、重試與並發

更新回覆遺失或不確定時，先重讀原 ID。若遠端 hash 等於候選，完成驗證，不重複業務交易；等於原檔才可重新進行寫前檢查；兩者皆否則停下保護現況。不得無條件重試。

現行 Plugin `update_file` 沒有公開原子 compare-and-swap 前置條件。來源 SHA 重查能拒絕已觀察到的變動，但不消除「重查之後、寫入之前」的競爭窗口。每戶同一時間只准一個受控寫回工作；不同 ChatGPT 會話不可自行並行寫同戶。這不是分散式鎖驗收。

舊 B06 單主機 `flock` 與 journal 是歷史常駐 writer 設計，不能在新 ChatGPT 環境冒稱跨主機互斥。若某戶仍由舊 B06 writer 管理，必須先核實並避免雙 writer，並處理其 journal 來源 hash 相容性；不能直接清空 journal 或任意更新未知 pending。也不能以此要求改回 Hostinger／Render。

本模組不替代正式業務規則，不將股債類別目標偷換為未經確認的特定 ETF，不把「可投資現金」自動等同已驗證交割、無待付款／無保留款。只保存真正已確認欄位，未知者保持未知。

已確認持股成本／長期股債比例／本人可投資金額的保存，使用同目錄 confirmed_asset_facts.py 的 append_confirmed_asset_facts(db,本人client_id,facts)，僅在獨立副本且 foreign_keys=ON 的交易內執行。facts 只放本次已確認資料與查證報價；此函式不代替 Drive 寫回。讀取最新本人已確認快照用 read_latest_confirmed_asset_facts(db,本人client_id)，依日期選最新非假設快照並驗證 CONFIRM 快照 hash；不把舊歷史當現況，不把股債偏好當逐標的 final_target。缺少此函式要求的必要欄位時沿用其他既有業務流程，不猜值。

選單12／13報告歸檔同理：`prepare_report_delivery` 先封存本地成果及SHA。當次工具確認支援本機上傳時，將每個 `uploads` 項的 `artifact` 對應到其 `path`，呼叫 `bind_connector_uploads(plan, refs, local_upload_supported=True)`；程式逐檔重驗大小與SHA，拒絕調換、修改或未核定路徑，再產生 `upload_file` 的 `file_uri、parent_folder_id、file_name、mime_type`。舊環境仍能使用真實工具回傳的檔案參照。`upload_file` 回傳檔名可能是 `file_name`，不是 `name`；必須以真實ID逐份下載驗SHA，最後上傳清單並讀回，才宣告 `PERSISTED_REMOTE_VERIFIED`。未知值不硬補，四戶資料絕不交叉。

本次傳輸驗證是非家人資料的合成SQLite，原/備份8192 bytes、SHA `b3dffb88aa258f4f44c5b7a41991a4f50208dd7e2aa95794f2b2c4dd5f08283b`；同ID更新後另行下載8192 bytes、SHA `384e9528ca2395833038ea01b47d74a17b8ea59391c5f622b38465dfec067c55`，SQL revision由1變2，備份仍為1。此證據解除本次Work環境的傳輸阻礙；四戶正式業務寫入與Project端對端分別驗收。


測試：在 W8 目錄執行 `PYTHONPATH=. python -m unittest discover -s tests -v`。測試資料為合成四戶，不含正式持倉或私人識別碼。

## 新對話接手及中斷後取回同筆結果

專案每收到一則訊息就呼叫 `on_demand_project.open_conversation(...)`，接著呼叫回傳物件的 `handle_message(message_id, text, number=原選號, payload=原作答)`。第一次只有「07」時直接傳文字即可。工具通知另傳 `notification_id`。專案與對話識別、固定私有目錄及重送時相同的訊息識別都由受信執行端提供。自由作答由原選單辨認，帶回原題號與作答資料。

同一對話沿用同一份只在記憶體內的 `live_context`。每戶由 Sources 傳入原驗密控制器的建構函式、驗證站來源、兩個手機工具、Space 讀寫工具、下載帳號庫及建構原選單的函式。手機工具交回其原生 `structuredContent`。每次 `read_page()` 都讀本戶正式頁。`patch_page(**args)` 將原條件更新一次，然後讀回。若執行環境被重建，只恢復私人暫存裡的原選號及作答，依原驗密流程重新取得登入。

帳本寫回前，暫存程式在同一筆 SQLite 交易中保存業務資料與既有 `_family_io_receipts` 收據。`DB_WRITEBACK_REQUIRED` 仍依上方備份、同 ID 更新與讀回工序辦理。將 `OnDemandMutationStager.receipt_reader(download_original)` 作為共用入口的 `recover_receipt`。該戶的 `download_original(file_id)` 透過原生 Drive 下載回傳 `(工具實際回報的檔案 ID, 新下載的路徑)`。帳本寫入後回覆中斷時，入口用這筆既有收據交回已保存的結果。若下載仍看不到收據，回傳 `AWAIT_DRIVE_CONFIRMATION`，沿用同一個寫回要求查核。私有暫存目錄限該執行身分存取，保存業務待辦，驗證密鑰只留在活的登入物件。

## 原選單 03 的 Docs 登入與分步寫回

此節適用於已配置 Docs 登入的 03 候選。沿用本戶 Sources 的固定資料、當則原生登入登記及已確認的票據。由執行端取得可信的專案、對話與訊息識別，並在同一對話的每則訊息沿用同一個私人工作區。只傳本戶固定帳本 ID 和新下載路徑，測試使用獨立私人帳本。

MOU 文件登記模式在本人原登入及登記寫入後，以 `project_login_steps.finish_docs_login_and_open_03()` 檢查同一本戶登記文件的此次登記、到期時間及讀回版本，綁定原登入並開啟暫存的 03。此步只開首頁或原題；原入口若有作答或確認，應留在獨立的續辦路徑。

支援絕對本機路徑上傳的執行端，使用 `docs03_receipt_entry.run_project_docs03_native_turn()`。將當則原生 Docs 登記、可信專案／對話／訊息識別及固定私人工作區交給這個入口。固定 `official_drive_file_id` 與 `progress_file_id` 分別取自同一戶 Sources。`download_original` 與 `download_progress` 各回傳下載工具實際回報的 Drive ID 和本機路徑。

接線驗收時，在本戶實際執行端先呼叫 `inspect_docs03_host_context()`，只傳執行端直接供應的專案、對話、當則訊息識別及工作區路徑。它只回欄位狀態與錯誤代碼，沒有原值，也不建立待辦或下載資料。全數呈現 `present` 代表當則輸入可用，可信來源與跨訊息工作區仍由執行端和原對話實測證實。四個欄位有缺漏或工作區不存在時，作答、確認與「繼續」均在下載及寫回前停止。

原對話接線驗收使用同一個新測試標籤（32 位小寫十六進位），先由第一則的實際執行端呼叫 `probe_docs03_host_roundtrip(action="start", ...)`，在下一則的實際執行端呼叫 `action="verify"`。兩則都只傳當次由執行端直接取得的識別和工作區。只有同一專案、同一對話及同一工作區找到起點，且訊息識別不同，才回 `DOCS03_HOST_PROBE_VERIFIED`。缺資料先回診斷；同則重送無法冒充第二則。測試只保存隔離記號與訊息摘要，無需開啟選單、下載或更新正式檔案。驗過此項後，再用本人私人合成檔驗 03 原作答及確認的續接。

兩條路共同使用執行端傳入的 `build_original_menu(login, workbook_path, ledger_path)`；以本戶已指定的選單程式及實際下載的兩個檔案建構選單。呼叫共用 `build_project_menu()` 時，把本機帳本交給 `downloaded_db_path`、本機 Excel 交給 `family03_progress_path`，兩個檔案可由下載工具放在不同目錄。候選池、B 表及行情快取維持從帳本本機目錄讀取。舊訪談續答也會提供同一種事件讀回入口。作答帶原選項，整戶確認帶原 03 的 `confirm_account`；下一則「繼續」將 `payload` 留空。這個共用入口負責分流，既有直接呼叫兩個分支的方式仍可沿用。可信識別或固定私人工作區取不到時，會在下載或寫回前停止；對話文字中的識別不能作為輸入來源。

整戶確認的預覽版號用於核對本人確認的內容。已核准文件產生的預覽版號包含文件版本。原選單另將產生預覽時的 Excel 摘要交給寫回流程，備份後用同一 Drive Excel 的新下載檔核對該摘要。若 Excel 或帳本已變更且還找不到原收據，依原流程重做預覽與確認。

共同入口先在本對話私人工作區保存首次派送的原作答或確認。第一次派送中斷時，「繼續」用原訊息識別及內容接回原待辦。新待辦也會核對當時綁定的本人、登入文件、正式帳本 ID 與 Excel ID。首次派送與已建立的原待辦都沿用這組來源。Sources 改指其他檔案時，備份前或授權送出後都先停止，暫不下載改指的檔案，恢復原設定後才接回。已完成的舊作答及收據也沿原來源核對，包含原訊息、原續接訊息、相同內容重送及只輸入「繼續」；新來源的待辦仍可各自處理。既有版本留下而未保存來源摘要的待辦，仍沿原業務紀錄的身分及原檔檢查續辦。後續要以程式的回應決定下一步。已收到寫回授權的待辦沿原收據或 Excel 事件唯讀查證，不重送更新。Excel 事件讀回成功時，回傳同一 Excel 在讀回當下的續選位置，以及原事件當時是否仍為最新作答。重送沿用原讀回結果；要取最新題卡時照常進入原選單 03。Excel 事件查證需要有效的本人登入及同一個已登記 Excel，帳本或候選池暫時無法下載時仍可確認已寫入的 Excel 事件。建立新的作答及整戶配置確認時照常檢查原資料。整戶確認即使由原單一路徑執行，也會把已登記 Excel 的實際下載路徑交給原選單。 建立私人紀錄途中若中斷，空白或尚未接收任何待辦的紀錄可由同一筆原訊息接續補建。舊作答或確認的重送只讀原結果。使用新訊息重送時，若與已核對的原內容完全相同，即使同一條路或另一條路有待辦，也只返回原收據，不更動待辦。兩條路都完成時，新的「繼續」依原待辦建立順序讀取最近結果。

| 程式回應 | 執行端動作 |
|---|---|
| `DOCS03_BACKUP_REQUIRED` | 備份回傳的本人 Drive 原 ID，下載備份，將原生備份 ID 及路徑以 `verified_progress_backup=(id, path)` 或 `verified_account_backup=(id, path)` 接回當筆。 |
| `DOCS03_DRIVE_UPDATE_REQUIRED` | 對回傳的 Excel 或帳本原 ID 呼叫一次 `update_file(**update_file_args)`。同一筆待辦已記錄授權送出。 |
| `DOCS03_DRIVE_WRITE_PENDING` | 同一工作區內另一筆 03 已占用該 Drive 檔的寫回。先在原對話讀回那筆收據，再繼續目前這筆。 |
| `DOCS03_READ_RETRY_REQUIRED` | 本輪下載逾時、連線中斷或本機下載檔未取得。下一則「繼續」沿原待辦及階段重試。若先前已發出寫回授權，就只查原收據。 |
| `AWAIT_DRIVE_CONFIRMATION` | 重新下載同一原檔，讓原待辦唯讀查原帳本收據或 Excel 事件。 |
| `DOCS03_CONTINUATION_NEEDS_ORIGINAL_ACTION` | 無法由原紀錄確認兩條路的先後時，沿原訊息或原作答回查。查回舊結果的順序不影響原待辦順序。舊版若兩筆皆有首次派送時的來源紀錄，仍沿原順序續接。 |
| `DOCS03_JOURNAL_RECOVERY_REQUIRED` | 某條路有無法讀取的原紀錄，先核對原對話的私人工作區，兩條路均暫停派送。 |
| `DOCS03_PREVIEW_STALE` | 授權送出前發現原帳本或 Excel 已變動，且當筆原收據未保存。回到原 03，重新預覽、確認與備份。 |
| `PERSISTED_REMOTE_VERIFIED` | 已讀到同戶、同檔的原 Excel 事件或帳本收據，交付保存結果。 |

寫回準備回應必須包含原待辦的 Drive 檔案 ID 和實際上傳檔案參照，才會把該筆記為已發出授權。其他檢查結果與未完整的工具回應不會消耗授權。

作答 Excel 和整戶帳本的待寫回副本，在首次派送時先核對內容摘要，再保存到原對話的私人待辦目錄。下一則「繼續」從這個目錄取得同一份副本，先前的下載或產檔暫存目錄可釋放。已存在的待辦仍沿原紀錄讀收據。若尚未送出寫回授權，且原待辦引用的副本已遺失，要求重新開啟 03 確認；若已送出授權，就只查原收據。

整戶確認在下一則重新下載原帳本。已授權的待辦用這次下載直接查原收據；在原收據已驗證後，原操作重送讀取本對話已核對的結果。兩者均無須重新開啟選單或載入 Excel。尚未授權時，寫回前仍另取新檔核對版本。只要是同一 Drive 檔、同一戶、同樣內容，下載暫存位置改變仍能沿原待辦完成驗證。第二次讀到的帳本已含該筆原收據時，直接回該筆收據。驗收候選檔和備份仍各自核對。

候選驗收包含原對話真人登入、原 03、私人合成帳本、分開的「確認」與「繼續」訊息，以及用新訊息重送原確認。查核原檔、備份、最後配置版本、收據與下載內容。 每戶應只新增一版與一張收據。共同原生入口及原本直接呼叫單一路徑，都在同一私人工作區內，對寫回同一 Drive 檔的不同對話逐筆處理。兩種入口沿用同一份寫回登記。同一工作區內先逐筆檢查原檔與備份。這一步若程序終止，尚未核准寫回的檢查不會留下持久占用。產生有效的更新參數後，以同一筆 SQLite 交易保存該檔寫回名額及原對話的「已進入送出」紀錄。兩項都寫成後才回傳 Drive 更新參數。交易完成前中斷時原待辦可重新準備，也不占用同檔；完成後即使回覆遺失，也只查原事件或收據。核對原結果後，以同一筆 SQLite 交易保存完成結果並釋放名額。若保存中斷，原待辦仍只讀回查；若已保存，重送直接回同一筆。回件與原請求不符時維持待辦與占用。尚未發出授權的備份或預覽檢查可在後續訊息重試。執行端若給不同工作區，或有其他寫入工具，仍須沿原工序由執行端逐筆處理；Drive 預先核對無法原子化整個寫回。

在 W8 目錄執行 `python -m unittest discover -s tests -p 'test_docs03_writeback.py' -v` 可重跑 03 回歸測試。
