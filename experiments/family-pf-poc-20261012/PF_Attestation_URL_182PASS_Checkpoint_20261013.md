# Family PF｜Gate A 證據 URL 安全加固 Checkpoint
日期：2026-10-13（Asia/Taipei）
施工範圍：LivingWaterAI GitHub 隔離分支 `family-pf-ci-20261012`

## 已實際完成
- 改動 `pf_gate_a_attestation.py`：Gate A 簽名證據 URL 除要求 HTTPS，也明確拒絕 localhost、本機／非公網 IP、非標準 HTTPS port、query／fragment、及佔位域名，以降低本地測試網址被當成外部真實證據的風險。
- `test_gate_a_attestation.py`：新增三項合成拒絕回歸測試（127.0.0.1、localhost、alternate port）。
- Commits：`96ce802bcfcad6e8cc679f535d9e6fff8ef89fa9`，`23ec641482d8e15091ffb759c19dd13e0b8a955d`。
- [GitHub Actions Run 38341820795](https://github.com/a23882005/LivingWaterAI/actions/runs/38341820795)：完整工作 completed SUCCESS；pytest **182 passed, 1 warning in 9.48s**；Demo SUCCESS。
- 新增主機費 0；`main`／正式 Runtime／真實客戶資料均未修改。

## 尚待正式獨立驗收
- 公網 HTTPS MCP、外部 OAuth 完整登入、遠端雙向客戶隔離、外部不可變 Audit 留存／錨點及獨立審查者核准公鑰簽名，均未取得真實 E2E 證據。
- 靜態 URL 型式驗證不代表網址內容真實，也不構成 SSL/TLS 實證、OAuth 實證或 SSRF 完整防護。
- Gate A = HOLD；WORK13 = 0/29；PR #2 維持 Draft、不得合併。
- 治理登記待正式大PM依 Google Drive 根目錄《檔案管理.md》執行備份與 Read-back；本棒只建立 GitHub checkpoint。
