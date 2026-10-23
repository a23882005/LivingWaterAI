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
