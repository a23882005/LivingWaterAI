# B07 帳號核心與服務接線

狀態：IN_PROGRESS。核心程式與測試已實作；B07尚未整項驗收，正式進度仍6/23。Production HOLD、交易NONE、W4取消、RM17凍結。

## 本輪實作

- `帳號管理.py` 建立account、login_session；帳號名單與管理角色由私有部署資料供入，沒有內建真人帳密、公開註冊或以程式名稱取得管理權。
- 初始/重設憑證有期限，首次登入只允許改密碼/登出；正常登入固定成功時間加14400秒，活動不展期。相同安全連線的不同請求可接續；其他登入session各自獨立。邏輯連線scope不宣稱原生ChatGPT Project ID。
- 本人改密碼由已驗證session決定目標，介面沒有可改成他人的user_id；改密碼、管理者重設/停用會撤銷該帳號所有登入。換人成功才撤銷被替換的登入，其他裝置session不受影響。
- 管理角色可建立、停用、啟用、重設帳號，不能停用最後一個有效管理者；帳號管理權不等於四戶私人資料權。每五次錯誤嘗試阻擋60秒，失敗計數也經B06持久保存。
- 依現行指揮官決定保留逐字元1/2/3/4循環位移。這是**可逆混淆，不是加密**；帳號庫及備份必須私有，普通業務介面不提供整庫、密碼欄位或反解操作。舊歷史「不可逆雜湊」描述不當成現行需求。
- Bearer token由持久服務密鑰產生，DB只保存keyed hash；相同request重試不重建登入，不會復活已撤銷/過期session。receipt只保存keyed fingerprint與無敏感值結果，不保存密碼或完整token。服務密鑰須從私有設定載入，不可每次啟動重產。
- B06AccountStore沿用正式Coordinator與備份/同ID寫回/讀回；帳號存取以內部account-manager身分啟動。業務的session_guard實查帳號庫與撤銷狀態，失聯拒絕通過。帳號交易不取得業務DB鎖，避免反向鎖依賴。
- `drive_service_transport.py` 注入OAuth憑證、快取與到期前更新access token、有限timeout/大小、Google目的地限制、禁redirect、遮罩provider錯誤。未知提交結果不自動重送寫入，交B06 journal恢復。這不會自動變更Google應用發布狀態。

## 驗證

核心首輪本機整合80項：新增帳號20項、傳輸11項，既有B05/B06回歸49項。包括實際B06並行鎖、不同worker接續、回存後失去ack重試、寫入備份期間登出拒絕提交、跨戶拒絕、到期邊界及服務key輪替失效。

GitHub workflow `family-b07-account-core.yml` 在既有獨占TEMP測試組內實跑新傳輸與B07→B06→Drive。只建立合成測試帳號；完成或失敗後精確還原既有TEMP基線並清除測試metadata。結果存evidence/B07/core_progress.json，只有證據完成才更新該檔。

## 正式資料位置

根目錄唯一帳號管理.db已建立account/login_session空schema；沒有真人密碼、管理者或active session。沿既有帳號表頭及私有資源設定同ID綁定第六庫；正式ID、變更前備份、checksum在Drive私有資源登錄，公開repo不保存。表頭保持Close，restore_subjects仍空；此為結構建置，並非登入上線。

## 尚待本人完成，不能簽B07 PASS

1. HTTP來源/請求大小/CSRF/整體節流、安全Cookie、背景工作與登入管理頁已實作，完整進展見B07_HTTP_ENTRY.md與http_progress.json。接下來完成管理員安全憑證交付、真人首次啟用與私有帳號配置。
2. MCP/OAuth服務身分與安全憑證保存接線，驗證同人跨對話的實際通道。不能把本機fresh worker或scope參數當作ChatGPT端驗收。
3. Google長期授權與常駐私有設定（持久服務key、lock目錄、經核實的管理角色）；測試狀態refresh token的限制仍未解除。
4. HTTPS合成帳號整合本輪已通過，正式部署/服務重啟與真人故障驗收仍待完成，再結案B07；完整四戶、實際四小時及跨裝置依原B23/W8工序。

帳號庫維護還原需撤銷舊session並輪替服務key後才重新開放；目前沒有對一般服務開放還原權。公開程式/測試/報告不含正式憑證；備份內的歷史混淆密碼也視為敏感資料。
