# W7-B04 能力探測

2026-10-22，Family總PM本人；SYNTHETIC ONLY。B04 PARTIAL：本機原型不是正式入口驗收。

| 能力 | 實證 | 判定與接續 |
|---|---|---|
| PM Chat修改檔案同ID回存 | TEMP既有W7_Arthur_Capability_Test.db，原合成值57→58；先Backup，SQLite交易，原ID更新，重新下載bytes/SHA/完整性/值核對 | PASS，證據evidence/B04/drive_probe.json。只證明本PM連線，不推論四家人Chat均有相同權限。 |
| 固定4小時與隔離契約 | 本機簽章原型：到期邊界、讀取不延長、不同project/member/device拒絕、竄改claims拒絕 | 原型PASS；尚未取得平台可信Project ID或跨對話session儲存入口，對話文字/檔名不可作信任根。 |
| 共同排隊契約 | 同一SQLite authority上多connection競爭、FIFO、重開接續、同request去重/衝突拒絕、租約到期fencing | 原型PASS；SQLite存在單一服務本機才有互斥意義，不能各Chat下載副本各自加鎖。正式共同服務與Drive提交fencing仍待B06。 |
| Action觸發與合成執行 | 新增family-w7-capability-probe.yml，main特定路徑push/手動入口，唯讀repo權限；僅12項合成測試和JUnit | 實跑run39823921536、job119982054504 SUCCESS，12/12 PASS，JUnit artifact上傳成功；不含私人DB、憑證或部署。API工具未提供workflow_dispatch寫入動作，實測push入口。 |
| Action存取Drive | 現行區域Actions只有市場CSV快取與git/artifact，不能從PM OAuth能力推論Action已取得Drive授權 | NOT_PROVEN；本次不讀或輸出任何secret值。B18/B21須取得指定資源的服務授權實證。 |

## 待接線的明確界面

1. 身分入口：受信任端取得Project/member/device/session並簽發固定4小時claims；每次工作重驗簽章、到期及資源對應。同Project跨對話重用同session，不靠模型記憶或延長到期；不同裝置獨立。
2. 所有Chat/Action提交同一request入口；由共同authority保存FIFO、冪等鍵、lease/fence及完成狀態。普通GitHub concurrency會限制pending數，不能代替保留每筆請求的持久queue。
3. 唯一正式writer在取得lease後下載最新版、備份、交易、完整性檢查、原ID更新、讀回再解鎖。fence必須由持有Drive寫權的服務端驗證，不能僅由舊工作自行檢查後直接上傳。
4. Action與Chat只發request；服務憑證不放repo、提示詞、MD或logs。正式帳號/業務DB仍只在Drive，排隊狀態是否需要服務端暫存由B06依可用機制定案。

## 尚未滿足的前置條件

目前可用工具沒有回傳本次Chat所屬的受信任ChatGPT Project識別/session通道；也未有已驗證供四戶Chat與Action共用、具Drive寫權與fencing的正式服務入口。原型不能補足這兩項外部能力。因此不簽B04完成，也不越序把B05～B07正式登入/共用鎖宣稱已上線。下一步為定位並實測這兩項既有入口；若平台不能提供，須提出具體替代接線供指揮官裁決，不另設網站、不自行擴張主機服務。

正式W7仍0/29；Production HOLD、交易NONE、W4取消、RM17凍結。測試DB在TEMP，四家人正式DB本輪無異動。
