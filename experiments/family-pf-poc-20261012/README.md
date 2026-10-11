# Family PF 本機測試原型（39項測試）｜2026/10/12

**狀態：僅本機 PoC；39項本機測試PASS；Gate A=HOLD；WORK13=EXECUTION HOLD。**
本原型由 Family 中PM 以合成資料開發，作為平台可行性探索。**並非正式 Family Runtime、Remote MCP 或任何正式家人資料庫。** 本目錄只做 GitHub 私有程式碼保存，不屬於 Family 生產部署。

## 內容
- `PF_Local_PoC_39Tests_Source.tar.xz`：完整的五個可執行原始檔（`pf_poc.py`、`run_demo.py`、`requirements.txt`、`tests/test_pf.py`、`tests/test_local_https.py`），均來自 2026/10/12 Family 中PM 原始39項測試ZIP。
- Core tar.xz SHA-256：`0049a772efb7ca86452ffafc5c319d38e69ccadeb40e8fc1a2581c3506d7214b`
- 原始完整證據ZIP SHA-256：`9cdc82a5d9a57373447ef66fdd4055bdef5a9866b61fe8e465a61593279fc72e`。原始證據 ZIP 仍由中PM保管；本GitHub包是原始可重跑程式碼部分的精簡副本。

## 如何重跑
```bash
mkdir -p pf-local-test
tar -xJf PF_Local_PoC_39Tests_Source.tar.xz -C pf-local-test
cd pf-local-test
python -m pip install -r requirements.txt
PYTHONPATH=. python -m pytest -q tests
PYTHONPATH=. python run_demo.py
```
預期：`39 passed`。TLS測試可能需要本機可用的loopback埠。

## 安全邊界
1. 所有 `PF_TEST_*` 身分、專案、金額都是合成測試資料；沒有客戶姓名、持倉、券商密碼或金融帳號。
2. `issue_for_test()` 是本地測試身分簽發器，**不能當作真正OAuth登入機制使用或暴露為正式API**。
3. 尚未測試真實ChatGPT Project可信身分、Remote HTTPS MCP、跨聊天／跨裝置及正式客戶資料隔離；這些都必須於PF正式平台實測後交 Family 中PM獨立驗收。
4. **不可宣稱 PF-01～08 正式PASS 或 Gate A PASS，也不能因此簽發 WORK13 EXECUTION_RELEASE。**
5. 不修改既有 `p128.py`、`V70_Live.html`、ABC/V75 Runtime 或任何GitHub Actions。

---
《活水書院》

一脈活水，流過歲月，
釀成青山，也釀成遠方。

不逐一時風起，
只守四季花開。

讓時間沉澱豐盛，
讓資產在歲月裡生長；
今日種下一方山水，
來日收成人生的富足。
