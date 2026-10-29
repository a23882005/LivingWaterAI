## 2026/10/29｜架構說明影片正式採用

Owner確認的完成版已保存Google Drive「系統工程」，[GitHub影片及維護說明](文件歸檔/十四項選單程式與DB架構圖/README.md)。Family中PM負責維護；沿用核准的花卉封面、原六頁架構、Loop雙頁及動畫配樂，依Owner具體要求修訂。

## 2026/10/29｜十四項選單架構圖正式保存

Owner已採用六頁「十四項選單・程式與資料庫架構圖」，正式原件保存於Google Drive「系統工程」；固定原件與私人連結依Drive《家人版_檔案管理.md》查找，TEMP為交付副本。GitHub同圖文副本及維護規則見[圖稿索引](文件歸檔/十四項選單程式與DB架構圖/README.md)，亦可[直接開啟PDF](文件歸檔/十四項選單程式與DB架構圖/Family_Menu14_Program_DB_Architecture.pdf)。視覺基準為Owner指定之綠色主視覺、彩色分區、圖示及清楚大字；後續路由變更時由Family中PM同步維護圖稿與治理索引。

最後修改日期時間：2026/10/29（台灣時間）
## 最新總PM三ZIP交接｜08:03複核修訂版

接任Family中PM＝全案總PM＝剩餘工程直接執行者，負責施工、Debug、整合、驗收、Gate、治理及結案。三包已在私人Drive根目錄TEMP沿原File ID更新，遠端下載3/3逐位元/SHA/CRC與37份payload校驗PASS，56項選單與最新PR tree核對一致。

[正式交接索引](W8/20261029_中PM總PM三ZIP正式交接索引.md)；[Checkpoint](W8/Checkpoint.json)。最新包名含`080313`及`複核修訂版`。已補全五類治理台帳職責、八份Project導航/本人報告folder、完整程式路徑及Gate D→PROD→TRIAL→Gate E→結案責任。

本次PR59 head `0334f9ae82f42b6a3786f7e1e2dd31cf1f52b0c3`，仍Draft未合併，正式W1目標/核准沿革及資金映射持續前進，完整04/FamilyRunner/Work9/Mentor待驗收。V82 v1.0已批准、MOU17檔目標原固定DB同ID寫回PASS；W6成果/W7 CLOSED保留，W8 IN_PROGRESS、Production HOLD、交易NONE。先Joseph/MOU04，後續依Master WBS順序完成全案。

架構保持GitHub程式、Drive本人DB/報告、ChatGPT按需執行。下方早期日期/進度/工具限制是歷史，以本節、正式交接索引及最新Owner決定優先。

---

最後修改日期時間：2026/10/27 03:05（台灣時間）
# Family 家人版四戶正式專案文件索引

## 🚩 2026/10/26｜Owner 最新優先架構裁決（高於下方舊Hostinger接線記錄）

**已核定：GitHub 存正式程式 → 家人在 ChatGPT Project 提問時由 ChatGPT 按需取得並執行程式 → Google Drive 讀寫該家人正式 DB／報告 → 回覆。** 家人版不需要24小時常駐 Python 伺服器；**Hostinger 不是指定的家人版程式執行主機**，OAuth／MCP 外部常駐後端也不是Owner核定的必備方案。先前為解決W8接線而自行導入Hostinger屬中PM架構偏離；後續不再擅自擴充。既有真實歷史測試成績維持原紀錄，與最新版正式施工目標分別標示；本次沒有擅自停用既有網站，也沒有更動個人DB。

正式約束與責任全文：[W8／正式架構裁決_ChatGPT按需執行.md](W8/正式架構裁決_ChatGPT按需執行.md)。後續W8必須以ChatGPT當次實際可用程式工具為準逐項接通，不能單憑GitHub有程式就聲稱已在Project執行。

## 2026/10/27｜W8當期入口：本人W1來源與原生V70按需計算

