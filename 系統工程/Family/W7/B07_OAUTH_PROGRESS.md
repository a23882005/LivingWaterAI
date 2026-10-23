## 2026-10-24 管理者帳號正式命名與中文支援

指揮官明確指定首位管理者登入帳號為「活水AI管理者」，取代 mou 建議值。帳號核心及 account: 身分驗證同步支援漢字，保留既有英數名稱；service: 身分保持英數範圍。拒絕空白、路徑、冒號、不可見控制字元及超長名稱。

實測中文管理者建立→首次登入→強制改密碼→重新登入→OAuth code/token→身分讀回通過；帳號/OAuth/HTTP 60項、資源表頭/來源/私有服務39項，共99項本機測試PASS。新案例納入既有B07 CI。正式真人帳號尚待安全啟用，HTTP gateway、短效初始憑證私有交付、token延遲及實際ChatGPT連線由Family中PM本人續作。B07仍IN_PROGRESS、6/23。

## 2026-10-24 B07 實際 ChatGPT OAuth 用戶端已私有部署

- 指揮官表單實際取得 metadata、scope family:session 與四個端點；已核實實際 callback https://chatgpt.com/connector_platform_oauth_redirect 。取代先前暫定 callback；client_id=family-chatgpt，公開用戶端、無 client secret、token auth=none、PKCE S256。
- 新增 private_entry_config.py 與獨立 family-b07-private-client.yml，既有 runtime.lock 序列化、0600 原子寫入、相同設定重裝備份讀回；不同既有設定拒絕靜默覆寫。無 Drive/帳號庫寫入、runtime 與 key 保持原值、未開放 HTTP。
- commit 6af8df3b4962fe0e859930b312c8e38315f88116；run 39996157180 / job 120560100393。28 項本機與 GitHub Python3.9 測試 PASS；正式主機 CONFIRMED_CLIENT_INSTALLED / public_enabled=false / stable_key=true / runtime_unchanged=true，清理 PASS。
- 未完成：正式 HTTP gateway、首位真人管理者經核實設定及安全短效交付、首次改密碼、token 延遲與 ChatGPT 實際登入/跨對話驗收。尚未指示提交 ChatGPT 表單，不能將 metadata 成功視為登入完成。B07 IN_PROGRESS、6/23 不變。

## 2026-10-24 B07 OAuth探索入口部署完成

- 獨立探索入口：https://www.happihelp.com/family-connect/mcp 。提供OAuth metadata與401 Bearer resource_metadata挑戰，暫不提供登入、token交換或資料操作；正式帳號庫、既有私有runtime未變更。
- 部署來源caa185a9c95b19b68f2d899401779d7a3358b99c；run39991335504/job120543562369 SUCCESS。15項PHP邊界/安裝保護測試PASS、PHP語法PASS；HTTPS兩份metadata=200、MCP=401、token=503、未知路徑=404，staging/runner清理PASS。
- 首輪run39991185926於測試中文路徑轉義失敗，未進入部署；改為環境變數傳遞路徑後重驗通過。本機無PHP，僅2項安裝測試PASS/13項skip；正式15項結果以GitHub PHP執行為準。
- 用途：讓指揮官在ChatGPT表單填入入口，展開進階OAuth設定，核對實際client/redirect。URL尚未經ChatGPT實際讀取；跨對話授權、真人帳號啟用及85.426秒token交換相容性仍待完成。無自動註冊或示範client。
- OAuth discovery目前提供路徑後綴形式；標準根/.well-known前綴路徑尚未部署，後續依客戶端實測補接或採手動精確端點設定。
- B01～B06 PASS，正式6/23；B07 IN_PROGRESS。Production HOLD、交易NONE、W4取消、RM17凍結。下一步由本人核對實際ChatGPT設定、完成正式gateway/安全真人啟用及驗收。


## 2026-10-24 私有帳號與路由組裝進展（尚未公開啟用）

