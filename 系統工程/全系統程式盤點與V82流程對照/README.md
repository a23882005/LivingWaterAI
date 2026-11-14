# 全系統程式盤點與 V82 流程對照

## 使用者要求之文件位置登錄（非中PM驗收裁定）

本目錄依使用者要求提供工程文件的唯一公開導航。正式閱讀原件保存於 Google Drive「系統工程」，原始程式來源仍是 GitHub；本圖冊是來源位置及函式對照，不取代正式規格、施工契約或中PM Gate。

- [114頁大字緊湊版 PDF（含逐檔用途、Input／Output）](https://drive.google.com/file/d/1Ytl33SXeekIqJTrhYFRyxrzOeL6Zzk-X/view)
- [Word 可編輯原件](https://drive.google.com/file/d/15eyFOGQpuGINVctnCNRGI3UUT7rxJ42e/view)
- [完整交付包](https://drive.google.com/file/d/1ijn5og0CWTBqKD8RRTBAfy8aH4wEcXMB/view)
- [固定來源版本的程式鏡像目錄](https://drive.google.com/drive/folders/10-z_W1IwuofPQohtsWRGVzKQGQTbINW2)

鏡像包含531個原始碼及11個HTML，共542檔；逐檔已比對Git blob SHA，並下載Drive原始內容核對大小、MD5及Git blob SHA。

上述Drive資源維持既有私人權限，不代表公開GitHub訪客可讀；本次不擴大分享權限。GitHub存放位置：`系統工程/全系統程式盤點與V82流程對照/`。

## 逐頁導覽

| PDF頁次 | 內容 |
|---|---|
| 1 | 封面及版本 |
| 2–4 | 章節／流程／目錄頁次索引 |
| 5 | 閱讀說明與目錄分布 |
| 6–10 | 原流程與放大參照 |
| 11–19 | V82 18項流程位置對照 |
| 20–111 | 全部531檔原始碼用途、Input／Output |
| 20–62 | 功能及共用模組235檔 |
| 62–75 | 作業工具與驗證腳本71檔 |
| 75–110 | 測試220檔 |
| 111 | 備份與封存5檔 |
| 111–114 | HTML補充11檔 |
| 114 | 版本證據與清冊核對 |

V82流程1–2見第11頁、3–4見第12頁、5–6見第13頁、7–8見第14頁、9–10見第15頁、11–12見第16頁、13–14見第17頁、15–16見第18頁、17–18見第19頁。每個程式的完整路徑與起訖頁次可由CSV查找。緊湊版保留大字與全部內容，以連續排版減少頁底留白；章節可在同頁銜接，因此頁次範圍可能重疊。

## 可檢索清單

- [531支原始碼用途／Input／Output／PDF頁次清冊](program_inventory_pr59_5163116b.csv)
- [11個HTML用途與頁次補充](html_inventory_pr59_5163116b.csv)
- [版本比對與分類附錄](version_comparison_5163116b.csv)
- [V82 18階段與函式位置對照](v82_18_stage_mapping_5163116b.csv)

531支原始碼均有依程式、函式及測試斷言整理的具體用途／Input／Output；全部來源Git blob SHA及所列依據行號已核對。獨立覆核另抽查30支程式與3個HTML的語義並修正兩處敘述；這是靜態查核，不是全部程式的動態驗收。V82對照另核對48個核心／來源／整合／支援程式的存在與函式定義；階段映射不是已執行的線性呼叫圖。531包括其他子系統、測試、工具及備份，不能全部視為V82主流程。producer／consumer／integration僅為用途分類，不是上線或驗收狀態。

## 不隨本次文件提交改變的盤點基準

| 快照 | Python | PHP | CJS | 原始碼合計 |
|---|---:|---:|---:|---:|
| PR59 `5163116bcdedaabbc3cf09ae091ca96968a26fdd` | 525 | 4 | 2 | 531 |
| main `591cf6256dc8942d68cf4441529b4b08391624b5` | 358 | 4 | 1 | 363 |

兩分支不能相加。兩份完整recursive tree均確認truncated=false；原始碼每個分支按Git blob SHA去重後數目不變。531含9個Python `__init__.py`；「程式」在此明確指原始碼檔，不是獨立產品或可執行主程式。

HTML各11檔另列；Markdown、JSON、YAML、CSV、資料、圖像、文件、壓縮包等不計入原始碼數。備份壓縮包未解壓。該快照全部檔案數1097／896亦只代表原盤點SHA，不是加入本文件後的新總數。

原始碼來源：[PR59固定快照](https://github.com/a23882005/LivingWaterAI/tree/5163116bcdedaabbc3cf09ae091ca96968a26fdd)／[main固定快照](https://github.com/a23882005/LivingWaterAI/tree/591cf6256dc8942d68cf4441529b4b08391624b5)。文件新增commit不改531支程式的來源版本，亦不等於PR59合併main。

## 維護與狀態邊界

本登錄由使用者明確要求新增頁次、保存於系統工程並更新相關工程／專案管理索引。既有中PM單一治理writer、Owner、工作分工及驗收權限保留；此文件不是中PM獨立驗收裁定。

只追加圖冊、清單及導覽，未修改程式、DB、排程、規則或券商操作；未重新執行金融鏈或測試。W8工程狀態、Production HOLD／交易NONE及原已驗收成果不因圖冊發布改變。歷史ZIP、規格、測試及來源鎖的日期／SHA保持原截點。

後續修訂須重新固定程式SHA、更新路徑與頁次、保留Drive原ID及歷史版本、讀回核對，並由現任中PM依既有權責完成治理交接。
