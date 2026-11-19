最後修改日期時間：2026/10/14 18:10（台灣時間）
# Family PF｜EA-01至EA-09外部證據工作清單自動化 Checkpoint（426 PASS）

## 本棒工程內容
1. 新增 pf_external_evidence_plan.py：離線讀取外部測試授權 Manifest 的有效性狀態，自動產出九項 Gate A 外部證據需求及逐項 NOT_VERIFIED；無論授權是否完整，Gate A 固定 HOLD、WORK13 false，亦不執行遠端探測。
2. 新增 test_pf_external_evidence_plan.py：檢查九個唯一的 EA 編號、有效／缺漏清單、安全角色、越權和非正式資料拒絕、授權文件的私人識別資訊不寫入工作清單、含敏感欄位不外洩、CLI 無文件或損壞文件仍 fail-closed。
3. 修改 .github/workflows/family-pf-ci.yml：完整合成測試後生成 ci-evidence/gate-a-workplan.json；其內容加入現有 Actions 合成證據 Artifact，第二個獨立 Job 下載後，驗證完整九項證據狀態皆 NOT_VERIFIED、遠端未執行、Gate A HOLD、WORK13 不放行。

## 實際提交與驗證
- 工具程式 commit：b97df2b016d810f95d30ac0b6c5e4faaf5ec0bdb。
- 回歸測試 commit：645f2e7cfeea3f3880bdf03126b83cf4574b4209。
- Workflow 整合 commit：aa739794099c0d050dd94de59302d72c0c6feb13。
- 正式 Actions Run：https://github.com/a23882005/LivingWaterAI/actions/runs/38547224686
- Job 115796164968 SUCCESS：合成測試 420 passed, 1 warning in 11.69s；另安全契約測試 6 passed in 0.03s。合計 426 PASS，分屬兩個 pytest 命令。
- 第二 Job 115796371161 SUCCESS：已回讀工作清單的九項 NOT_VERIFIED 及持續 Gate A HOLD，同時驗證獨立合成證據完整性。

## 嚴格驗收邊界
- 此清單是離線工作規劃和 CI 自動證據交接，不是真實外部 TLS、IdP OAuth、兩租戶隔離、獨立持久化 Audit 或安全審查的合格證據。
- EA-01～EA-09 仍 BLOCKED，Gate A HOLD，WORK13 0/29。
- PR #2 Draft 未合併，main 與正式 Runtime 無更動；無購買、無部署、無對外測試。