- 新授權部署 run39985989631/job120525205726 SUCCESS；來源1fd20c6068fb4c7319fd3edd61c42d9661d95925。12項部署測試、固定key、私有設定讀回與暫存清理PASS；主機仍PRIVATE_PERSISTENT_DISABLED。
- private_account_service.py 從私有runtime載入既有key與正式B06帳號映射；帳號服務只取得accounts，拒絕表頭不一致、不可信鎖路徑、多主機writer與遺失key。建構不讀寫Drive、不初始化真人帳號、不載入合成測試清理程式。
- load_router 從私有entry.json組裝既有AccountHTTP/OAuthService/AccountRouter。origin、固定connection_scope、精確base與已驗證client/redirect必須由部署設定提供。沒有示範client上線，也未新增公開入口。
- 新增15項測試；涵蓋新模組、帳號、OAuth、MCP、HTTP、B06及Drive transport的149項本機測試全數PASS。嘗試整個W7目錄時有兩項舊測試因本地子集缺W5模組無法收集，此次不宣稱整個W7測試通過。
- 下一步：部署專用gateway、真人安全啟用、取得實際ChatGPT client/redirect並做跨對話驗收；85.426秒既有token交換仍需實際客戶端驗證。
- 正式6/23；B07 IN_PROGRESS；Production HOLD、交易NONE、W4取消、RM17凍結。

## 2026-10-23 品牌公開說明頁部署完成

- 本人新增 Family-Drive 介紹、隱私權政策與服務條款，固定公開路徑 `/family-info/`、`/family-info/privacy.html`、`/family-info/terms.html`。
- 程式 a19f628618f02fa0b2523ceafb1929d5928b87d6；run39954347660/job120416326346 SUCCESS。三頁HTTP200、UTF-8、SHA256逐檔一致；瀏覽器三頁與導覽確認。暫存清理PASS。
- 首次run39954152904因新目錄受umask077影響而403，保留失敗紀錄；補0755後通過嚴格umask首次/重複部署驗證。修改前私有備份、拒絕未知目錄、既有總經首頁保留。
- 指揮官截圖已見happihelp.com授權網域及舊首頁儲存；下一步將Google品牌三個網址改填新三頁，觀察Audience發布按鈕及後續提示。未宣告Google發布/驗證或長期授權完成。
- 正式6/23，B07 IN_PROGRESS；Production HOLD、交易NONE、W4取消、RM17凍結。後續仍需真人安全啟用、正式服務接線、實際ChatGPT跨對話及Google長期授權。

# B07 OAuth／MCP 接線進展

狀態：IN_PROGRESS；W7正式6/23。Production HOLD、交易NONE。

本輪總PM本人實作：
- account_oauth.py：B06帳號庫交易保存授權碼與權杖雜湊；短效單次授權碼、PKCE S256、精確client/redirect/resource/scope、issuer、refresh輪替及重播撤銷；每次呼叫讀回帳號enabled/generation/session。期限不超過原登入四小時。
- oauth_http.py：授權探索文件、既有登入頁加明確同意、同源/CSRF、精確redirect、表單token endpoint。採已核實的預先登錄public client；無任意metadata URL抓取或動態註冊。
- account_mcp.py：JSON MCP初始化、工具清單與唯讀family_session；不接受姓名、SQL、路徑或資源ID覆寫身分。B08以後的業務工具尚未納入。
- private_service_config.py：私有目錄及權限檢查、原子建立穩定32-byte key、競爭建立一致、啟動只讀、遺失/損毀拒絕默默重建。
- 46項新增測試加原103項，共149/149本機PASS；GitHub Python3.9 run39901611803/job120244239584同為149/149 PASS。核心程式commit ffc42ea610f930a59cba9bbc33c3c047830f5cc4。
- 真實Drive OAuth測試腳本沿既定合成TEMP，具always cleanup、回復精確基線，並量測token交換時間。結果以evidence/B07/oauth_progress.json讀回為準。

仍由本人完成：
1. 真實HTTPS OAuth路由與同步token endpoint驗收；既有背景202輪詢只適用瀏覽器登入，不能直接套進標準OAuth token流程。需測量主機延遲並修復實際問題。
2. 正式私有設定與穩定key實際部署、單一writer目錄、真人管理者短效安全啟用及首次改密碼。程式完成不等於部署完成；正式帳號庫尚未因本輪程式測試而變更。
3. 從實際ChatGPT管理頁取得精確client/redirect配置、建立連接並實際換對話驗證。目錄搜尋Family尚無既有可直接呼叫的連接；不把MCP本機測試當ChatGPT端結果。
4. Google長期授權：本輪代理瀏覽器開console.cloud.google.com顯示Site Unavailable，尚未讀到live發布狀態或改設定；最後已驗證狀態仍Testing。管理頁需使用者協助，憑證不貼對話。
5. 最終新增路徑安全覆核與正式B07裁決、雙端交付及治理讀回。

已讀官方接線依據（2026-10-23）：
https://developers.openai.com/plugins/build/auth
https://developers.openai.com/plugins/build/mcp-server

