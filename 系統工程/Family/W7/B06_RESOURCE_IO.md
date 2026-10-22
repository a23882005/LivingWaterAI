# B06 統一資料存取管理

唯一執行者：Family總PM本人。沿v1.6.0工序，元件資料存取驗收完成後接B07登入及服務接線；正式部署仍循B23/W8→Gate D。

## 程式與可信設定

- `資料存取管理.py`：Coordinator、SQLite完整性/外鍵檢查、交易與同影像receipt、單主機逐資源flock、備份與恢復。
- `drive_resource_backend.py`：固定ID/parent/私有journal/MD表頭映射，Drive同ID更新、備份複本及逐位元讀回。
- `resource_headers.py`：B05資源ACL及VerifiedPrincipal；後端供入catalog/policy/handlers，使用者文字不得改動。
- B06私有資源設定存Drive W7；五個既有DB映射完成，六份日誌同目錄建立。帳號庫依原B07工序待建，pending紀錄不進入可寫映射。

Coordinator建構必須提供`session_guard`：B07以其VerifiedPrincipal衍生型別的session ID向可信session登錄查核；入口、取得鎖後、回傳資料前與寫入前皆再查。已撤銷或過期工作拒絕提交。帳號庫啟動走受信任account-manager服務身分，避免登入查帳號庫再要求登入的循環。

## 執行與復原契約

所有Chat/Actions的業務請求先進B04/B21共同服務佇列，再由同一持久writer主機呼叫Coordinator。各DB使用固定lock目錄與固定inode，flock涵蓋最新版下載、備份、交易、Drive上傳與讀回；鎖檔不刪除。flock提供互斥及等待，不承諾FIFO；持久任務與排程順序由既有共同佇列管理。禁止另起獨立writer主機或任意runner直接寫正式庫。B18/B21接正式Action，B07接服務設定。

更新：核驗→取得鎖→再次核驗→對帳pending→下載完整最新影像→Update表頭→SQLite BEGIN IMMEDIATE→可信handler→外鍵/完整性檢查→原版Drive備份及讀回→持久before/after journal→重新比對來源及登入→同ID上傳→讀回→Close→解鎖。MD只呈現狀態；鎖由主機維持。MD更新前另存備份。

每個handler只能由後端白名單載入，不接收使用者SQL；SQL參數由handler綁定。Coordinator禁止handler提前COMMIT、ATTACH、PRAGMA或修改receipt表。receipt與業務修改同一SQLite影像提交，request_id以subject隔離，同ID異內容拒絕；回覆遺失後重試返回原結果。業務schema/金額/owner/run檢查由各B08～B16可信handler接入，原規則保持。

讀者在同一資源鎖中取得最後完整影像並驗證，再回傳不可變bytes及sha256/epoch。遠端服務不可用時回報錯誤並保留journal，由下一次有效請求對帳；不回傳未核驗片段。

pending持久於Drive私有JSON，含before/after、備份ID與epoch。程序中斷後重新下載：符合before視為尚未寫入，符合after視為已提交；其他內容停止覆寫並保留現況。取得鎖後重建Close狀態；MD落後時由journal重新呈現。

還原是明確維護操作：需更新ACL及額外restore_subjects。私有正式設定預設維護名單空，B07管理權接妥後才賦權。驗證備份source/parent/hash、先備份目前版本，再同ID還原並讀回。還原切換epoch，舊epoch的排隊請求全部拒絕；新登入工作須重新取得snapshot epoch。還原會回復當時的業務及receipt影像，epoch隔離避免舊請求重新寫入；維護還原不是一般業務undo。

## 實測範圍

本機/Actions合成測試涵蓋八程序競爭更新、並行完整讀者、強制exit73、上傳前後中斷、新worker復原、去重/碰撞、備份、精確還原及中斷重試、舊epoch拒絕、過期/登出撤銷、錯戶、handler回滾、外部改動、檔案移位及表頭綁定。

真實Drive實測使用既有固定TEMP合成庫：強制寫入後退出→新worker去重、兩程序合併、3筆唯一receipt/累計4、同ID精確還原原8192bytes，MD回Close，TEMP journal/header清理。正式四戶與共用DB僅準備資源設定，整體實際家人操作依後續B23/W8驗收。

單主機持久lock目錄、可信後端政策、Drive服務憑證由部署者維護；journal是提交恢復資訊，不是分散式鎖。Transport須有timeout/大小限制、token更新與錯誤遮罩；B07供入服務transport。正式私有設定與實際DB ID留Drive，不寫GitHub。

## 私有設定啟動順序

B07建立可信session_guard與token transport，從Drive正式私有設定載入headers及外置policy；只取BOUND的五項resources。每項首次存取日誌為JSON null，由共同writer在取得固定鎖後初始化epoch與最新完整影像hash。帳號庫建立後以備份→同ID更新私有設定及帳號表頭→讀回方式補入第六項。維護restore_subjects需由B07管理權明確設定；業務入口維持空名單。每個動作只傳resource_key、request_id、snapshot epoch、白名單operation與JSON payload，不接受caller指定file_id/journal_id/handler/SQL。
