# B07 Actions 帳號工作入口｜2026-10-24

## 最新決策
家人從 Arthur／mou／Lilian／Joseph 原有 ChatGPT 專案進入。收到首則訊息後先登入，成功後顯示功能選單。每個新對話重新登入；同對話沿用成功登入起算固定 4 小時。正式程式放 GitHub、在 GitHub Actions 執行；正式 DB 在 Google Drive。happihelp.com／Hostinger 不作此版本的必要依賴。這些使用者最新決策優先於舊契約的跨對話共用 session 與固定主機部署敘述。

## 已完成範圍
actions_account_job.py 為可在 Actions worker 匯入呼叫的執行核心。沿用 AccountManager 與 B06 store，不另寫帳密演算法。提供 login、session、logout、change_password。受信任入口提供 connection/conversation 的不透明識別，推導獨立 scope；request_id 按 scope 與操作隔離，保留原重試及撤銷行為。

回覆分成無個資/憑證的 receipt 與須私下加密傳送的 private_response。沒有 stdout 輸出；錯誤回覆不包含供應商回應或例外內容。測試使用既有合成帳號及 B06 本地 Disk backend，不改正式 DB、不建立真人帳號。

2026-10-24 本機執行：新增 10 項，連同 accounts/OAuth/HTTP 回歸合計 67 項通過。新增 workflow 只執行合成測試，不讀 repository secrets、不部署主機、不傳家人資料、不建立排程。

## 尚待接通：不可用提示詞代替
1. 真正私密的登入輸入及結果交付：不能把密碼/token 放進對話、workflow_dispatch 明文 inputs、issue、commit、日誌或一般 artifact。現有 HTML 表單依賴 HTTP 服務；Actions 本身的工作流程尚未提供替代輸入介面。
2. ChatGPT 端工作觸發與讀回：本次可用 GitHub 工具沒有新 workflow_dispatch 操作；已查詢外掛目錄，仍只有既有 GitHub 整合。維護者推送程式觸發 CI 與家人操作提交工作不同。不得為觸發而反覆提交含請求資料的程式碼。
3. conversation 目前為呼叫端注入的可信介面契約；單元測試證明 scope 隔離，不代表已取得 ChatGPT 的原生對話識別。不以原生 Project/裝置 ID 作前置要求；可採經驗證的對話工作握手，但必須另實作與測試，不能直接相信模型或使用者填入的識別。
4. Drive 共同寫入：既有 private_account_service 明確要求 single_writer_host 與本機 flock。移到不同 Actions runner 後，本機鎖不跨 runner。正式修改前須完成唯一寫入排程/持久佇列及故障復原驗證；一般 concurrency 設定不能未經驗證就宣稱保留所有工作。
5. 穩定驗證金鑰、真人帳號安全啟用及私有資源映射需走既有正式治理；本分支不生成或發佈真人初始密碼。

## 施工責任及驗收
由 Family 中PM 本人循序續作 B07 登入接線、B08 工作身分；B18/B21 排隊寫入依最新 Actions 執行決策修訂。W7 正式完成數維持 6/23，B07 IN_PROGRESS。本分支是執行核心及 CI 增補，非可立即給家人使用的安裝包。

需完成一次真實端到端：Joseph 新對話→私密登入→Actions 真實驗證→對話取得成功→選單；第二對話再次登入、到期、登出、錯戶及重試測試。成功後再提供專案指令安裝。Drive 正式契約及 Checkpoint 的同步尚待依根目錄《檔案管理.md》備份後辦理。
