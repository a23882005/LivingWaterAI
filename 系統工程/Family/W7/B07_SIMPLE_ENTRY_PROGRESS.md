# B07 簡易登入及02讀取接線｜2026-10-24

責任：Family總PM本人施工及覆核。B07 IN_PROGRESS；正式6/23。

## 已完成與證據
- ZIP1～ZIP4：CRC通過，verify_handoff.py 598/598 size/SHA256通過。
- GitHub live main基準67718670da162a6b46dab2df91a7d70ad94a7001，與四包一致。
- joseph_login.py逐字承接已核定Joseph Sources v1.11登入程式；沒有新增另一套密碼或OAuth。
- joseph_read_entry.read_my_data(auth, database)：先核對登入，再按需載入既有W5 read_snapshot，固定Joseph client_id；不提供外部client_id或SQL覆寫。
- 15項合成測試PASS：登入/不延長4小時、錯帳密清除舊狀態、停用/強制改密碼/憑證期限/暫時鎖定、兩種時鐘到期、登出/重建實例、未登入先拒絕、固定本人及錯戶拒絕。
- PM授權唯讀核對正式Joseph.db：29資料表成功讀取，身分一致，SQLite integrity ok，foreign key 0錯誤，讀前後bytes相同；既有W5 reader Git blob cdab707a55b0dea7ed9e94f67f90c9f976e8a1c7與live一致。本機讀取0.0164秒，不代表完整下載/聊天延遲。
- 私人資料庫、內容及其指紋不提交GitHub；具體唯讀憑證只存私人Drive W7。

## 直接使用
在已按Sources v1.11完成auth.login的同一Python環境：
```python
from joseph_read_entry import read_my_data
snapshot = read_my_data(auth, joseph_db_path)
```
保留同一auth；到期或環境重置，保留待辦並重新登入。此入口傳回完整原始資料及歷史；持倉清倉投影仍由B09接線，不從歷史事件自行猜算目前持倉。程式與W5 reader須取同一commit。

## 明確待完成
1. 真人JO登入與Joseph專案v1.11安裝驗收仍待實際使用；此次沒有真人密碼，合成登入與PM讀庫分別記錄。
2. 簡易auth仍是本對話記憶體核對，不直接授予Coordinator principal。帳號管理/改密碼及保存入口須由既有AccountManager與共同I/O接合；尚未新增正式DB寫入。
3. 原v1.11 require_login只核對本機期限；登入後帳號停用/改密碼的即時撤銷尚未重驗遠端狀態，列B07正式接合必驗；不能以本地15測試結束B07。
4. 跨對話持久登入仍為既有待辦；Joseph現行體驗依最新決定重新登入後接續。B07→B08～B23→W8→Gate D→四戶部署→試用修復→Gate E由本人續作。
5. Production HOLD、交易NONE、W4取消、RM17凍結。本段實跑帳號/HTTP/OAuth/資源/服務及新增簡易入口測試合計118/118 PASS（其中新案例15項）。
