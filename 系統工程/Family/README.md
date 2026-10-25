# Family 家人版專案參考索引

## 最新工程裁定｜2026/10/25

**指揮官正式確認 W7 全面 PASS／CLOSED。** MOU、Joseph、Arthur、Lilian 四位家人專案承接同一W7正式結案成果。此前 B07 IN_PROGRESS／6/23 等皆屬歷史進度，現行以本日Owner最終裁決為準；詳見 [W7 Checkpoint.json](W7/Checkpoint.json)。

**下一階段：W8 全面整合測試與程式 Debug。** 由 Family 中PM（總PM）承接全案整合測試與修復，涵蓋各戶14項選單、有效登入會話、資料庫讀寫讀回、建倉／配置／V70／V82／債券V75、報告生成及異常回歸。W8各項成果與Gate後續另依實測記錄；保持交易授權NONE。這是最新Owner驗收決定，保留歷史測試證據，不捏造新測試數量。

四位家人專案的 **Sources.txt** 已於 2026/10/25 原 Google Drive ID 更新至 **v1.16.5**，各檔新增「W7全面PASS／下一階段W8測試Debug」簡短進度紀錄並讀回通過；原 Instructions v1.16.4 不變，使用者選單及身分資料均維持原版。


最後修改日期時間：2026/10/25 12:44（台灣時間）

本檔為公開的專案設定索引。各人完整 Instructions 與 Sources 保存在 Google Drive 正式檔；GitHub 不公開個人資料庫、client_id、帳號驗證資料庫與私人報告資料夾的位置。

## 四個家人專案文件

| 專案 | Instructions（Google Drive） | Sources（Google Drive） |
|---|---|---|
| MOU | [MOU_Project_Instructions.txt](https://drive.google.com/file/d/1rzj5FP6re6dfhme2Mos9DRthygqM3zMM/view) | [MOU_Project_Sources.txt](https://drive.google.com/file/d/1LoB6o4hWgj94Sy4yTV3bdiiybzRqGesF/view) |
| Joseph | [Joseph_Project_Instructions.txt](https://drive.google.com/file/d/1qjVWts4u-IuIM9I5vTgXc6sfcZ_2LAVw/view) | [Joseph_Project_Sources.txt](https://drive.google.com/file/d/194zJSkEKRxbfkxUcGKiTCT5a4GEe2nVG/view) |
| Arthur | [Arthur_Project_Instructions.txt](https://drive.google.com/file/d/18h6TYSQiCFtUeWF9osnxwM0_Za2KT1-8/view) | [Arthur_Project_Sources.txt](https://drive.google.com/file/d/1Q43U_uI24HM0BVw_h1rGjJk9xR7Wn4Hy/view) |
| Lilian | [Lilian_Project_Instructions.txt](https://drive.google.com/file/d/1TPKp1zY9ZVWb0WLsdCuWMwHa_fmdoUqU/view) | [Lilian_Project_Sources.txt](https://drive.google.com/file/d/1jIUWODZ5OWBBCtF2i7rjhrpaN62yycZb/view) |

## 2026/10/25 指揮官核定的操作原則（目標版本 v1.16.4）

1. 登入成功起四小時有效；換新對話時，只要能驗證同一有效登入會話，就直接沿用，不重新索取密碼。四小時到期再重新登入。
2. 使用者提出需求後，沿用已確認資料、現有程式與現有功能；第一次建倉直接保存已確認資料，完成後讀回。
3. 實際遇到登入、讀寫或授權故障時，只針對當前故障處理；不因其他工程尚在施工就停下正常工作。
4. 保留本人資料隔離、真正的身分驗證、寫入後讀回確認與使用者自行下單的既有原則；十四項選單不變。

**版本同步狀態：** 2026/10/25 Google Drive 八份正式原檔皆以相同原 ID 更新為 v1.16.4，逐份遠端讀回確認。GitHub 保留非敏感版索引，私人資料仍以 Drive 原檔為準。

**技術狀態：** 目前 Python 驗證物件仍以單一執行環境為有效範圍；跨對話四小時登入沿用，需以實際共享且可驗證的會話機制完成後才能宣告功能實測通過。
