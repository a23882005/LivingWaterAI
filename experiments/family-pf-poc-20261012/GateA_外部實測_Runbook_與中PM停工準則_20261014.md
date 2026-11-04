# Family PF｜Gate A 真實外部驗收 Runbook 與中 PM 停工準則
日期：2026/10/14（台灣時間）｜分支：family-pf-ci-20261012｜PR #2 Draft
依據：GateA_外部真實驗收_中PM執行契約_20261014.md、GateA_外部驗收_證據責任與阻塞登記_20261014.md

## 0. 啟動前決策（必須逐項確認）
- [ ] 具有權限的治理人核准測試用途、測試環境、時段、成本與範圍；保留書面核准證據。
- [ ] 指定中 PM、測試執行者、獨立安全審查者、Audit 保管者與最終治理核准者；獨立審查者不得自審自己製作的證據。
- [ ] 核准的真實 HTTPS MCP 端點與 IdP/OAuth 測試身分可用；不得使用真實客戶投資持倉及個資。
- [ ] 指定獨立證據留存空間、最小權限、保存期限、雜湊與簽署信任錨，明確規範哪些資訊須遮罩。
- [ ] 核實 main/正式 Runtime 不受此次 PoC 變動；PR #2 保持 Draft，Gate A 保持 HOLD。
任一項缺漏：標記 BLOCKED；不啟動涉及真實服務或身分的測試。

## 1. 實測順序與安全停止點
1. HTTPS MCP：從核准外部網路驗證 DNS、TLS、端點可達與拒絕不安全重新導向；錄製 UTC、環境 ID、request ID、非敏感回應摘要。
2. OAuth：以隔離測試帳號驗證 issuer、audience、subject、scope、expiration 與伺服器端資源綁定；負向案例須拒絕不符 token / resource，絕不保存 token 明文。
3. Tenant binding：驗證授權來自可信伺服器端身分，不能被 URL query、client_id、資源 ID、檔名或 header 中的自述值覆蓋。
4. 雙向隔離：僅用合法合成測試身分與資料，A→A / B→B 預期授權，A→B / B→A 預期拒絕；API、文件檢索、資料庫代理路徑均納入核准範圍。
5. Audit：獨立保管方重新開啟拒絕事件，核對請求關聯、時間、內容最小化、原始檔 SHA-256、簽章與留存政策。
6. 獨立審查：審查者獨立抽樣重測，提交正式判定與理由；由有權治理者另行決策 Gate，不能由測試程式自行宣布放行。

**立即停工條件**：發現疑似跨客戶成功讀取、token 或機密曝光、未預期寫入正式資料、環境/身分不在授權範圍、Audit 無法追溯、證據保管權限不明、重要證據互相矛盾。停止測試、保留最少必要且遮罩的事件證據、通知中 PM 與獨立安全審查者；不得自行擴大測試範圍。

## 2. 逐項驗收標準與交付證據
每一測項需登記：case_id、environment_id、approved_scope_id、test_actor_role、UTC observed_at、sanitized request_id、expected、observed、status (PASS/FAIL/BLOCKED)、evidence_uri（限有權存取）、sha256、independent_reviewer_decision、review_time、retention_policy。
PASS 限真實執行且經獨立核驗；無授權或證據不足為 BLOCKED；實測不符為 FAIL。合成 Demo PASS 絕不可填為外部 PASS。

## 3. 中 PM 每次審查檢核
- 核對所有測試使用同一受核准環境、可比對版本與明確時間；確認沒有混用其他客戶或專案。
- 核對五類證據、成功與拒絕的雙向測試、獨立保管位置、雜湊重算及正式見證者。
- 將來源、SHA、已通過 CI、未解阻塞、例外、風險與後續權限要求登記入 Checkpoint；跨任務交接不得只用聊天室連結作唯一保存。
- 缺任一項證據、爭議未解、獨立簽署未完成：Gate A HOLD、WORK13 0/29。
- 僅正式治理角色可決議 Gate；即使另行核准 Gate 也不等於可合併 PR 或部署正式 Runtime。

## 4. 已知基準
最後正式合成 QA：349 PASS、1 warning、0 failed；GitHub Actions run 38475016463。
本 Runbook 是**規格文件，非已執行實測紀錄**。目前外部五類證據均 BLOCKED，Gate A HOLD、WORK13 0/29、PR #2 Draft。
