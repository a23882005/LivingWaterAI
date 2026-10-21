最後修改日期時間：2026/10/14 18:32（台灣時間）
# Family PF｜Gate A 外部驗收執行手冊 v1

本文件為正式外部驗收「前」的獨立環境準備和人工操作依賴清單，不代表外部驗收完成。PR #2 僅隔離合成工程；main/正式 Runtime 不變。

## 已完成，可以立刻在 GitHub Actions 重現
1. 在隔離分支 family-pf-ci-20261012 執行現有 family-pf-ci.yml。
2. 首個 Job 執行套件／本機 TCP MCP 合成身分和租戶雙向拒絕、九項 EA 工作清單及證據矩陣生成。
3. 第二 Job 回讀下載的摘要、Commit SHA、Gate A HOLD、9 個 NOT_VERIFIED。
4. 從 Actions Artifact 下載 gate-a-workplan.json、external-matrix.json、receipt.json 與 receipt.sha256。這些只是合成 CI 交接成品，保留期限 7 天。

## 真正外部驗收需要的外部決策
- 環境：獨立的非正式公網 HTTPS MCP Endpoint、擁有者、域名/TLS 證書、允許外部連線的測試窗口及必要預算核准。GitHub Hosted Runner 不是供外部長期連入的服務。
- 身分：真實 IdP/OAuth 測試 Tenant A/B、分開的合成使用者、設定正確 audience/scope/JWKS 與過期/撤銷控制。測試密鑰僅存在受保護 Secret Store，禁止進入 PR、Artifact、log。
- Audit：不同於 App Runner 的持久化外部只附加儲存；必須能證明每次 ALLOW/DENY 的身份、租戶、資源、時間與完整性雜湊，並由獨立保管者驗證。
- 人員：執行者、Audit 保管者、獨立審查者、Gate 核准者須依身份核實分工；對外檢查前獲明確核准的範圍／窗口及資金。
- 不得向公開網站或正式客戶地址發送未經批准的測試要求；不使用任何真實客戶資料。

## 外部操作順序（待獲授權後才可實施）
A. 先以 pf_external_start_guard.py / 授權 Manifest 本地預檢；READY_FOR_AUTHORIZED_OPERATOR_REVIEW 僅代表可交操作人員複核。
B. 運行經核准的 HTTPS MCP Metadata 僅讀預檢，記錄 TLS、HTTP Status、受保護資源 Metadata 與 OAuth Issuer；注意 metadata discoverable 不表示登入已驗證。
C. 獨立 OAuth 驗證 issuer、audience、scope、JWT 簽章和 token 過期／撤銷；只用合成身分，避免在 log 或證據中輸出 token。
D. 每個 Tenant 先驗證「自己讀自己」，再驗證 A→B 與 B→A 都拒絕，且交替登入或 session 變更不交叉授權。
E. 將全部拒絕／允許審計事件保留至外部獨立 Audit Store，再由另一位保管者完成可回讀完整性核對。
F. 交獨立審查員核對 EA-01～EA-09 原始外部證據與 SHA256；治理負責人最後另作 Gate A 明確放行／不放行決定。

## 放行限制
任何單一 CI PASS、GitHub Artifact、自己簽名的證據矩陣、測試客戶資料、本機 loopback HTTP/TCP 或聲稱已核准的 Manifest 都不足以直接解除 Gate A。現況：EA-01～EA-09 NOT_VERIFIED；Gate A HOLD；WORK13 0／29；PR #2 Draft 未合併。
