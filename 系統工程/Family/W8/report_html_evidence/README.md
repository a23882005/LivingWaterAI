# 合成報告／HTML 驗收證據

全部數字、ID、持倉、核准記錄、C／Work9 回覆與正文均出自 `../tests/fixtures/report_html/synthetic.py`；Arthur 只是既有受准報表 alias。未讀私人 DB 或歷史客戶數字，沒有真實 Drive 上傳。原 W6 圖像／CSS／reader 只取核准母包的指定參考資產。

- 工作區 `/workspace/report-evidence/report.html`：已保存完整分頁 DOM，可檢視 14 章正文／目錄／頁碼；無需分頁程式。
- 同工作區 `report.pdf`／`index.html`／`report.zip`：與 HTML 同一 DOM 的 16 實體頁及完整 reader／原 PNG。
- 同工作區 `contact.jpg`：全部 16 頁總覽；`radar.png`／`drift.png` 是原始頁面 PNG，`mobile.png` 是 390×844 手機截圖。
- `render_qa.json`：七項瀏覽器驗證、逐頁 overflow／頁碼／內嵌圖片狀態。16 頁保存 HTML 與 ZIP 原 PNG 逐頁像素完全一致。
- 工作區 `current.synthetic.json`：傳給 renderer 的完整合成 CurrentData 與 canonical sidecar。
- `junit.xml`／`validation.json`：W8＋W6 完整回歸，241 PASS，51 subtests PASS，0 failures/errors/skips；含實際命令、環境及母版 SHA；JUnit 另將 51 個子案例列為獨立 records。
- `artifact_hashes.json`：完整四種工作區產物的 bytes／SHA256。

自動核准審查以「報告衍生圖片可能敏感、GitHub 目的地未獲確認」拒絕圖片外傳。本 PR 改為只提交程式、合成測試與文字證據；完整報告／圖片留在上述工作區回交，沒有以其他編碼繞過該拒絕。

瀏覽器政策禁止 `file://`，因此直接雙擊開檔仍待中 PM 環境驗收。此處離線驗證使用保存檔原始位元組、停用 JavaScript，未注入 PAGINATION_SCRIPT；reader 同時驗證 data URI fallback 與離線 local-asset route 的同目錄 PNG。這不是繞過該政策或宣稱 file:// 已通過。

最短重現程序、producer→consumer 映射與剩餘上游責任見 [本線契約](../Report_HTML_Contract_20261030.md)。未提供核准母包時瀏覽器測試會明確 skip；本次完整執行已提供同 SHA 母包，沒有跳過。

逐頁人工覆核：已檢視全部頁面總覽、原尺寸雷達／漂移頁及手機截圖；封面、頁框與綠金配色沿母版，中文長名及六軸長標籤可見，沒有截出頁框。實體第 10～11 頁同屬第 9 章，是內容分頁；封面不編號，正文為 1/15～15/15。