`W8/on_demand_project.py` 的第04項目前可透過 `on_demand_current_sources.py` 讀取本人最新已確認目標、同一最新真實快照的股債基準，以及既有 `cash_available_view`／`funding_planning_view` 的原始資金狀態。`v70_original_runtime.cjs` 在本次執行環境使用 Node＋jsdom@26.1.0，直接執行原 `總經V70/V70-3-27.html` 與同目錄正式feed，沿用原分數、日期驗證及配置公式；只讀本機來源，沒有額外網站或常駐主機。執行者可在本次暫存環境安裝jsdom，並將 `NODE_PATH` 指向該node_modules。

來源與原程式SHA、原本的候選／未回測狀態、資料驗證結果完整保留；UI預設人生情境不當作家人已填資料。缺少本人確認基準時不套預設60／40；可用現金不當成全投資組合NAV，資金未知不補零或估算可買股數。第04項在完整原生request未齊時回傳 `DATA_UNAVAILABLE` 並附已讀回的 `current_source_inputs`，供當次ChatGPT交代已完成的資料與V70比例計算。

當期工程狀態以 [W8/Checkpoint.json](W8/Checkpoint.json) 為準。R19已驗證本次Work的SQLite同ID傳輸；R20已修復04→13版本綁定；R21已完成三檔觀測資料的原程式數值運算。完整V82／V75／Mentor同輪輸入、正式四戶報告與56項Project端對端、Gate D/E仍接續驗收；W6/W7既有PASS保留。

## 2026/10/27｜Family中PM＝全專案總PM｜最新正式三ZIP交接

**這是最新交接，優先於下方2026/10/26及2026/10/25舊交接歷史。** 指揮官已核定由新對話的Family中PM／總PM**親自完成**W8剩餘施工、04投資計算、11真正SQLite同ID寫回、13本期正式PDF/HTML、四戶14項Project真實驗收、Gate D/E及所有工程與檔案治理。Owner授權相關工程繼續，無需重做已通過Gate，不再無故新發包。

三包均已上傳至指揮官私有Google Drive**根目錄既有TEMP**，且**下載讀回3／3 ZIP CRC、各檔 SHA及全ZIP SHA全部PASS**：

|順序|正式ZIP檔名|SHA-256|
|---|---|---|
|ZIP1 總PM權責與最高架構|Family_W8_20261027_ZIP1_中PM總PM職責與最高架構.zip|b19ae57f6aabc53cacf74c65516698e4459a3d32e7ff851c7f5b3d282818ae29|
|ZIP2 已完成工程與程式證據|Family_W8_20261027_ZIP2_已完成工程與程式證據位置.zip|c96ec15ab0ac556e1cd25d630b53c5dc301e03dab7f37f2fab01f49e9de45b06|
|ZIP3 未完工序與四戶Gate|Family_W8_20261027_ZIP3_剩餘工序與四戶Gate驗收.zip|77a330ddd33aa2a9ae762a1cf3b9bae6cfa64342aa0a9dcad29432c7199ef1e7|

[2026/10/27正式交接詳細索引](W8/20261027_中PM總PM三ZIP正式交接索引.md)，以及[當期W8 Checkpoint](W8/Checkpoint.json)；各家人正式私有資料不進公開Repo。

**新確認工具突破：**當次ChatGPT可使用 files__manage_library 把本機真正ZIP／SQLite新檔直接上傳Google Drive/TEMP，真實讀回已核實；但是**overwrite=true對既有Drive檔明確回overwrite_not_supported**，因此**四戶正式SQLite同原File ID更新/遠端讀回仍未PASS**。不要因三ZIP已存就誤稱原DB能覆寫或Gate D/E已通過。W7 PASS/CLOSED、W6工程PASS_WITH_DECLARED_SOURCE_GAPS保留；W8仍IN_PROGRESS、Production HOLD、交易NONE。

## 2026/10/26｜Family 中PM／總PM新對話三ZIP交接（最新接棒，取代下方舊20261025交接）

已依Owner指揮官要求，在Google Drive根目錄現有私有 **TEMP** 上傳下列新三包並獨立**重新下載比對3/3 SHA-256與ZIP CRC PASS**：

