# B05資源管理表頭｜進行中

2026-10-23；Family總PM本人；B04已依原v1.6.0最小能力探測契約結案。

已新增resource_headers.py與16項測試。表頭固定Close/Read/Update、資源鍵、唯一Drive file_id、外置policy_ref、目前讀者與更新持有者；拒絕重複JSON鍵、未知欄位、路徑型ID、重複資源/檔案綁定及缺少政策。Close代表沒有活動持有者，並非永久禁止存取。真正互斥由B06管理，authorize只做身分/期限與ACL判斷，不授予鎖。

VerifiedPrincipal只能由受信任後端的session驗證層建立；此型別不是加密憑證或網路身分驗證。不得將HTTP/工具使用者輸入直接轉成此物件。B07須接入真實驗證來源，B06才取得檔案與執行鎖。

六個資料庫表頭草稿已由B01/B02私有登錄產生：四戶與共用庫有既有唯一ID；帳號庫按B07尚待建立，binding=PENDING_B07、file_id=null、Close，所有存取拒絕。草稿最小ACL為本人私庫、四戶讀共用庫、受信任共用writer更新共用庫、帳號服務管理帳號庫；服務角色後續須在正式政策覆核與身分接線時落實。

私有草稿位置：Drive W7/Family_W7_B05_私有管理表頭草稿.zip，ID1Il5hlTRi7dyuw9LxWAQPacZoQD7Pe5IS；六份MD、外置policy、registry與README共9檔。SHA256 2dae436d2b7f43a468f9c24512a6485faedc9366fde696e55a8c90b7cb84a93b。此包尚未部署至各DB同目錄。真實DB ID與私有登錄保持Drive；程式庫只含合成測試。

本機測試16/16 PASS：本人權限、錯戶/過期/非驗證principal、文字偽造權限、三種狀態、待綁定拒絕、重複欄位/多表頭/多資源/多file_id、缺少政策、未知操作及萬用權限拒絕。

本人下一步：依B03的169檔清冊完成其餘共用規則/設定資源逐項歸類與外置ACL覆核，驗證完整catalog，將核准表頭放回正確DB/資源同目錄並讀回，再簽B05接B06。B05仍進行中；W7 4/23。
