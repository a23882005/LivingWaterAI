最後修改日期時間：2026/10/25 16:31（台灣時間）
# Family 家人版四戶正式專案文件索引

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
