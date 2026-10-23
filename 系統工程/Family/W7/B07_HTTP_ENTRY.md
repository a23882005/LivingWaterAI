# B07 HTTPS 登入入口施工紀錄

B07仍為IN_PROGRESS，正式進度6/23，Production HOLD、交易NONE。

## 已實作

`account_http.py`提供手機登入頁、登入狀態、本人改密碼、登出及管理操作。服務以固定HTTPS origin/Host、同源POST、簽章CSRF、Secure/HttpOnly/SameSite cookie、嚴格JSON欄位、大小上限與持久IP節流保護入口。密碼直接送服務，不回傳給模型；token不放JSON。管理角色從帳號庫重驗。

同一請求重送保留登入結果；換帳號時先成功建立新登入，再撤銷舊cookie代表的登入。原帳號其他裝置登入不受影響。四小時截止時間不因連線切換延長。

`b07_account_gateway.php`、worker與Actions只部署唯一run專屬的測試入口。需額外測試key，使用合成帳號及已核准TEMP，設定位於網站公開根目錄之外。測試後先隱藏入口，再精確還原TEMP，最後刪除該run的私有設定。這個入口尚未對真人啟用。

## 背景工作與主機時間限制

同步登入實測連續在約121秒收到主機HTTP500，三次同request重試仍未完成驗收。因此測試gateway改回傳202與48字元隨機工作編號，由私有背景worker處理；客戶端同源查詢結果，完成後才發送原Cookie/狀態。工作請求與結果位於公開根目錄之外，結果以原子替換寫入，請求內容處理後刪除。poll仍需測試gate，結果不進公開artifact。cleanup先等待所有背景請求完成，再取得共同鎖還原TEMP。

## 主機相容性

既有主機Python 3.9；SQLite `set_authorizer(None)`從Python 3.11才支援。共同資料交易改用允許回呼解除handler階段的限制，handler執行期間仍阻擋COMMIT/ATTACH/PRAGMA及receipt操作。新增實際SQLite提交、回滾與禁止提前提交測試。HTTPS workflow同步採Python 3.9及相容pytest版本。

來源：https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.set_authorizer

遇到500/502/503/504或連線中斷時，登入頁最多三次保留同一request_id重試；測試客戶端對上述HTTP狀態最多三次重試且保留同一序列化request_id，由B06 journal/receipt處理未知回應。主機worker與cleanup共用固定檔案鎖，避免網頁逾時後仍在寫入的子程序與還原交錯。

## 驗收範圍

本機103項通過（含五項直接執行實際頁面JavaScript的中斷重試/查詢測試及三項私有背景工作測試）。主機run39886316687 / job120195204049 SUCCESS，16項HTTPS→Drive驗收全數PASS，過程沒有HTTP重試。原8192-byte TEMP已精確還原，獨立Drive下載SHA256亦一致；臨時入口及私有工作檔清理成功。完整證據見evidence/B07/http_progress.json。

HTTP新連線沿用cookie只是服務端驗證，不是ChatGPT跨對話驗收。後續MCP需完整OAuth discovery、authorization code/PKCE、精確redirect與client驗證、token issuer/audience/expiry/scope核驗。實際ChatGPT連接與真人首次啟用仍須獨立完成。

官方接線參考：https://developers.openai.com/plugins/build/auth

## 下一段實作約束（待實作）

- OAuth授權碼綁定已驗證帳號、client、精確redirect、resource、scope與PKCE challenge；短效、單次使用，以持久交易原子兌換。
- OAuth access/refresh期限不得超過原登入14400秒截止點；刷新不能偷偷延長登入。每次工具呼叫重驗帳號enabled、generation、session撤銷及B05業務ACL。
- 授權碼、登入token與refresh token只存keyed hash及必要的私有狀態；Google Drive服務憑證與Family使用者授權分開，工具不接收密碼。
- client metadata的抓取須限制可信HTTPS來源、大小、時限與重新導向，不能允許任意URL變成伺服器代抓入口。正式redirect須讀取實際連接設定後精確登錄。
- 首次啟用採短效、單次私有交付，建立管理者的權限由經核實部署設定決定，不由HTTP欄位或應用程式名稱推定。
- 驗收包含授權碼重播、PKCE錯誤、redirect/resource錯置、到期與撤銷，以及真正的ChatGPT跨對話接續。以上是接線設計，尚未完成實作或驗收。
