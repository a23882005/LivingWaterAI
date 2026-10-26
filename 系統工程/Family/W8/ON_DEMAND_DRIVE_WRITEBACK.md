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
