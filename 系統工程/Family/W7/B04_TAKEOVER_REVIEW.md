# B04 接任查核與接線裁決候選
日期：2026-10-23（Asia/Taipei）；責任與後續執行：Family全專案總PM本人。
狀態：PARTIAL_CAPABILITY_PROVEN；新增查核完成，B04整項尚待服務能力及範圍裁決。正式W7 0/29。

## 已完成且可重現
- H3原ZIP SHA256 dd26a7b07309d37f6f0a305d3a40e47bd04f7a42715c2e9d62716568e8247df2，99,610,102 bytes。
- 執行原verify_package.py：363內容檔、37契約、83原工序、6內包CRC、115工作包manifest、282 Git blobs、5 SQLite完整性/外鍵全部PASS。
- GitHub live main為bb9c2769dac7151261e586321ebf644332c456fa，與H3 CURRENT_STATE一致；四份live治理紀錄與契約v1.5.10皆已核對。
- 原PM Drive合成回存及Action合成測試沿用已驗收證據；本輪沒有重做既有合成測試。
- 現行Checkpoint來源H2/舊main欄補正為本輪讀取基準與H3，歷史提交另欄保留；H3封版ZIP保持原件。

## 本輪能力查核
1. 查閱現行工具介面與GitHub完整tree（未截斷），直接相關W7原型、Checkpoint及部署授權：可用GitHub/Drive工具沒有提供本次ChatGPT原生Project ID、裝置身分或跨對話登入session的受信任驗證介面。這是本次可見介面的結論，不宣稱整個平台永遠不支援。
2. Plugin Management搜尋「ChatGPT Project session identity MCP server」未找到直接對應能力；「LivingWaterAI Family」結果為空。搜尋非全目錄證明，不推論其他環境不存在服務。
3. GitHub來源中的B04原型明確為單機SQLite authority，尚未有已驗證供Chat/Action共用的部署端點。部署授權文件允許例行工程，並未提供這些外部服務設定。
4. Action Drive授權仍NOT_PROVEN：GitHub工具明確不開放secrets端點，本輪不讀secret值，不將不可讀metadata判成沒有憑證。原workflow只驗合成資料，無指定Drive測試資源存取證據。
5. 官方Plugins authentication文件要求伺服器依request credentials驗證身分及權限；Project說明提供跨對話共享來源/指令。本次讀到的官方文件未建立「原生Project及裝置ID由可信工具傳入」保證。

## 要解決的兩個外部前置
B04-ID：來源可驗證的Project/member/device/session，或由指揮官核定調整身分邊界。
B04-WRITER：Chat與Action共同入口、唯一Drive寫入權、持久排隊、重試冪等及過期工作拒絕。單純各自下載DB或修改MD Flag不形成跨程序互斥。

## 具體最小候選（待指揮官裁決，尚未部署）
建一個私有Family連接服務，只提供登入/登出、讀取、提交、查狀態；不增加使用者報表網站。沿用GitHub程式與Drive正式DB。
- 服務端依認證連線綁定家人帳號；使用者填的角色/Project字串只作申請值，不作授權證據。
- 固定4小時業務登入期限由服務保存，讀取不延長；跨對話依同一受驗證連線接續。
- Chat與Action均提交request_id至同一服務，唯一writer負責備份、交易、同ID提交、讀回；批次失敗與重試可追蹤。
- 正式家人/帳號/共用DB仍僅在Drive；服務端需要最小排隊/鎖/重試狀態與短暫SQLite工作副本。具體落地必須先核對既有託管服務能力與授權，未知費用不自行購買。
- 若無可信原生Project ID，正式隔離邊界改為「認證家人帳號」，Project保留對話分組。同帳號在另一Project仍可取用本人資料，與原契約嚴格Project封鎖不同。
- 若無可信裝置ID，不能承諾同一連線跨裝置各自獨立四小時；須測試連線是否提供裝置級session，或另核定裝置驗證方式。
- 上述兩項是實質需求取捨，總PM不得自行把候選當已核定。若指揮官維持嚴格原生Project與裝置邊界，須先取得平台可信傳遞介面才有B04正向驗收依據。

## 核定後本人施工與驗收
先核對託管/連線可用性及成本，再用兩個合成家人完成：登入、四小時邊界、跨對話、跨戶拒絕、跨裝置行為、Chat/Action同入口排隊、Drive合成回存與逾期拒絕。B04通過才接B05～B23；後續W8→Gate D→四戶部署→試用修復→Gate E順序保持。
Production HOLD、交易NONE、W4取消、RM17凍結及原已通過Gate均保持。
本輪僅接任校驗、能力查核及治理修補；無新的正式runtime功能或DB異動。

## 查核來源
- https://developers.openai.com/plugins/build/auth （官方，認證身分來自server request credentials）
- https://learn.chatgpt.com/docs/projects （官方，Project共享脈絡）
- GitHub docs/family-deployment-authorization.md、系統工程/Family/W7/B04_CAPABILITY_REPORT.md、probes/session_queue_probe.py。

