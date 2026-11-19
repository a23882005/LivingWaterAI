# Family PF｜Persistent Authentication Denial Checkpoint
日期：2026-10-13（Asia/Taipei）；工作層級：Family 家人版全生命週期中PM；僅限 GitHub 隔離實驗分支。

## 已完成
1. 更新 `pf_mcp_protocol.py`：不可信 Origin、缺少 Bearer、驗證 Token 拒絕三種 early DENY 透過已有 AuditStore 寫入固定、去敏欄位；原 in-memory scope.audit 保持相容。
2. 新增 `test_mcp_persistent_auth_denials.py`，驗證以上三類 HTTP 403/401/401 拒絕並於重新開啟 SQLite 後保留、HMAC 鏈校驗 PASS。
3. 更新 isolated CI workflow 複製新的測試檔。
4. GitHub commits: `8395188a49effc6f72a85d68645009386556b009`, `98ef926279333fd188a714270c4a16c36ca21c67`, `13a530037c001c0ed0c06c3d5b3d92b5c80d6d95`.
5. [GitHub Actions Run 38316550582](https://github.com/a23882005/LivingWaterAI/actions/runs/38316550582)：full test step PASS、Demo PASS、job completed success。Job 名稱仍叫 verify-pf-full-158，正式精確 pytest 數需原始日誌核實。

## 安全邊界與待辦
- 本輪在本地／CI 合成 MCP 身分做測試，尚未以真實外部 HTTPS、OAuth 登入、遠端客戶隔離或外部持久化稽核完成 Gate A 證據。
- Origin/bearer 拒絕 audit actor_ref 採 anonymous；resource-read path 現使用 synthetic_subject，尚需伺服器端 pseudonym、request-id correlation、真實持久化與獨立不可竄改留存。
- SQLite + HMAC 本身不能作外部審核不可竄改保證。
- Gate A HOLD，WORK13 0/29，PR #2 維持 Draft，main/正式 Runtime/真實客戶資料未碰，額外主機費 NT$0。
- 治理登記事項：正式大PM 依 Google Drive 根目錄《檔案管理.md》Fresh Read→備份→登記本 checkpoint、Run、commit；本棒未改正式 Drive 治理檔。