|順序|最新ZIP|驗證SHA-256|
|---|---|---|
|1｜總PM責任與Owner最高架構|`Family_W8_20261026_ZIP1_總PM職責與最高架構.zip`|`1995fcb08775ba77b1dedcce1300aa18fdf0889674c7072ad1a23a203a2d83d8`|
|2｜已完成工程、十四選單、程式/正式DB及證據位置|`Family_W8_20261026_ZIP2_已完成工程與正式檔案位置.zip`|`3a7ad7988641bc57a3108641103ea76f700bb8a35d8b9b8758be34221e665cd0`|
|3｜剩餘W8施工、4×14驗收、Gate D/E|`Family_W8_20261026_ZIP3_剩餘工序與Gate驗收.zip`|`0fd2dcd8298d08f1fb01822bf142434c5122a1d035703e49ac5d8a0a892cb4d7`|

下一棒**中PM＝Family全專案總PM＝自己直接完成剩餘工程的執行者**，先依1→2→3讀取正式TEMP新三包及live main/Checkpoint，**最優先服從本頁上方Owner按需架構**（GitHub程式、ChatGPT使用者提問時按需執行、Google Drive本人DB及報告；**不准自行設Hostinger為執行主機或24h常駐**）；完成04 V70/V82/V75/Mentor、11成交後真實資料、13正式W6報告與四戶14項端對端、Gate D/E。**W7已PASS/CLOSED、W8仍IN_PROGRESS**。不得用舊Hostinger測試當作最新按需Project端對端通過。

GitHub導航：[`W8/20261026_中PM總PM三ZIP正式交接索引.md`](W8/20261026_中PM總PM三ZIP正式交接索引.md)。舊10/25交接保留歷史，不應誤選。

## 2026/10/25｜Family 中PM全案總PM三ZIP正式交接（Drive私有TEMP）

**W7 Owner裁定全線 PASS/CLOSED，下一階段 W8 全面整合測試與 Debug，完成後循既有 Master WBS → Gate D → 四Project部署 → 試用修復 → Gate E。** 新對話接任人即Family中PM／全案總PM，本人負責工程、測試修Bug、Gate與檔案治理；既有 W7 PASS 不重開。

三包保存在 Google Drive 根目錄既有 owner-only TEMP；GitHub **僅列非敏感的交接檔名與校驗碼**，實際私人來源、個人DB、憑證不進公開庫：

| 交接包 | 內容 | ZIP SHA-256 |
|---|---|---|
| `Family_W8_交接_ZIP1_總PM責任_20261025.zip` | 總PM職權與責任、目前W7裁定和完成/未完成 | `375cd6d57697a28c4e310bbade585f70421314a254d100eac9e3839ffc70f33e` |
| `Family_W8_交接_ZIP2_成果檔案定位_20261025.zip` | 八份Owner核定TXT原件、各Drive ID及SHA、核實的程式位置、正式治理導航 | `95bcbd4ae6ecc128c08853676bd967420013a411a976edcf9b427b7da63ad47f` |
| `Family_W8_交接_ZIP3_全面測試Debug與後續工序_20261025.zip` | W8端對端測試、Bug定位修復、回歸驗收、Gate D至Gate E | `1387086363bf7c717c40c9d20793182e2c0d17484e9c3dd66529dfafd50982e9` |

三包已在Google Drive原始TEMP父目錄上傳、遠端重新取得，大小/CRC/Manifest與SHA-256核對通過。沿用本頁上方正式八份Project版本：七份v1.16.4＋Arthur Sources v1.16.5（16:16 Owner更新），v1.17已被取代。W8尚待實際驗收，不能以本次交接宣稱W8 PASS；交易授權NONE，Production HOLD。完整私有包連結與ID已寫Family工程/檔案管理及MasterWBS。


## 2026/10/25 16:31 指揮官最新版指定：恢復八份原始 TXT

