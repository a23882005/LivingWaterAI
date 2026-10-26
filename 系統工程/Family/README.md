最後修改日期時間：2026/10/26 11:47（台灣時間）
# Family 家人版四戶正式專案文件索引

## 🚩 2026/10/26｜Owner 最新優先架構裁決（高於下方舊Hostinger接線記錄）

**已核定：GitHub 存正式程式 → 家人在 ChatGPT Project 提問時由 ChatGPT 按需取得並執行程式 → Google Drive 讀寫該家人正式 DB／報告 → 回覆。** 家人版不需要24小時常駐 Python 伺服器；**Hostinger 不是指定的家人版程式執行主機**，OAuth／MCP 外部常駐後端也不是Owner核定的必備方案。先前為解決W8接線而自行導入Hostinger屬中PM架構偏離；後續不再擅自擴充。既有真實歷史測試成績維持原紀錄，與最新版正式施工目標分別標示；本次沒有擅自停用既有網站，也沒有更動個人DB。

正式約束與責任全文：[W8／正式架構裁決_ChatGPT按需執行.md](W8/正式架構裁決_ChatGPT按需執行.md)。後續W8必須以ChatGPT當次實際可用程式工具為準逐項接通，不能單憑GitHub有程式就聲稱已在Project執行。

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
