# Family PF 中PM｜整批施工 Checkpoint：金鑰分離與 Audit 完整性
日期：2026-10-13（台灣時間）
工作範圍：獨立 GitHub 實驗分支 `family-pf-ci-20261012`，Draft PR #2

## 實際完成的程式與 QA
1. `pf_audit_store.py` 增加獨立 `pseudonym_key` 參數，要求至少 32 bytes 且與 `integrity_key` 不相同。保留舊呼叫方式作合成測試相容，故 **正式部署前須強制提供獨立金鑰**。
2. `test_audit_store.py` 增加 4 項測試：獨立金鑰不破壞舊稽核鏈校驗、相同／過短金鑰拒絕、多元件寫入完整性、去識別化金鑰輪換後歷史紀錄可驗證。
3. 施工 Commits：`34eaa916da92f60e18acebef4b9a7590f66101b4`、`d976d2001968b6dc84a1ec1327df3f12a5b26be6`、`8c8994236c3744c5dcae5e935f4046e248f63add`。
4. [GitHub Actions Run 38325227918](https://github.com/a23882005/LivingWaterAI/actions/runs/38325227918)：job completed SUCCESS；pytest 原始日誌 **173 passed, 1 warning in 10.39s**，Demo SUCCESS。
5. 未修改正式 Runtime、main、真實客戶資料；新增付費主機費用 NT$0。

## 下一階段安全重點
- 正式 bootstrap 必須強制獨立金鑰、定義金鑰輪替與秘密管理。當前相容預設仍用同一把金鑰，尚未符合正式 Gate A 要求。
- SQLite 鏈式 HMAC 可以偵測中間修改／刪除，但持有金鑰的管理者能重算整條鏈，尾部刪除也可能無法辨識；需外部可信 checkpoint/append-only 系統或獨立審核才能符合遠端不可竄改證據。
- 真實 HTTPS MCP、外部 OAuth、Joseph↔mou 遠端雙向隔離、持久化外部 Audit Log 與經核准獨立審查者簽名仍待實證。
- Gate A HOLD、WORK13 0/29、PR #2 保持 Draft，禁止合併或放行。

## 治理待登記事項
請總PM依根目錄《檔案管理.md》最新治理規則完成正式檔案備份／整合；中PM本輪已落 GitHub Checkpoint，未改 Google Drive 正式檔。