本次以指揮官重新上傳的八份 TXT 為唯一文件版本基準：
- MOU／Joseph／Lilian：Instructions v1.16.4、Sources v1.16.4。
- Arthur：Instructions v1.16.4、Sources **v1.16.5（指揮官 16:16 更新版）**。

2026/10/25 下午原 Google Drive 的八份 v1.17 已被覆寫回以上指定版本；沿用每份原始 Google Drive File ID，逐份遠端讀回。v1.17 為已取代的歷史版本，留存私人備份，不得覆蓋 Owner 當前指定版本。

**GitHub 是公開儲存庫。** 私人 Sources（含個人 DB 及報告位置、client_id）保持在有權限控管的 Google Drive；GitHub 只提供可查核的版本／SHA-256／連結與正式工程程式，避免公佈家人私人資源。

## 四戶正式檔案及原始 SHA-256

| 專案 | Instructions | SHA-256 | Sources | SHA-256 |
|---|---|---|---|---|
| MOU | [v1.16.4](https://drive.google.com/file/d/1rzj5FP6re6dfhme2Mos9DRthygqM3zMM/view) | `37be5a1b6525e42618c16402b6d1600d1375b8af615c03ea629dcb509df9a5e0` | [v1.16.4](https://drive.google.com/file/d/1LoB6o4hWgj94Sy4yTV3bdiiybzRqGesF/view) | `43fdd14c982f727a48461f44f804b01bcf79ee5c127db52ac8bc09894367739b` |
| Joseph | [v1.16.4](https://drive.google.com/file/d/1qjVWts4u-IuIM9I5vTgXc6sfcZ_2LAVw/view) | `f4a018a3a6466717001b5c1a245d8641c511b59a4c6d13e84ed843833b6e9cac` | [v1.16.4](https://drive.google.com/file/d/194zJSkEKRxbfkxUcGKiTCT5a4GEe2nVG/view) | `b24fcda67cb037dea8140eb42c7ba8a2e163515ed0a69f17a809ab396494dee8` |
| Arthur | [v1.16.4](https://drive.google.com/file/d/18h6TYSQiCFtUeWF9osnxwM0_Za2KT1-8/view) | `caf985b19b337278fd5361b791aa79340d58f80ace9488c980eec8551cba6923` | [v1.16.5](https://drive.google.com/file/d/1Q43U_uI24HM0BVw_h1rGjJk9xR7Wn4Hy/view) | `f647900e58ced5b6a33e48a291f6742f1f34aa76674f5865d1a9b97552ed10cc` |
| Lilian | [v1.16.4](https://drive.google.com/file/d/1TPKp1zY9ZVWb0WLsdCuWMwHa_fmdoUqU/view) | `e4339e3c2e57a31889a3b8c5ac994c8950bab7cbc0f4a871b92c02ccbed46733` | [v1.16.4](https://drive.google.com/file/d/1jIUWODZ5OWBBCtF2i7rjhrpaN62yycZb/view) | `09aec2f423de2f3eecf071dd9a331c75926480ee5087922c78d58ed7b4451167` |

SHA-256 來自指揮官本次八份實際附件原始位元組；若 Google Drive 檔案變動，應先確認是否為最新 Owner 授權修改，不能把舊版 v1.17 自動當新版。

## 使用與工程狀態（沿用先前定案）

- 每位家人使用自己的 Project 與 DB，十四項選單不變。
- 登入成功後四小時有效；新對話先查現有有效登入狀態，未到期無須重新輸入密碼；實際功能仍以可信驗證會話為準。
- 已確認資料直接走現有寫入流程、成功後讀回；發生真實錯誤才針對該步修復。
- **W7 Owner 最終裁定 PASS／CLOSED**；參考 [W7 Checkpoint](W7/Checkpoint.json)。下一工序 W8 全面整合測試與程式 Debug，由 Family 中PM（總PM）執行。
- 不自動證券下單；正式 DB 留 Google Drive，不將私人原件公佈於 GitHub。

以上為版本/檔案治理同步，不代表本輪對四人 Projects GUI 的安裝或 W8 實測已完成。
