# B04 共同入口與Drive writer整合

2026-10-23｜Family總PM本人循序施工｜契約v1.6.0

## 實作與邊界

`shared_drive_writer.py`是既有Hostinger單主機的TEMP合成writer；`shared_writer_client.py`產生與驗證短暫HTTPS入口。`family-b04-shared-writer.yml`沿既有Actions部署，沒有新增付費服務、排程或正式家人資料。

HTTP入口沿用服務端key digest→合成帳號及chat/action映射、固定14400秒session與本戶排隊。PHP的SQLite BEGIN IMMEDIATE涵蓋queue讀取、呼叫writer與回執確認；所有worker另持有同主機固定flock，鎖涵蓋Drive下載、備份、交易、上傳與journal收尾。Actions所有TEMP寫入probe共用同一concurrency group，cancel-in-progress=false。

正式資料仍由Drive保存。暫存SQLite工作檔只放服務執行期間的私人目錄；此回合只改指定TEMP DB `1SDnOCLoHpX-XfJ9v838o84VJmzdmoPzI`。新表b04s_counters、b04s_receipts只作兩個合成帳號的計數與request_id驗收。

## 提交流程與重試

1. PHP驗證連線用途、帳號與固定四小時期限；Action借用同戶已登入session，不能建立登入。
2. submit以(account, request_id)唯一鍵入queue；同ID不同delta回409。
3. drain持有queue交易；writer獲得固定flock，檢查TEMP位置及本run所有權。
4. 下載Drive同ID內容；若有前次未確認上傳，依before/after雜湊判定已提交或尚未提交。陌生雜湊立即停止並保留原檔，交由恢復處理。
5. 在單一SQLite交易更新本戶counter並插入request receipt。已存在的request_id回傳原結果，避免重複累加；本戶其他更新後重試舊請求也保留舊receipt結果。
6. 複製Drive修改前備份到Backup並讀回；把before/after寫入Drive appProperties持久journal。上傳前再檢查登入期限及來源雜湊。
7. 同ID回存完整SQLite image；精確讀回後更新last/清除journal，最後PHP把queue receipt標為DONE。
8. 若Drive已提交而worker中斷，PHP queue交易回滾，原工作保留QUEUED。下一次drain先辨認Drive的after image，再讀取其中已提交receipt，最後補上queue DONE，不再累加。
9. 登出及舊session失效後登入，先對照Drive已提交receipt，補上DONE，再取消未提交工作。登出若遇Drive暫時不可用，保留RECONCILE工作但立即撤銷session；下一次登入先對帳，對帳失敗則暫不建立新session。receipt核對不新增資料變更，無須沿用已過期寫入授權。

此鎖契約涵蓋所有走這個單主機入口的writer。其他應用程式或PM直接回存同一Drive檔不受flock約束；正式運行必須維持唯一writer路徑。跨主機、多副本服務與Drive API的跨應用CAS鎖不在這次實作範圍。

## 備份、復原與憑證

Drive每次變更前有已讀回的備份；每個測試run另有baseline備份及持久run/base/basehash/last紀錄。cleanup先關閉HTTP入口，再辨認未完成上傳、以baseline還原同ID並精確讀回，最後移除該run服務程式、臨時key/OAuth設定及queue資料庫。若復原失敗，保留私人恢復檔與Drive備份供排錯，workflow標記失敗。

OAuth設定由GitHub Secrets產生於Actions暫存，透過既有SSH送至public_html外、mode700的專用目錄，config.json為mode600。HTTP公開PHP只含隨機key的digest；secret值不進程式庫、工程ZIP或測試artifact。固定鎖檔為不含資料的空檔，維持同一inode，不在清理時刪除以免分裂互斥鎖。

## 驗收與下一步

本機14項：上傳前/後故障重試、復原中斷重試、去重/碰撞、外部更動拒覆寫、run所有權、帳號限制、舊receipt重試、到期前後、無有效session的receipt核對及原表保持。
線上驗收由相同HTTPS入口分別用chat/action合成連線送件；另以Actions OAuth直接讀Drive交叉驗證counter與receipt。精確結果以evidence/B04/shared_writer_action_run.json及Checkpoint為準。

後續由總PM本人完成真實ChatGPT工具接入與跨對話驗收、常駐服務正式設定及OAuth長期授權。B04維持進行中，W7 3/23；B04通過後依序B05～B23→W8→Gate D→四戶部署→試用修復→Gate E。Production HOLD、交易NONE、W4取消、RM17凍結。

## ChatGPT接入路線（2026-10-23官方文件已核對）

官方目前提供「ChatGPT網頁→Plugins→加號→Add custom MCP server→設定Server URL與認證→Create as a plugin→安裝」；支援streaming HTTP/SSE及OAuth。現有PHP POST業務入口下一步須加MCP transport與OAuth連線身分映射；Google Drive OAuth只供後端writer存取Drive，與家人登入服務的OAuth用途分開。工程沿用已測的queue/writer，避免再建立第二個寫入流程。

由總PM本人完成MCP介面與服務端認證後，再接入指揮官帳號並驗證兩段真實ChatGPT對話續接；安裝介面與帳號登入需要使用者配合時只交代具體一步。官方路線不保證本帳號/Android當下已有相同UI，尚待實際檢查。

來源：https://developers.openai.com/api/docs/guides/custom-mcp-server （2026-10-23實際開啟）

## 本輪驗收紀錄

工程commit36199c834d986012d5a4b85c59d8c5e567acafe1；run39869009274/job120138396679 SUCCESS。14/14程式測試與27/27 HTTPS/Drive整合檢查PASS；Actions直接讀回本戶value=18、7個唯一receipt。baseline已同ID精確還原為8192 bytes、SHA7c75b192ff45bb0d71f88f0b6f16bfb59fc1a73d53a7aa29ad9e9471238872a8；備份1ZRKcTzli75zV2g67NbaxAdI3Bst5RzcR保留Backup。臨時入口、私人OAuth設定及合成queue移除確認PASS。artifact12464738416，SHA f63669ae2b18c743df12600e3558c0135561febdbb1d9be1a6aaf6ecd201c709。既有回歸run39869009482三個job亦SUCCESS。

登出交界已加入實作：先依Drive receipt確認已提交工作，再取消其餘工作。線上新增「已提交但回覆中斷→登出→重新登入→同筆DONE且只累加一次」驗收。到期後登入走相同對帳分支；本輪沒有等待真實四小時，也沒有在線上注入Drive離線後登出的情境，這兩種情境不宣稱已獨立實測。
