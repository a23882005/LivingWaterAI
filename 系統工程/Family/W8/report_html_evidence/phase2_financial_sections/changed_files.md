# 本輪准改清單與用途

以下路徑皆相對 `系統工程/Family/W8/`，共 16 檔；精確 bytes／SHA／Git blob 與 commit/tree 以私人驗收入口的凍結提交收據為準。

| 檔案 | 用途 |
| --- | --- |
| report_canonical_adapter.py | 原驗證後接 coverage／八章 fallback，保留原輸入及顯式章節，拒未來 available_at |
| w6_current_data.py | 只附已驗證 coverage 摘要／章節狀態，缺 NAV 原守門保持 |
| report_financial_sections.py | 新增純顯示器與逐欄 provenance，不跑金融策略 |
| tests/fixtures/report_html/synthetic.py | 新增明確合成股票/V75/現金 fixture |
| tests/test_report_canonical_adapter.py | 逐檔舊入口斷言調整為八章及完整標的承接 |
| tests/test_report_financial_sections.py | 新增七項正反與無副作用測試，含15個攻擊子案例 |
| tests/test_report_rendered_html.py | 新增兩項實際 Chromium 全章與 PNG/PDF/ZIP 同源核對 |
| Report_HTML_Contract_20261030.md | 附本輪來源、資格、缺項及回交邊界 |
| Report_HTML_Checkpoint.json | 本線第二階段進度，保留前階段 PM PASS |
| report_html_evidence/phase2_financial_sections/README.md | 驗收入口與閱讀順序 |
| report_html_evidence/phase2_financial_sections/field_mapping.md | 原欄位到八章映射及來源優先規則 |
| report_html_evidence/phase2_financial_sections/source_versions.json | producer/consumer/母版／程式 hash 與未改檔鎖 |
| report_html_evidence/phase2_financial_sections/validation.json | 實際命令、數量、QA 與限制 |
| report_html_evidence/phase2_financial_sections/junit.xml | 完整本機 281 主案例＋149 子案例結果 |
| report_html_evidence/phase2_financial_sections/synthetic_artifacts.json | 合成輸出逐檔大小及 SHA，原檔在私人證據包 |
| report_html_evidence/phase2_financial_sections/changed_files.md | 本清單 |

W6 renderer/receiver、W5、金融策略、DB/ledger、原核准配置、帳號驗證、Tasks、Family README 及 W8 Checkpoint.json 均未修改；沒有合併 PR59。私人原件與真人輸出不在公開 diff。原已驗收77頁／20件仍保留。