限制：上述測試採合成帳號；正式client/redirect尚待實際連接管理頁，不以synthetic.invalid或測試client代替。工具只回帳號及access期限，不暴露token。Google服務授權與Family使用者OAuth分離。

## 真實Drive首輪診斷

run39901726271於normal-login-and-resume發生ServiceTransportError，尚未走到OAuth交換；不能據此斷言是授權碼期限或Google發布狀態造成。cleanup PASS，獨立Drive下載8192 bytes之SHA256與原始基線完全一致。補入白名單provider錯誤代碼後run39902456514重測PASS：PKCE交換、fresh instance MCP身分、refresh與登出撤銷均通過；cleanup還原8192 bytes原始基線，再檢查CLEAN。token交換52.538秒，尚待HTTPS主機與ChatGPT實測。

正式私有資源設定原backup_folder指向公開根Backup，已先在私有W7備份，建立owner-only私人備份子目錄，原ID僅替換backup_folder並精確讀回。正式帳號資料尚未啟用；未調整根Backup分享權限。私人ID僅保存於Drive治理。

指揮官截圖確認Family-Drive專案為External／Testing，發布按鈕灰色並提示先完成品牌設定；代理瀏覽器仍Site Unavailable。使用者已授權總PM本人自行查資料與設定，可獨立完成部分繼續施工，不反覆要求使用者搬資料。

## 主機持久私有設定

run39904973080/job120254733860 PASS，程式fc81ee553a2b46d6ba7988c2480d630364bbf191。私有服務目錄位於公開網站根之外；runtime.json與32-byte server.key為0600，目錄0700；設定取自已核實owner-only Drive配置與備份目錄。設定更新前私有備份、原子替換、逐位元讀回；重複安裝維持同key，已有設定卻遺失/損毀key則拒絕重建。12項Python3.9測試PASS，主機安裝／讀回與staging cleanup PASS。沒有公開入口、沒有真人帳號初始化，enabled=false。

標準HTTPS路由與隔離驗收已提交92838009813eb96e391d7de6a8bb721af9968316；token/MCP/consent回應直接等待至105秒，不向OAuth客戶端送背景工作202。實測結果待下段讀回。

## HTTPS首輪與延遲修復

run39905273785/job120255680420：153項CI PASS；登入/首次改密碼/正常登入/discovery/明確同意/精確回呼等9項檢查PASS，token交換105.834秒後客戶端失敗；唯讀主機診斷確認該背景工作最終200。已關閉入口、移除測試工作、還原TEMP，獨立Drive下載基線雜湊一致。

修復：Coordinator只省略已讀回且完全不變的Close journal重寫，以及commit後重複Close；保留每次新讀DB/hash/journal、Read/Update/Close實際轉換、備份、pending、同ID寫回及復原。完整本機166項PASS，將重驗B06真實Drive與HTTPS，不因單元測試就宣稱逾時解決。

代理已實際進入ChatGPT登入帳號的Plugins→Add custom MCP server→Advanced OAuth settings，讀到User-Defined OAuth Client、callback、none token auth與手動endpoint/PKCE欄位。測試URL僅作未提交表單檢視；沒有建立插件、沒有完成授權、沒有跨對話驗收。正式callback於提交前需再次核對。

## HTTPS修補後驗收

run39907089509/job120262198216 SUCCESS，來源afc7abaf4fd01946c561b79a996701916b1f7f72。Python3.9 154項PASS，合成HTTPS完整14項PASS，包含標準token直接回覆、MCP身分、refresh、登出撤銷401。token交換85.426秒，仍偏慢；未證明實際ChatGPT客戶端可接受此延遲。隔離入口與私有測試檔移除，8192-byte TEMP還原原始SHA256；artifact12482405198／ec73a4d2fcf9bca08de70a76f2cf1c59d8d203c88edbf78cc9e7465821acc8d8。

正式私有設定仍disabled；沒有真人帳號啟用，沒有提交ChatGPT連接，Google長期授權未完成。B07仍IN_PROGRESS，正式6/23。

共同I/O修補重驗 run39907089439 第二次 job120267393120 SUCCESS：51單元測試，真實Drive中斷exit73、lost-ack去重、parallel_value4／unique_receipts3、old_epoch拒絕、Close表頭、精確還原PASS；二次cleanup CLEAN。首次並行worker TimeoutError及成功還原仍保留歷史，不覆寫成通過。
