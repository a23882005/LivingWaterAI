# 金融→報告接收相容修補 v1.0

先讀同目錄 `01_金融與報告介面契約及施工單_v1.0.md`（中PM原施工契約），再讀本線主契約新增的「金融→報告欄位相容修補」段落。

- `source_versions.json`：固定producer d250d3c、consumer基準4319556、18份依賴的Git blob/SHA256及測試程式SHA。
- `upstream_snapshot.json`：三份與報告分支不同的原始公開來源全文、十五份相同來源hash；只供合成測試的臨時隔離載入，不是正式producer更新。
- `validation.json`：272項＋134子案例、13項Chromium，正負案例、回歸、四戶保留證明與範圍。
- `junit.xml`：本輪完整測試記錄的公開去私人化副本；原始406 records（272主案例＋134子案例）在私人回交包。
- `render_qa.json`、`artifact_hashes.json`：原換行／PDF／PNG／reader檢查，以及新增16頁原Mentor建議合成報告的逐頁像素與原文字據；二進位檔案及視覺圖留私人包。
- `changed_files.json`：本輪精確准改清單。W6 receiver是本工單新增明確准改路徑；W5及核准renderer、共享README／Checkpoint保持。

快速重現（不需私人DB、網路或母版）：

```bash
PYTHONPATH=系統工程/Family/W8:系統工程/Family/W5:系統工程/Family/W6/runtime \
python -m pytest 系統工程/Family/W8/tests/test_report_canonical_adapter.py 系統工程/Family/W6/runtime/test_report_receiver.py -q
```

需既有W5 requirements.lock及pytest。完整回歸另需既有jsdom 26.1.0與核准v16母包（SHA256 b9b8d6eb1718b510f82e41e925f7a9145880caa8d3fe0a2dec4320ada515796e）、Playwright、Chromium、Pillow及PyMuPDF：命令見validation.json。未提供母包會明示skip，不能算視覺PASS。既有遠端W8 CI與本機新receiver／adapter／browser案例分列，CI不修改准改範圍外的workflow。

原四戶77頁SOURCE_REVIEW的正式分段PASS見PR60 issuecomment-6535506724；本輪不重產或改其20份正式檔。第一階段新修補待中PM複驗，第二階段真人金融章節仍WAITING_FOR_QUALIFIED_FINANCIAL_SOURCE_AND_PM_VERSION_LOCK。Production HOLD／交易NONE。
