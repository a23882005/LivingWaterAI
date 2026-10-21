最後修改日期時間：2026/10/14 12:13（台灣時間）
# Family PF｜GitHub Actions 手動觸發安全隔離與憑證最小權限 Checkpoint（389 PASS）

## 範圍
- Repository: a23882005/LivingWaterAI
- Branch: family-pf-ci-20261012
- PR #2: Draft、未合併，未修改 main / Production Runtime
- 本棒是隔離合成 CI 工作流程之安全強化；不是外部 Gate A 正式驗收。

## 完成的實際工程
1. .github/workflows/family-pf-ci.yml：為 workflow_dispatch 加入工作分支條件，手動觸發僅准 refs/heads/family-pf-ci-20261012 上兩個 Job 執行；原 push 與 PR 合成測試仍保留。
2. 兩個 checkout@v4 均新增 persist-credentials: false；繼續使用最小 GitHub 權限 contents: read。
3. 新增 concurrency 分組並禁止取消既有執行；保留 7 天合成 CI 摘要 Artifact；第二 Job 仍獨立回讀測試證據並比對 GitHub Commit。
4. 新增 test_workflow_security_contract.py 四項契約測試並加入 GitHub CI 的實際執行路徑。

## Commit / GitHub Actions 證據
- Workflow 安全改動：3ecbc644b6afc7765438642119b04582ea88ba02
- 契約測試程式：702557baf5e33dffe70f6e33953be1bcaae648f7
- 將契約測試接入 CI：9bf79bcad03fb745aae9d7ea2009f502d6a9831c
- 正式 CI：https://github.com/a23882005/LivingWaterAI/actions/runs/38510150778
- Job 115676621257: SUCCESS；4 passed in 0.02s（契約測試）及 385 passed, 1 warning in 11.38s（既有整套）。
- Job 115676744612: SUCCESS；合成證據 receipt 的 SHA256 和來源 Commit 綁定驗證通過。
- 新增 4 項契約測試，故本棒執行總計 389 passed；舊套件自有 385 passed 原封保留。

## 正式 Gate 不變
- Gate A HOLD；EA-01～EA-09 BLOCKED；WORK13 0/29；PR #2 Draft。
- 仍缺外部 HTTPS MCP、真實 OAuth 合成帳號、雙向跨租戶外部驗收、獨立 Audit 持久化與獨立安全審查的正式證據。
- CI 憑證、最小權限與人工觸發限制屬程序防護，無權替代外部 Gate A 簽核。
